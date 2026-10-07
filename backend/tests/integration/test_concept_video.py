import os
from io import BytesIO
from pathlib import Path
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
from app.db.models.generations import Generation  # noqa: E402
from app.db.models.users import User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.generations.enums import (  # noqa: E402
    GenerationOrigin,
    GenerationStatus,
    GenerationType,
)
from app.domain.users.enums import UserRole  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.neironych_responses import NeironychResponsesProvider  # noqa: E402
from app.providers.neironych_video import (  # noqa: E402
    NeironychVideoProvider,
    NeironychVideoResult,
)
from app.providers.nexus import NexusImageProvider  # noqa: E402
from app.services.asset_service import LocalMediaStorage  # noqa: E402
from app.services.generation_service import GENERATION_QUEUE_KEY  # noqa: E402
from app.workers import generation_worker  # noqa: E402


def _png() -> bytes:
    image = Image.new("RGB", (128, 72), (60, 90, 120))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def _register(
    client: AsyncClient, *, admin: bool = False
) -> tuple[dict, dict[str, str]]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"concept-video-{uuid4()}@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "Concept Video",
        },
    )
    assert response.status_code == 201, response.text
    tokens = response.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    if admin:
        async with get_session_factory()() as session:
            user = await session.get(User, UUID(tokens["user"]["id"]))
            assert user is not None
            user.role = UserRole.SUPERADMIN
            await session.commit()
    return tokens, headers


