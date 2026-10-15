from __future__ import annotations

import json
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from PIL import Image

from app.core.config import Settings
from app.domain.generations.enums import GenerationStatus
from app.providers import neironych_scene_qa
from app.providers.neironych_scene_qa import (
    QwenSceneProvider,
    SceneQualityReview,
    validate_scene_verdict,
)
from app.providers.nexus import NexusOutcomeUnknown
from app.services.asset_service import LocalMediaStorage
from app.services.generation_service import _public_quality_report
from app.workers import semantic_scene_gate as gate
from app.workers.semantic_scene_gate import read_candidate, selected_scene_objects


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
    return (
        "AUROOM_INITIAL_CONCEPT_V1\nSTRUCTURED_SPEC:\n"
        + json.dumps(
            {"schema": "auroom.initial_concept.v1", "task": {"objects": objects}},
            ensure_ascii=False,
        )
    )


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
    assert payload["messages"][0]["content"][1]["image_url"]["url"].startswith(
        "data:image/jpeg;base64,"
    )
    assert "Баня" in payload["messages"][0]["content"][0]["text"]
    assert "summer kitchen" in payload["messages"][0]["content"][0]["text"].lower()
    assert "no selected house" in payload["messages"][0]["content"][0]["text"].lower()
    assert "interior sauna" in payload["messages"][0]["content"][0]["text"].lower()
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
    expected = _canonical()
    saved = {"state": "submitted", "model": "qwen3.8-max",
             "candidate_sha256": sha256(_png()).hexdigest(),
             "candidate_path": "internal/semantic-scene/a.png"}
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
    with pytest.raises(NexusOutcomeUnknown):
        await gate.evaluate_candidate(uuid4(), _png(), expected, _settings(tmp_path))
    post.assert_not_awaited()


def test_private_qwen_checkpoint_is_redacted_from_generation_api():
    checkpoint = {
        "version": "architectural-image-qa.v1",
        "model": "qwen3.8-max",
        "state": "reviewed",
        "candidate_path": "internal/semantic-scene/hidden/candidate.png",
        "candidate_sha256": "private-checksum",
        "provider_task_id": "private-task",
        "request_key": "private-idempotency-key",
        "client_request_id": "private-client-id",
        "request_id": "private-response-id",
        "verdict": {"passed": True, "missing_object_keys": []},
    }
    result = _public_quality_report({"image_scene_review": checkpoint})
    assert result["image_scene_review"] == {
        "version": "architectural-image-qa.v1", "model": "qwen3.8-max",
        "state": "reviewed", "verdict": {"passed": True, "missing_object_keys": []},
    }
    for private in ("internal/", "private-checksum", "private-task", "private-id"):
        assert private not in str(result)
    assert checkpoint["request_key"] == "private-idempotency-key"


