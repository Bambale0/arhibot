from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings
from app.providers.neironych import (
    NeironychProviderError,
    build_neironych_http_config,
    extract_request_id,
    safe_error,
)
from app.providers.nexus import NexusOutcomeUnknown

_TERMINAL_SUCCESS = {"completed", "succeeded", "success", "done", "ready"}
_TERMINAL_FAILURE = {"failed", "error", "expired", "cancelled", "canceled"}
_ALLOWED_RESOLUTIONS_20 = {"480p", "720p", "1080p", "4k"}
_ALLOWED_RESOLUTIONS_25 = {"480p", "720p", "1080p"}
_ALLOWED_ASPECT_RATIOS_20 = {"1:1", "16:9", "9:16", "4:3", "3:4", "21:9"}
_ALLOWED_PARAMS = {"duration", "resolution", "aspect_ratio"}
_STATUS_VISIBILITY_GRACE_SECONDS = 90.0


class NeironychVideoNotVisible(NeironychProviderError):
    pass


@dataclass(frozen=True, slots=True)
class NeironychVideoResult:
    request_id: str
    content: bytes
    mime_type: str


class NeironychVideoProvider:
    name = "neironych"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = build_neironych_http_config(settings)

    @staticmethod
    def _https_url(value: str, field: str) -> str:
        clean = str(value or "").strip()
        parsed = urlsplit(clean)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ValueError(f"{field} must be an HTTPS URL")
        return clean

    def build_payload(
        self,
        *,
        model: str,
        prompt: str,
        start_image_url: str,
        end_image_url: str,
        params: dict[str, object] | None,
    ) -> dict[str, object]:
        clean_model = model.strip()
        if clean_model not in {"seedance-2.0", "seedance-2.5"}:
            raise ValueError("Concept video requires seedance-2.0 or seedance-2.5")
        clean_prompt = str(prompt or "").strip()
        if not clean_prompt:
            raise ValueError("Seedance prompt is required")
        if len(clean_prompt.encode("utf-8")) > 40_000:
            raise ValueError("Seedance prompt exceeds 40,000 UTF-8 bytes")

        supplied = dict(params or {})
        unknown = set(supplied) - _ALLOWED_PARAMS
        if unknown:
            raise ValueError(
                "Unsupported Seedance parameters: " + ", ".join(sorted(unknown))
            )

        duration = supplied.get("duration", 8)
        max_duration = 30 if clean_model == "seedance-2.5" else 15
        if type(duration) is not int or not 4 <= duration <= max_duration:
            raise ValueError(
                f"{clean_model} duration must be an integer from 4 to {max_duration}"
            )

        resolution = str(supplied.get("resolution", "480p")).strip()
        if resolution == "4K":
            resolution = "4k"
        allowed_resolutions = (
            _ALLOWED_RESOLUTIONS_25
            if clean_model == "seedance-2.5"
            else _ALLOWED_RESOLUTIONS_20
        )
        if resolution not in allowed_resolutions:
            raise ValueError(f"Unsupported {clean_model} resolution")

        if clean_model == "seedance-2.5":
            # Neironych contract: frame mode on 2.5 requires adaptive or omitted ratio.
            aspect_ratio = "adaptive"
        else:
            aspect_ratio = str(supplied.get("aspect_ratio", "16:9")).strip()
            if aspect_ratio not in _ALLOWED_ASPECT_RATIOS_20:
                raise ValueError("Unsupported seedance-2.0 aspect_ratio")

        return {
            "model": clean_model,
            "prompt": clean_prompt,
            "start_image": {
                "url": self._https_url(start_image_url, "start_image")
            },
            "end_image": {
                "url": self._https_url(end_image_url, "end_image")
            },
            "duration": duration,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "n": 1,
        }

    @staticmethod
    def _request_id(payload: object) -> str:
        if isinstance(payload, dict):
            for key in ("request_id", "id", "video_id"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            data = payload.get("data")
            if isinstance(data, dict):
                for key in ("request_id", "id", "video_id"):
                    value = data.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        return ""

    @staticmethod
    def _status(payload: object) -> str:
        if not isinstance(payload, dict):
            return ""
        source = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        return str(source.get("status") or source.get("state") or "").strip().lower()

    async def create(
        self,
        *,
        request_body: str,
        idempotency_key: str,
        client_request_id: str,
    ) -> str:
        if not 8 <= len(idempotency_key) <= 160:
            raise ValueError("Idempotency-Key must contain 8..160 characters")

        headers = {
            **self.http.headers,
            "Idempotency-Key": idempotency_key,
            "X-Client-Request-Id": client_request_id,
        }
        last_error: Exception | None = None
        # The provider explicitly guarantees that replaying VIDEO create with the
        # identical body and idempotency key returns the original request_id.
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    base_url=self.http.base_url,
                    timeout=self.http.timeout,
                    follow_redirects=False,
                ) as client:
                    response = await client.post(
                        "/v1/videos/generations",
                        headers=headers,
                        content=request_body.encode("utf-8"),
                    )
            except (httpx.HTTPError, TimeoutError) as exc:
                last_error = exc
                if attempt == 0:
                    continue
                raise NexusOutcomeUnknown(
                    "Neironych video create outcome is unknown after safe same-key replay"
                ) from exc

            if response.status_code in {408, 429} or response.status_code >= 500:
                last_error = RuntimeError(safe_error(response))
                if attempt == 0:
                    retry_after = response.headers.get("retry-after")
                    if retry_after and retry_after.isdigit():
                        await asyncio.sleep(min(int(retry_after), 5))
                    continue
                raise NexusOutcomeUnknown(
                    "Neironych video create outcome is unknown after safe same-key replay",
                    request_id=extract_request_id(response),
                )
            if response.status_code >= 400:
                error_detail = safe_error(response)
                raise NeironychProviderError(
                    f"Neironych video create failed ({response.status_code}): "
                    f"{error_detail}"
                )
            try:
                body = response.json()
            except ValueError as exc:
                raise NexusOutcomeUnknown(
                    "Neironych video create returned invalid JSON",
                    request_id=extract_request_id(response),
                ) from exc
            request_id = self._request_id(body)
            if not request_id:
                raise NexusOutcomeUnknown(
                    "Neironych video create returned no request_id",
                    request_id=extract_request_id(response),
                )
            return request_id

        raise NexusOutcomeUnknown(
            "Neironych video create outcome is unknown"
        ) from last_error

    async def _status_request(self, request_id: str) -> tuple[str, object]:
        async with httpx.AsyncClient(
            base_url=self.http.base_url,
            timeout=self.http.timeout,
            follow_redirects=False,
        ) as client:
            response = await client.get(
                f"/v1/videos/{request_id}",
                headers={
                    "Authorization": self.http.headers["Authorization"],
                    "Accept": "application/json",
                },
            )
        if response.status_code >= 400:
            error_detail = safe_error(response)
            if response.status_code == 404 and error_detail == "generation_not_found":
                raise NeironychVideoNotVisible(
                    "Neironych video request is not visible in status API yet",
                    retryable=True,
                )
            raise NeironychProviderError(
                f"Neironych video status failed ({response.status_code}): {error_detail}",
                retryable=response.status_code in {408, 429} or response.status_code >= 500,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise NeironychProviderError(
                "Neironych video status returned invalid JSON", retryable=True
            ) from exc
        return self._status(payload), payload

    @staticmethod
    def validate_video_content(content: bytes, *, max_bytes: int) -> None:
        if not content or len(content) > max_bytes:
            raise ValueError("MP4 video size is invalid")
        # ISO Base Media File Format normally exposes an ftyp box at the
        # beginning. Accept a small leading box, but reject arbitrary bytes
        # or an HTML/error body returned with a misleading content type.
        offset = content.find(b"ftyp", 4, min(len(content), 64))
        if offset < 4:
            raise ValueError("MP4 ftyp box is missing")
        box_size = int.from_bytes(content[offset - 4 : offset], "big")
        if box_size < 8 or offset - 4 + box_size > len(content):
            raise ValueError("MP4 ftyp box is invalid")


    async def _download(self, request_id: str) -> tuple[bytes, str]:
        max_bytes = int(self.settings.max_video_size_bytes)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                chunks: list[bytes] = []
                received = 0
                async with httpx.AsyncClient(
                    base_url=self.http.base_url,
                    timeout=httpx.Timeout(
                        self.settings.neironych_request_timeout_seconds,
                        connect=self.settings.neironych_http_connect_timeout_seconds,
                    ),
                    follow_redirects=False,
                ) as client:
                    async with client.stream(
                        "GET",
                        f"/v1/videos/{request_id}/content",
                        headers={
                            "Authorization": self.http.headers["Authorization"],
                            "Accept": "video/mp4,application/octet-stream",
                        },
                    ) as response:
                        if response.status_code >= 400:
                            body = await response.aread()
                            buffered = httpx.Response(
                                response.status_code,
                                headers=response.headers,
                                content=body,
                            )
                            raise NeironychProviderError(
                                f"Neironych video download failed ({response.status_code}): "
                                f"{safe_error(buffered)}",
                                retryable=response.status_code in {408, 429}
                                or response.status_code >= 500,
                            )
                        length = response.headers.get("content-length")
                        if length and length.isdigit() and int(length) > max_bytes:
                            raise NeironychProviderError(
                                "Neironych video exceeds configured size limit"
                            )
                        async for chunk in response.aiter_bytes():
                            received += len(chunk)
                            if received > max_bytes:
                                raise NeironychProviderError(
                                    "Neironych video exceeds configured size limit"
                                )
                            chunks.append(chunk)
                        mime = str(
                            response.headers.get("content-type") or "video/mp4"
                        ).split(";", 1)[0]
                content = b"".join(chunks)
                if mime not in {"video/mp4", "application/octet-stream"}:
                    raise NeironychProviderError(
                        f"Unexpected Neironych video content type: {mime}"
                    )
                try:
                    self.validate_video_content(content, max_bytes=max_bytes)
                except ValueError as exc:
                    raise NeironychProviderError(str(exc)) from exc
                return content, "video/mp4"
            except (httpx.HTTPError, TimeoutError, NeironychProviderError) as exc:
                last_error = exc
                if isinstance(exc, NeironychProviderError) and not exc.retryable:
                    raise
                if attempt < 2:
                    continue
        raise NeironychProviderError(
            "Neironych video download could not be completed", retryable=True
        ) from last_error

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        start_image_url: str,
        end_image_url: str,
        params: dict[str, object] | None,
        idempotency_key: str,
        client_request_id: str,
        request_id: str | None = None,
        request_body: str | None = None,
        on_request_created=None,
    ) -> NeironychVideoResult:
        if request_body is None:
            payload = self.build_payload(
                model=model,
                prompt=prompt,
                start_image_url=start_image_url,
                end_image_url=end_image_url,
                params=params,
            )
            request_body = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            )
        else:
            try:
                saved = json.loads(request_body)
            except json.JSONDecodeError as exc:
                raise ValueError("Saved Seedance request body is invalid JSON") from exc
            if not isinstance(saved, dict) or saved.get("model") != model:
                raise ValueError("Saved Seedance request body model mismatch")
        current_id = (request_id or "").strip()
        if not current_id:
            current_id = await self.create(
                request_body=request_body,
                idempotency_key=idempotency_key,
                client_request_id=client_request_id,
            )
            if on_request_created is not None:
                await on_request_created(current_id)

        deadline = monotonic() + self.settings.neironych_video_timeout_seconds
        not_visible_since: float | None = None
        while monotonic() < deadline:
            try:
                status, payload_status = await self._status_request(current_id)
                not_visible_since = None
            except NeironychVideoNotVisible as exc:
                now = monotonic()
                not_visible_since = not_visible_since or now
                if now - not_visible_since > _STATUS_VISIBILITY_GRACE_SECONDS:
                    raise NeironychProviderError(
                        "Neironych accepted the video request, but it did not become "
                        "visible in the status API within the recovery window",
                        retryable=False,
                    ) from exc
                await asyncio.sleep(self.settings.neironych_video_poll_seconds)
                continue
            except NeironychProviderError as exc:
                if exc.retryable:
                    await asyncio.sleep(self.settings.neironych_video_poll_seconds)
                    continue
                raise
            if status in _TERMINAL_SUCCESS:
                content, mime = await self._download(current_id)
                return NeironychVideoResult(
                    request_id=current_id,
                    content=content,
                    mime_type=mime,
                )
            if status in _TERMINAL_FAILURE:
                raise NeironychProviderError(
                    f"Neironych video generation failed: {payload_status}",
                    retryable=False,
                )
            await asyncio.sleep(self.settings.neironych_video_poll_seconds)

        raise NeironychProviderError(
            "Neironych video generation timed out while polling accepted request",
            retryable=True,
        )
