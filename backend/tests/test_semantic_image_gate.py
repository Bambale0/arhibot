from __future__ import annotations

import json
from io import BytesIO
from uuid import uuid4
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from app.core.config import Settings
from app.providers.neironych_scene_qa import (
    QwenSceneProvider, SceneQualityReview, validate_scene_verdict,
)
from app.workers.semantic_scene_gate import (
    SemanticSceneRejected, selected_scene_objects, read_candidate,
)


def _settings(tmp_path=None):
    values = {
        "neironych_api_key": "test-only",
        "neironych_api_base_url": "https://neironych.example",
    }
    if tmp_path:
        values["media_root"] = str(tmp_path)
    return Settings(**values)


def _png():
    out = BytesIO()
    Image.new("RGB", (256, 144), "white").save(out, "PNG")
    return out.getvalue()


def _canonical(selected=("banya", "besedka")):
    objects = [
        {
            "object_key": key,
            "object_name": {"banya": "Баня", "besedka": "Беседка", "eskez-doma": "Дом"}[key],
            "questionnaire_constraints": (
                [{"question": "Какая печь?", "answer": "Дровяная, с трубой"}]
                if key == "banya" else []
            ),
        }
        for key in selected
    ]
    return ("AUROOM_INITIAL_CONCEPT_V1\nSTRUCTURED_SPEC:\n"
            + json.dumps({"schema": "auroom.initial_concept.v1", "task": {"objects": objects}}, ensure_ascii=False))


def test_selected_objects_are_read_only_from_canonical_initial_concept():
    expected = selected_scene_objects(_canonical())
    assert [obj["object_key"] for obj in expected] == ["banya", "besedka"]
    assert expected[0]["object_name"] == "Баня"
    assert "Дровяная" in json.dumps(expected[0], ensure_ascii=False)
    assert selected_scene_objects("User prompt: a sauna") == []


def test_qwen_image_request_uses_one_downsampled_data_uri_and_strict_schema():
    provider = QwenSceneProvider(_settings())
    payload = provider.build_payload(
        model="qwen3.8-max", image_data=_png(),
        selected_objects=selected_scene_objects(_canonical()),
    )
    assert payload["model"] == "qwen3.8-max"
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["messages"][0]["content"][1]["type"] == "image_url"
    assert payload["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "Баня" in payload["messages"][0]["content"][0]["text"]
    assert "summer kitchen" in payload["messages"][0]["content"][0]["text"].lower()
    assert "api_key" not in str(payload)


@pytest.mark.parametrize("wrong", [
    {"objects": [{"object_key": "banya", "status": "present", "evidence": "building"}],
     "overall_pass": True, "notes": ""},  # missing gazebo
    {"objects": [
        {"object_key": "banya", "status": "present", "evidence": "building"},
        {"object_key": "banya", "status": "present", "evidence": "duplicate"},
    ], "overall_pass": True, "notes": ""},  # duplicate bathhouse
    {"objects": [
        {"object_key": "banya", "status": "present", "evidence": "building"},
        {"object_key": "besedka", "status": "yes", "evidence": "canopy"},
    ], "overall_pass": True, "notes": ""},  # invalid status
])
def test_qwen_review_rejects_incomplete_or_invalid_selected_object_lists(wrong):
    with pytest.raises(ValueError):
        validate_scene_verdict(SceneQualityReview.model_validate(wrong), ["banya", "besedka"])


def test_qwen_review_rejects_bathhouse_substituted_by_summer_kitchen():
    review = SceneQualityReview.model_validate({
        "objects": [
            {"object_key": "banya", "status": "substituted", "evidence": "Open cooking canopy"},
            {"object_key": "besedka", "status": "present", "evidence": "Separate gazebo"},
        ], "overall_pass": False, "notes": "Bathhouse is missing",
    })
    result = validate_scene_verdict(review, ["banya", "besedka"])
    assert result["passed"] is False
    assert result["missing_object_keys"] == ["banya"]
    assert result["objects"][0]["status"] == "substituted"


def test_qwen_review_accepts_all_visible_named_buildings():
    review = SceneQualityReview.model_validate({
        "objects": [
            {"object_key": "banya", "status": "present", "evidence": "Enclosed sauna and flue"},
            {"object_key": "besedka", "status": "present", "evidence": "Open gazebo behind"},
        ], "overall_pass": True, "notes": "",
    })
    assert validate_scene_verdict(review, ["banya", "besedka"])["passed"] is True


@pytest.mark.asyncio
async def test_qwen_api_success_is_one_post_with_strict_json(monkeypatch):
    from app.providers import neironych_scene_qa
    requests = []
    body = {"objects": [
        {"object_key": "banya", "status": "present", "evidence": "Building"},
        {"object_key": "besedka", "status": "present", "evidence": "Gazebo"},
    ], "overall_pass": True, "notes": ""}

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}}]},
                              headers={"X-Request-Id": "qa-reference-1"})

    original = httpx.AsyncClient
    monkeypatch.setattr(neironych_scene_qa.httpx, "AsyncClient",
                        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)))
    provider = QwenSceneProvider(_settings())
    result, request_id = await provider.review_scene(
        model="qwen3.8-max", image_data=_png(),
        selected_objects=selected_scene_objects(_canonical()),
        idempotency_key="auroom-unit-test-qwen",
        client_request_id=str(uuid4()),
    )
    assert request_id == "qa-reference-1"
    assert result.overall_pass is True
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/chat/completions"


