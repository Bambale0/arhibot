"""A duplicate refresh must not revoke the replacement created seconds ago.

The initial sign-in and replay races were observed on 2026-10-15. These
tests use synthetic session IDs only and never call Telegram or production DB.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.services.auth_service import AuthService


def _service(*, age_seconds: int, used: bool = True):
    settings = Settings()
    now = datetime.now(UTC)
    token = SimpleNamespace(
        family_id=uuid4(),
        used_at=(now - timedelta(seconds=age_seconds)) if used else None,
        revoked_at=now - timedelta(seconds=age_seconds),
        replaced_by_token_id=uuid4() if used else None,
        expires_at=now + timedelta(days=5),
    )
    repo = SimpleNamespace(
        get_refresh_token_for_update=AsyncMock(return_value=token),
        revoke_token_family=AsyncMock(),
        get_user=AsyncMock(),
        session=SimpleNamespace(commit=AsyncMock()),
    )
    service = AuthService(repo, settings)
    return service, repo


@pytest.mark.asyncio
async def test_fast_duplicate_rotated_refresh_does_not_revoke_new_valid_session():
    service, repo = _service(age_seconds=4)
    with pytest.raises(AppError) as exc_info:
        await service.refresh("synthetic-rotated-refresh")
    assert exc_info.value.status == 401
    assert exc_info.value.type == "refresh_token_rotated"
    repo.revoke_token_family.assert_not_awaited()
    repo.session.commit.assert_not_awaited()
    repo.get_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_old_replayed_refresh_still_revokes_entire_token_family():
    settings = Settings()
    service, repo = _service(age_seconds=settings.refresh_token_reuse_grace_seconds + 5)
    with pytest.raises(AppError) as exc_info:
        await service.refresh("synthetic-old-refresh")
    assert exc_info.value.status == 401
    assert exc_info.value.type == "refresh_token_reused"
    repo.revoke_token_family.assert_awaited_once()
    repo.session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_explicitly_revoked_unused_refresh_never_gets_grace():
    service, repo = _service(age_seconds=2, used=False)
    with pytest.raises(AppError) as exc_info:
        await service.refresh("synthetic-logged-out-refresh")
    assert exc_info.value.type == "refresh_token_reused"
    repo.revoke_token_family.assert_awaited_once()


def test_refresh_replay_grace_is_bounded_security_setting():
    with pytest.raises(ValueError):
        Settings(refresh_token_reuse_grace_seconds=-1)
    with pytest.raises(ValueError):
        Settings(refresh_token_reuse_grace_seconds=61)
