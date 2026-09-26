import os
from io import BytesIO
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "set RUN_INTEGRATION_TESTS=1 with a migrated test database",
        allow_module_level=True,
    )

from app.core.config import get_settings  # noqa: E402
from app.core.redis import redis_client  # noqa: E402
from app.db.models.assets import Asset  # noqa: E402
from app.db.models.generations import Generation  # noqa: E402
from app.db.models.users import AuthIdentity, User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.generations.enums import GenerationOrigin, GenerationStatus, GenerationType  # noqa: E402
from app.domain.users.enums import AuthProvider, UserRole  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.nexus import NexusImageProvider, NexusImageResult  # noqa: E402
from app.services.asset_service import LocalMediaStorage  # noqa: E402
from app.services.generation_service import GENERATION_QUEUE_KEY  # noqa: E402
from app.telegram_bot.generation_notifications import deliver_pending_generations_once  # noqa: E402
from app.workers import generation_worker  # noqa: E402


def _png(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def _register_user(
    client: AsyncClient, *, display_name: str = "Generation Pipeline User"
) -> tuple[dict, dict[str, str]]:
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"generation-pipeline-{uuid4()}@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": display_name,
        },
    )
    assert register.status_code == 201, register.text
    tokens = register.json()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


async def _register_admin(client: AsyncClient) -> tuple[dict, dict[str, str]]:
    tokens, headers = await _register_user(client, display_name="Generation Pipeline Admin")
    user_id = UUID(tokens["user"]["id"])
    async with get_session_factory()() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.role = UserRole.SUPERADMIN
        await session.commit()
    return tokens, headers


