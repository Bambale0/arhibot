import os
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

pytestmark = pytest.mark.integration
if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True
    )

from app.core.config import get_settings
from app.core.redis import redis_client
from app.db.models.generations import Generation
from app.db.models.users import User
from app.db.session import dispose_engine, get_session_factory
from app.domain.generations.enums import GenerationStatus
from app.domain.users.enums import UserRole
from app.main import app
from app.providers.nexus import NexusImageProvider, NexusImageResult, NexusOutcomeUnknown
from app.services.asset_service import LocalMediaStorage
from app.services.generation_service import GENERATION_QUEUE_KEY
from app.workers import generation_worker as worker


def png(index):
    b = BytesIO()
    Image.new("RGB", (96, 64), (100 + index * 10, 120, 140)).save(b, format="PNG")
    return b.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["orbit", "flyover-gif"])
@pytest.mark.parametrize(
    "fault",
    ["accepted_timeout", "download_timeout", "unknown_submit", "missing_cache", "corrupt_cache"],
)
async def test_admin_animation_resumes_accepted_frame_without_rebuying_completed_frames(
    monkeypatch, kind, fault
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        reg = await c.post(
            "/api/v1/auth/register",
            json={
                "email": str(uuid4()) + "@example.com",
                "password": "animation-strong-password",
                "display_name": "Animation recovery QA",
            },
        )
        assert reg.status_code == 201
        t = reg.json()
        h = {"Authorization": "Bearer " + t["access_token"]}
        async with get_session_factory()() as db:
            u = await db.get(User, UUID(t["user"]["id"]))
            u.role = UserRole.ADMIN
            await db.commit()

        async def source_generate(self, **kw):
            if kw.get("on_task_created"):
                await kw["on_task_created"]("source-task")
            return NexusImageResult(task_id="source-task", image_url="https://test.invalid/0")

        download_failed = False

        async def download(url, settings):
            nonlocal download_failed
            index = int(url.rsplit("/", 1)[-1])
            if fault == "download_timeout" and index == 2 and not download_failed:
                download_failed = True
                raise TimeoutError("accepted image download timed out")
            return png(index)

        monkeypatch.setattr(NexusImageProvider, "generate", source_generate)
        monkeypatch.setattr(worker, "_download_image", download)
        s = await c.post(
            "/api/v1/admin/generation/sandbox",
            headers=h,
            json={"model_name": "isolated", "prompt": "house", "params": {}},
        )
        assert s.status_code == 202
        sid = UUID(s.json()["id"])
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(sid))
        await worker.process_generation(sid, get_settings())
        body = {"source_generation_id": str(sid), "model_name": "isolated", "params": {}}
        body.update(
            {"frame_count": 6} if kind == "orbit" else {"keyframe_count": 4, "inbetween_frames": 0}
        )
        x = await c.post("/api/v1/admin/generation/" + kind, headers=h, json=body)
        assert x.status_code == 202, x.text
        gid = UUID(x.json()["id"])
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(gid))
        calls = []
        timed_out = False

        async def frame_generate(self, **kw):
            nonlocal timed_out
            index = int(kw["idempotency_key"].rsplit("-", 1)[-1])
            calls.append({"index": index, "resume": kw.get("task_id")})
            if index == 2 and fault == "unknown_submit":
                raise NexusOutcomeUnknown("provider accepted no known task ID")
            if kw.get("on_task_created"):
                await kw["on_task_created"]("frame-" + str(index))
            if index == 2 and not timed_out and fault != "download_timeout":
                timed_out = True
                raise NexusOutcomeUnknown("accepted frame still rendering")
            return NexusImageResult(
                task_id="frame-" + str(index), image_url="https://test.invalid/" + str(index)
            )

        monkeypatch.setattr(NexusImageProvider, "generate", frame_generate)
        await worker.process_generation(gid, get_settings())
        async with get_session_factory()() as db:
            pending = await db.get(Generation, gid)
            phase = "orbit-2" if kind == "orbit" else "flyover-2"
            checkpoints = pending.quality_report["provider_frame_requests"]
            assert checkpoints[phase]["task_id"] == (
                None if fault == "unknown_submit" else "frame-2"
            )
            assert pending.quality_report["requires_reconciliation"]
        storage = LocalMediaStorage(get_settings())
        cached_path = storage.absolute_path(checkpoints[phase.replace("-2", "-1")]["path"])
        assert cached_path.is_file(), "completed frames survive a pending task"
        if fault == "missing_cache":
            cached_path.unlink()
        elif fault == "corrupt_cache":
            cached_path.write_bytes(b"corrupt")
        await worker._reconcile_database_jobs(get_settings())
        if fault == "unknown_submit":
            assert str(gid) not in await redis_client.lrange(GENERATION_QUEUE_KEY, 0, -1)
            before = list(calls)
            async with get_session_factory()() as db:
                pending = await db.get(Generation, gid)
                pending.status = GenerationStatus.QUEUED
                await db.commit()
            await worker.process_generation(gid, get_settings())
            assert calls == before, "an unacknowledged POST must never be purchased again"
            await worker._mark_failed_and_refund(gid, "isolated test cleanup")
            await worker._cleanup_admin_frames(gid, get_settings())
            assert not cached_path.parent.exists()
            return
        assert str(gid) in await redis_client.lrange(GENERATION_QUEUE_KEY, 0, -1)
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(gid))
        before = list(calls)
        await worker.process_generation(gid, get_settings())
        result = await c.get("/api/v1/generations/" + str(gid), headers=h)
        assert not cached_path.parent.exists(), "terminal tasks release temporary frame storage"
        if fault in {"missing_cache", "corrupt_cache"}:
            assert result.json()["status"] == "failed", result.text
            assert calls == before, "validate all cached frames before further purchases"
            return
        assert result.json()["status"] == "completed", result.text
        count = 5 if kind == "orbit" else 3
        assert sorted(x["index"] for x in calls if not x["resume"]) == list(range(1, count + 1))
        assert [x for x in calls if x["resume"]] == [{"index": 2, "resume": "frame-2"}]
    await redis_client.aclose()
    await dispose_engine()
