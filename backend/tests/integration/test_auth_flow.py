import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip("set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True)

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_refresh_token  # noqa: E402
from app.db.models.users import RefreshToken  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_email_register_me_refresh_login_flow() -> None:
    email = f"auth-{uuid4()}@example.com"
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
        assert me.json()["role"] == "user"

        admin = await client.get(
            "/api/v1/admin/overview",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert admin.status_code == 403, admin.text
        assert admin.json()["type"] == "admin_access_required"

        refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refresh.status_code == 200, refresh.text
        rotated = refresh.json()
        assert rotated["refresh_token"] != tokens["refresh_token"]

        # A second WebView can still hold the old HttpOnly cookie just after
        # rotation. Reject it without killing the newer, already issued token.
        reuse = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert reuse.status_code == 401, reuse.text
        assert reuse.json()["type"] == "refresh_token_rotated"
        still_valid = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
        )
        assert still_valid.status_code == 200, still_valid.text

        # A much later replay is no longer a benign concurrent-WebView race:
        # preserve strict compromise/revocation detection beyond the grace.
        settings = get_settings()
        async with get_session_factory()() as db:
            previous = (
                await db.execute(
                    select(RefreshToken)
                    .where(
                        RefreshToken.token_hash == hash_refresh_token(
                            tokens["refresh_token"], settings
                        )
                    )
                    .with_for_update()
                )
            ).scalar_one()
            previous.used_at = datetime.now(UTC) - timedelta(
                seconds=settings.refresh_token_reuse_grace_seconds + 5
            )
            await db.commit()
        old_replay = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert old_replay.status_code == 401, old_replay.text
        assert old_replay.json()["type"] == "refresh_token_reused"

        family_revoked = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": still_valid.json()["refresh_token"]}
        )
        assert family_revoked.status_code == 401, family_revoked.text

        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert login.status_code == 200, login.text
        assert "auroom_refresh_token=" in login.headers.get("set-cookie", "")
        assert "httponly" in login.headers.get("set-cookie", "").lower()


@pytest.mark.asyncio
async def test_browser_refresh_cookie_rotates_without_javascript_token_access() -> None:
    email = f"cookie-auth-{uuid4()}@example.com"
    password = "correct-horse-battery-staple"
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        register = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "display_name": "Cookie User"},
        )
        assert register.status_code == 201, register.text
        original_cookie = client.cookies.get("auroom_refresh_token")
        assert original_cookie
        set_cookie = register.headers.get("set-cookie", "").lower()
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie

        refresh = await client.post("/api/v1/auth/refresh")
        assert refresh.status_code == 200, refresh.text
        rotated_cookie = client.cookies.get("auroom_refresh_token")
        assert rotated_cookie
        assert rotated_cookie != original_cookie

        logout = await client.post("/api/v1/auth/logout")
        assert logout.status_code == 200, logout.text
        assert client.cookies.get("auroom_refresh_token") is None

        missing = await client.post("/api/v1/auth/refresh")
        assert missing.status_code == 401, missing.text
        assert missing.json()["type"] == "invalid_refresh_token"
