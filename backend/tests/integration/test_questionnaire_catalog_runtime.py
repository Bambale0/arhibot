import os

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip("set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True)

from app.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_questionnaire_catalog_is_served_after_fresh_migrations() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/questionnaires")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["version"] == "2026-09-10.1"
    assert len(payload["questionnaires"]) == 27
    assert payload["questionnaires"][0]["key"] == "eskez-doma"
