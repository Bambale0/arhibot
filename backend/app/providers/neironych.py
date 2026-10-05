"""Synchronous Neironych image boundary; ambiguous purchases must not be replayed.

The existing worker exception contract is intentionally reused so unknown outcomes
retain their credit reservation and never trigger a paid fallback.
"""
from __future__ import annotations

import asyncio
import base64
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlsplit

import httpx
from PIL import Image

from app.core.config import Settings
from app.prompt_builders.image_output import build_image_output_prompt
from app.prompt_builders.visual_fidelity import build_visual_fidelity_prompt
from app.providers.nexus import NexusOutcomeUnknown, NexusProviderError


class NeironychProviderError(NexusProviderError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message, retryable=retryable)


@dataclass(frozen=True, slots=True)
class NeironychHttpConfig:
    base_url: str
    headers: dict[str, str]
    timeout: httpx.Timeout


def build_neironych_http_config(settings: Settings) -> NeironychHttpConfig:
    key = (settings.neironych_api_key or "").strip()
    if not key:
        raise NeironychProviderError("NEIRONYCH_API_KEY is not configured")
    return NeironychHttpConfig(
        base_url=settings.neironych_api_base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=httpx.Timeout(
            settings.neironych_request_timeout_seconds,
            connect=settings.neironych_http_connect_timeout_seconds,
        ),
    )


def extract_request_id(response: httpx.Response) -> str | None:
    for name in ("x-request-id", "request-id", "x-correlation-id"):
        value = response.headers.get(name)
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value):
            return value
    return None


