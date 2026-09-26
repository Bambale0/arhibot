import asyncio
import copy
import json
import os
from urllib.parse import urlsplit

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True,
    )

from test_generation_pipeline import (  # noqa: E402
    _create_strict_masked_generation,
    _png,
    _register_admin,
    _register_user,
)

from app.core.config import get_settings  # noqa: E402
from app.core.redis import redis_client  # noqa: E402
from app.db.models.admin import GenerationRuntimeSettings  # noqa: E402
from app.db.models.generations import Generation  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.localized_edit import local_source  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.nexus import NexusImageProvider, NexusImageResult  # noqa: E402
from app.services.generation_service import GENERATION_QUEUE_KEY  # noqa: E402
from app.workers import generation_worker  # noqa: E402


async def _prepare_local_addition(client):
    _, admin_headers = await _register_admin(client)
    tokens, headers = await _register_user(client)
    generation_id, base_data, _ = await _create_strict_masked_generation(
        client, admin_headers=admin_headers, headers=headers, user_id=tokens["user"]["id"],
    )
    async with get_session_factory()() as db:
        row = await db.get(Generation, generation_id)
        row.prompt = "AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n" + json.dumps(
            {"task": {"object_key": "banya", "operation": "render_or_refine"}}
        )
        runtime = await db.get(GenerationRuntimeSettings, 1)
        runtime.fallback_model = "original-framing-fallback"
        await db.commit()
    return generation_id, base_data, headers


async def _recover_reserved(generation_id):
    await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))
    await redis_client.rpush(generation_worker.GENERATION_PROCESSING_KEY, str(generation_id))
    await generation_worker._recover_reserved_jobs()


def _image_roles(call):
    return (
        urlsplit(call["image_url"]).path,
        [urlsplit(url).path for url in call["reference_image_urls"] or []],
    )


