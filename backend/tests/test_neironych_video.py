from __future__ import annotations

import pytest

from app.core.config import Settings
from app.providers.neironych_video import NeironychVideoProvider


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
