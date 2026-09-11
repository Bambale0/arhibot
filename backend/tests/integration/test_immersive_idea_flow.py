from __future__ import annotations

import os
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True
    )

from app.db.models.assets import Asset  # noqa: E402
from app.db.models.generations import Generation  # noqa: E402
from app.db.models.projects import Project  # noqa: E402
from app.db.models.users import User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.assets.enums import AssetPurpose, AssetType  # noqa: E402
from app.domain.generations.enums import GenerationStatus, GenerationType  # noqa: E402
from app.domain.users.enums import UserRole  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.questionnaires import DesignSession  # noqa: E402


async def _register(
    client: AsyncClient, *, role: UserRole = UserRole.USER
) -> tuple[dict[str, str], UUID]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ideas-{uuid4()}@example.com",
            "password": "integration-test-password-123",
            "display_name": "Ideas Test",
        },
    )
    assert response.status_code == 201, response.text
    user_id = UUID(response.json()["user"]["id"])
    if role != UserRole.USER:
        async with get_session_factory()() as session:
            user = await session.get(User, user_id)
            assert user is not None
            user.role = role
            await session.commit()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, user_id


async def _accepted_generation(
    *,
    owner_id: UUID,
    catalog_version: str,
    object_key: str = "eskez-doma",
    answers: dict[str, object] | None = None,
) -> UUID:
    generation_id = uuid4()
    project_id = uuid4()
    asset_id = uuid4()
    now = datetime.now(UTC)
    session_state = DesignSession(
        catalog_version=catalog_version,
        selected_objects=[object_key],
        current_object=None,
        source_step_completed=True,
        scene_asset_id=asset_id,
        answers={object_key: answers or {"1": "Современный минимализм"}},
        accepted_objects=[object_key],
        generation_ids={object_key: generation_id},
    )
    async with get_session_factory()() as session:
        session.add(
            Project(
                id=project_id,
                user_id=owner_id,
                name="Generated source",
                description="Accepted Create work",
                context={
                    "questionnaire_draft": False,
                    "design_session": session_state.model_dump(mode="json"),
                },
            )
        )
        await session.flush()
        session.add(
            Asset(
                id=asset_id,
                user_id=owner_id,
                project_id=project_id,
                type=AssetType.IMAGE,
                purpose=AssetPurpose.GENERATION_OUTPUT,
                original_filename="result.png",
                mime_type="image/png",
                size_bytes=1024,
                width=1024,
                height=768,
                storage_path=f"tests/ideas/{asset_id}.png",
            )
        )
        await session.flush()
        session.add(
            Generation(
                id=generation_id,
                user_id=owner_id,
                project_id=project_id,
                output_asset_id=asset_id,
                type=GenerationType.MASTER_PLAN,
                status=GenerationStatus.COMPLETED,
                prompt="accepted questionnaire prompt",
                completed_at=now,
            )
        )
        await session.commit()
    return generation_id


