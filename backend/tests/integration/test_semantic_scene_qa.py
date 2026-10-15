"""End-to-end checkpointed initial-scene review against isolated test DB.

No external Neironych or Nexus requests are made by these tests.
"""
from __future__ import annotations

import os
from uuid import UUID
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.integration
if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip("requires isolated migrated test DB", allow_module_level=True)

from httpx import ASGITransport, AsyncClient  # noqa: E402

from test_initial_layout_recovery import prepare  # noqa: E402
from test_generation_pipeline import _png  # noqa: E402
from test_framing_retry_recovery import _recover_reserved  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models.admin import GenerationRuntimeSettings  # noqa: E402
from app.db.models.generations import Generation  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.generations.enums import GenerationStatus  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.neironych_scene_qa import SceneQualityReview, QwenSceneProvider  # noqa: E402
from app.providers.nexus import NexusImageProvider, NexusImageResult, NexusOutcomeUnknown  # noqa: E402
from app.questionnaires.catalog import build_catalog  # noqa: E402
from app.questionnaires.generation_prompt import build_initial_concept_prompt  # noqa: E402
from app.schemas.questionnaires import DesignSession  # noqa: E402
from app.workers import generation_worker  # noqa: E402


def _bathhouse_prompt():
    catalog = build_catalog()
    return build_initial_concept_prompt(
        catalog,
        DesignSession(
            catalog_version=catalog["version"],
            selected_objects=["banya", "besedka"],
            plot_area_sotkas=10,
            initial_concept_mode=True,
            answers={
                "banya": {"4": "Финская сауна", "5": "Дровяная, с трубой",
                          "6": "Отдельное строение", "7": "Слева от дома"},
                "besedka": {"1": "Современный минимализм", "5": "Сзади, во дворе"},
            },
        ),
        input_asset_present=False,
    )


async def _prepare_semantic_test(client):
    generation_id, headers = await prepare(client)
    async with get_session_factory()() as db:
        row = await db.get(Generation, generation_id)
        row.prompt = _bathhouse_prompt()
        runtime = await db.get(GenerationRuntimeSettings, 1)
        runtime.quality_judge_model = "qwen3.8-max"
        runtime.fallback_model = None
        await db.commit()
    return generation_id, headers


def _review(status):
    return SceneQualityReview.model_validate({
        "objects": [
            {"object_key": "banya", "status": status,
             "evidence": "enclosed wood-fired bath" if status == "present" else "open summer kitchen"},
            {"object_key": "besedka", "status": "present", "evidence": "separate gazebo"},
        ],
        "overall_pass": status == "present",
        "notes": "" if status == "present" else "bathhouse not visible",
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("sauna_status", ["present", "substituted"])
async def test_qa_holds_asset_until_qwen_confirms_each_selected_structure(
    monkeypatch, sauna_status,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generation_id, headers = await _prepare_semantic_test(client)
        image_calls = []
        async def image_generate(self, **kwargs):
            image_calls.append(kwargs)
            await kwargs["on_task_created"]("paid-image-accepted")
            return NexusImageResult(
                task_id="paid-image-accepted", image_url="https://cdn.example.test/generated.png",
            )
        async def image_download(*args):
            return _png((320, 180), (90, 100, 110))
        review_post = AsyncMock(return_value=(_review(sauna_status), "qwen-correlation-1"))
        monkeypatch.setattr(NexusImageProvider, "generate", image_generate)
        monkeypatch.setattr(generation_worker, "_download_image", image_download)
        monkeypatch.setattr(QwenSceneProvider, "review_scene", review_post)

        await generation_worker.process_generation(generation_id, get_settings())
        response = (await client.get(f"/api/v1/generations/{generation_id}", headers=headers))
        assert response.status_code == 200
        result = response.json()
        if sauna_status == "present":
            assert result["status"] == "completed", result
            assert result["output_asset"] is not None
            assert result["quality_status"] == "passed"
        else:
            assert result["status"] == "failed", result
            assert result["output_asset"] is None
            assert result["quality_status"] == "rejected"
            assert (await client.get("/api/v1/me", headers=headers)).json()["credits_balance"] == 5
        public = result["quality_report"]["image_scene_review"]
        assert public["state"] == "reviewed"
        assert public["verdict"]["missing_object_keys"] == (
            [] if sauna_status == "present" else ["banya"]
        )
        assert set(public) == {"version", "model", "state", "verdict"}
        assert len(image_calls) == 1
        review_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_lost_qwen_reply_preserves_post_checkpoint_and_never_rebuys(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generation_id, headers = await _prepare_semantic_test(client)
        image_calls = []
        async def image_generate(self, **kwargs):
            image_calls.append(kwargs)
            await kwargs["on_task_created"]("paid-image-accepted")
            return NexusImageResult(
                task_id="paid-image-accepted", image_url="https://cdn.example.test/generated.png",
            )
        async def image_download(*args):
            return _png((320, 180), (90, 100, 110))
        review_post = AsyncMock(side_effect=NexusOutcomeUnknown("Qwen response lost"))
        monkeypatch.setattr(NexusImageProvider, "generate", image_generate)
        monkeypatch.setattr(generation_worker, "_download_image", image_download)
        monkeypatch.setattr(QwenSceneProvider, "review_scene", review_post)

        await generation_worker.process_generation(generation_id, get_settings())
        first = (await client.get(f"/api/v1/generations/{generation_id}", headers=headers)).json()
        assert first["status"] == "processing"
        assert first["quality_report"]["image_scene_review"]["state"] == "submitted"
        assert first["quality_report"]["requires_reconciliation"] is True

        await _recover_reserved(generation_id)
        await generation_worker.process_generation(generation_id, get_settings())
        after = (await client.get(f"/api/v1/generations/{generation_id}", headers=headers)).json()
        assert after["status"] == "processing"
        assert len(image_calls) == 1
        review_post.assert_awaited_once()
        assert (await client.get("/api/v1/me", headers=headers)).json()["credits_balance"] == 3
