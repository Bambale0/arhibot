import os
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "set RUN_INTEGRATION_TESTS=1 with a migrated test database",
        allow_module_level=True,
    )

from app.core.config import get_settings  # noqa: E402
from app.core.redis import redis_client  # noqa: E402
from app.db.models.users import User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.users.enums import UserRole  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.nexus import NexusImageProvider, NexusImageResult  # noqa: E402
from app.services.generation_service import GENERATION_QUEUE_KEY  # noqa: E402
from app.workers import generation_worker  # noqa: E402


def _png() -> bytes:
    image = Image.new("RGB", (96, 64), (120, 130, 140))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def _register(
    client: AsyncClient,
    *,
    role: UserRole = UserRole.USER,
) -> tuple[dict, dict[str, str]]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ai-sandbox-{uuid4()}@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "AI Sandbox Test",
        },
    )
    assert response.status_code == 201, response.text
    tokens = response.json()
    if role != UserRole.USER:
        async with get_session_factory()() as session:
            user = await session.get(User, UUID(tokens["user"]["id"]))
            assert user is not None
            user.role = role
            await session.commit()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.mark.asyncio
async def test_admin_ai_sandbox_forces_selected_model_without_credits_or_runtime_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, user_headers = await _register(client)
        denied = await client.post(
            "/api/v1/admin/generation/sandbox",
            headers=user_headers,
            json={
                "model_name": "nexus/test-model",
                "prompt": "A modern house",
                "params": {},
            },
        )
        assert denied.status_code == 403, denied.text

        _, admin_headers = await _register(client, role=UserRole.SUPERADMIN)
        before_me = await client.get("/api/v1/me", headers=admin_headers)
        assert before_me.status_code == 200, before_me.text
        before_balance = before_me.json()["credits_balance"]

        runtime = await client.put(
            "/api/v1/admin/generation",
            headers=admin_headers,
            json={
                "primary_model": "production-primary",
                "fallback_model": "production-fallback",
                "primary_params": {"quality": "production"},
                "fallback_params": {"quality": "fallback"},
                "mode_params": {},
            },
        )
        assert runtime.status_code == 200, runtime.text

        created = await client.post(
            "/api/v1/admin/generation/sandbox",
            headers=admin_headers,
            json={
                "model_name": "nexus/experimental-image",
                "prompt": "Photorealistic compact house on a landscaped plot",
                "params": {"aspect_ratio": "16:9", "steps": 7},
            },
        )
        assert created.status_code == 202, created.text
        body = created.json()
        generation_id = UUID(body["id"])
        assert body["status"] == "queued"
        assert body["credits_charged"] == 0
        assert body["model_name"] == "nexus/experimental-image"

        projects = await client.get("/api/v1/projects", headers=admin_headers)
        assert projects.status_code == 200, projects.text
        assert body["project_id"] not in {item["id"] for item in projects.json()["items"]}

        provider_calls: list[dict] = []

        async def fake_generate(self, **kwargs):  # noqa: ANN001, ARG001
            provider_calls.append(kwargs)
            return NexusImageResult(
                task_id="sandbox-task",
                image_url="https://cdn.example.test/sandbox.png",
            )

        async def fake_download(url, settings):  # noqa: ANN001, ARG001
            assert url == "https://cdn.example.test/sandbox.png"
            return _png()

        monkeypatch.setattr(NexusImageProvider, "generate", fake_generate)
        monkeypatch.setattr(generation_worker, "_download_image", fake_download)

        await generation_worker.process_generation(generation_id, get_settings())
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))

        assert len(provider_calls) == 1
        assert provider_calls[0]["model_name"] == "nexus/experimental-image"
        assert provider_calls[0]["prompt"] == (
            "Photorealistic compact house on a landscaped plot"
        )
        assert provider_calls[0]["model_params"] == {
            "aspect_ratio": "16:9",
            "steps": 7,
        }

        completed = await client.get(
            f"/api/v1/generations/{generation_id}",
            headers=admin_headers,
        )
        assert completed.status_code == 200, completed.text
        completed_body = completed.json()
        assert completed_body["status"] == "completed"
        assert completed_body["model_name"] == "nexus/experimental-image"
        assert completed_body["fallback_used"] is False
        assert completed_body["credits_charged"] == 0
        assert completed_body["output_asset"]["mime_type"] == "image/png"

        after_me = await client.get("/api/v1/me", headers=admin_headers)
        assert after_me.status_code == 200, after_me.text
        assert after_me.json()["credits_balance"] == before_balance

        unchanged_runtime = await client.get(
            "/api/v1/admin/generation",
            headers=admin_headers,
        )
        assert unchanged_runtime.status_code == 200, unchanged_runtime.text
        assert unchanged_runtime.json()["primary_model"] == "production-primary"
        assert unchanged_runtime.json()["fallback_model"] == "production-fallback"

        audit = await client.get("/api/v1/admin/audit", headers=admin_headers)
        assert audit.status_code == 200, audit.text
        sandbox_entries = [
            item
            for item in audit.json()
            if item["action"] == "generation.sandbox.create"
            and item["entity_id"] == str(generation_id)
        ]
        assert len(sandbox_entries) == 1
        assert sandbox_entries[0]["details"]["model_name"] == "nexus/experimental-image"
