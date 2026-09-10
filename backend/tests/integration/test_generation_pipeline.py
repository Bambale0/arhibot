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
from app.db.models.assets import Asset  # noqa: E402
from app.db.models.generations import Generation  # noqa: E402
from app.db.models.users import User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.users.enums import UserRole  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.nexus import NexusImageProvider, NexusImageResult  # noqa: E402
from app.services.asset_service import LocalMediaStorage  # noqa: E402
from app.services.generation_service import GENERATION_QUEUE_KEY  # noqa: E402
from app.workers import generation_worker  # noqa: E402


def _png(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def _register_user(
    client: AsyncClient, *, display_name: str = "Generation Pipeline User"
) -> tuple[dict, dict[str, str]]:
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"generation-pipeline-{uuid4()}@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": display_name,
        },
    )
    assert register.status_code == 201, register.text
    tokens = register.json()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


async def _register_admin(client: AsyncClient) -> tuple[dict, dict[str, str]]:
    tokens, headers = await _register_user(client, display_name="Generation Pipeline Admin")
    user_id = UUID(tokens["user"]["id"])
    async with get_session_factory()() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.role = UserRole.SUPERADMIN
        await session.commit()
    return tokens, headers


@pytest.mark.asyncio
async def test_generation_worker_completes_masked_pipeline_and_preserves_pixels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, admin_headers = await _register_admin(client)
        tokens, headers = await _register_user(client)
        user_id = tokens["user"]["id"]

        runtime = await client.put(
            "/api/v1/admin/generation",
            headers=admin_headers,
            json={
                "primary_model": "integration-image-model",
                "fallback_model": None,
                "primary_params": {"steps": 12},
                "fallback_params": {},
                "mode_params": {},
            },
        )
        assert runtime.status_code == 200, runtime.text
        prompt = await client.put(
            "/api/v1/admin/prompts/master_plan",
            headers=admin_headers,
            json={"template": "Architectural render. {user_prompt}"},
        )
        assert prompt.status_code == 200, prompt.text
        price = await client.put(
            "/api/v1/admin/generation-prices/master_plan",
            headers=admin_headers,
            json={"credits": 2, "is_active": True},
        )
        assert price.status_code == 200, price.text
        credit = await client.post(
            f"/api/v1/admin/users/{user_id}/credits",
            headers=admin_headers,
            json={"delta": 5, "reason": "masked pipeline integration budget"},
        )
        assert credit.status_code == 200, credit.text

        project = await client.post(
            "/api/v1/projects",
            headers=headers,
            json={"name": "Masked generation pipeline", "context": {}},
        )
        assert project.status_code == 201, project.text
        project_id = project.json()["id"]

        base_data = _png((100, 100), (10, 20, 30))
        uploaded = await client.post(
            "/api/v1/assets",
            headers=headers,
            data={"purpose": "generation_input", "project_id": project_id},
            files={"file": ("base.png", base_data, "image/png")},
        )
        assert uploaded.status_code == 201, uploaded.text

        edit_region = {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8}
        protected_region = {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2}
        created = await client.post(
            "/api/v1/generations",
            headers=headers,
            json={
                "project_id": project_id,
                "input_asset_id": uploaded.json()["id"],
                "type": "master_plan",
                "prompt": "Add a bathhouse only in the editable area",
                "composition_mode": "masked_edit",
                "edit_region": edit_region,
                "protected_regions": [protected_region],
            },
        )
        assert created.status_code == 202, created.text
        generation_id = UUID(created.json()["id"])

        candidate_data = _png((100, 100), (220, 210, 200))
        provider_calls: list[dict] = []

        async def fake_generate(self, **kwargs):  # noqa: ANN001, ARG001
            provider_calls.append(kwargs)
            return NexusImageResult(
                task_id="integration-task",
                image_url="https://cdn.example.test/generated.png",
            )

        async def fake_download(url, settings):  # noqa: ANN001, ARG001
            assert url == "https://cdn.example.test/generated.png"
            return candidate_data

        monkeypatch.setattr(NexusImageProvider, "generate", fake_generate)
        monkeypatch.setattr(generation_worker, "_download_image", fake_download)
        await generation_worker.process_generation(generation_id, get_settings())
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))

        completed = await client.get(f"/api/v1/generations/{generation_id}", headers=headers)
        assert completed.status_code == 200, completed.text
        body = completed.json()
        assert body["status"] == "completed"
        assert body["output_asset"]["mime_type"] == "image/png"
        assert body["composition_mode"] == "masked_edit"
        assert provider_calls and provider_calls[0]["image_url"] == uploaded.json()["url"]
        assert "Add a bathhouse only in the editable area" in provider_calls[0]["prompt"]

        async with get_session_factory()() as session:
            generation = await session.get(Generation, generation_id)
            assert generation is not None and generation.output_asset_id is not None
            output = await session.get(Asset, generation.output_asset_id)
            assert output is not None
            output_path = LocalMediaStorage(get_settings()).absolute_path(output.storage_path)
        with Image.open(output_path) as image:
            result = image.convert("RGB")
            assert result.getpixel((5, 5)) == (10, 20, 30)
            assert result.getpixel((50, 50)) == (10, 20, 30)
            assert result.getpixel((20, 20)) == (220, 210, 200)

        me = await client.get("/api/v1/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["credits_balance"] == 3
