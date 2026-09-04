from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic

import httpx

from app.core.config import Settings


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
        self.headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    async def generate(
        self,
        *,
        model_name: str,
        prompt: str,
        image_url: str,
        aspect_ratio: str,
        idempotency_key: str,
    ) -> NexusImageResult:
        params: dict[str, object] = {
            "model_name": model_name,
            "prompt": prompt,
            "image_urls": [image_url],
            "aspect_ratio": aspect_ratio,
        }
        if model_name == "nano-banana-pro":
            params["image_size"] = "2K"

        headers = {**self.headers, "Idempotency-Key": idempotency_key}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/generate",
                    headers=headers,
                    json={"params": params},
                )
            except httpx.HTTPError as exc:
                raise NexusProviderError("Nexus generation request failed", retryable=True) from exc

            if response.status_code >= 400:
                detail = self._safe_error(response)
                retryable = response.status_code >= 500 or response.status_code in {408}
                raise NexusProviderError(
                    f"Nexus create failed ({response.status_code}): {detail}",
                    retryable=retryable,
                )

            payload = response.json()
            task_id = str(payload.get("task_id") or "").strip()
            if not task_id:
                raise NexusProviderError("Nexus response did not include task_id", retryable=True)

            deadline = monotonic() + self.timeout_seconds
            while monotonic() < deadline:
                await asyncio.sleep(self.poll_interval_seconds)
                try:
                    task_response = await client.get(
                        f"{self.base_url}/tasks/{task_id}",
                        headers=self.headers,
                    )
                except httpx.HTTPError as exc:
                    raise NexusProviderError("Nexus polling failed", retryable=True) from exc

                if task_response.status_code >= 400:
                    detail = self._safe_error(task_response)
                    retryable = task_response.status_code >= 500 or task_response.status_code in {408}
                    raise NexusProviderError(
                        f"Nexus polling failed ({task_response.status_code}): {detail}",
                        retryable=retryable,
                    )

                task = task_response.json()
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