@pytest.mark.asyncio
async def test_concept_video_continuation_is_idempotent_and_outputs_mp4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, admin_headers = await _register(client, admin=True)
        tokens, headers = await _register(client)
        user_id = UUID(tokens["user"]["id"])

        runtime = await client.put(
            "/api/v1/admin/generation",
            headers=admin_headers,
            json={
                "primary_provider": "nexus",
                "primary_model": "gpt-image-2",
                "fallback_provider": "nexus",
                "fallback_model": None,
                "primary_timeout_seconds": 45,
                "primary_params": {"resolution": "2K"},
                "fallback_params": {},
                "mode_params": {},
                "quality_judge_model": None,
                "video_enabled": True,
                "video_model": "seedance-2.5",
                "video_params": {
                    "duration": 8,
                    "resolution": "480p",
                    "aspect_ratio": "16:9",
                },
            },
        )
        assert runtime.status_code == 200, runtime.text

        price = await client.put(
            "/api/v1/admin/generation-prices/video",
            headers=admin_headers,
            json={"credits": 3, "is_active": True},
        )
        assert price.status_code == 200, price.text
        credit = await client.post(
            f"/api/v1/admin/users/{user_id}/credits",
            headers=admin_headers,
            json={"delta": 20, "reason": "concept video integration budget"},
        )
        assert credit.status_code == 200, credit.text
        before = (await client.get("/api/v1/me", headers=headers)).json()["credits_balance"]

        project = await client.post(
            "/api/v1/projects",
            headers=headers,
            json={"name": "Video continuation", "context": {}},
        )
        assert project.status_code == 201, project.text
        project_id = UUID(project.json()["id"])
        uploaded = await client.post(
            "/api/v1/assets",
            headers=headers,
            data={"purpose": "generation_input", "project_id": str(project_id)},
            files={"file": ("concept.png", _png(), "image/png")},
        )
        assert uploaded.status_code == 201, uploaded.text
        source_asset_id = UUID(uploaded.json()["id"])

        source_id = uuid4()
        async with get_session_factory()() as session:
            session.add(
                Generation(
                    id=source_id,
                    user_id=user_id,
                    project_id=project_id,
                    input_asset_id=None,
                    output_asset_id=source_asset_id,
                    type=GenerationType.MASTER_PLAN,
                    status=GenerationStatus.COMPLETED,
                    origin=GenerationOrigin.QUESTIONNAIRE_INITIAL.value,
                    prompt=(
                        "AUROOM_INITIAL_CONCEPT_V1\n"
                        "STRUCTURED_SPEC:\n"
                        '{"task":{"objects":[{"object_key":"eskez-doma"}]}}'
                    ),
                    credits_charged=0,
                    model_name="gpt-image-2",
                )
            )
            await session.commit()

        created = await client.post(
            f"/api/v1/generations/{source_id}/video",
            headers=headers,
        )
        assert created.status_code == 202, created.text
        video_id = UUID(created.json()["id"])
        assert created.json()["type"] == "video"
        assert created.json()["credits_charged"] == 3
        assert created.json()["model_name"] == "seedance-2.5"

        duplicate = await client.post(
            f"/api/v1/generations/{source_id}/video",
            headers=headers,
        )
        assert duplicate.status_code == 202, duplicate.text
        assert duplicate.json()["id"] == str(video_id)
        after_duplicate = (await client.get("/api/v1/me", headers=headers)).json()[
            "credits_balance"
        ]
        assert after_duplicate == before - 3

        nexus_calls: list[dict] = []
        seedance_calls: list[dict] = []

        async def fail_if_nexus_generate_is_called(self, **kwargs):  # noqa: ANN001, ARG001
            nexus_calls.append(kwargs)
            raise AssertionError("concept video must not buy a Nexus keyframe")

        async def fail_if_grok_identity_is_called(self, **kwargs):  # noqa: ANN001, ARG001
            raise AssertionError(
                "locked pixel-derived concept video must not depend on Grok identity review"
            )

        async def fake_video_generate(self, **kwargs):  # noqa: ANN001, ARG001
            seedance_calls.append(kwargs)
            assert kwargs["model"] == "seedance-2.5"
            # The Nexus keyframe task id must never be reused as a Seedance request id.
            assert kwargs["request_id"] is None
            assert kwargs["request_body"]
            assert '"aspect_ratio":"adaptive"' in kwargs["request_body"]
            assert kwargs["start_image_url"].startswith("https://media.example.test/")
            assert kwargs["end_image_url"] is None
            assert '"end_image"' not in kwargs["request_body"]
            callback = kwargs.get("on_request_created")
            if callback is not None and not kwargs.get("request_id"):
                await callback("seedance-request-1")
            return NeironychVideoResult(
                request_id="seedance-request-1",
                content=b"\x00\x00\x00\x18ftypmp42concept-video",
                mime_type="video/mp4",
            )

        monkeypatch.setattr(
            NexusImageProvider,
            "generate",
            fail_if_nexus_generate_is_called,
        )
        monkeypatch.setattr(
            NeironychResponsesProvider,
            "review_identity",
            fail_if_grok_identity_is_called,
        )
        monkeypatch.setattr(NeironychVideoProvider, "generate", fake_video_generate)

        settings = get_settings().model_copy(
            update={"media_public_base_url": "https://media.example.test"}
        )
        await generation_worker.process_generation(video_id, settings)
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(video_id))

        assert nexus_calls == []
        assert len(seedance_calls) == 1
        assert UUID(seedance_calls[0]["client_request_id"])

        completed = await client.get(
            f"/api/v1/generations/{video_id}",
            headers=headers,
        )
        assert completed.status_code == 200, completed.text
        body = completed.json()
        assert body["status"] == "completed"
        assert body["type"] == "video"
        assert body["model_name"] == "seedance-2.5"
        assert body["quality_status"] == "passed"
        assert body["output_asset"]["type"] == "video"
        assert body["output_asset"]["mime_type"] == "video/mp4"
        assert body["output_asset"]["width"] == 854
        assert body["output_asset"]["height"] == 480
        identity = body["quality_report"]["video_identity_review"]
        assert identity["same_scene"] is True
        assert identity["confidence"] == 1.0
        assert identity["verification"] == "accepted_start_frame_only_v1"
        assert identity["source_sha256"]
        assert body["quality_report"]["video_motion_profile"] == "bird_flyover_safe_v2"
        constraints = body["quality_report"]["video_motion_constraints"]
        assert constraints["target_arc_degrees"] == [20, 35]
        assert constraints["max_arc_degrees"] == 45
        assert constraints["rear_facade_reveal"] is False
        assert constraints["resolution"] == "480p"
        assert constraints["input_mode"] == "start_image_only"
        assert "provider_frame_requests" not in body["quality_report"]
        assert "request_body" not in body["quality_report"]["video_request"]
        assert "key" not in body["quality_report"]["video_request"]

        restored = await client.get(
            f"/api/v1/generations/{source_id}/video",
            headers=headers,
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["id"] == str(video_id)

        output_path: Path
        async with get_session_factory()() as session:
            video = await session.get(Generation, video_id)
            assert video is not None and video.output_asset_id is not None
            output = await session.get(
                __import__("app.db.models.assets", fromlist=["Asset"]).Asset,
                video.output_asset_id,
            )
            assert output is not None
            output_path = LocalMediaStorage(settings).absolute_path(output.storage_path)
        assert output_path.read_bytes() == b"\x00\x00\x00\x18ftypmp42concept-video"
