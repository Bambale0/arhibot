import asyncio
import copy
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.integration
if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip("requires isolated migrated database", allow_module_level=True)

from httpx import ASGITransport, AsyncClient  # noqa: E402
from test_framing_retry_recovery import _recover_reserved  # noqa: E402
from test_generation_pipeline import (  # noqa: E402
    _create_strict_masked_generation,
    _png,
    _register_admin,
    _register_user,
)  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models.admin import GenerationRuntimeSettings  # noqa: E402
from app.db.models.generations import Generation  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.generations.enums import GenerationOrigin  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.nexus import (  # noqa: E402
    NexusImageProvider,
    NexusImageResult,
    NexusOutcomeUnknown,
)
from app.questionnaires.catalog import build_catalog  # noqa: E402
from app.questionnaires.generation_prompt import build_initial_concept_prompt  # noqa: E402
from app.schemas.questionnaires import DesignSession  # noqa: E402
from app.services.asset_service import LocalMediaStorage  # noqa: E402
from app.workers import generation_worker  # noqa: E402


def canonical():
    catalog = build_catalog()
    values = json.loads(
        (Path(__file__).parents[1] / "fixtures/initial-layout-case7.json").read_text()
    )
    values["catalog_version"] = catalog["version"]
    return build_initial_concept_prompt(catalog, DesignSession(**values), input_asset_present=False)


