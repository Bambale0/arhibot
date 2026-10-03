from copy import deepcopy
from datetime import UTC, datetime
from json import loads
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.api.v1.admin import router
from app.core.config import get_settings
from app.core.errors import AppError, install_exception_handlers
from app.db.models.admin import AdminAuditLog, GenerationRuntimeSettings
from app.db.models.projects import Project
from app.db.session import get_db_session
from app.domain.generations.enums import GenerationOrigin, GenerationStatus
from app.domain.users.enums import UserRole
from app.schemas.admin import (
    AdminAiFlyoverGifCreate,
    AdminAiOrbitCreate,
    AdminAiSandboxCreate,
    GenerationRuntimeUpdate,
)
from app.services import admin_service
from app.services.admin_service import AdminService


def _service(primary_provider="nexus", fallback_provider="nexus"):
    row = GenerationRuntimeSettings(
        id=1,
        primary_provider=primary_provider,
        fallback_provider=fallback_provider,
        primary_model="old-primary",
        fallback_model="old-fallback",
        primary_timeout_seconds=90,
        primary_params={},
        fallback_params={},
        mode_params={},
        masked_edit_provider_context_margin_fraction=0.03,
        masked_edit_feather_fraction=0.014,
        masked_edit_feather_min_px=4,
        masked_edit_feather_max_px=24,
        masked_edit_recomposite_feather_multiplier=1.75,
        masked_edit_boundary_band_px=4,
        masked_edit_max_luma_excess=20,
        masked_edit_max_color_excess=32,
        masked_edit_max_straight_edge_fraction=0.65,
        generation_quality_max_retries=1,
        updated_at=datetime.now(UTC),
    )
    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.scalar_one_or_none.return_value = row
    session.execute.return_value = result
    settings = SimpleNamespace(
        nexus_task_timeout_seconds=180,
        neironych_request_timeout_seconds=300,
    )
    return AdminService(session, settings), row, session


@pytest.mark.asyncio
async def test_runtime_response_returns_saved_providers() -> None:
    service, _, _ = _service(primary_provider="neironych")
    response = await service.get_generation_settings()
    assert response.primary_provider == "neironych"
    assert response.fallback_provider == "nexus"


@pytest.mark.asyncio
async def test_runtime_update_persists_provider_choices_and_audits_actor() -> None:
    service, row, session = _service()
    actor = SimpleNamespace(id=uuid4())
    response = await service.update_generation_settings(
        actor,
        GenerationRuntimeUpdate(
            primary_provider="neironych",
            fallback_provider="neironych",
            primary_model="new-primary",
            fallback_model="new-fallback",
        ),
    )
    assert row.primary_provider == response.primary_provider == "neironych"
    assert row.fallback_provider == response.fallback_provider == "neironych"
    assert row.updated_by_user_id == actor.id
    audit = next(
        call.args[0] for call in session.add.call_args_list
        if isinstance(call.args[0], AdminAuditLog)
    )
    assert audit.actor_user_id == actor.id
    assert audit.action == "generation.settings.update"
    assert audit.details["primary_provider"] == "neironych"
    assert audit.details["fallback_provider"] == "neironych"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_runtime_update_preserves_saved_providers() -> None:
    service, row, _ = _service(primary_provider="neironych", fallback_provider="neironych")
    response = await service.update_generation_settings(
        SimpleNamespace(id=uuid4()),
        GenerationRuntimeUpdate(primary_model="new-primary"),
    )
    assert response.primary_provider == row.primary_provider == "neironych"
    assert response.fallback_provider == row.fallback_provider == "neironych"


@pytest.mark.asyncio
async def test_runtime_update_checks_selected_provider_timeout() -> None:
    service, row, _ = _service()
    response = await service.update_generation_settings(
        SimpleNamespace(id=uuid4()),
        GenerationRuntimeUpdate(
            primary_provider="neironych", primary_model="image-model", primary_timeout_seconds=240
        ),
    )
    assert response.primary_timeout_seconds == row.primary_timeout_seconds == 240


@pytest.mark.asyncio
@pytest.mark.parametrize("provider, timeout", [("nexus", 181), ("neironych", 301)])
async def test_runtime_update_rejects_provider_timeout_without_mutating_settings(provider, timeout):
    service, row, session = _service()
    with pytest.raises(AppError) as error:
        await service.update_generation_settings(
            SimpleNamespace(id=uuid4()),
            GenerationRuntimeUpdate(
                primary_provider=provider,
                primary_model="image-model",
                primary_timeout_seconds=timeout,
            ),
        )
    assert error.value.status == 422
    assert error.value.type == "generation_primary_timeout_too_large"
    assert row.primary_provider == "nexus"
    assert row.primary_model == "old-primary"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_update_keeps_parameter_objects_independent() -> None:
    service, row, _ = _service()
    payload = GenerationRuntimeUpdate(
        primary_model="image-model",
        primary_params={"metadata": {"source": "admin"}},
        fallback_params={"metadata": {"source": "fallback"}},
        mode_params={"master_plan": {"metadata": {"source": "mode"}}},
    )
    original = deepcopy(payload.model_dump())
    await service.update_generation_settings(SimpleNamespace(id=uuid4()), payload)
    row.primary_params["metadata"]["source"] = "changed"
    row.fallback_params["metadata"]["source"] = "changed"
    row.mode_params["master_plan"]["metadata"]["source"] = "changed"
    assert payload.model_dump() == original