@pytest.mark.asyncio
async def test_generation_worker_completes_masked_pipeline_and_preserves_pixels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, admin_headers = await _register_admin(client)
        tokens, headers = await _register_user(client)
        user_id = tokens["user"]["id"]

        too_slow_runtime = await client.put(
            "/api/v1/admin/generation",
            headers=admin_headers,
            json={
                "primary_model": "integration-image-model",
                "fallback_model": None,
                "primary_timeout_seconds": get_settings().nexus_task_timeout_seconds + 1,
                "primary_params": {"steps": 12},
                "fallback_params": {},
                "mode_params": {},
            },
        )
        assert too_slow_runtime.status_code == 422, too_slow_runtime.text

        runtime = await client.put(
            "/api/v1/admin/generation",
            headers=admin_headers,
            json={
                "primary_model": "integration-image-model",
                "fallback_model": None,
                "primary_timeout_seconds": 45,
                "primary_params": {"steps": 12},
                "fallback_params": {},
                "mode_params": {},
            },
        )
        assert runtime.status_code == 200, runtime.text
        prompt = await client.put(
            "/api/v1/admin/prompts/master_plan",
            headers=admin_headers,
            json={"template": "Architectural render. {user_prompt}"},
        )
        assert prompt.status_code == 200, prompt.text
        price = await client.put(
            "/api/v1/admin/generation-prices/master_plan",
            headers=admin_headers,
            json={"credits": 2, "is_active": True},
        )
        assert price.status_code == 200, price.text
        credit = await client.post(
            f"/api/v1/admin/users/{user_id}/credits",
            headers=admin_headers,
            json={"delta": 5, "reason": "masked pipeline integration budget"},
        )
        assert credit.status_code == 200, credit.text

        project = await client.post(
            "/api/v1/projects",
            headers=headers,
            json={"name": "Masked generation pipeline", "context": {}},
        )
        assert project.status_code == 201, project.text
        project_id = project.json()["id"]

        base_data = _png((100, 100), (10, 20, 30))
        uploaded = await client.post(
            "/api/v1/assets",
            headers=headers,
            data={"purpose": "generation_input", "project_id": project_id},
            files={"file": ("base.png", base_data, "image/png")},
        )
        assert uploaded.status_code == 201, uploaded.text

        edit_region = {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8}
        protected_region = {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2}
        created = await client.post(
            "/api/v1/generations",
            headers=headers,
            json={
                "project_id": project_id,
                "input_asset_id": uploaded.json()["id"],
                "type": "master_plan",
                "prompt": "Add a bathhouse only in the editable area",
                "composition_mode": "masked_edit",
                "edit_region": edit_region,
                "protected_regions": [protected_region],
            },
        )
        assert created.status_code == 202, created.text
        generation_id = UUID(created.json()["id"])

        candidate_data = _png((100, 100), (220, 210, 200))
        provider_calls: list[dict] = []
        provider_guides: list[bytes] = []

        async def fake_generate(self, **kwargs):  # noqa: ANN001, ARG001
            provider_calls.append(kwargs)
            for guide_url in kwargs.get("reference_image_urls") or []:
                parsed = urlsplit(guide_url)
                guide_response = await client.get(
                    f"{parsed.path}?{parsed.query}"
                )
                assert guide_response.status_code == 200, guide_response.text
                provider_guides.append(guide_response.content)
            return NexusImageResult(
                task_id="integration-task",
                image_url="https://cdn.example.test/generated.png",
            )

        async def fake_download(url, settings):  # noqa: ANN001, ARG001
            assert url == "https://cdn.example.test/generated.png"
            return candidate_data

        monkeypatch.setattr(NexusImageProvider, "generate", fake_generate)
        monkeypatch.setattr(generation_worker, "_download_image", fake_download)
        await generation_worker.process_generation(generation_id, get_settings())
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))

        completed = await client.get(f"/api/v1/generations/{generation_id}", headers=headers)
        assert completed.status_code == 200, completed.text
        body = completed.json()
        assert body["status"] == "completed"
        assert body["output_asset"]["mime_type"] == "image/png"
        assert body["composition_mode"] == "masked_edit"
        assert provider_calls
        provider_url = provider_calls[0]["image_url"]
        assert provider_url is not None
        assert urlsplit(provider_url).path == urlsplit(uploaded.json()["url"]).path
        signed_media = await client.get(f"{urlsplit(provider_url).path}?{urlsplit(provider_url).query}")
        assert signed_media.status_code == 200, signed_media.text
        assert signed_media.content == base_data
        assert "Add a bathhouse only in the editable area" in provider_calls[0]["prompt"]
        assert "pixel-aligned binary edit guide" in provider_calls[0]["prompt"]
        assert provider_calls[0]["timeout_seconds"] == 45
        guide_urls = provider_calls[0].get("reference_image_urls")
        assert guide_urls is not None and len(guide_urls) == 1
        assert len(provider_guides) == 1
        with Image.open(BytesIO(provider_guides[0])) as opened_guide:
            guide = opened_guide.convert("RGB")
            assert guide.size == (100, 100)
            assert guide.getpixel((5, 5)) == (0, 0, 0)
            assert guide.getpixel((20, 20)) == (255, 255, 255)
            assert guide.getpixel((50, 50)) == (0, 0, 0)
        guide_parts = urlsplit(guide_urls[0])
        cleaned_guide = await client.get(f"{guide_parts.path}?{guide_parts.query}")
        assert cleaned_guide.status_code == 404

        async with get_session_factory()() as session:
            generation = await session.get(Generation, generation_id)
            assert generation is not None and generation.output_asset_id is not None
            output = await session.get(Asset, generation.output_asset_id)
            assert output is not None
            output_path = LocalMediaStorage(get_settings()).absolute_path(output.storage_path)
        with Image.open(output_path) as image:
            result = image.convert("RGB")
            assert result.getpixel((5, 5)) == (10, 20, 30)
            assert result.getpixel((50, 50)) == (10, 20, 30)
            assert result.getpixel((20, 20)) == (220, 210, 200)

        me = await client.get("/api/v1/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["credits_balance"] == 3

        async with get_session_factory()() as session:
            session.add(
                AuthIdentity(
                    user_id=UUID(user_id),
                    provider=AuthProvider.TELEGRAM,
                    provider_user_id="900000001",
                )
            )
            await session.commit()

        class FakeTelegramApi:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def send_document_file(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return {"message_id": 1}

        telegram = FakeTelegramApi()
        sent, failed = await deliver_pending_generations_once(
            api=telegram,  # type: ignore[arg-type]
            webapp_url="https://app.example.test/",
        )
        assert sent == 1
        assert failed == 0
        assert len(telegram.calls) == 1
        telegram_payload = telegram.calls[0]
        assert telegram_payload["chat_id"] == "900000001"
        assert telegram_payload["path"] == output_path
        assert telegram_payload["path"].read_bytes() == output_path.read_bytes()
        assert "Add a bathhouse only in the editable area" not in telegram_payload["caption"]
        keyboard = telegram_payload["reply_markup"]["inline_keyboard"]
        assert f"project={project_id}" in keyboard[0][0]["web_app"]["url"]
        assert f"generation={generation_id}" in keyboard[1][0]["web_app"]["url"]

        async with get_session_factory()() as session:
            generation = await session.get(Generation, generation_id)
            assert generation is not None
            assert generation.telegram_delivery_status == "sent"
            assert generation.telegram_delivery_attempts == 1
            assert generation.telegram_notified_at is not None

            # Simulate a process crash after Telegram accepted the document but before
            # AuRoom committed the final "sent" state. Delivery is intentionally
            # at-least-once: the next maintenance pass retries instead of losing it.
            generation.telegram_delivery_status = "sending"
            generation.telegram_notified_at = None
            await session.commit()

        retried_sent, retried_failed = await deliver_pending_generations_once(
            api=telegram,  # type: ignore[arg-type]
            webapp_url="https://app.example.test/",
        )
        assert retried_sent == 1
        assert retried_failed == 0
        assert len(telegram.calls) == 2

        async with get_session_factory()() as session:
            generation = await session.get(Generation, generation_id)
            assert generation is not None
            assert generation.telegram_delivery_status == "sent"
            assert generation.telegram_delivery_attempts == 2
            assert generation.telegram_notified_at is not None

@pytest.mark.asyncio
async def test_public_reserved_prompt_is_rejected_and_internal_questionnaire_origin_bypasses_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, admin_headers = await _register_admin(client)
        tokens, headers = await _register_admin(client)
        await client.put(
            "/api/v1/admin/generation",
            headers=admin_headers,
            json={
                "primary_model": "integration-image-model",
                "fallback_model": None,
                "primary_params": {},
                "fallback_params": {},
                "mode_params": {"master_plan": {"aspect_ratio": "1:1"}},
            },
        )
        await client.put(
            "/api/v1/admin/prompts/master_plan",
            headers=admin_headers,
            json={"template": "LEGACY MASTER PLAN TEMPLATE {user_prompt}"},
        )
        await client.put(
            "/api/v1/admin/generation-prices/master_plan",
            headers=admin_headers,
            json={"credits": 1, "is_active": True},
        )
        project = await client.post(
            "/api/v1/projects", headers=headers, json={"name": "Structured render", "context": {}}
        )
        project_id = project.json()["id"]
        source = _png((160, 90), (20, 30, 40))
        uploaded = await client.post(
            "/api/v1/assets",
            headers=headers,
            data={"purpose": "generation_input", "project_id": project_id},
            files={"file": ("wide.png", source, "image/png")},
        )
        structured = 'AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:{"task":"test"}'
        created = await client.post(
            "/api/v1/generations",
            headers=headers,
            json={
                "project_id": project_id,
                "input_asset_id": uploaded.json()["id"],
                "type": "master_plan",
                "prompt": structured,
            },
        )
        assert created.status_code == 422, created.text
        assert created.json()["type"] == "reserved_generation_prompt"

        generation_id = uuid4()
        async with get_session_factory()() as session:
            session.add(
                Generation(
                    id=generation_id,
                    user_id=UUID(tokens["user"]["id"]),
                    project_id=UUID(project_id),
                    input_asset_id=UUID(uploaded.json()["id"]),
                    type=GenerationType.MASTER_PLAN,
                    status=GenerationStatus.QUEUED,
                    origin=GenerationOrigin.QUESTIONNAIRE.value,
                    prompt=structured,
                    credits_charged=0,
                )
            )
            await session.commit()

        calls: list[dict] = []

        async def fake_generate(self, **kwargs):  # noqa: ANN001, ARG001
            calls.append(kwargs)
            return NexusImageResult(task_id="structured-task", image_url="https://cdn.example.test/out.png")

        async def fake_download(url, settings):  # noqa: ANN001, ARG001
            return _png((160, 90), (90, 100, 110))

        monkeypatch.setattr(NexusImageProvider, "generate", fake_generate)
        monkeypatch.setattr(generation_worker, "_download_image", fake_download)
        await generation_worker.process_generation(generation_id, get_settings())
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))
        assert len(calls) == 1
        assert calls[0]["prompt"] == structured
        assert "LEGACY MASTER PLAN TEMPLATE" not in calls[0]["prompt"]
        assert calls[0]["model_params"]["aspect_ratio"] == "16:9"



