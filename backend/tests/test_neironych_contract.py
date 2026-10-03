from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "neironych"


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_guide_contract_pins_required_endpoints_and_models() -> None:
    contract = load_fixture("guide-contract.json")
    models = load_fixture("models-success.json")

    assert contract["guide_sha256"] == (
        "756367c0aea3faaebe562a6d6e16b9dd1f635d0e417284cee76e36d19516c517"
    )
    assert contract["endpoints"] == {
        "models": "GET /v1/models",
        "responses": "POST /v1/responses",
        "image_generation": "POST /v1/images/generations",
        "image_edit": "POST /v1/images/edits",
        "video_generation": "POST /v1/videos/generations",
        "video_status": "GET /v1/videos/{request_id}",
        "video_content": "GET /v1/videos/{request_id}/content",
    }
    available = {item["id"] for item in models["data"]}
    assert {
        "gpt-image-2.5-sunburst",
        "grok-4.5",
        "seedance-2.0",
    } <= available


def test_image_contract_pins_sunburst_generation_and_edit_shapes() -> None:
    fixture = load_fixture("image-contract.json")

    generation = fixture["generation_request"]
    assert generation == {
        "model": "gpt-image-2.5-sunburst",
        "prompt": "A cinematic mountain panorama",
        "size": "3840x2160",
        "quality": "high",
        "n": 1,
        "response_format": "b64_json",
    }
    edit = fixture["edit_request"]
    assert edit["model"] == "gpt-image-2.5-sunburst"
    assert edit["images"] == [{"image_url": "https://media.example/reference.png"}]
    assert edit["mask"] == {"image_url": "https://media.example/mask.png"}
    assert base64.b64decode(fixture["success_response"]["data"][0]["b64_json"])
    assert fixture["idempotency"]["header"] == "Idempotency-Key"
    assert fixture["idempotency"]["sync_replay_returns_result"] is False
    assert fixture["idempotency"]["retry_ambiguous_post"] is False


def test_responses_contract_pins_multimodal_json_schema_shape() -> None:
    fixture = load_fixture("responses-contract.json")
    request = fixture["request"]

    assert request["model"] == "grok-4.5"
    assert request["input"][0]["content"][0]["type"] == "input_text"
    assert request["input"][0]["content"][1] == {
        "type": "input_image",
        "image_url": "https://media.example/candidate.png",
    }
    output_format = request["text"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["strict"] is True
    assert output_format["schema"]["additionalProperties"] is False

    response = fixture["success_response"]
    output_text = response["output"][0]["content"][0]
    assert output_text["type"] == "output_text"
    assert json.loads(output_text["text"])["verdict"] == "pass"
    assert fixture["verification"]["model_specific_json_schema"] == "requires_authenticated_smoke"
    assert fixture["verification"]["vision_limits"] == "not_declared_by_public_guide"


def test_seedance_contract_pins_start_image_and_async_recovery() -> None:
    fixture = load_fixture("video-contract.json")
    request = fixture["request"]

    assert request["model"] == "seedance-2.0"
    assert request["start_image"] == {"url": "https://media.example/accepted-still.png"}
    assert not any(key.startswith("reference_") for key in request)
    assert 4 <= request["duration"] <= 15
    assert request["resolution"] in {"480p", "720p", "1080p", "4k"}

    accepted = fixture["accepted_response"]
    assert accepted == {"request_id": "req_video_sanitized"}
    assert fixture["status_response"]["status"] == "done"
    assert fixture["content_response"]["supports_range"] is True
    assert fixture["idempotency"]["same_body_and_key_returns_original_request_id"] is True


@pytest.mark.parametrize(
    ("status", "error_type", "retry_allowed"),
    [
        (409, "idempotency_conflict", False),
        (409, "request_already_submitted", False),
        (429, "provider_rate_limited", False),
        (503, "submission_outcome_unknown", False),
        (503, "provider_response_invalid", False),
    ],
)
def test_paid_post_failures_are_pinned_fail_closed(
    status: int,
    error_type: str,
    retry_allowed: bool,
) -> None:
    errors = load_fixture("error-contract.json")

    entry = next(item for item in errors["errors"] if item["type"] == error_type)
    assert entry["status"] == status
    assert entry["automatic_paid_post_retry"] is retry_allowed
