from __future__ import annotations

import asyncio
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from time import monotonic

import httpx

from app.core.config import Settings
from app.core.resilience import (
    CircuitOpenError,
    RetryPolicy,
    get_circuit_breaker,
    request_with_resilience,
)
from app.prompt_builders.image_output import build_image_output_prompt
from app.prompt_builders.visual_fidelity import build_visual_fidelity_prompt


@dataclass(frozen=True, slots=True)
class NexusImageResult:
    task_id: str
    image_url: str


class NexusProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class NexusOutcomeUnknown(NexusProviderError):
    """A request may still be billable/running; never permit a fresh purchase."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


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
        reference_image_urls: list[str] | None = None,
        timeout_seconds: float | None = None,
        task_id: str | None = None,
        on_task_created: Callable[[str], Awaitable[None]] | None = None,
    ) -> NexusImageResult:
        create_timeout = self.timeout_seconds if timeout_seconds is None else min(
            float(timeout_seconds), float(self.timeout_seconds)
        )
        if create_timeout <= 0:
            raise ValueError("timeout_seconds must be positive")
        started = monotonic()
        deadline = started + self.timeout_seconds
        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            if not task_id:
                params = self._build_params(
                    model_name=model_name, prompt=prompt, image_url=image_url,
                    model_params=model_params, reference_image_urls=reference_image_urls,
                )
                try:
                    response = await request_with_resilience(
                        lambda: client.post(
                            f"{self.base_url}/generate",
                            headers={**self.headers, "Idempotency-Key": idempotency_key},
                            json={"params": params},
                        ),
                        dependency="nexus", operation="create_generation", breaker=self.breaker,
                        # Nexus does not document deduplication of POST /generate.
                        # An ambiguous response is not permission to purchase another image.
                        policy=RetryPolicy(max_attempts=1),
                        deadline_monotonic=started + create_timeout,
                    )
                except CircuitOpenError as exc:
                    raise NexusProviderError("Nexus circuit is open", retryable=False) from exc
                except (httpx.HTTPError, TimeoutError) as exc:
                    raise NexusOutcomeUnknown(
                        "Nexus did not confirm generation creation; no duplicate request was sent"
                    ) from exc
                if response.status_code == 408 or response.status_code >= 500:
                    raise NexusOutcomeUnknown("Nexus creation outcome is unknown")
                if response.status_code >= 400:
                    raise NexusProviderError(
                        f"Nexus create failed ({response.status_code}): {self._safe_error(response)}",
                        retryable=False,
                    )
                payload = self._task_payload(response, "create-task")
                task_id = str(payload.get("task_id") or "").strip()
                immediate = self._extract_image_url(payload, payload.get("result") or {})
                if immediate:
                    if on_task_created is not None:
                        await on_task_created(task_id or "sync")
                    return NexusImageResult(task_id=task_id or "sync", image_url=immediate)
                if not task_id:
                    raise NexusOutcomeUnknown("Nexus response did not include task_id or image URL")
                if on_task_created is not None:
                    await on_task_created(task_id)

            # Once accepted, use the full task deadline and only GET the same task.
            # A soft primary timeout must not launch a paid fallback in parallel.
            while monotonic() < deadline:
                try:
                    task_response = await request_with_resilience(
                        lambda: client.get(f"{self.base_url}/tasks/{task_id}", headers=self.headers),
                        dependency="nexus", operation="poll_generation", breaker=self.breaker,
                        policy=self.retry_policy, deadline_monotonic=deadline,
                    )
                except (CircuitOpenError, httpx.HTTPError, TimeoutError) as exc:
                    raise NexusOutcomeUnknown("Nexus task status is unknown; no fallback was started") from exc
                if task_response.status_code >= 400:
                    raise NexusOutcomeUnknown(f"Nexus polling failed ({task_response.status_code})")
                task = self._task_payload(task_response, "task-status")
                status = str(task.get("status") or "").lower()
                if status == "completed":
                    output = self._extract_image_url(task, task.get("result") or {})
                    if not output:
                        raise NexusOutcomeUnknown("Nexus task completed without image URL")
                    return NexusImageResult(task_id=task_id, image_url=output)
                if status == "failed":
                    # A terminal failed task is the only safe automatic fallback trigger.
                    raise NexusProviderError("Nexus task failed", retryable=True)
                await asyncio.sleep(min(self.poll_interval_seconds, max(0, deadline - monotonic())))
            raise NexusOutcomeUnknown(f"Nexus task timed out after {self.timeout_seconds:g}s; no fallback was started")

    @staticmethod
    def _task_payload(response: httpx.Response, operation: str) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise NexusOutcomeUnknown(f"Nexus returned an invalid {operation} response") from exc
        if not isinstance(payload, dict):
            raise NexusOutcomeUnknown(f"Nexus returned an invalid {operation} response")
        return payload

    @staticmethod
    def _build_params(
        *,
        model_name: str,
        prompt: str,
        image_url: str | None,
        model_params: dict[str, object] | None,
        reference_image_urls: list[str] | None = None,
    ) -> dict[str, object]:
        # Operator-controlled tuning parameters must never override provenance-critical
        # request fields. Preserve the stored brief, adding only the shared image output contract.
        reserved = {"model_name", "prompt", "image_url", "image_urls"}
        params = {
            key: value
            for key, value in (model_params or {}).items()
            if key not in reserved
        }
        params["model_name"] = model_name
        params["prompt"] = build_image_output_prompt(build_visual_fidelity_prompt(prompt))
        image_urls = [
            url.strip()
            for url in [image_url, *(reference_image_urls or [])]
            if isinstance(url, str) and url.strip()
        ]
        if image_urls:
            params["image_urls"] = list(dict.fromkeys(image_urls))
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
