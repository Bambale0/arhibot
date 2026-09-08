import io
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True
    )

from app.core.config import get_settings  # noqa: E402
from app.db.models.architecture_renders import ArchitectureRender  # noqa: E402
from app.db.models.assets import Asset  # noqa: E402
from app.db.models.users import User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.architecture.enums import ArchitectureRenderStatus  # noqa: E402
from app.domain.assets.enums import AssetPurpose  # noqa: E402
from app.domain.users.enums import UserRole  # noqa: E402
from app.main import app  # noqa: E402
from app.services.architecture_render_publication_service import (  # noqa: E402
    ArchitectureRenderPublicationService,
)


def _architecture_payload(primary_material: str = "wood") -> dict:
    return {
        "schema_version": "1.0",
        "program": {"living_area_sqm": 140, "storeys": 1, "bedrooms": 3, "bathrooms": 2},
        "appearance": {
            "architecture_style": "modern",
            "primary_material": primary_material,
            "accent_materials": ["stone"],
        },
        "geometry": {
            "levels": [
                {
                    "id": "ground",
                    "label": "1 этаж",
                    "z": 0,
                    "height": 3.2,
                    "footprint": {
                        "points": [
                            {"x": 0, "y": 0},
                            {"x": 12, "y": 0},
                            {"x": 12, "y": 9},
                            {"x": 0, "y": 9},
                        ]
                    },
                    "rooms": [],
                }
            ],
            "external_objects": [],
            "roof": {
                "type": "gable",
                "eave_z": 3.2,
                "ridge_z": 5.8,
                "ridge_start": {"x": 6, "y": 0},
                "ridge_end": {"x": 6, "y": 9},
                "overhang_m": 0.45,
            },
        },
    }


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (160, 120), color).save(buffer, format="PNG")
    return buffer.getvalue()


async def _register_admin(client: AsyncClient) -> tuple[dict[str, str], UUID]:
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"render-publish-{uuid4()}@example.com",
            "password": "integration-test-password-123",
            "display_name": "Render Publisher",
        },
    )
    assert register.status_code == 201, register.text
    user_id = UUID(register.json()["user"]["id"])
    async with get_session_factory()() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.role = UserRole.SUPERADMIN
        await session.commit()
    return {"Authorization": f"Bearer {register.json()['access_token']}"}, user_id


