from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from app.architecture.glb import CanonicalGlbBuilder
from app.architecture.schemas import ArchitecturePackage
from app.core.config import Settings, get_settings
from app.core.redis import redis_client
from app.db.models.architecture_renders import ArchitectureRender
from app.db.models.assets import Asset
from app.db.session import dispose_engine, get_session_factory
from app.domain.architecture.enums import ArchitectureCameraProfile, ArchitectureRenderStatus
from app.domain.assets.enums import AssetPurpose, AssetType
from app.renderers.blender import BlenderRenderer
from app.renderers.blender_profiles import build_blender_v2_config
from app.renderers.quality import score_render_quality
from app.services.architecture_render_publication_service import ArchitectureRenderPublicationService
from app.services.architecture_render_service import (
    ARCHITECTURE_RENDER_QUEUE_KEY,
    RENDERER_PROFILE_V1,
    RENDERER_PROFILE_V2,
    digest_architecture_payload,
)
from app.services.asset_service import LocalMediaStorage

logger = logging.getLogger(__name__)
ARCHITECTURE_RENDER_PROCESSING_KEY = "auroom:architecture_render_processing"
_STALE_PROCESSING_AFTER = timedelta(minutes=10)
_TERMINAL_STATUSES = {
    ArchitectureRenderStatus.COMPLETED,
    ArchitectureRenderStatus.FAILED,
}


async def _try_finalize_batch(batch_id: UUID | None, settings: Settings) -> None:
    if batch_id is None:
        return
    try:
        async with get_session_factory()() as session:
            result = await ArchitectureRenderPublicationService(session, settings).finalize(batch_id)
        if result.published:
            logger.info(
                "Architecture render batch %s published render %s to Idea %s",
                batch_id,
                result.winner_render_id,
                result.target_idea_id,
            )
        elif result.resolved and result.skip_reason:
            logger.warning(
                "Architecture render batch %s resolved without publication: %s",
                batch_id,
                result.skip_reason,
            )
    except Exception:
        logger.exception("Architecture render batch %s finalization failed", batch_id)


async def _mark_failed(render_id: UUID, error: Exception | str) -> UUID | None:
    async with get_session_factory()() as session:
        render = await session.get(ArchitectureRender, render_id)
        if render is None:
            return None
        batch_id = render.batch_id
        if render.status == ArchitectureRenderStatus.COMPLETED:
            return batch_id
        render.status = ArchitectureRenderStatus.FAILED
        render.error = str(error)[:2000] or "Architecture render failed"
        render.completed_at = datetime.now(UTC)
        await session.commit()
        return batch_id