@pytest.mark.asyncio
async def test_restart_after_framing_rejection_before_retry_intent_does_not_repurchase_first_task(
    monkeypatch,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generation_id, base_data, headers = await _prepare_local_addition(client)
        original_checkpointed = generation_worker._generate_checkpointed
        calls = []
        saved_geometry = None
        interrupted = False

        async def checkpointed(provider, current_id, **kwargs):
            nonlocal interrupted, saved_geometry
            if kwargs["attempt"] == 1 and not interrupted:
                async with get_session_factory()() as db:
                    row = await db.get(Generation, current_id)
                    report = row.quality_report
                    assert report["final"] == "retry_pending"
                    assert len(report["attempts"]) == 1
                    assert report["provider_request"]["attempt"] == 0
                    assert report["provider_request"]["task_id"] == "original-task"
                    saved_geometry = copy.deepcopy(report["provider_geometry"])
                interrupted = True
                # The rejection committed, but the next submission intent has not.
                raise asyncio.CancelledError()
            return await original_checkpointed(provider, current_id, **kwargs)

        async def generate(self, **kwargs):
            calls.append(kwargs)
            retry = "-quality-1-" in kwargs["idempotency_key"]
            task_id = "fallback-task" if retry else "original-task"
            if kwargs["task_id"] is None:
                await kwargs["on_task_created"](task_id)
            else:
                assert kwargs["task_id"] == "original-task"
            return NexusImageResult(task_id=task_id, image_url=f"https://cdn.example.test/{task_id}")

        async def download(url, settings):
            if url.endswith("original-task"):
                return _png((120, 60), (240, 240, 240))
            return local_source(base_data, saved_geometry, max_pixels=20000)

        monkeypatch.setattr(generation_worker, "_generate_checkpointed", checkpointed)
        monkeypatch.setattr(NexusImageProvider, "generate", generate)
        monkeypatch.setattr(generation_worker, "_download_image", download)
        with pytest.raises(asyncio.CancelledError):
            await generation_worker.process_generation(generation_id, get_settings())
        assert len(calls) == 1
        assert saved_geometry["operation"] == "add"
        await _recover_reserved(generation_id)
        await generation_worker.process_generation(generation_id, get_settings())
        await generation_worker.process_generation(generation_id, get_settings())

        result = (await client.get(f"/api/v1/generations/{generation_id}", headers=headers)).json()
        assert result["status"] == "completed", result
        assert result["output_asset"] is not None
        assert result["quality_report"]["provider_geometry"] == saved_geometry
        assert [call["task_id"] for call in calls] == [None, "original-task", None]
        assert [call["model_name"] for call in calls] == [
            "quality-model", "quality-model", "original-framing-fallback",
        ]
        assert all(_image_roles(call) == _image_roles(calls[0]) for call in calls)
        attempts = result["quality_report"]["attempts"]
        assert [attempt["attempt"] for attempt in attempts] == [1, 2]
        assert [attempt["provider_task_id"] for attempt in attempts] == [
            "original-task", "fallback-task",
        ]
        assert (await client.get("/api/v1/me", headers=headers)).json()["credits_balance"] == 3
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement_fallback", [None, "replacement-fallback"])
async def test_accepted_fallback_resumes_same_task_after_runtime_model_change(
    monkeypatch, replacement_fallback,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generation_id, base_data, headers = await _prepare_local_addition(client)
        calls = []
        saved_geometry = None

        async def generate(self, **kwargs):
            nonlocal saved_geometry
            calls.append(kwargs)
            retry = "-quality-1-" in kwargs["idempotency_key"]
            task_id = "accepted-fallback-task" if retry else "original-task"
            if kwargs["task_id"] is None:
                await kwargs["on_task_created"](task_id)
                if retry:
                    async with get_session_factory()() as db:
                        row = await db.get(Generation, generation_id)
                        saved_geometry = copy.deepcopy(row.quality_report["provider_geometry"])
                    raise asyncio.CancelledError()
            else:
                assert kwargs["task_id"] == "accepted-fallback-task"
                assert kwargs["model_name"] == "original-framing-fallback"
                assert kwargs["idempotency_key"].endswith("-quality-1-fallback")
            return NexusImageResult(task_id=task_id, image_url=f"https://cdn.example.test/{task_id}")

        async def download(url, settings):
            if url.endswith("original-task"):
                return _png((120, 60), (240, 240, 240))
            return local_source(base_data, saved_geometry, max_pixels=20000)

        monkeypatch.setattr(NexusImageProvider, "generate", generate)
        monkeypatch.setattr(generation_worker, "_download_image", download)
        with pytest.raises(asyncio.CancelledError):
            await generation_worker.process_generation(generation_id, get_settings())
        async with get_session_factory()() as db:
            row = await db.get(Generation, generation_id)
            checkpoint = row.quality_report["provider_request"]
            assert checkpoint["state"] == "accepted"
            assert checkpoint["phase"] == "fallback"
            assert checkpoint["task_id"] == "accepted-fallback-task"
            runtime = await db.get(GenerationRuntimeSettings, 1)
            runtime.primary_model = "replacement-primary"
            runtime.fallback_model = replacement_fallback
            await db.commit()
        await _recover_reserved(generation_id)
        await generation_worker.process_generation(generation_id, get_settings())
        await generation_worker.process_generation(generation_id, get_settings())

        result = (await client.get(f"/api/v1/generations/{generation_id}", headers=headers)).json()
        assert result["status"] == "completed", result
        assert result["output_asset"] is not None
        assert result["model_name"] == "original-framing-fallback"
        assert result["fallback_used"] is True
        async with get_session_factory()() as db:
            row = await db.get(Generation, generation_id)
            assert row.provider_task_id == "accepted-fallback-task"
        assert result["quality_report"]["provider_geometry"] == saved_geometry
        assert [call["task_id"] for call in calls] == [None, None, "accepted-fallback-task"]
        assert calls[1]["idempotency_key"] == calls[2]["idempotency_key"]
        assert all(_image_roles(call) == _image_roles(calls[0]) for call in calls)
        assert [item["attempt"] for item in result["quality_report"]["attempts"]] == [1, 2]
        assert (await client.get("/api/v1/me", headers=headers)).json()["credits_balance"] == 3
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))