def _fake_scene_db(monkeypatch, checkpoint):
    row = SimpleNamespace(status=GenerationStatus.PROCESSING,
                          quality_report={"image_scene_review": dict(checkpoint)})
    session = AsyncMock()
    session.__aenter__.return_value = session
    repo = SimpleNamespace(get_for_update=AsyncMock(return_value=row))
    monkeypatch.setattr(gate, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(gate, "GenerationRepository", lambda _: repo)
    return row, session


@pytest.mark.asyncio
async def test_candidate_checkpoint_reused_and_verdict_persisted_once(monkeypatch, tmp_path):
    data = _png()
    row, session = _fake_scene_db(
        monkeypatch, {"model": "qwen3.8-max", "state": "configured",
                      "version": gate.SCENE_QA_VERSION},
    )
    generation_id = uuid4()
    await gate.checkpoint_candidate(
        generation_id, data, image_model="nexus-test",
        provider_task_id="accepted-image-id", fallback_used=False,
        extension="png", settings=_settings(tmp_path),
    )
    snap = row.quality_report["image_scene_review"]
    assert snap["state"] == "candidate_ready"
    assert snap["candidate_sha256"] == sha256(data).hexdigest()
    assert await read_candidate(snap, _settings(tmp_path)) == data

    review = SceneQualityReview.model_validate({
        "objects": [
            {"object_key": "banya", "status": "present", "evidence": "sauna with chimney"},
            {"object_key": "besedka", "status": "present", "evidence": "separate gazebo"},
        ], "overall_pass": True, "notes": "",
    })
    paid_post = AsyncMock(return_value=(review, "qwen-req-id"))
    monkeypatch.setattr(gate.QwenSceneProvider, "review_scene", paid_post)
    result = await gate.evaluate_candidate(
        generation_id, data, _canonical(), _settings(tmp_path),
    )
    assert result["passed"] is True
    assert row.quality_report["image_scene_review"]["state"] == "reviewed"
    assert row.quality_report["image_scene_review"]["request_id"] == "qwen-req-id"
    cached = await gate.evaluate_candidate(
        generation_id, data, _canonical(), _settings(tmp_path),
    )
    assert cached == result
    paid_post.assert_awaited_once()
    assert session.commit.await_count >= 3


@pytest.mark.asyncio
async def test_failed_bathhouse_review_refuses_publishing_and_never_reposts(monkeypatch, tmp_path):
    image_data = _png()
    checkpoint = {
        "model": "qwen3.8-max", "state": "candidate_ready",
        "candidate_sha256": sha256(image_data).hexdigest(),
        "candidate_path": "internal/semantic-scene/candidate.png",
    }
    row, session = _fake_scene_db(monkeypatch, checkpoint)
    review = SceneQualityReview.model_validate({
        "objects": [
            {"object_key": "banya", "status": "substituted", "evidence": "outdoor summer kitchen"},
            {"object_key": "besedka", "status": "present", "evidence": "gazebo"},
        ], "overall_pass": False, "notes": "no enclosed bath",
    })
    paid_post = AsyncMock(return_value=(review, "req-bath-missing"))
    monkeypatch.setattr(gate.QwenSceneProvider, "review_scene", paid_post)
    for _ in range(2):
        with pytest.raises(gate.SemanticSceneRejected):
            await gate.evaluate_candidate(
                uuid4(), image_data, _canonical(), _settings(tmp_path),
            )
    assert row.quality_report["image_scene_review"]["state"] == "reviewed"
    assert row.quality_report["image_scene_review"]["verdict"]["missing_object_keys"] == ["banya"]
    paid_post.assert_awaited_once()
    assert session.commit.await_count >= 2


@pytest.mark.asyncio
async def test_ambiguous_qwen_post_recovery_never_reposts(monkeypatch, tmp_path):
    image_data = _png()
    checkpoint = {
        "model": "qwen3.8-max", "state": "candidate_ready",
        "candidate_sha256": sha256(image_data).hexdigest(),
        "candidate_path": "internal/semantic-scene/candidate.png",
    }
    row, _ = _fake_scene_db(monkeypatch, checkpoint)
    post = AsyncMock(side_effect=NexusOutcomeUnknown("response lost"))
    monkeypatch.setattr(gate.QwenSceneProvider, "review_scene", post)
    for _ in range(2):
        with pytest.raises(NexusOutcomeUnknown):
            await gate.evaluate_candidate(
                uuid4(), image_data, _canonical(), _settings(tmp_path),
            )
    assert row.quality_report["image_scene_review"]["state"] == "submitted"
    post.assert_awaited_once()


@pytest.mark.asyncio
async def test_incomplete_qwen_verdict_is_terminal_rejection_not_indefinite_reconciliation(
    monkeypatch, tmp_path,
):
    data = _png()
    checkpoint = {
        "model": "qwen3.8-max",
        "state": "candidate_ready",
        "candidate_sha256": sha256(data).hexdigest(),
        "candidate_path": "internal/semantic-scene/candidate.png",
    }
    row, _ = _fake_scene_db(monkeypatch, checkpoint)
    incomplete = SceneQualityReview.model_validate({
        "objects": [
            {"object_key": "banya", "status": "present", "evidence": "enclosed sauna"},
        ],
        "overall_pass": True,
        "notes": "",
    })
    paid_post = AsyncMock(return_value=(incomplete, "qwen-answered"))
    monkeypatch.setattr(gate.QwenSceneProvider, "review_scene", paid_post)

    for _ in range(2):
        with pytest.raises(gate.SemanticSceneRejected):
            await gate.evaluate_candidate(
                uuid4(), data, _canonical(), _settings(tmp_path),
            )

    saved = row.quality_report["image_scene_review"]
    assert saved["state"] == "reviewed"
    assert saved["verdict"]["passed"] is False
    assert saved["verdict"]["missing_object_keys"] == ["besedka"]
    paid_post.assert_awaited_once()
