import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip("set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True)

from app.main import app  # noqa: E402


async def _register(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"questionnaire-draft-{uuid4()}@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "Questionnaire Draft Tester",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_questionnaire_project_is_hidden_until_source_step_and_can_be_discarded() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _register(client)

        start = await client.post(
            "/api/v1/questionnaire-projects",
            headers=headers,
            json={"selected_objects": ["eskez-doma"]},
        )
        assert start.status_code == 201, start.text
        project = start.json()
        project_id = project["id"]
        assert project["context"]["questionnaire_draft"] is True
        design_session = project["context"]["design_session"]
        assert design_session["selected_objects"] == ["eskez-doma"]
        assert design_session["source_step_completed"] is False

        hidden_list = await client.get("/api/v1/projects", headers=headers)
        assert hidden_list.status_code == 200, hidden_list.text
        assert project_id not in {item["id"] for item in hidden_list.json()["items"]}

        design_session["source_step_completed"] = True
        saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=design_session,
        )
        assert saved.status_code == 200, saved.text

        promoted = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["context"]["questionnaire_draft"] is False

        visible_list = await client.get("/api/v1/projects", headers=headers)
        assert visible_list.status_code == 200, visible_list.text
        assert project_id in {item["id"] for item in visible_list.json()["items"]}

        draft = await client.post(
            "/api/v1/questionnaire-projects",
            headers=headers,
            json={"selected_objects": ["banya"]},
        )
        assert draft.status_code == 201, draft.text
        draft_id = draft.json()["id"]

        discard = await client.delete(
            f"/api/v1/questionnaire-projects/{draft_id}/draft",
            headers=headers,
        )
        assert discard.status_code == 204, discard.text

        missing = await client.get(f"/api/v1/projects/{draft_id}", headers=headers)
        assert missing.status_code == 404, missing.text


@pytest.mark.asyncio
async def test_questionnaire_project_start_rejects_unknown_duplicates_and_client_catalog_version() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _register(client)

        unknown = await client.post(
            "/api/v1/questionnaire-projects",
            headers=headers,
            json={"selected_objects": ["not-a-real-object"]},
        )
        assert unknown.status_code == 422, unknown.text

        duplicate = await client.post(
            "/api/v1/questionnaire-projects",
            headers=headers,
            json={"selected_objects": ["eskez-doma", "eskez-doma"]},
        )
        assert duplicate.status_code == 422, duplicate.text

        client_version = await client.post(
            "/api/v1/questionnaire-projects",
            headers=headers,
            json={"selected_objects": ["eskez-doma"], "catalog_version": "stale-client-value"},
        )
        assert client_version.status_code == 422, client_version.text