async def process_render(render_id: UUID, settings: Settings, renderer: BlenderRenderer) -> None:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(ArchitectureRender)
            .where(ArchitectureRender.id == render_id)
            .with_for_update()
        )
        render = result.scalar_one_or_none()
        if render is None or render.status != ArchitectureRenderStatus.QUEUED:
            return

        batch_id = render.batch_id
        try:
            if digest_architecture_payload(render.architecture) != render.source_digest:
                raise RuntimeError("Architecture render snapshot digest mismatch")
            package = ArchitecturePackage.model_validate(render.architecture)
            camera_profile = ArchitectureCameraProfile(render.camera_profile)
            renderer_profile = render.renderer_profile
        except Exception as exc:
            render.status = ArchitectureRenderStatus.FAILED
            render.error = str(exc)[:2000] or "Architecture render snapshot is invalid"
            render.completed_at = datetime.now(UTC)
            await session.commit()
            logger.error("Architecture render %s rejected before Blender: %s", render_id, exc)
            await _try_finalize_batch(batch_id, settings)
            return

        render.status = ArchitectureRenderStatus.PROCESSING
        render.started_at = datetime.now(UTC)
        render.completed_at = None
        render.error = None
        await session.commit()
        user_id = render.user_id
        project_id = render.project_id

    try:
        glb = CanonicalGlbBuilder().build(package)
        if glb.warnings:
            logger.warning("Architecture render %s GLB fidelity warnings: %s", render_id, glb.warnings)

        if renderer_profile == RENDERER_PROFILE_V1:
            rendered = await renderer.render(glb.data)
        elif renderer_profile == RENDERER_PROFILE_V2:
            config = build_blender_v2_config(package, camera_profile)
            rendered = await renderer.render(glb.data, config=config)
        else:
            raise RuntimeError(f"Unsupported architecture renderer profile: {renderer_profile}")

        if len(rendered.data) > settings.max_image_size_bytes:
            raise RuntimeError("Blender render exceeds the configured media size limit")
        if rendered.width * rendered.height > settings.max_image_pixels:
            raise RuntimeError("Blender render exceeds the configured pixel limit")

        quality = score_render_quality(rendered.data)
        asset_id = uuid4()
        now = datetime.now(UTC)
        relative_path = f"users/{user_id}/{now:%Y/%m}/architecture-renders/{asset_id}.png"
        storage = LocalMediaStorage(settings)
        await storage.write(relative_path, rendered.data)
        target = storage.absolute_path(relative_path)

        try:
            async with get_session_factory()() as session:
                result = await session.execute(
                    select(ArchitectureRender)
                    .where(ArchitectureRender.id == render_id)
                    .with_for_update()
                )
                render = result.scalar_one_or_none()
                if render is None or render.status != ArchitectureRenderStatus.PROCESSING:
                    await asyncio.to_thread(target.unlink, missing_ok=True)
                    return

                output = Asset(
                    id=asset_id,
                    user_id=user_id,
                    project_id=project_id,
                    type=AssetType.IMAGE,
                    purpose=AssetPurpose.ARCHITECTURE_RENDER_OUTPUT,
                    original_filename=f"architecture-{camera_profile.value}.png",
                    mime_type="image/png",
                    size_bytes=len(rendered.data),
                    width=rendered.width,
                    height=rendered.height,
                    storage_path=relative_path,
                )
                session.add(output)
                render.status = ArchitectureRenderStatus.COMPLETED
                render.renderer_version = rendered.renderer_version
                render.storage_path = relative_path
                render.output_asset_id = output.id
                render.width = rendered.width
                render.height = rendered.height
                render.quality_score = quality.score
                render.quality_report = quality.report
                render.error = None
                render.completed_at = datetime.now(UTC)
                batch_id = render.batch_id
                await session.commit()
        except Exception:
            await asyncio.to_thread(target.unlink, missing_ok=True)
            raise

        logger.info(
            "Architecture render %s completed with %s (%s, %s, quality=%s)",
            render_id,
            rendered.renderer_version,
            renderer_profile,
            camera_profile.value,
            quality.score,
        )
        await _try_finalize_batch(batch_id, settings)
    except Exception as exc:
        logger.exception("Architecture render %s failed", render_id)
        batch_id = await _mark_failed(render_id, exc)
        await _try_finalize_batch(batch_id, settings)


async def _recover_reserved_jobs() -> None:
    reserved = await redis_client.lrange(ARCHITECTURE_RENDER_PROCESSING_KEY, 0, -1)
    stale_before = datetime.now(UTC) - _STALE_PROCESSING_AFTER

    for raw_id in reserved:
        try:
            render_id = UUID(raw_id)
        except (TypeError, ValueError):
            await redis_client.lrem(ARCHITECTURE_RENDER_PROCESSING_KEY, 1, raw_id)
            continue

        remove_reservation = False
        should_requeue = False
        async with get_session_factory()() as session:
            result = await session.execute(
                select(ArchitectureRender)
                .where(ArchitectureRender.id == render_id)
                .with_for_update()
            )
            render = result.scalar_one_or_none()
            if render is None or render.status in _TERMINAL_STATUSES:
                remove_reservation = True
            elif render.status == ArchitectureRenderStatus.QUEUED:
                remove_reservation = True
                should_requeue = True
            elif render.status == ArchitectureRenderStatus.PROCESSING and (
                render.started_at is None or render.started_at <= stale_before
            ):
                render.status = ArchitectureRenderStatus.QUEUED
                render.started_at = None
                render.error = None
                render.completed_at = None
                await session.commit()
                remove_reservation = True
                should_requeue = True

        if not remove_reservation:
            continue
        removed = await redis_client.lrem(ARCHITECTURE_RENDER_PROCESSING_KEY, 1, raw_id)
        if should_requeue and removed:
            await redis_client.rpush(ARCHITECTURE_RENDER_QUEUE_KEY, raw_id)


