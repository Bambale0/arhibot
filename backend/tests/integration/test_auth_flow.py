import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip("set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True)

from app.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_email_register_me_refresh_login_flow() -> None:
    email = f"auth-{uuid4()}@example.test"
    password = "correct-horse-battery-staple"
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        register = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "display_name": "Integration User"},
        )
        assert register.status_code == 201, register.text
        tokens = register.json()
        assert tokens["token_type"] == "bearer"
        assert register.headers["cache-control"] == "no-store"

        me = await client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert me.status_code == 200, me.text
        assert me.json()["display_name"] == "Integration User"

        refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refresh.status_code == 200, refresh.text
        rotated = refresh.json()
        assert rotated["refresh_token"] != tokens["refresh_token"]

        reuse = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert reuse.status_code == 401, reuse.text
        assert reuse.json()["type"] == "refresh_token_reused"

        family_revoked = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
        )
        assert family_revoked.status_code == 401, family_revoked.text

        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert login.status_code == 200, login.text
