from __future__ import annotations

import pytest

from app.core.config import Settings
from app.providers.neironych_video import (
    NeironychVideoNotVisible,
    NeironychVideoProvider,
)


def _settings() -> Settings:
    return Settings(
        app_env="test",
        neironych_api_key="test-key",
        neironych_api_base_url="https://api.neironych.example",
    )


def test_seedance_20_builds_locked_start_end_frame_payload() -> None:
    provider = NeironychVideoProvider(_settings())
    payload = provider.build_payload(
        model="seedance-2.0",
        prompt="Camera move only. Preserve the exact architecture.",
        start_image_url="https://media.example.test/start.png",
        end_image_url="https://media.example.test/end.png",
        params={"duration": 8, "resolution": "1080p", "aspect_ratio": "16:9"},
    )

    assert payload == {
        "model": "seedance-2.0",
        "prompt": "Camera move only. Preserve the exact architecture.",
        "start_image": {"url": "https://media.example.test/start.png"},
        "end_image": {"url": "https://media.example.test/end.png"},
        "duration": 8,
        "resolution": "1080p",
        "aspect_ratio": "16:9",
        "n": 1,
    }


@pytest.mark.parametrize("duration", [3, 16])
def test_seedance_20_rejects_duration_outside_contract(duration: int) -> None:
    provider = NeironychVideoProvider(_settings())
    with pytest.raises(ValueError, match="duration"):
        provider.build_payload(
            model="seedance-2.0",
            prompt="move",
            start_image_url="https://media.example.test/start.png",
            end_image_url="https://media.example.test/end.png",
            params={"duration": duration, "resolution": "1080p", "aspect_ratio": "16:9"},
        )


def test_seedance_frame_mode_rejects_non_https_images() -> None:
    provider = NeironychVideoProvider(_settings())
    with pytest.raises(ValueError, match="HTTPS"):
        provider.build_payload(
            model="seedance-2.0",
            prompt="move",
            start_image_url="http://localhost/start.png",
            end_image_url="https://media.example.test/end.png",
            params={"duration": 8},
        )


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not-an-mp4",
        b"\x00\x00\x00\x18moovwithout-ftyp",
    ],
)
def test_seedance_output_requires_mp4_ftyp_box(content: bytes) -> None:
    with pytest.raises(ValueError, match="MP4"):
        NeironychVideoProvider.validate_video_content(content, max_bytes=1024)


def test_seedance_output_accepts_mp4_ftyp_box() -> None:
    content = b"\x00\x00\x00\x18ftypmp42" + b"x" * 32
    NeironychVideoProvider.validate_video_content(content, max_bytes=1024)


@pytest.mark.asyncio
async def test_seedance_retries_status_visibility_without_new_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = NeironychVideoProvider(
        _settings().model_copy(
            update={
                "neironych_video_poll_seconds": 0.01,
                "neironych_video_timeout_seconds": 60,
            }
        )
    )
    calls = 0

    async def fake_status(request_id: str):
        nonlocal calls
        calls += 1
        assert request_id == "video-request-1"
        if calls == 1:
            raise NeironychVideoNotVisible("not visible yet", retryable=True)
        return "done", {"status": "done"}

    async def fake_download(request_id: str):
        assert request_id == "video-request-1"
        return b"\x00\x00\x00\x18ftypmp42" + b"x" * 32, "video/mp4"

    async def no_sleep(_seconds: float) -> None:
        return None

    async def forbidden_create(**_kwargs):
        raise AssertionError("accepted video request must not be submitted again")

    monkeypatch.setattr(provider, "_status_request", fake_status)
    monkeypatch.setattr(provider, "_download", fake_download)
    monkeypatch.setattr(provider, "create", forbidden_create)
    monkeypatch.setattr("app.providers.neironych_video.asyncio.sleep", no_sleep)

    result = await provider.generate(
        model="seedance-2.0",
        prompt="Camera motion only.",
        start_image_url="https://media.example.test/start.png",
        end_image_url="https://media.example.test/end.png",
        params={"duration": 8, "resolution": "1080p", "aspect_ratio": "16:9"},
        idempotency_key="video-idempotency-key",
        client_request_id="11111111-1111-4111-8111-111111111111",
        request_id="video-request-1",
    )

    assert result.request_id == "video-request-1"
    assert calls == 2