def _api(role: UserRole | None):
    service, row, session = _service()
    app = FastAPI()
    install_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: service.settings
    if role is not None:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4(), role=role)
    return app, row, session


@pytest.mark.asyncio
@pytest.mark.parametrize("role, status", [(None, 401), (UserRole.USER, 403)])
@pytest.mark.parametrize("method", ["GET", "PUT"])
async def test_provider_routing_admin_api_denies_unauthorized_access(role, status, method):
    app, row, session = _api(role)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(
            method,
            "/api/v1/admin/generation",
            json={"primary_model": "image-model", "primary_provider": "neironych"},
        )
    assert response.status_code == status
    assert row.primary_provider == "nexus"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPERADMIN])
async def test_provider_routing_admin_api_reads_and_updates_routing(role):
    app, row, _ = _api(role)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        original = await client.get("/api/v1/admin/generation")
        assert original.status_code == 200
        assert original.json()["primary_provider"] == "nexus"
        updated = await client.put(
            "/api/v1/admin/generation",
            json={
                "primary_provider": "neironych",
                "fallback_provider": "nexus",
                "primary_model": "image-model",
                "fallback_model": "legacy-image-model",
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["primary_provider"] == "neironych"
        assert updated.json()["fallback_provider"] == "nexus"
        saved = await client.get("/api/v1/admin/generation")
        assert saved.status_code == 200
        assert saved.json()["primary_provider"] == "neironych"
        assert row.primary_provider == "neironych"


@pytest.mark.asyncio
async def test_provider_routing_api_rejects_unknown_provider_before_commit():
    app, row, session = _api(UserRole.ADMIN)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(
            "/api/v1/admin/generation",
            json={"primary_model": "image-model", "primary_provider": "unknown"},
        )
    assert response.status_code == 422
    assert row.primary_provider == "nexus"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["nexus", "neironych", None])
@pytest.mark.parametrize(
    "method, schema, prefix",
    [
        (
            "create_ai_sandbox_generation",
            AdminAiSandboxCreate,
            admin_service.ADMIN_SANDBOX_PROMPT_PREFIX,
        ),
        (
            "create_ai_orbit_generation",
            AdminAiOrbitCreate,
            admin_service.ADMIN_ORBIT_PROMPT_PREFIX,
        ),
        (
            "create_ai_flyover_gif_generation",
            AdminAiFlyoverGifCreate,
            admin_service.ADMIN_FLYOVER_GIF_PROMPT_PREFIX,
        ),
    ],
)
async def test_admin_ai_creation_snapshots_provider_in_envelope_and_audit(
    monkeypatch, provider, method, schema, prefix
):
    service, _, session = _service(primary_provider=provider or "neironych")
    if provider is None:
        session.execute.return_value.scalar_one_or_none.return_value = None
    actor = SimpleNamespace(id=uuid4())
    project = Project(id=uuid4(), user_id=actor.id, context={"admin_ai_sandbox": True})
    service.projects.get_admin_ai_sandbox = AsyncMock(return_value=project)
    session.get.return_value = project
    source = SimpleNamespace(
        id=uuid4(),
        project_id=project.id,
        status=GenerationStatus.COMPLETED,
        output_asset_id=uuid4(),
        origin=GenerationOrigin.ADMIN_SANDBOX.value,
    )
    monkeypatch.setattr(
        admin_service, "GenerationRepository",
        lambda _: SimpleNamespace(get_owned=AsyncMock(return_value=source)),
    )
    create = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(
        admin_service, "build_generation_service",
        lambda *_: SimpleNamespace(create=create),
    )
    payload = schema(
        model_name="selected-image-model",
        prompt="A modern house",
        source_generation_id=source.id,
        params={"quality": "medium"},
    )

    await getattr(service, method)(actor, payload)

    envelope = create.call_args.args[1].prompt
    assert envelope.startswith(prefix)
    snapshot = loads(envelope.removeprefix(prefix))
    assert snapshot["provider"] == (provider or "neironych")
    assert snapshot["prompt"] == "A modern house"
    assert snapshot["params"] == {"quality": "medium"}
    audit = next(
        call.args[0] for call in session.add.call_args_list
        if isinstance(call.args[0], AdminAuditLog)
    )
    assert audit.details["provider"] == (provider or "neironych")