async def _upload_project_image(
    client: AsyncClient,
    headers: dict[str, str],
    project_id: str,
    name: str,
    color: tuple[int, int, int],
) -> str:
    response = await client.post(
        "/api/v1/assets",
        headers=headers,
        data={"purpose": "project_reference", "project_id": project_id},
        files={"file": (name, _png_bytes(color), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _complete_batch(
    batch_payload: dict,
    asset_ids: list[str],
    qualities: list[tuple[float, bool]],
) -> None:
    async with get_session_factory()() as session:
        for render_payload, asset_id, (score, usable) in zip(
            batch_payload["renders"], asset_ids, qualities, strict=True
        ):
            render = await session.get(ArchitectureRender, UUID(render_payload["id"]))
            asset = await session.get(Asset, UUID(asset_id))
            assert render is not None
            assert asset is not None
            asset.purpose = AssetPurpose.ARCHITECTURE_RENDER_OUTPUT
            render.status = ArchitectureRenderStatus.COMPLETED
            render.renderer_version = "Blender integration-test"
            render.storage_path = asset.storage_path
            render.output_asset_id = asset.id
            render.width = asset.width
            render.height = asset.height
            render.quality_score = score
            render.quality_report = {"technically_usable": usable}
            render.completed_at = datetime.now(UTC)
        await session.commit()


@pytest.mark.asyncio
async def test_render_batch_publishes_winner_and_rejects_stale_architecture() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers, _user_id = await _register_admin(client)
        project = await client.post(
            "/api/v1/projects",
            headers=headers,
            json={
                "name": "Automatic hero source",
                "context": {"architecture": _architecture_payload()},
            },
        )
        assert project.status_code == 201, project.text
        project_id = project.json()["id"]

        hero_id = await _upload_project_image(
            client, headers, project_id, "initial.png", (120, 120, 120)
        )
        render_asset_ids = [
            await _upload_project_image(client, headers, project_id, "hero.png", (150, 130, 110)),
            await _upload_project_image(client, headers, project_id, "reverse.png", (105, 115, 125)),
            await _upload_project_image(client, headers, project_id, "elevated.png", (165, 150, 135)),
        ]

        idea = await client.post(
            "/api/v1/admin/ideas",
            headers=headers,
            json={
                "title": "Автоматический архитектурный hero",
                "category": "Фасад",
                "text": "Публикация из canonical geometry.",
                "generation_type": "facade",
                "prompt": "",
                "image_asset_id": hero_id,
                "architecture_project_id": project_id,
                "media": [],
                "is_active": True,
                "sort_order": -50,
            },
        )
        assert idea.status_code == 201, idea.text
        idea_id = idea.json()["id"]

        queued = await client.post(
            f"/api/v1/admin/ideas/{idea_id}/architecture-render-batches",
            headers=headers,
        )
        assert queued.status_code == 202, queued.text
        batch = queued.json()
        assert batch["target_idea_id"] == idea_id
        assert [item["camera_profile"] for item in batch["renders"]] == [
            "hero_corner",
            "reverse_corner",
            "elevated",
        ]

        await _complete_batch(
            batch,
            render_asset_ids,
            [(0.70, True), (0.95, False), (0.80, True)],
        )
        async with get_session_factory()() as session:
            publication = await ArchitectureRenderPublicationService(
                session, get_settings()
            ).finalize(UUID(batch["batch_id"]))
        assert publication.published is True
        assert publication.winner_render_id == UUID(batch["renders"][2]["id"])

        batch_status = await client.get(
            f"/api/v1/admin/ideas/{idea_id}/architecture-render-batches/{batch['batch_id']}",
            headers=headers,
        )
        assert batch_status.status_code == 200, batch_status.text
        assert batch_status.json()["selected_render_id"] == batch["renders"][2]["id"]
        assert batch_status.json()["renders"][2]["selected_for_batch"] is True

        ideas = await client.get("/api/v1/admin/ideas", headers=headers)
        assert ideas.status_code == 200, ideas.text
        published = next(item for item in ideas.json() if item["id"] == idea_id)
        assert published["image_asset_id"] == render_asset_ids[2]
        assert published["model_url"].endswith(".glb")
        assert published["model_original_filename"] == f"architecture-{batch['batch_id']}.glb"
        assert published["architecture"]["appearance"]["primary_material"] == "wood"
        published_model_url = published["model_url"]

        stale = await client.post(
            f"/api/v1/admin/ideas/{idea_id}/architecture-render-batches",
            headers=headers,
        )
        assert stale.status_code == 202, stale.text
        stale_batch = stale.json()

        changed = await client.put(
            f"/api/v1/projects/{project_id}/architecture",
            headers=headers,
            json=_architecture_payload(primary_material="plaster"),
        )
        assert changed.status_code == 200, changed.text

        await _complete_batch(
            stale_batch,
            render_asset_ids,
            [(0.99, True), (0.80, True), (0.75, True)],
        )
        async with get_session_factory()() as session:
            stale_result = await ArchitectureRenderPublicationService(
                session, get_settings()
            ).finalize(UUID(stale_batch["batch_id"]))
        assert stale_result.published is False
        assert stale_result.skip_reason == "architecture_changed_after_enqueue"
        assert stale_result.winner_render_id == UUID(stale_batch["renders"][0]["id"])

        ideas_after_stale = await client.get("/api/v1/admin/ideas", headers=headers)
        current = next(item for item in ideas_after_stale.json() if item["id"] == idea_id)
        assert current["image_asset_id"] == render_asset_ids[2]
        assert current["model_url"] == published_model_url
        assert current["architecture"]["appearance"]["primary_material"] == "wood"

        audit = await client.get("/api/v1/admin/audit", headers=headers)
        assert audit.status_code == 200, audit.text
        assert any(
            item["action"] == "idea.architecture_render_batch.skip"
            and item["entity_id"] == idea_id
            and item["details"].get("reason") == "architecture_changed_after_enqueue"
            for item in audit.json()
        )