async def _reconcile_database_jobs() -> None:
    queued_raw = await redis_client.lrange(ARCHITECTURE_RENDER_QUEUE_KEY, 0, -1)
    processing_raw = await redis_client.lrange(ARCHITECTURE_RENDER_PROCESSING_KEY, 0, -1)
    redis_ids = {str(value) for value in [*queued_raw, *processing_raw]}
    stale_before = datetime.now(UTC) - _STALE_PROCESSING_AFTER
    recovered: list[str] = []

    async with get_session_factory()() as session:
        result = await session.execute(
            select(ArchitectureRender)
            .where(
                ArchitectureRender.status.in_(
                    [ArchitectureRenderStatus.QUEUED, ArchitectureRenderStatus.PROCESSING]
                )
            )
            .order_by(ArchitectureRender.created_at.asc())
            .with_for_update(skip_locked=True)
        )
        for render in result.scalars().all():
            raw_id = str(render.id)
            if raw_id in redis_ids:
                continue
            if render.status == ArchitectureRenderStatus.PROCESSING:
                if render.started_at is not None and render.started_at > stale_before:
                    continue
                render.status = ArchitectureRenderStatus.QUEUED
                render.started_at = None
                render.error = None
                render.completed_at = None
            recovered.append(raw_id)
        if recovered:
            await session.commit()

    for raw_id in recovered:
        await redis_client.rpush(ARCHITECTURE_RENDER_QUEUE_KEY, raw_id)
    if recovered:
        logger.warning("Rehydrated %s architecture render job(s) from PostgreSQL", len(recovered))


async def _reconcile_batch_finalization(settings: Settings) -> None:
    selected_batches = select(ArchitectureRender.batch_id).where(
        ArchitectureRender.batch_id.is_not(None),
        ArchitectureRender.selected_for_batch.is_(True),
    )
    async with get_session_factory()() as session:
        result = await session.execute(
            select(ArchitectureRender.batch_id)
            .where(
                ArchitectureRender.batch_id.is_not(None),
                ArchitectureRender.batch_id.notin_(selected_batches),
                ArchitectureRender.status == ArchitectureRenderStatus.COMPLETED,
            )
            .distinct()
            .limit(100)
        )
        batch_ids = [batch_id for batch_id in result.scalars().all() if batch_id is not None]

    for batch_id in batch_ids:
        await _try_finalize_batch(batch_id, settings)


async def _reserve_job() -> str | None:
    return await redis_client.lmove(
        ARCHITECTURE_RENDER_QUEUE_KEY,
        ARCHITECTURE_RENDER_PROCESSING_KEY,
        "LEFT",
        "RIGHT",
    )


async def _ack_job(raw_id: str) -> None:
    await redis_client.lrem(ARCHITECTURE_RENDER_PROCESSING_KEY, 1, raw_id)


async def run_worker() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    renderer = BlenderRenderer()
    version = await renderer.version()
    logger.info("AuRoom architecture renderer started with %s", version)
    await _recover_reserved_jobs()
    await _reconcile_database_jobs()
    await _reconcile_batch_finalization(settings)
    reconcile_tick = 0

    while True:
        try:
            reconcile_tick += 1
            if reconcile_tick >= 60:
                await _recover_reserved_jobs()
                await _reconcile_database_jobs()
                await _reconcile_batch_finalization(settings)
                reconcile_tick = 0
            raw_id = await _reserve_job()
            if raw_id is None:
                await asyncio.sleep(1)
                continue
            try:
                await process_render(UUID(raw_id), settings, renderer)
            except Exception:
                logger.exception("Reserved architecture render %s crashed", raw_id)
                await asyncio.sleep(2)
                await _recover_reserved_jobs()
            else:
                await _ack_job(raw_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Architecture render worker iteration failed")
            await asyncio.sleep(2)


async def _main() -> None:
    try:
        await run_worker()
    finally:
        await redis_client.aclose()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
