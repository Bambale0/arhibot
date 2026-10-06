from __future__ import annotations

import json
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.core.config import Settings
from app.providers.neironych import (
    NeironychProviderError,
    build_neironych_http_config,
    extract_request_id,
    safe_error,
)
from app.providers.nexus import NexusOutcomeUnknown


_VIDEO_IDENTITY_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "same_scene": {"type": "boolean"},
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "critical_differences": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        },
    },
    "required": [
        "same_scene",
        "confidence",
        "critical_differences",
    ],
    "additionalProperties": False,
}


class VideoIdentityReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    same_scene: StrictBool
    confidence: float = Field(ge=0, le=1)
    critical_differences: list[str] = Field(default_factory=list, max_length=20)


class NeironychResponsesProvider:
    name = "neironych"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = build_neironych_http_config(settings)

    @staticmethod
    def _https_url(value: str) -> str:
        clean = str(value or "").strip()
        parsed = urlsplit(clean)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ValueError("Grok identity images must use HTTPS URLs")
        return clean

    def build_identity_payload(
        self,
        *,
        model: str,
        prompt: str,
        image_urls: list[str],
    ) -> dict[str, object]:
        if model.strip() != "grok-4.5":
            raise ValueError("Concept video identity review currently requires grok-4.5")
        if len(image_urls) != 2:
            raise ValueError("Identity review requires exactly two images")
        instruction = (
            str(prompt or "").strip()
            + "\n\nReturn JSON only, with exactly these fields: "
            + '{"same_scene": true|false, "confidence": 0..1, '
            + '"critical_differences": ["..."]}. '
            + "same_scene may be true only if both images depict the same architectural "
            + "project and site layout with the same buildings, roof, openings, garage, "
            + "terraces, pool, paths, fence, landscaping structure, materials and relative "
            + "object positions. Camera position/parallax may differ. Do not excuse redesigns."
        )
        content: list[dict[str, str]] = [
            {"type": "input_text", "text": instruction}
        ]
        content.extend(
            {"type": "input_image", "image_url": self._https_url(url)}
            for url in image_urls
        )
        return {
            "model": model.strip(),
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": 1200,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "auroom_video_identity",
                    "strict": True,
                    "schema": _VIDEO_IDENTITY_JSON_SCHEMA,
                }
            },
        }

    @staticmethod
    def _output_text(payload: object) -> str:
        if not isinstance(payload, dict):
            return ""
        texts: list[str] = []
        output = payload.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "output_text"
                        and isinstance(block.get("text"), str)
                    ):
                        texts.append(block["text"])
        return "".join(texts).strip()

    async def review_identity(
        self,
        *,
        model: str,
        prompt: str,
        image_urls: list[str],
        idempotency_key: str,
        client_request_id: str,
    ) -> VideoIdentityReview:
        if not 8 <= len(idempotency_key) <= 160:
            raise ValueError("Idempotency-Key must contain 8..160 characters")
        body = self.build_identity_payload(
            model=model,
            prompt=prompt,
            image_urls=image_urls,
        )
        headers = {
            **self.http.headers,
            "Idempotency-Key": idempotency_key,
            "X-Client-Request-Id": client_request_id,
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.http.base_url,
                timeout=self.http.timeout,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    "/v1/responses",
                    headers=headers,
                    json=body,
                )
        except (httpx.HTTPError, TimeoutError) as exc:
            raise NexusOutcomeUnknown(
                "Neironych Grok response outcome is unknown; do not resubmit with a new key"
            ) from exc

        request_id = extract_request_id(response)
        if response.status_code in {408, 409} or response.status_code >= 500:
            raise NexusOutcomeUnknown(
                "Neironych Grok response outcome is unknown; do not duplicate",
                request_id=request_id,
            )
        if response.status_code >= 400:
            raise NeironychProviderError(
                f"Neironych Grok request failed ({response.status_code}): {safe_error(response)}",
                retryable=response.status_code == 429,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise NexusOutcomeUnknown(
                "Neironych Grok returned invalid JSON envelope",
                request_id=request_id,
            ) from exc
        if not isinstance(payload, dict) or payload.get("status") != "completed":
            raise NeironychProviderError(
                "Neironych Grok did not return a completed response"
            )
        text = self._output_text(payload)
        if not text:
            raise NeironychProviderError(
                "Neironych Grok completed without output_text"
            )
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise NeironychProviderError(
                "Neironych Grok returned non-JSON identity review"
            ) from exc
        try:
            return VideoIdentityReview.model_validate(decoded)
        except ValueError as exc:
            raise NeironychProviderError(
                "Neironych Grok identity review failed schema validation"
            ) from exc
