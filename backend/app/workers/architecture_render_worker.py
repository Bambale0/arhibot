from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select

from app.architecture.glb import CanonicalGlbBuilder
from app.architecture.render_selection import RenderCandidate, choose_batch_winner
from app.architecture.schemas import ArchitecturePackage
from app.core.config import Settings, get_settings
from app.core.redis import redis_client
from app.db.models.admin import IdeaTemplate
from app.db.models.architecture_renders import ArchitectureRender
from app.db.models.assets import Asset
from app.db.models.projects import Project
from app.db.session import dispose_engine, get_session_factory
from app.domain.architecture.enums import ArchitectureCameraProfile, ArchitectureRenderStatus
from app.domain.assets.enums import AssetPurpose, AssetType
from app.renderers.blender import BlenderRenderer
from app.renderers.blender_profiles import build_blender_v2_config
from app.renderers.quality import score_render_quality
from app.repositories.admin import AdminRepository
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


def _current_project_digest(project: Project) -> str | None:
    raw = (project.context or {}).get("architecture")
    if not isinstance(raw, dict):
        return None
    try:
        package = ArchitecturePackage.model_validate(raw)
    except ValidationError:
        return None
    payload = package.model_dump(mode="json", exclude_none=True)
    return digest_architecture_payload(payload)


def _candidate(render: ArchitectureRender) -> RenderCandidate | None:
    if (
        render.status != ArchitectureRenderStatus.COMPLETED
        or render.output_asset_id is None
        or render.quality_score is None
    ):
        return None
    try:
        camera_profile = ArchitectureCameraProfile(render.camera_profile)
    except ValueError:
        return None
    return RenderCandidate(
        render_id=render.id,
        camera_profile=camera_profile,
        quality_score=float(render.quality_score),
        technically_usable=bool((render.quality_report or {}).get("technically_usable")),
    )


def _audit_batch_skip(
    repository: AdminRepository,
    winner: ArchitectureRender,
    *,
    reason: str,
) -> None:
    repository.add_audit(
        actor_user_id=winner.user_id,
        action="idea.architecture_render_batch.skip",
        entity_type="idea",
        entity_id=str(winner.target_idea_id) if winner.target_idea_id else None,
        details={
            "batch_id": str(winner.batch_id) if winner.batch_id else None,
            "render_id": str(winner.id),
            "project_id": str(winner.project_id),
            "source_digest": winner.source_digest,
            "camera_profile": winner.camera_profile,
            "quality_score": winner.quality_score,
            "reason": reason,
        },
    )


async def _finalize_batch(batch_id: UUID, settings: Settings) -> None:
    storage = LocalMediaStorage(settings)
    new_model_path: str | None = None
    previous_model_path: str | None = None

    async with get_session_factory()() as session:
        result = await session.execute(
            select(ArchitectureRender)
            .where(ArchitectureRender.batch_id == batch_id)
            .order_by(ArchitectureRender.created_at.asc(), ArchitectureRender.id.asc())
            .with_for_update()
        )
        renders = list(result.scalars().all())
        if not renders or any(render.status not in _TERMINAL_STATUSES for render in renders):
            return
        if any(render.selected_for_batch for render in renders):
            return

        candidates = [candidate for render in renders if (candidate := _candidate(render))]
        winner_candidate = choose_batch_winner(candidates)
        if winner_candidate is None:
            return

        winner = next(render for render in renders if render.id == winner_candidate.render_id)
        winner.selected_for_batch = True
        if winner.target_idea_id is None:
            await session.commit()
            return

        admin_repository = AdminRepository(session)
        idea_result = await session.execute(
            select(IdeaTemplate)
            .where(IdeaTemplate.id == winner.target_idea_id)
            .with_for_update()
        )
        idea = idea_result.scalar_one_or_none()
        if idea is None:
            _audit_batch_skip(admin_repository, winner, reason="idea_not_found")
            await session.commit()
            return
        if idea.architecture_project_id != winner.project_id:
            _audit_batch_skip(admin_repository, winner, reason="idea_project_changed")
            await session.commit()
            return

        project = await session.get(Project, winner.project_id)
        if project is None or _current_project_digest(project) != winner.source_digest:
            _audit_batch_skip(admin_repository, winner, reason="architecture_changed_after_enqueue")
            await session.commit()
            return
        if not winner_candidate.technically_usable:
            _audit_batch_skip(admin_repository, winner, reason="winner_failed_technical_qa")
            await session.commit()
            return

        output_asset = await session.get(Asset, winner.output_asset_id)
        if (
            output_asset is None
            or output_asset.deleted_at is not None
            or output_asset.user_id != winner.user_id
            or output_asset.project_id != winner.project_id
        ):
            _audit_batch_skip(admin_repository, winner, reason="winner_asset_unavailable")
            await session.commit()
            return

        try:
            package = ArchitecturePackage.model_validate(winner.architecture)
        except ValidationError:
            _audit_batch_skip(admin_repository, winner, reason="immutable_snapshot_invalid")
            await session.commit()
            return
        glb = CanonicalGlbBuilder().build(package)
        if len(glb.data) > settings.max_model_size_bytes:
            _audit_batch_skip(admin_repository, winner, reason="canonical_glb_too_large")
            await session.commit()
            return

        new_model_path = f"ideas/{idea.id}/models/architecture-{batch_id}.glb"
        previous_model_path = idea.model_storage_path
        await storage.write(new_model_path, glb.data)

        idea.image_asset_id = output_asset.id
        idea.architecture_snapshot = winner.architecture
        idea.model_storage_path = new_model_path
        idea.model_original_filename = f"architecture-{batch_id}.glb"
        idea.model_size_bytes = len(glb.data)
        admin_repository.add_audit(
            actor_user_id=winner.user_id,
            action="idea.architecture_render_batch.publish",
            entity_type="idea",
            entity_id=str(idea.id),
            details={
                "batch_id": str(batch_id),
                "render_id": str(winner.id),
                "project_id": str(winner.project_id),
                "source_digest": winner.source_digest,
                "camera_profile": winner.camera_profile,
                "quality_score": winner.quality_score,
                "output_asset_id": str(output_asset.id),
                "model_size_bytes": len(glb.data),
            },
        )

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            if new_model_path:
                target = storage.absolute_path(new_model_path)
                if target.exists():
                    await asyncio.to_thread(target.unlink, missing_ok=True)
            raise

    if previous_model_path and previous_model_path != new_model_path:
        previous = storage.absolute_path(previous_model_path)
        if previous.exists():
            await asyncio.to_thread(previous.unlink, missing_ok=True)

    logger.info(
        "Architecture render batch %s published render %s to Idea %s",
        batch_id,
        winner_candidate.render_id,
        renders[0].target_idea_id,
    )


async def _try_finalize_batch(batch_id: UUID | None, settings: Settings) -> None:
    if batch_id is None:
        return
    try:
        await _finalize_batch(batch_id, settings)
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
    async with get_session_factory()() as session:
        result = await session.execute(
            select(ArchitectureRender.batch_id)
            .where(
                ArchitectureRender.batch_id.is_not(None),
                ArchitectureRender.status == ArchitectureRenderStatus.COMPLETED,
                ArchitectureRender.selected_for_batch.is_(False),
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