def safe_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return (response.text or "unknown error")[:300]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()[:300]
        for key in ("detail", "message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:300]
    return "provider_error"


@dataclass(frozen=True, slots=True)
class NeironychImageResult:
    task_id: str
    image_url: str
    image_data: bytes | None = None
    request_id: str | None = None


class NeironychImageProvider:
    name = "neironych"

    def __init__(self, settings: Settings) -> None:
        key = (settings.neironych_api_key or "").strip()
        if not key:
            raise NexusProviderError("NEIRONYCH_API_KEY is not configured", retryable=False)
        self.settings = settings
        self.base_url = settings.neironych_api_base_url.rstrip("/")
        self.timeout_seconds = settings.neironych_request_timeout_seconds
        self.headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    @staticmethod
    def build_request(*, model_name: str, prompt: str, image_url: str | None,
                      model_params: dict[str, object] | None,
                      reference_image_urls: list[str] | None = None) -> tuple[str, dict]:
        # Model choice remains in the admin control plane. Only the documented
        # image protocol is supported; never silently send Nexus-only knobs.
        allowed = {"size", "quality", "aspect_ratio"}
        reserved = {"model", "model_name", "prompt", "images", "image_url", "image_urls",
                    "mask", "n", "response_format"}
        unknown = set(model_params or {}) - allowed - reserved
        if unknown:
            raise NexusProviderError("Unsupported Neironych image parameters: "
                                     + ", ".join(sorted(unknown)), retryable=False)
        params = {key: value for key, value in (model_params or {}).items() if key in allowed}
        if params.get("quality", "auto") not in {"auto", "low", "medium", "high"}:
            raise NexusProviderError("Invalid Neironych image quality", retryable=False)
        size = params.get("size", "auto")
        match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", str(size))
        if size != "auto" and match is None:
            raise NexusProviderError("Neironych size must be auto or WIDTHxHEIGHT", retryable=False)
        aspect = params.pop("aspect_ratio", None)
        if aspect is not None:
            ratio = re.fullmatch(r"([1-9][0-9]*):([1-9][0-9]*)", str(aspect))
            if ratio is None or match is None:
                raise NexusProviderError("Neironych geometry requires an explicit WIDTHxHEIGHT size", retryable=False)
            width, height = map(int, ratio.groups())
            edge = max(map(int, match.groups()))
            # The worker's frozen source geometry is authoritative. Keep the
            # operator's configured long-edge resolution, changing only shape.
            params["size"] = f"{max(1, round(edge * width / max(width, height)))}x{max(1, round(edge * height / max(width, height)))}"
        params.update(model=model_name, prompt=build_image_output_prompt(
            build_visual_fidelity_prompt(prompt)), n=1, response_format="b64_json")
        references = list(dict.fromkeys(url.strip() for url in [image_url, *(reference_image_urls or [])]
                                       if isinstance(url, str) and url.strip()))
        if len(references) > 16:
            raise NexusProviderError("Neironych supports at most 16 input images", retryable=False)
        if references:
            params["images"] = [{"image_url": url} for url in references]
        return "/v1/images/edits" if references else "/v1/images/generations", params

    async def generate(self, *, model_name: str, prompt: str, image_url: str | None,
                       model_params: dict[str, object] | None, idempotency_key: str,
                       reference_image_urls: list[str] | None = None,
                       timeout_seconds: float | None = None, task_id: str | None = None,
                       on_task_created: Callable[[str], Awaitable[None]] | None = None,
                       prepared_request: tuple[str, dict] | None = None) -> NeironychImageResult:
        if task_id:
            raise NexusOutcomeUnknown("Neironych synchronous result needs reconciliation; no replay")
        if not 8 <= len(idempotency_key) <= 160:
            raise NexusProviderError("Invalid Neironych idempotency key length", retryable=False)
        endpoint, body = prepared_request or self.build_request(
            model_name=model_name, prompt=prompt, image_url=image_url,
            model_params=model_params, reference_image_urls=reference_image_urls)
        deadline = min(float(timeout_seconds or self.timeout_seconds), self.timeout_seconds)
        if deadline <= 0:
            raise NexusProviderError("Invalid Neironych deadline", retryable=False)
        timeout = httpx.Timeout(deadline, connect=self.settings.neironych_http_connect_timeout_seconds)
        try:
            async with asyncio.timeout(deadline):
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                    response = await client.post(f"{self.base_url}{endpoint}", json=body,
                        headers={**self.headers, "Idempotency-Key": idempotency_key})
        except (httpx.ConnectTimeout, httpx.ConnectError) as exc:
            raise NexusProviderError(
                "Neironych connection failed before request submission",
                retryable=True,
            ) from exc
        except (httpx.HTTPError, TimeoutError) as exc:
            raise NexusOutcomeUnknown("Neironych submission outcome is unknown; no retry") from exc
        request_id = self._safe_identifier(response.headers.get("X-Request-Id"))
        if 300 <= response.status_code < 500 and response.status_code not in {408, 409}:
            try:
                rejected_payload = response.json()
            except ValueError:
                rejected_payload = None
            code = self._error_code(rejected_payload)
            raise NexusProviderError(
                f"Neironych rejected request ({response.status_code}, {code})", retryable=False
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise NexusOutcomeUnknown(
                "Neironych response is not valid JSON", request_id=request_id
            ) from exc
        code = self._error_code(payload)
        if response.status_code in {408, 409} or response.status_code >= 500:
            raise NexusOutcomeUnknown(
                f"Neironych outcome unknown ({response.status_code}, {code})",
                request_id=request_id,
            )
        if response.status_code >= 300:
            raise NexusProviderError(f"Neironych rejected request ({response.status_code}, {code})", retryable=False)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list) or len(payload["data"]) != 1:
            raise NexusOutcomeUnknown("Neironych did not return exactly one image")
        item = payload["data"][0]
        if not isinstance(item, dict):
            raise NexusOutcomeUnknown("Neironych returned an invalid image result")
        data = None
        url = ""
        encoded = item.get("b64_json")
        if isinstance(encoded, str):
            if len(encoded) > (self.settings.max_image_size_bytes + 2) // 3 * 4:
                raise NexusOutcomeUnknown("Neironych output exceeds the image size limit")
            try:
                data = base64.b64decode(encoded, validate=True)
                self.validate_image_bytes(data, self.settings)
            except Exception as exc:
                raise NexusOutcomeUnknown("Neironych returned invalid image bytes") from exc
        elif isinstance(item.get("url"), str):
            try:
                parsed = urlsplit(item["url"])
                if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                    raise ValueError("Invalid output URL")
            except ValueError as exc:
                raise NexusOutcomeUnknown("Neironych returned invalid output URL") from exc
            # Worker downloads with SSRF checks and no provider Authorization header.
            url = item["url"]
        else:
            raise NexusOutcomeUnknown("Neironych did not return image bytes or an HTTPS URL")
        if on_task_created is not None:
            await on_task_created("sync")
        return NeironychImageResult(task_id="sync", image_url=url, image_data=data, request_id=request_id)

    @staticmethod
    def validate_image_bytes(data: bytes, settings: Settings) -> None:
        if not data or len(data) > settings.max_image_size_bytes:
            raise ValueError("Image size invalid")
        with Image.open(BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"} or image.width * image.height > settings.max_image_pixels:
                raise ValueError("Image format or dimensions invalid")
            image.verify()

    @staticmethod
    def _safe_identifier(value: object) -> str | None:
        return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value) else None

    @classmethod
    def _error_code(cls, payload: object) -> str:
        if isinstance(payload, dict):
            error = payload.get("error")
            candidate = error.get("type") if isinstance(error, dict) else payload.get("detail")
            return cls._safe_identifier(candidate) or "provider_error"
        return "provider_error"