@pytest.mark.asyncio
async def test_qwen_ambiguous_timeout_never_retries(monkeypatch):
    from app.providers import neironych_scene_qa
    from app.providers.nexus import NexusOutcomeUnknown
    sent = []

    def handle(request):
        sent.append(request)
        raise httpx.ReadTimeout("unknown", request=request)

    original = httpx.AsyncClient
    monkeypatch.setattr(neironych_scene_qa.httpx, "AsyncClient",
                        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)))
    provider = QwenSceneProvider(_settings())
    with pytest.raises(NexusOutcomeUnknown):
        await provider.review_scene(
            model="qwen3.8-max", image_data=_png(),
            selected_objects=selected_scene_objects(_canonical()),
            idempotency_key="auroom-unit-test-timeout",
            client_request_id=str(uuid4()),
        )
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_saved_candidate_digest_is_required(tmp_path):
    from app.services.asset_service import LocalMediaStorage
    from hashlib import sha256
    settings = _settings(tmp_path)
    storage = LocalMediaStorage(settings)
    path = "internal/semantic-scene/test-id/candidate.png"
    await storage.write(path, _png())
    saved = {"candidate_path": path, "candidate_sha256": sha256(_png()).hexdigest(),
             "image_model": "test-image", "provider_task_id": "sync", "fallback_used": False}
    assert await read_candidate(saved, settings) == _png()
    saved["candidate_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        await read_candidate(saved, settings)


@pytest.mark.asyncio
async def test_submitted_checkpoint_blocks_repurchase(monkeypatch, tmp_path):
    from app.workers import semantic_scene_gate as gate
    from app.domain.generations.enums import GenerationStatus
    from types import SimpleNamespace
    expected = _canonical()
    saved = {"state": "submitted", "model": "qwen3.8-max",
             "candidate_sha256": "irrelevant", "candidate_path": "internal/semantic-scene/a.png"}
    row = SimpleNamespace(status=GenerationStatus.PROCESSING,
                          quality_report={"image_scene_review": saved})
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.get.return_value = row
    repo = SimpleNamespace(get_for_update=AsyncMock(return_value=row))
    monkeypatch.setattr(gate, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(gate, "GenerationRepository", lambda _: repo)
    post = AsyncMock(side_effect=AssertionError("Must not resubmit Qwen"))
    monkeypatch.setattr(gate.QwenSceneProvider, "review_scene", post)
    from app.providers.nexus import NexusOutcomeUnknown
    with pytest.raises(NexusOutcomeUnknown):
        await gate.evaluate_candidate(uuid4(), _png(), expected, _settings(tmp_path))
    post.assert_not_awaited()
