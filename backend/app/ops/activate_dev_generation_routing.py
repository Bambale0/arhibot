"""Apply canonical development generation routing through the authenticated admin API."""
from __future__ import annotations

import asyncio
import os

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.models.users import User
from app.db.session import dispose_engine, get_session_factory
from app.domain.users.enums import UserRole, UserStatus


def build_activation_payload(current: dict[str, object]) -> dict[str, object]:
    editable = {
        "primary_provider",
        "fallback_provider",
        "primary_model",
        "fallback_model",
        "primary_timeout_seconds",
        "primary_params",
        "fallback_params",
        "mode_params",
        "masked_edit_provider_context_margin_fraction",
        "masked_edit_feather_fraction",
        "masked_edit_feather_min_px",
        "masked_edit_feather_max_px",
        "masked_edit_recomposite_feather_multiplier",
        "masked_edit_boundary_band_px",
        "masked_edit_max_luma_excess",
        "masked_edit_max_color_excess",
        "masked_edit_max_straight_edge_fraction",
        "generation_quality_max_retries",
    }
    payload = {key: value for key, value in current.items() if key in editable}
    payload.update(
        primary_provider="nexus",
        fallback_provider="nexus",
        primary_model="gpt-image-2",
        fallback_model="nano-banana-pro",
        primary_params={},
        fallback_params={"image_size": "2K"},
    )
    return payload


async def activate() -> None:
    if os.environ.get("AUROOM_DEPLOY_TARGET") != "dev":
        raise RuntimeError("Development generation routing is restricted to the dev target")
    settings = get_settings()
    if not (settings.nexus_api_key or "").strip():
        raise RuntimeError("NEXUS_API_KEY is not configured")

    async with get_session_factory()() as session:
        result = await session.execute(
            select(User)
            .where(
                User.role == UserRole.SUPERADMIN,
                User.status == UserStatus.ACTIVE,
            )
            .order_by(User.created_at.asc())
            .limit(1)
        )
        actor = result.scalar_one_or_none()
    if actor is None:
        raise RuntimeError("An active superadmin is required for dev activation")

    token, _ = create_access_token(actor.id, settings)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=15) as client:
        current_response = await client.get("/api/v1/admin/generation", headers=headers)
        current_response.raise_for_status()
        response = await client.put(
            "/api/v1/admin/generation",
            headers=headers,
            json=build_activation_payload(current_response.json()),
        )
        response.raise_for_status()
        saved = response.json()

    expected = {
        "primary_provider": "nexus",
        "fallback_provider": "nexus",
        "primary_model": "gpt-image-2",
        "fallback_model": "nano-banana-pro",
    }
    if any(saved.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Authenticated dev activation did not persist Nexus routing")
    print("Canonical dev image routing activated through authenticated admin control plane")


async def main() -> int:
    try:
        await activate()
        return 0
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