async def _configure_strict_masked_quality(
    client: AsyncClient,
    admin_headers: dict[str, str],
    *,
    retries: int = 1,
) -> None:
    response = await client.put(
        "/api/v1/admin/generation",
        headers=admin_headers,
        json={
            "primary_model": "quality-model",
            "fallback_model": None,
            "primary_timeout_seconds": 45,
            "primary_params": {},
            "fallback_params": {},
            "mode_params": {},
            "masked_edit_provider_context_margin_fraction": 0.05,
            "masked_edit_feather_fraction": 0.0,
            "masked_edit_feather_min_px": 0,
            "masked_edit_feather_max_px": 8,
            "masked_edit_recomposite_feather_multiplier": 2.0,
            "masked_edit_boundary_band_px": 2,
            "masked_edit_max_luma_excess": 1.0,
            "masked_edit_max_color_excess": 1.0,
            "masked_edit_max_straight_edge_fraction": 0.1,
            "generation_quality_max_retries": retries,
        },
    )
    assert response.status_code == 200, response.text


async def _create_strict_masked_generation(
    client: AsyncClient,
    *,
    admin_headers: dict[str, str],
    headers: dict[str, str],
    user_id: str,
) -> tuple[UUID, bytes, dict]:
    await _configure_strict_masked_quality(client, admin_headers)
    price = await client.put(
        "/api/v1/admin/generation-prices/master_plan",
        headers=admin_headers,
        json={"credits": 2, "is_active": True},
    )
    assert price.status_code == 200, price.text
    credit = await client.post(
        f"/api/v1/admin/users/{user_id}/credits",
        headers=admin_headers,
        json={"delta": 5, "reason": "strict masked quality integration budget"},
    )
    assert credit.status_code == 200, credit.text

    project = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Strict masked quality", "context": {}},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    base_data = _png((120, 120), (30, 30, 30))
    uploaded = await client.post(
        "/api/v1/assets",
        headers=headers,
        data={"purpose": "generation_input", "project_id": project_id},
        files={"file": ("base.png", base_data, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    edit_region = {"x": 0.3, "y": 0.3, "width": 0.4, "height": 0.4}
    created = await client.post(
        "/api/v1/generations",
        headers=headers,
        json={
            "project_id": project_id,
            "input_asset_id": uploaded.json()["id"],
            "type": "master_plan",
            "prompt": "temporary public envelope",
            "composition_mode": "masked_edit",
            "edit_region": edit_region,
            "protected_regions": [],
        },
    )
    assert created.status_code == 202, created.text
    generation_id = UUID(created.json()["id"])
    async with get_session_factory()() as session:
        generation = await session.get(Generation, generation_id)
        assert generation is not None
        generation.origin = GenerationOrigin.QUESTIONNAIRE.value
        generation.prompt = "AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:{\"task\":\"quality-test\"}"
        generation.edit_policy = {
            "version": "exterior-edit-policy.v1",
            "domain": "exterior",
            "intent": "facade_finish",
            "quality_checks": ["outside_region_integrity", "boundary_continuity"],
        }
        generation.quality_status = "pending"
        await session.commit()
    return generation_id, base_data, edit_region


@pytest.mark.asyncio
async def test_questionnaire_masked_quality_retry_reuses_one_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, admin_headers = await _register_admin(client)
        tokens, headers = await _register_user(client)
        generation_id, base_data, edit_region = await _create_strict_masked_generation(
            client,
            admin_headers=admin_headers,
            headers=headers,
            user_id=tokens["user"]["id"],
        )
        calls: list[dict] = []
        guides: list[bytes] = []

        async def fake_generate(self, **kwargs):  # noqa: ANN001, ARG001
            calls.append(kwargs)
            for guide_url in kwargs.get("reference_image_urls") or []:
                parts = urlsplit(guide_url)
                response = await client.get(f"{parts.path}?{parts.query}")
                assert response.status_code == 200, response.text
                guides.append(response.content)
            return NexusImageResult(
                task_id=f"quality-task-{len(calls)}",
                image_url=f"https://cdn.example.test/quality-{len(calls)}.png",
            )

        async def fake_download(url, settings):  # noqa: ANN001, ARG001
            if url.endswith("quality-1.png"):
                return _png((120, 120), (230, 230, 230))
            return base_data

        monkeypatch.setattr(NexusImageProvider, "generate", fake_generate)
        monkeypatch.setattr(generation_worker, "_download_image", fake_download)

        await generation_worker.process_generation(generation_id, get_settings())
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))

        assert len(calls) == 2
        assert calls[0]["idempotency_key"] == f"auroom-{generation_id}-primary"
        assert calls[1]["idempotency_key"] == f"auroom-{generation_id}-quality-1-primary"
        assert "PREVIOUS CANDIDATE REJECTED" in calls[1]["prompt"]
        assert len(guides) == 2
        with Image.open(BytesIO(guides[0])) as opened:
            guide = opened.convert("RGB")
            assert guide.getpixel((20, 60)) == (0, 0, 0)
            assert guide.getpixel((32, 60)) == (0, 0, 0)
            assert guide.getpixel((40, 60)) == (255, 255, 255)

        completed = await client.get(f"/api/v1/generations/{generation_id}", headers=headers)
        assert completed.status_code == 200, completed.text
        body = completed.json()
        assert body["status"] == "completed"
        assert body["quality_status"] == "passed"
        assert body["quality_report"]["final"] == "passed"
        assert body["quality_report"]["enforced_checks"] == [
            "outside_region_integrity",
            "boundary_continuity",
        ]
        assert body["quality_report"]["deferred_checks"] == []
        assert body["quality_report"]["scene_analysis"] == "not_required"
        assert len(body["quality_report"]["attempts"]) == 2
        assert body["quality_report"]["provider_work_region"] == {
            "x": 0.25,
            "y": 0.25,
            "width": 0.5,
            "height": 0.5,
        }
        assert body["edit_region"] == edit_region
        me = await client.get("/api/v1/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["credits_balance"] == 3


@pytest.mark.asyncio
async def test_questionnaire_masked_quality_rejection_refunds_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, admin_headers = await _register_admin(client)
        tokens, headers = await _register_user(client)
        generation_id, _, _ = await _create_strict_masked_generation(
            client,
            admin_headers=admin_headers,
            headers=headers,
            user_id=tokens["user"]["id"],
        )
        calls: list[dict] = []

        async def fake_generate(self, **kwargs):  # noqa: ANN001, ARG001
            calls.append(kwargs)
            return NexusImageResult(
                task_id=f"reject-task-{len(calls)}",
                image_url=f"https://cdn.example.test/reject-{len(calls)}.png",
            )

        async def fake_download(url, settings):  # noqa: ANN001, ARG001
            return _png((120, 120), (240, 240, 240))

        monkeypatch.setattr(NexusImageProvider, "generate", fake_generate)
        monkeypatch.setattr(generation_worker, "_download_image", fake_download)

        await generation_worker.process_generation(generation_id, get_settings())
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))

        assert len(calls) == 2
        failed = await client.get(f"/api/v1/generations/{generation_id}", headers=headers)
        assert failed.status_code == 200, failed.text
        body = failed.json()
        assert body["status"] == "failed"
        assert body["output_asset"] is None
        assert body["quality_status"] == "rejected"
        assert body["quality_report"]["final"] == "rejected"
        assert len(body["quality_report"]["attempts"]) == 2
        assert "Не удалось аккуратно выполнить" in body["error"]

        me = await client.get("/api/v1/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["credits_balance"] == 5

        await generation_worker._mark_failed_and_refund(
            generation_id,
            "duplicate terminal handling",
        )
        me_again = await client.get("/api/v1/me", headers=headers)
        assert me_again.status_code == 200
        assert me_again.json()["credits_balance"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize('acknowledged', [True, False])
async def test_worker_restart_never_reposts_an_existing_or_ambiguous_request(monkeypatch, acknowledged):
    import asyncio
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        _, admin_headers = await _register_admin(client)
        tokens, headers = await _register_user(client)
        user_id = tokens['user']['id']
        generation_id, base_data, _ = await _create_strict_masked_generation(
            client, admin_headers=admin_headers, headers=headers, user_id=user_id,
        )
        calls = []
        async def generate(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                assert kwargs['task_id'] is None
                if acknowledged:
                    await kwargs['on_task_created']('durable-task')
                raise asyncio.CancelledError()
            assert kwargs['task_id'] == 'durable-task'
            return NexusImageResult(task_id='durable-task',image_url='https://cdn.example.test/recovered.png')
        async def download(url, settings):
            return base_data
        monkeypatch.setattr(NexusImageProvider, 'generate', generate)
        monkeypatch.setattr(generation_worker, '_download_image', download)
        with pytest.raises(asyncio.CancelledError):
            await generation_worker.process_generation(generation_id, get_settings())
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))
        await redis_client.rpush(generation_worker.GENERATION_PROCESSING_KEY, str(generation_id))
        await generation_worker._recover_reserved_jobs()
        await generation_worker.process_generation(generation_id, get_settings())
        await generation_worker.process_generation(generation_id, get_settings())
        result = (await client.get(f'/api/v1/generations/{generation_id}', headers=headers)).json()
        assert result['status'] == ('completed' if acknowledged else 'processing')
        assert len(calls) == (2 if acknowledged else 1)
        assert sum(c['task_id'] is None for c in calls) == 1
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_stage', ['poll', 'download'])
async def test_unknown_provider_status_keeps_charge_and_reconciles_same_task(monkeypatch, failure_stage):
    from datetime import UTC, datetime, timedelta
    from app.providers.nexus import NexusOutcomeUnknown
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        _, admin_headers = await _register_admin(client)
        tokens, headers = await _register_user(client)
        generation_id, base_data, _ = await _create_strict_masked_generation(
            client, admin_headers=admin_headers, headers=headers, user_id=tokens['user']['id'])
        calls = []
        async def generate(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                await kwargs['on_task_created']('slow-confirmed-task')
                if failure_stage == 'poll':
                    raise NexusOutcomeUnknown('Temporary polling outage')
            else:
                assert kwargs['task_id'] == 'slow-confirmed-task'
            return NexusImageResult(task_id='slow-confirmed-task', image_url='https://cdn.example.test/result.png')
        async def download(url, settings):
            if len(calls) == 1 and failure_stage == 'download':
                from httpx import ReadTimeout
                raise ReadTimeout('transient media outage')
            return base_data
        monkeypatch.setattr(NexusImageProvider, 'generate', generate)
        monkeypatch.setattr(generation_worker, '_download_image', download)
        await generation_worker.process_generation(generation_id, get_settings())
        pending = (await client.get(f'/api/v1/generations/{generation_id}', headers=headers)).json()
        assert pending['status'] == 'processing'
        assert pending['quality_report']['requires_reconciliation'] is True
        assert (await client.get('/api/v1/me', headers=headers)).json()['credits_balance'] == 3
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))
        async with get_session_factory()() as session:
            row = await session.get(Generation, generation_id)
            row.started_at = datetime.now(UTC) - timedelta(hours=1)
            await session.commit()
        await generation_worker._reconcile_database_jobs(get_settings())
        await generation_worker.process_generation(generation_id, get_settings())
        result = (await client.get(f'/api/v1/generations/{generation_id}', headers=headers)).json()
        assert result['status'] == 'completed'
        assert not result['quality_report'].get('requires_reconciliation')
        assert len(calls) == 2
        assert sum(call['task_id'] is None for call in calls) == 1
        assert (await client.get('/api/v1/me', headers=headers)).json()['credits_balance'] == 3
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))