async def prepare(client):
    _, admin_headers = await _register_admin(client)
    tokens, headers = await _register_user(client)
    generation_id, _, _ = await _create_strict_masked_generation(
        client,
        admin_headers=admin_headers,
        headers=headers,
        user_id=tokens["user"]["id"],
    )
    async with get_session_factory()() as db:
        row = await db.get(Generation, generation_id)
        row.prompt = canonical()
        row.origin = GenerationOrigin.QUESTIONNAIRE_INITIAL.value
        row.composition_mode = "replace"
        row.edit_region = None
        row.edit_policy = {}
        row.protected_regions = []
        row.input_asset_id = None
        runtime = await db.get(GenerationRuntimeSettings, 1)
        runtime.primary_params = {"private_operator_parameter": "must-not-leak"}
        await db.commit()
    return generation_id, headers


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_file", [False, True])
async def test_accepted_initial_guide_survives_runtime_changes_and_missing_input(
    monkeypatch, missing_file
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generation_id, headers = await prepare(client)
        calls = []
        frozen = None

        async def generate(self, **kwargs):
            nonlocal frozen
            calls.append(kwargs)
            async with get_session_factory()() as db:
                row = await db.get(Generation, generation_id)
                snapshot = row.quality_report["initial_layout_guide"]
                assert row.prompt == canonical()
                if frozen is None:
                    frozen = copy.deepcopy(snapshot)
                assert snapshot == frozen
            if kwargs["task_id"] is None:
                await kwargs["on_task_created"]("paid-initial-task")
                raise asyncio.CancelledError()
            assert kwargs["task_id"] == "paid-initial-task"
            return NexusImageResult(
                task_id="paid-initial-task", image_url="https://cdn.example.test/result"
            )

        async def download(*args):
            return _png((160, 90), (30, 90, 20))

        monkeypatch.setattr(NexusImageProvider, "generate", generate)
        monkeypatch.setattr(generation_worker, "_download_image", download)
        with pytest.raises(asyncio.CancelledError):
            await generation_worker.process_generation(generation_id, get_settings())
        path = LocalMediaStorage(get_settings()).absolute_path(frozen["path"])
        assert path.exists()
        original_data = path.read_bytes()
        if missing_file:
            path.unlink()
        async with get_session_factory()() as db:
            runtime = await db.get(GenerationRuntimeSettings, 1)
            runtime.primary_model = ""
            runtime.fallback_model = "new-fallback"
            runtime.primary_params = {"changed": True}
            await db.commit()

        def never_rebuild(*args):
            pytest.fail("Accepted guide must not be rebuilt")

        monkeypatch.setattr(generation_worker, "build_initial_layout_guide", never_rebuild)
        await _recover_reserved(generation_id)
        await generation_worker.process_generation(generation_id, get_settings())
        await generation_worker.process_generation(generation_id, get_settings())
        result = (await client.get(f"/api/v1/generations/{generation_id}", headers=headers)).json()
        assert result["status"] == "completed", result
        assert set(result["quality_report"]["initial_layout_guide"]) == {
            "version",
            "sha256",
            "reference_role",
        }
        assert "must-not-leak" not in str(result)
        assert [call["task_id"] for call in calls] == [None, "paid-initial-task"]
        for field in ["model_name", "model_params", "prompt", "reference_image_urls"]:
            assert calls[0][field] == calls[1][field]
        assert urlsplit(calls[0]["image_url"]).path == urlsplit(calls[1]["image_url"]).path
        assert original_data.startswith(b"\x89PNG")
        assert not path.exists()
        assert (await client.get("/api/v1/me", headers=headers)).json()["credits_balance"] == 3


@pytest.mark.asyncio
async def test_ambiguous_initial_submission_keeps_guide_and_never_posts_again(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generation_id, headers = await prepare(client)
        calls = []

        async def generate(self, **kwargs):
            calls.append(kwargs)
            raise NexusOutcomeUnknown("lost POST response")

        monkeypatch.setattr(NexusImageProvider, "generate", generate)
        await generation_worker.process_generation(generation_id, get_settings())
        await _recover_reserved(generation_id)
        await generation_worker.process_generation(generation_id, get_settings())
        result = (await client.get(f"/api/v1/generations/{generation_id}", headers=headers)).json()
        assert result["status"] == "processing", result
        assert len(calls) == 1
        assert set(result["quality_report"]["initial_layout_guide"]) == {
            "version",
            "sha256",
            "reference_role",
        }
        assert "must-not-leak" not in str(result)
        async with get_session_factory()() as db:
            snapshot = (await db.get(Generation, generation_id)).quality_report[
                "initial_layout_guide"
            ]
        assert LocalMediaStorage(get_settings()).absolute_path(snapshot["path"]).exists()
        assert (await client.get("/api/v1/me", headers=headers)).json()["credits_balance"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", [False, True])
async def test_missing_or_changed_guide_before_new_purchase_fails_without_provider_post(
    monkeypatch, tamper
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generation_id, headers = await prepare(client)
        original = generation_worker._generate_checkpointed
        paths = []

        async def interrupt_input(provider, generation_id, **kwargs):
            path, _ = kwargs["required_input"]
            paths.append(path)
            if tamper:
                path.write_bytes(b"changed")
            else:
                path.unlink()
            return await original(provider, generation_id, **kwargs)

        async def forbidden_post(*args, **kwargs):
            pytest.fail("Invalid frozen input must never be purchased")

        monkeypatch.setattr(generation_worker, "_generate_checkpointed", interrupt_input)
        monkeypatch.setattr(NexusImageProvider, "generate", forbidden_post)
        await generation_worker.process_generation(generation_id, get_settings())
        result = (await client.get(f"/api/v1/generations/{generation_id}", headers=headers)).json()
        assert result["status"] == "failed", result
        assert len(paths) == 1 and not paths[0].exists()
        assert (await client.get("/api/v1/me", headers=headers)).json()["credits_balance"] == 5


@pytest.mark.asyncio
async def test_existing_initial_checkpoint_is_not_retrofitted_with_a_guide(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generation_id, headers = await prepare(client)
        async with get_session_factory()() as db:
            row = await db.get(Generation, generation_id)
            row.quality_report = {
                "provider_request": {
                    "key": f"auroom-{generation_id}-primary",
                    "attempt": 0,
                    "phase": "primary",
                    "state": "accepted",
                    "task_id": "legacy-paid",
                    "model": "legacy-model",
                }
            }
            await db.commit()
        calls = []

        async def generate(self, **kwargs):
            calls.append(kwargs)
            assert kwargs["task_id"] == "legacy-paid"
            assert kwargs["image_url"] is None
            assert kwargs["reference_image_urls"] is None
            assert kwargs["prompt"] == canonical()
            return NexusImageResult(
                task_id="legacy-paid", image_url="https://cdn.example.test/result"
            )

        async def download(*args):
            return _png((160, 90), (30, 90, 20))

        def never_rebuild(*args):
            pytest.fail("Legacy provider task must retain its original inputs")

        monkeypatch.setattr(generation_worker, "build_initial_layout_guide", never_rebuild)
        monkeypatch.setattr(NexusImageProvider, "generate", generate)
        monkeypatch.setattr(generation_worker, "_download_image", download)
        await generation_worker.process_generation(generation_id, get_settings())
        result = (await client.get(f"/api/v1/generations/{generation_id}", headers=headers)).json()
        assert result["status"] == "completed", result
        assert len(calls) == 1
        assert "initial_layout_guide" not in result["quality_report"]


@pytest.mark.asyncio
async def test_guide_checkpoint_before_submission_intent_freezes_first_purchase(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generation_id, headers = await prepare(client)
        original = generation_worker._generate_checkpointed
        frozen = None
        calls = []

        async def interrupted(provider, current_id, **kwargs):
            nonlocal frozen
            if frozen is None:
                async with get_session_factory()() as db:
                    row = await db.get(Generation, current_id)
                    assert "provider_request" not in row.quality_report
                    frozen = copy.deepcopy(row.quality_report["initial_layout_guide"])
                raise asyncio.CancelledError()
            return await original(provider, current_id, **kwargs)

        async def generate(self, **kwargs):
            calls.append(kwargs)
            assert kwargs["task_id"] is None
            assert kwargs["model_name"] == frozen["primary_model"]
            assert kwargs["prompt"] == frozen["prompt"]
            assert kwargs["model_params"] == frozen["primary_params"]
            await kwargs["on_task_created"]("first-purchase")
            return NexusImageResult(
                task_id="first-purchase", image_url="https://cdn.example.test/result"
            )

        async def download(*args):
            return _png((160, 90), (30, 90, 20))

        monkeypatch.setattr(generation_worker, "_generate_checkpointed", interrupted)
        monkeypatch.setattr(NexusImageProvider, "generate", generate)
        monkeypatch.setattr(generation_worker, "_download_image", download)
        with pytest.raises(asyncio.CancelledError):
            await generation_worker.process_generation(generation_id, get_settings())
        path = LocalMediaStorage(get_settings()).absolute_path(frozen["path"])
        assert path.exists()
        async with get_session_factory()() as db:
            runtime = await db.get(GenerationRuntimeSettings, 1)
            runtime.primary_model = "changed-after-checkpoint"
            runtime.primary_params = {"changed": True}
            await db.commit()

        def never_rebuild(*args):
            pytest.fail("Committed guide must not be rebuilt before first POST either")

        monkeypatch.setattr(generation_worker, "build_initial_layout_guide", never_rebuild)
        await _recover_reserved(generation_id)
        await generation_worker.process_generation(generation_id, get_settings())
        result = (await client.get(f"/api/v1/generations/{generation_id}", headers=headers)).json()
        assert result["status"] == "completed", result
        assert len(calls) == 1
        assert not path.exists()


@pytest.mark.asyncio
async def test_accepted_guided_fallback_recovers_same_id_with_missing_reference(monkeypatch):
    from app.providers.nexus import NexusProviderError

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        generation_id, headers = await prepare(client)
        async with get_session_factory()() as db:
            runtime = await db.get(GenerationRuntimeSettings, 1)
            runtime.fallback_model = "original-guided-fallback"
            await db.commit()
        calls = []

        async def generate(self, **kwargs):
            calls.append(kwargs)
            if kwargs["model_name"] != "original-guided-fallback":
                assert kwargs["task_id"] is None
                await kwargs["on_task_created"]("primary-paid-task")
                raise NexusProviderError("confirmed terminal primary failure", retryable=True)
            if kwargs["task_id"] is None:
                await kwargs["on_task_created"]("fallback-paid-task")
                raise asyncio.CancelledError()
            assert kwargs["task_id"] == "fallback-paid-task"
            return NexusImageResult(
                task_id="fallback-paid-task", image_url="https://cdn.example.test/result"
            )

        async def download(*args):
            return _png((160, 90), (30, 90, 20))

        monkeypatch.setattr(NexusImageProvider, "generate", generate)
        monkeypatch.setattr(generation_worker, "_download_image", download)
        with pytest.raises(asyncio.CancelledError):
            await generation_worker.process_generation(generation_id, get_settings())
        async with get_session_factory()() as db:
            row = await db.get(Generation, generation_id)
            snapshot = row.quality_report["initial_layout_guide"]
            assert row.quality_report["provider_request"]["phase"] == "fallback"
            runtime = await db.get(GenerationRuntimeSettings, 1)
            runtime.primary_model = "replacement-primary"
            runtime.fallback_model = None
            runtime.fallback_params = {"changed": True}
            await db.commit()
        path = LocalMediaStorage(get_settings()).absolute_path(snapshot["path"])
        path.unlink()
        await _recover_reserved(generation_id)
        await generation_worker.process_generation(generation_id, get_settings())
        result = (await client.get(f"/api/v1/generations/{generation_id}", headers=headers)).json()
        assert result["status"] == "completed", result
        assert result["fallback_used"] is True
        assert [call["task_id"] for call in calls] == [None, None, "fallback-paid-task"]
        assert calls[-1]["model_name"] == calls[-2]["model_name"] == "original-guided-fallback"
        for key in ["model_params", "prompt", "reference_image_urls"]:
            assert calls[-1][key] == calls[-2][key]
        assert not path.exists()
        assert (await client.get("/api/v1/me", headers=headers)).json()["credits_balance"] == 3
