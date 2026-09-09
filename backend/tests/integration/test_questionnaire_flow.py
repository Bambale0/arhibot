import os
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip("set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True)

from app.db.models.assets import Asset  # noqa: E402
from app.db.models.generations import Generation  # noqa: E402
from app.db.models.users import User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.assets.enums import AssetPurpose, AssetType  # noqa: E402
from app.domain.generations.enums import GenerationStatus, GenerationType  # noqa: E402
from app.domain.users.enums import UserRole  # noqa: E402
from app.main import app  # noqa: E402


async def _register_admin(client: AsyncClient) -> tuple[dict, dict[str, str]]:
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"questionnaire-{uuid4()}@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "Questionnaire Admin",
        },
    )
    assert register.status_code == 201, register.text
    tokens = register.json()
    user_id = UUID(tokens["user"]["id"])
    async with get_session_factory()() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.role = UserRole.SUPERADMIN
        await session.commit()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


def _question(definition: dict, question_id: str) -> dict:
    return next(item for item in definition["questions"] if item["id"] == question_id)


@pytest.mark.asyncio
async def test_questionnaire_catalog_session_and_application_flow() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens, headers = await _register_admin(client)
        user_id = UUID(tokens["user"]["id"])

        catalog_response = await client.get("/api/v1/questionnaires", headers=headers)
        assert catalog_response.status_code == 200, catalog_response.text
        catalog = catalog_response.json()
        assert len(catalog["questionnaires"]) == 27

        admin_catalog = await client.get("/api/v1/admin/questionnaires", headers=headers)
        assert admin_catalog.status_code == 200, admin_catalog.text
        assert len(admin_catalog.json()["source_texts"]) == 27

        project_response = await client.post(
            "/api/v1/projects",
            headers=headers,
            json={"name": "Questionnaire integration", "context": {}},
        )
        assert project_response.status_code == 201, project_response.text
        project_id = UUID(project_response.json()["id"])

        fake_session = {
            "session_id": str(uuid4()),
            "catalog_version": catalog["version"],
            "selected_objects": ["eskez-doma"],
            "current_object": "zayavka",
            "current_question_id": "20",
            "source_step_completed": True,
            "source_asset_id": None,
            "scene_asset_id": None,
            "answers": {},
            "accepted_objects": ["eskez-doma"],
            "generation_ids": {"eskez-doma": str(uuid4())},
            "edit_question_ids": [],
            "review_comments": {},
            "application_submitted": False,
        }
        rejected = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=fake_session,
        )
        assert rejected.status_code == 422, rejected.text

        output_asset = Asset(
            user_id=user_id,
            project_id=project_id,
            type=AssetType.IMAGE,
            purpose=AssetPurpose.GENERATION_OUTPUT,
            original_filename="questionnaire-output.webp",
            mime_type="image/webp",
            size_bytes=128,
            width=1024,
            height=1024,
            storage_path=f"integration/questionnaires/{uuid4()}.webp",
        )
        generation = Generation(
            user_id=user_id,
            project_id=project_id,
            input_asset_id=None,
            type=GenerationType.MASTER_PLAN,
            status=GenerationStatus.COMPLETED,
            prompt="integration questionnaire render",
            credits_charged=0,
        )
        async with get_session_factory()() as session:
            session.add(output_asset)
            await session.flush()
            generation.output_asset_id = output_asset.id
            session.add(generation)
            await session.commit()
            await session.refresh(output_asset)
            await session.refresh(generation)

        design_session = {
            **fake_session,
            "session_id": str(uuid4()),
            "scene_asset_id": str(output_asset.id),
            "generation_ids": {"eskez-doma": str(generation.id)},
        }
        saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=design_session,
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["session"]["scene_asset_id"] == str(output_asset.id)

        application_definition = next(
            item for item in catalog["questionnaires"] if item["key"] == "zayavka"
        )
        application_answers = {
            "20": _question(application_definition, "20")["options"][0],
            "21": _question(application_definition, "21")["options"][0],
            "22": _question(application_definition, "22")["options"][0],
            "23": "Иван",
            "24": "+79990000000",
            "25": True,
        }
        submitted_payload = {
            **design_session,
            "current_question_id": None,
            "answers": {"zayavka": application_answers},
            "application_submitted": True,
        }
        submitted = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-application",
            headers=headers,
            json=submitted_payload,
        )
        assert submitted.status_code == 200, submitted.text
        application_id = submitted.json()["application"]["id"]
        assert submitted.json()["application"]["status"] == "new"

        repeated = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-application",
            headers=headers,
            json=submitted_payload,
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["application"]["id"] == application_id

        applications = await client.get(
            "/api/v1/admin/questionnaire-applications",
            headers=headers,
        )
        assert applications.status_code == 200, applications.text
        assert any(item["id"] == application_id for item in applications.json())