@pytest.mark.asyncio
async def test_user_adds_own_accepted_create_result_to_ideas() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        admin_headers, _ = await _register(client, role=UserRole.SUPERADMIN)
        user_headers, user_id = await _register(client)
        catalog_response = await client.get("/api/v1/questionnaires", headers=user_headers)
        assert catalog_response.status_code == 200, catalog_response.text
        generation_id = await _accepted_generation(
            owner_id=user_id,
            catalog_version=catalog_response.json()["version"],
        )

        before = await client.get(
            f"/api/v1/ideas/mine/{generation_id}", headers=user_headers
        )
        assert before.status_code == 200, before.text
        assert before.json() is None

        published = await client.post(
            "/api/v1/ideas",
            headers=user_headers,
            json={"generation_id": str(generation_id)},
        )
        assert published.status_code == 201, published.text
        publication = published.json()
        assert publication["generation_id"] == str(generation_id)
        assert publication["is_active"] is True
        assert publication["sort_order"] == 0
        assert urlsplit(publication["image_url"]).path.endswith(".png")
        assert publication["objects"][0]["answers"] == [
            {"question": "Какой стиль вам нравится?", "answer": "Современный минимализм"}
        ]

        own = await client.get(
            f"/api/v1/ideas/mine/{generation_id}", headers=user_headers
        )
        assert own.status_code == 200, own.text
        assert own.json()["id"] == publication["id"]

        duplicate = await client.post(
            "/api/v1/ideas",
            headers=user_headers,
            json={"generation_id": str(generation_id)},
        )
        assert duplicate.status_code == 201, duplicate.text
        assert duplicate.json()["id"] == publication["id"]
        assert duplicate.json()["is_active"] is True

        public = await client.get("/api/v1/ideas", headers=user_headers)
        assert public.status_code == 200, public.text
        idea = next(item for item in public.json() if item["id"] == publication["id"])
        assert idea["title"] == "Дом, фасад"
        assert idea["selected_objects"] == ["eskez-doma"]
        assert "prompt" not in idea
        assert "text" not in idea
        assert "model_url" not in idea
        assert "media" not in idea

        owner_hidden = await client.delete(
            f"/api/v1/ideas/mine/{generation_id}", headers=user_headers
        )
        assert owner_hidden.status_code == 200, owner_hidden.text
        assert owner_hidden.json()["is_active"] is False
        republished = await client.post(
            "/api/v1/ideas",
            headers=user_headers,
            json={"generation_id": str(generation_id)},
        )
        assert republished.status_code == 201, republished.text
        assert republished.json()["id"] == publication["id"]
        assert republished.json()["is_active"] is True

        started = await client.post(
            f"/api/v1/ideas/{idea['id']}/project", headers=user_headers
        )
        assert started.status_code == 201, started.text
        started_session = started.json()["context"]["design_session"]
        assert started.json()["context"]["questionnaire_draft"] is True
        assert started_session["selected_objects"] == ["eskez-doma"]
        assert started_session["answers"] == {}
        assert started_session["accepted_objects"] == []

        async with get_session_factory()() as session:
            generation = await session.get(Generation, generation_id)
            assert generation is not None and generation.output_asset_id is not None
            asset = await session.get(Asset, generation.output_asset_id)
            assert asset is not None
            asset.deleted_at = datetime.now(UTC)
            await session.commit()

        degraded_admin = await client.get("/api/v1/admin/ideas", headers=admin_headers)
        assert degraded_admin.status_code == 200, degraded_admin.text
        degraded = next(
            item for item in degraded_admin.json() if item["id"] == publication["id"]
        )
        assert degraded["is_active"] is True
        assert degraded["image_url"] is None
        public_without_asset = await client.get("/api/v1/ideas", headers=user_headers)
        assert all(item["id"] != publication["id"] for item in public_without_asset.json())

        hidden = await client.delete(
            f"/api/v1/admin/ideas/{idea['id']}", headers=admin_headers
        )
        assert hidden.status_code == 200, hidden.text
        assert hidden.json()["is_active"] is False
        public_after = await client.get("/api/v1/ideas", headers=user_headers)
        assert all(item["id"] != idea["id"] for item in public_after.json())

        own_after_moderation = await client.get(
            f"/api/v1/ideas/mine/{generation_id}", headers=user_headers
        )
        assert own_after_moderation.status_code == 200
        assert own_after_moderation.json()["is_active"] is False

        restored = await client.patch(
            f"/api/v1/admin/ideas/{idea['id']}",
            headers=admin_headers,
            json={"is_active": True},
        )
        assert restored.status_code == 200, restored.text
        unpublished = await client.delete(
            f"/api/v1/ideas/mine/{generation_id}", headers=user_headers
        )
        assert unpublished.status_code == 200, unpublished.text
        assert unpublished.json()["is_active"] is False
        public_after_owner_unpublish = await client.get("/api/v1/ideas", headers=user_headers)
        assert all(item["id"] != idea["id"] for item in public_after_owner_unpublish.json())


@pytest.mark.asyncio
async def test_user_cannot_publish_another_users_generation() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        owner_headers, owner_id = await _register(client)
        other_headers, _ = await _register(client)
        catalog = await client.get("/api/v1/questionnaires", headers=owner_headers)
        generation_id = await _accepted_generation(
            owner_id=owner_id,
            catalog_version=catalog.json()["version"],
        )

        response = await client.post(
            "/api/v1/ideas",
            headers=other_headers,
            json={"generation_id": str(generation_id)},
        )
        assert response.status_code == 404, response.text
        assert response.json()["type"].endswith("idea_source_not_found")

        status_response = await client.get(
            f"/api/v1/ideas/mine/{generation_id}", headers=other_headers
        )
        assert status_response.status_code == 404


@pytest.mark.asyncio
async def test_previous_display_only_catalog_revision_can_still_be_user_published() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_headers, user_id = await _register(client)
        generation_id = await _accepted_generation(
            owner_id=user_id,
            catalog_version="2026-09-09.2",
            answers={
                "1": "Современный минимализм",
                "6": "Да",
                "6а": "Не в доме",
            },
        )

        published = await client.post(
            "/api/v1/ideas",
            headers=user_headers,
            json={"generation_id": str(generation_id)},
        )
        assert published.status_code == 201, published.text
        answer_rows = published.json()["objects"][0]["answers"]
        garage_place = next(row for row in answer_rows if row["answer"] == "Не в доме")
        assert garage_place["question"] == "Где гараж?"
        assert "если" not in garage_place["question"].lower()


@pytest.mark.asyncio
async def test_completed_but_unaccepted_generation_cannot_be_user_published() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_headers, user_id = await _register(client)
        catalog = await client.get("/api/v1/questionnaires", headers=user_headers)
        generation_id = await _accepted_generation(
            owner_id=user_id,
            catalog_version=catalog.json()["version"],
        )

        async with get_session_factory()() as session:
            generation = await session.get(Generation, generation_id)
            assert generation is not None
            project = await session.get(Project, generation.project_id)
            assert project is not None
            context = dict(project.context or {})
            design_session = dict(context["design_session"])
            design_session["accepted_objects"] = []
            context["design_session"] = design_session
            project.context = context
            await session.commit()

        response = await client.post(
            "/api/v1/ideas",
            headers=user_headers,
            json={"generation_id": str(generation_id)},
        )
        assert response.status_code == 422, response.text
        assert response.json()["type"].endswith("idea_source_not_accepted")
