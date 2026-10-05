from __future__ import annotations

import pytest

from app.core.config import Settings
from app.providers.neironych_responses import (
    NeironychResponsesProvider,
    VideoIdentityReview,
)


def _settings() -> Settings:
    return Settings(
        app_env="test",
        neironych_api_key="test-key",
        neironych_api_base_url="https://api.neironych.example",
    )


def test_grok_identity_payload_contains_both_frames_and_json_instruction() -> None:
    provider = NeironychResponsesProvider(_settings())
    payload = provider.build_identity_payload(
        model="grok-4.5",
        prompt="Compare these two views of the same architecture.",
        image_urls=[
            "https://media.example.test/start.png",
            "https://media.example.test/end.png",
        ],
    )

    assert payload["model"] == "grok-4.5"
    assert payload["max_output_tokens"] == 1200
    content = payload["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert "JSON" in content[0]["text"]
    assert [item["image_url"] for item in content[1:]] == [
        "https://media.example.test/start.png",
        "https://media.example.test/end.png",
    ]


def test_grok_identity_review_rejects_unknown_shape() -> None:
    with pytest.raises(ValueError):
        VideoIdentityReview.model_validate(
            {"same_scene": "yes", "confidence": 2, "critical_differences": "none"}
        )


def test_grok_identity_review_accepts_strict_result() -> None:
    review = VideoIdentityReview.model_validate(
        {
            "same_scene": True,
            "confidence": 0.96,
            "critical_differences": [],
        }
    )
    assert review.same_scene is True
    assert review.confidence == 0.96
