import io
import os
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True
    )

from app.db.models.users import User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.users.enums import UserRole  # noqa: E402
from app.main import app  # noqa: E402


def _architecture_payload() -> dict:
    return {
        "schema_version": "1.0",
        "program": {"living_area_sqm": 160, "storeys": 2, "bedrooms": 4, "bathrooms": 2},
        "appearance": {
            "architecture_style": "modern",
            "primary_material": "wood",
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
                    "rooms": [
                        {
                            "id": "living",
                            "name": "Гостиная",
                            "kind": "living",
                            "polygon": {
                                "points": [
                                    {"x": 0, "y": 0},
                                    {"x": 6, "y": 0},
                                    {"x": 6, "y": 5},
                                    {"x": 0, "y": 5},
                                ]
                            },
                        }
                    ],
                },
                {
                    "id": "upper",
                    "label": "2 этаж",
                    "z": 3.2,
                    "height": 3.0,
                    "footprint": {
                        "points": [
                            {"x": 0, "y": 0},
                            {"x": 12, "y": 0},
                            {"x": 12, "y": 9},
                            {"x": 0, "y": 9},
                        ]
                    },
                    "rooms": [],
                },
            ],
            "external_objects": [],
            "roof": {
                "type": "gable",
                "eave_z": 6.2,
                "ridge_z": 8.7,
                "ridge_start": {"x": 6, "y": 0},
                "ridge_end": {"x": 6, "y": 9},
                "overhang_m": 0.5,
            },
        },
    }


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (96, 72), color).save(buffer, format="PNG")
    return buffer.getvalue()


async def _register_admin(client: AsyncClient) -> dict[str, str]:
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ideas-{uuid4()}@example.com",
            "password": "integration-test-password-123",
            "display_name": "Ideas Admin",
        },
    )
    assert register.status_code == 201, register.text
    user_id = UUID(register.json()["user"]["id"])
    async with get_session_factory()() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.role = UserRole.SUPERADMIN
        await session.commit()
    return {"Authorization": f"Bearer {register.json()['access_token']}"}


@pytest.mark.asyncio
async def test_published_idea_contains_media_and_architecture_snapshot() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _register_admin(client)
        project = await client.post(
            "/api/v1/projects",
            headers=headers,
            json={
                "name": "Immersive feed source",
                "context": {"architecture": _architecture_payload()},
            },
        )
        assert project.status_code == 201, project.text
        project_id = project.json()["id"]

        hero = await client.post(
            "/api/v1/assets",
            headers=headers,
            data={"purpose": "project_reference"},
            files={"file": ("hero.png", _png_bytes((170, 135, 95)), "image/png")},
        )
        reference = await client.post(
            "/api/v1/assets",
            headers=headers,
            data={"purpose": "project_reference"},
            files={"file": ("reference.png", _png_bytes((95, 115, 125)), "image/png")},
        )
        assert hero.status_code == 201, hero.text
        assert reference.status_code == 201, reference.text

        created = await client.post(
            "/api/v1/admin/ideas",
            headers=headers,
            json={
                "title": "Дом с 3D-обзором",
                "category": "Фасад",
                "text": "Интерактивная архитектурная публикация.",
                "generation_type": "facade",
                "prompt": "Use this architectural direction",
                "image_asset_id": hero.json()["id"],
                "architecture_project_id": project_id,
                "media": [
                    {
                        "asset_id": reference.json()["id"],
                        "kind": "reference",
                        "label": "Материал фасада",
                    }
                ],
                "is_active": True,
                "sort_order": -100,
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["architecture_project_id"] == project_id
        assert body["architecture"]["geometry"]["levels"][1]["id"] == "upper"
        assert body["media"][0]["kind"] == "reference"
        assert body["media"][0]["url"].endswith(".png")

        public = await client.get("/api/v1/ideas", headers=headers)
        assert public.status_code == 200, public.text
        published = next(item for item in public.json() if item["id"] == body["id"])
        assert published["image_url"].endswith(".png")
        assert "architecture_project_id" not in published
        assert published["architecture"]["geometry"]["roof"]["type"] == "gable"
        assert published["media"] == body["media"]

        # A second superadmin may edit the publication without taking ownership of
        # already-attached assets or the original architecture source project.
        second_headers = await _register_admin(client)
        edited = await client.patch(
            f"/api/v1/admin/ideas/{body['id']}",
            headers=second_headers,
            json={
                "title": "Дом с 3D-обзором · обновлено",
                "image_asset_id": body["image_asset_id"],
                "architecture_project_id": body["architecture_project_id"],
                "media": [
                    {
                        "asset_id": item["asset_id"],
                        "kind": item["kind"],
                        "label": item["label"],
                    }
                    for item in body["media"]
                ],
            },
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["title"].endswith("обновлено")
        assert edited.json()["architecture_project_id"] == project_id
        assert edited.json()["media"] == body["media"]