@pytest.mark.asyncio
async def test_accepted_task_checkpoint_commit_failure_does_not_refund_or_repost(monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        _, admin_headers = await _register_admin(client)
        tokens, headers = await _register_user(client)
        generation_id, _, _ = await _create_strict_masked_generation(
            client, admin_headers=admin_headers, headers=headers, user_id=tokens['user']['id'])
        original_commit = AsyncSession.commit
        injected = False
        async def commit(session):
            nonlocal injected
            if not injected and any(isinstance(row, Generation) and row.provider_task_id == 'accepted-before-db-outage' for row in session.dirty):
                injected = True
                raise RuntimeError('database connection interrupted before checkpoint commit')
            return await original_commit(session)
        calls = []
        async def generate(self, **kwargs):
            calls.append(kwargs)
            await kwargs['on_task_created']('accepted-before-db-outage')
            pytest.fail('checkpoint failure must stop polling without resubmission')
        monkeypatch.setattr(AsyncSession, 'commit', commit)
        monkeypatch.setattr(NexusImageProvider, 'generate', generate)
        await generation_worker.process_generation(generation_id, get_settings())
        result = (await client.get(f'/api/v1/generations/{generation_id}', headers=headers)).json()
        assert injected
        assert result['status'] == 'processing'
        assert result['quality_report']['requires_reconciliation'] is True
        assert result['quality_report']['provider_request']['task_id'] is None
        assert (await client.get('/api/v1/me', headers=headers)).json()['credits_balance'] == 3
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))
        await generation_worker._reconcile_database_jobs(get_settings())
        await generation_worker.process_generation(generation_id, get_settings())
        assert len(calls) == 1
