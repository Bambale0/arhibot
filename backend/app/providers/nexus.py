from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic

import httpx

from app.core.config import Settings
from app.core.resilience import (
    CircuitOpenError,
    RetryPolicy,
    get_circuit_breaker,
    request_with_resilience,
)


@dataclass(frozen=True, slots=True)
class NexusImageResult:
    task_id: str
    image_url: str


class NexusProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class NexusImageProvider:
    def __init__(self, settings: Settings) -> None:
        key = (settings.nexus_api_key or "").strip()
        if not key:
            raise NexusProviderError("NEXUS_API_KEY is not configured", retryable=False)
        self.base_url = settings.nexus_base_url.rstrip("/")
        self.timeout_seconds = settings.nexus_task_timeout_seconds
        self.poll_interval_seconds = settings.nexus_poll_interval_seconds
        self.breaker = get_circuit_breaker(
            'nexus',
            failure_threshold=settings.nexus_circuit_failure_threshold,
            recovery_seconds=settings.nexus_circuit_recovery_seconds,
        )
        self.retry_policy = RetryPolicy(max_attempts=settings.nexus_retry_attempts)
        self.http_timeout = httpx.Timeout(
            settings.nexus_http_read_timeout_seconds,
            connect=settings.nexus_http_connect_timeout_seconds,
        )
        self.headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    async def generate(
        self,
        *,
        model_name: str,
        prompt: str,
        image_url: str | None,
        model_params: dict[str, object] | None,
        idempotency_key: str,
    ) -> NexusImageResult:
        deadline = monotonic() + self.timeout_seconds
        params = self._build_params(
            model_name=model_name,
            prompt=prompt,
            image_url=image_url,
            model_params=model_params,
        )

        headers = {**self.headers, "Idempotency-Key": idempotency_key}
        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            try:
                response = await request_with_resilience(
                    lambda: client.post(
                        f"{self.base_url}/generate",
                        headers=headers,
                        json={"params": params},
                    ),
                    dependency="nexus",
                    operation="create_generation",
                    breaker=self.breaker,
                    policy=self.retry_policy,
                    deadline_monotonic=deadline,
                )
            except CircuitOpenError as exc:
                raise NexusProviderError("Nexus is temporarily unavailable", retryable=False) from exc
            except (httpx.HTTPError, TimeoutError) as exc:
                raise NexusProviderError("Nexus generation request failed", retryable=True) from exc

            if response.status_code >= 400:
                detail = self._safe_error(response)
                retryable = response.status_code >= 500 or response.status_code in {408, 429}
                raise NexusProviderError(
                    f"Nexus create failed ({response.status_code}): {detail}",
                    retryable=retryable,
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise NexusProviderError(
                    "Nexus returned an invalid create-task response",
                    retryable=True,
                ) from exc
            immediate_url = self._extract_image_url(payload, payload.get("result") or {})
            task_id = str(payload.get("task_id") or "").strip()
            if immediate_url:
                return NexusImageResult(task_id=task_id or "sync", image_url=immediate_url)
            if not task_id:
                raise NexusProviderError(
                    "Nexus response did not include task_id or image URL",
                    retryable=True,
                )

            while monotonic() < deadline:
                await asyncio.sleep(self.poll_interval_seconds)
                try:
                    task_response = await request_with_resilience(
                        lambda: client.get(
                            f"{self.base_url}/tasks/{task_id}",
                            headers=self.headers,
                        ),
                        dependency="nexus",
                        operation="poll_generation",
                        breaker=self.breaker,
                        policy=self.retry_policy,
                        deadline_monotonic=deadline,
                    )
                except CircuitOpenError as exc:
                    raise NexusProviderError("Nexus is temporarily unavailable", retryable=False) from exc
                except (httpx.HTTPError, TimeoutError) as exc:
                    raise NexusProviderError("Nexus polling failed", retryable=True) from exc

                if task_response.status_code >= 400:
                    detail = self._safe_error(task_response)
                    retryable = (
                        task_response.status_code >= 500
                        or task_response.status_code in {408, 429}
                    )
                    raise NexusProviderError(
                        f"Nexus polling failed ({task_response.status_code}): {detail}",
                        retryable=retryable,
                    )

                try:
                    task = task_response.json()
                except ValueError as exc:
                    raise NexusProviderError(
                        "Nexus returned an invalid task-status response",
                        retryable=True,
                    ) from exc
                status = str(task.get("status") or "").lower()
                if status == "completed":
                    result = task.get("result") or {}
                    image_url_result = self._extract_image_url(task, result)
                    if not image_url_result:
                        raise NexusProviderError(
                            "Nexus task completed without image URL",
                            retryable=True,
                        )
                    return NexusImageResult(task_id=task_id, image_url=image_url_result)
                if status == "failed":
                    error = task.get("error") or "provider task failed"
                    raise NexusProviderError(f"Nexus task failed: {error}", retryable=True)

            raise NexusProviderError("Nexus task timed out", retryable=True)

    @staticmethod
    def _build_params(
        *,
        model_name: str,
        prompt: str,
        image_url: str | None,
        model_params: dict[str, object] | None,
    ) -> dict[str, object]:
        # Operator-controlled tuning parameters must never override provenance-critical
        # request fields. The generation row must describe what Nexus actually receives.
        reserved = {"model_name", "prompt", "image_url", "image_urls"}
        params = {
            key: value
            for key, value in (model_params or {}).items()
            if key not in reserved
        }
        params["model_name"] = model_name
        params["prompt"] = prompt
        if image_url:
            params["image_urls"] = [image_url]
        return params

    @staticmethod
    def _extract_image_url(task: dict, result: object) -> str | None:
        candidates: list[object] = []
        if isinstance(result, dict):
            candidates.extend([result.get("image_url"), result.get("image_urls")])
        candidates.extend([task.get("image_url"), task.get("image_urls")])
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                return candidate
            if isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, str) and item.startswith(("http://", "https://")):
                        return item
        return None

    @staticmethod
    def _safe_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text[:300] or "unknown error"
        if isinstance(payload, dict):
            for key in ("detail", "error", "message"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value[:300]
        return str(payload)[:300]
