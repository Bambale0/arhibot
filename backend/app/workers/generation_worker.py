from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.redis import redis_client
from app.db.models.assets import Asset
from app.db.models.generations import Generation
from app.db.models.projects import Project
from app.db.session import dispose_engine, get_session_factory
from app.domain.assets.enums import AssetPurpose, AssetType
from app.domain.generations.enums import GenerationStatus
from app.prompt_builders.generation import build_generation_prompt
from app.providers.nexus import NexusImageProvider, NexusProviderError
from app.repositories.admin import AdminRepository
from app.repositories.assets import AssetRepository
from app.repositories.generations import GenerationRepository
from app.repositories.projects import ProjectRepository
from app.services.asset_service import AssetService
from app.services.credit_service import CreditService
from app.services.generation_service import GENERATION_QUEUE_KEY

logger = logging.getLogger(__name__)
GENERATION_PROCESSING_KEY = "auroom:generation_processing"


async def _download_image(url: str, settings: Settings) -> bytes:
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0), follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > settings.max_image_size_bytes:
            raise RuntimeError("Generated image exceeds media size limit")
        data = response.content
    if len(data) > settings.max_image_size_bytes:
        raise RuntimeError("Generated image exceeds media size limit")
    return data


async def _mark_failed_and_refund(generation_id: UUID, error: Exception | str) -> None:
    async with get_session_factory()() as session:
        generation = await session.get(Generation, generation_id)
        if generation is None or generation.status == GenerationStatus.COMPLETED:
            return
        generation.status = GenerationStatus.FAILED
        generation.error = str(error)[:1000] or "Generation failed"
        generation.completed_at = datetime.now(UTC)
        if generation.credits_charged > 0:
            await CreditService(session).apply(
                user_id=generation.user_id,
                amount=generation.credits_charged,
                kind="generation_refund",
                idempotency_key=f"generation:{generation.id}:refund",
                reference_type="generation",
                reference_id=str(generation.id),
                reason=generation.error,
            )
        await session.commit()


async def process_generation(generation_id: UUID, settings: Settings) -> None:
    async with get_session_factory()() as session:
        generation = await GenerationRepository(session).get_for_update(generation_id)
        if generation is None or generation.status != GenerationStatus.QUEUED:
            return
        project = await session.get(Project, generation.project_id)
        input_asset = (
            await session.get(Asset, generation.input_asset_id)
            if generation.input_asset_id is not None
            else None
        )
        if project is None:
            await session.rollback()
            await _mark_failed_and_refund(generation_id, "Generation project is no longer available.")
            return
        if generation.input_asset_id is not None and (
            input_asset is None or input_asset.deleted_at is not None
        ):
            await session.rollback()
            await _mark_failed_and_refund(generation_id, "Generation input is no longer available.")
            return

        admin_repository = AdminRepository(session)
        runtime = await admin_repository.get_generation_settings()
        prompt_template = await admin_repository.get_prompt_template(generation.type.value)
        if (
            runtime is None
            or not runtime.primary_model.strip()
            or prompt_template is None
            or not prompt_template.template.strip()
        ):
            await session.rollback()
            await _mark_failed_and_refund(
                generation_id,
                "Generation is not configured in AuRoom admin.",
            )
            return

        generation.status = GenerationStatus.PROCESSING
        generation.started_at = datetime.now(UTC)
        generation.error = None
        await session.commit()

        asset_service = AssetService(
            AssetRepository(session),
            ProjectRepository(session),
            settings,
        )
        source_url = (
            asset_service.storage.public_url(input_asset.storage_path)
            if input_asset is not None
            else None
        )
        prompt = build_generation_prompt(prompt_template.template, generation.prompt, project)
        mode_params = dict((runtime.mode_params or {}).get(generation.type.value) or {})
        primary_params = {**dict(runtime.primary_params or {}), **mode_params}
        fallback_params = {**dict(runtime.fallback_params or {}), **mode_params}
        primary_model = runtime.primary_model
        fallback_model = runtime.fallback_model

    provider = NexusImageProvider(settings)
    model_name = primary_model
    fallback_used = False
    try:
        try:
            result = await provider.generate(
                model_name=model_name,
                prompt=prompt,
                image_url=source_url,
                model_params=primary_params,
                idempotency_key=f"auroom-{generation_id}-primary",
            )
        except NexusProviderError as primary_error:
            if not primary_error.retryable or not fallback_model:
                raise
            logger.warning(
                "Primary Nexus model failed for %s; using admin-configured fallback: %s",
                generation_id,
                primary_error,
            )
            model_name = fallback_model
            fallback_used = True
            result = await provider.generate(
                model_name=model_name,
                prompt=prompt,
                image_url=source_url,
                model_params=fallback_params,
                idempotency_key=f"auroom-{generation_id}-fallback",
            )

        data = await _download_image(result.image_url, settings)

        async with get_session_factory()() as session:
            generation = await session.get(Generation, generation_id)
            if generation is None:
                return
            asset_service = AssetService(
                AssetRepository(session),
                ProjectRepository(session),
                settings,
            )
            image = asset_service._validate_image(data)
            asset_id = uuid4()
            now = datetime.now(UTC)
            relative_path = f"users/{generation.user_id}/{now:%Y/%m}/{asset_id}.{image.extension}"
            await asset_service.storage.write(relative_path, image.data)

            output = Asset(
                id=asset_id,
                user_id=generation.user_id,
                project_id=generation.project_id,
                type=AssetType.IMAGE,
                purpose=AssetPurpose.GENERATION_OUTPUT,
                original_filename=f"auroom-{generation.type.value}.{image.extension}",
                mime_type=image.mime_type,
                size_bytes=len(image.data),
                width=image.width,
                height=image.height,
                storage_path=relative_path,
            )
            session.add(output)
            generation.output_asset_id = output.id
            generation.model_name = model_name
            generation.fallback_used = fallback_used
            generation.provider_task_id = result.task_id
            generation.status = GenerationStatus.COMPLETED
            generation.error = None
            generation.completed_at = datetime.now(UTC)
            await session.commit()
            logger.info(
                "Generation %s completed with %s%s",
                generation_id,
                model_name,
                " (fallback)" if fallback_used else "",
            )
    except Exception as exc:
        logger.exception("Generation %s failed", generation_id)
        await _mark_failed_and_refund(generation_id, exc)


async def _reconcile_database_jobs(settings: Settings) -> None:
    """Rehydrate Redis from PostgreSQL after Redis/AOF loss.

    QUEUED rows are always safe to enqueue when they are absent from both Redis lists.
    PROCESSING rows are recovered only after the provider timeout window, which avoids
    stealing genuinely active work during a short worker overlap.
    """
    queued_raw = await redis_client.lrange(GENERATION_QUEUE_KEY, 0, -1)
    processing_raw = await redis_client.lrange(GENERATION_PROCESSING_KEY, 0, -1)
    redis_ids = {str(value) for value in [*queued_raw, *processing_raw]}
    stale_before = datetime.now(UTC) - timedelta(
        seconds=max(int(settings.nexus_task_timeout_seconds) + 60, 300)
    )
    recovered: list[str] = []

    async with get_session_factory()() as session:
        result = await session.execute(
            select(Generation)
            .where(Generation.status.in_([GenerationStatus.QUEUED, GenerationStatus.PROCESSING]))
            .order_by(Generation.created_at.asc())
            .with_for_update(skip_locked=True)
        )
        for generation in result.scalars().all():
            raw_id = str(generation.id)
            if raw_id in redis_ids:
                continue
            if generation.status == GenerationStatus.PROCESSING:
                if generation.started_at is not None and generation.started_at > stale_before:
                    continue
                generation.status = GenerationStatus.QUEUED
                generation.started_at = None
                generation.error = None
            recovered.append(raw_id)
        if recovered:
            await session.commit()

    for raw_id in recovered:
        await redis_client.rpush(GENERATION_QUEUE_KEY, raw_id)
    if recovered:
        logger.warning("Rehydrated %s generation job(s) from PostgreSQL", len(recovered))


async def _recover_reserved_jobs() -> None:
    reserved = await redis_client.lrange(GENERATION_PROCESSING_KEY, 0, -1)
    if not reserved:
        return
    recovered = 0
    for raw_id in reserved:
        try:
            generation_id = UUID(raw_id)
        except (TypeError, ValueError):
            await redis_client.lrem(GENERATION_PROCESSING_KEY, 0, raw_id)
            continue
        should_requeue = False
        async with get_session_factory()() as session:
            generation = await session.get(Generation, generation_id)
            if generation is not None and generation.status in {
                GenerationStatus.QUEUED,
                GenerationStatus.PROCESSING,
            }:
                generation.status = GenerationStatus.QUEUED
                generation.started_at = None
                generation.error = None
                await session.commit()
                should_requeue = True
        await redis_client.lrem(GENERATION_PROCESSING_KEY, 0, raw_id)
        if should_requeue:
            await redis_client.rpush(GENERATION_QUEUE_KEY, raw_id)
            recovered += 1
    if recovered:
        logger.warning("Recovered %s reserved generation job(s) after worker restart", recovered)


async def _reserve_job() -> str | None:
    raw_id = await redis_client.lmove(
        GENERATION_QUEUE_KEY,
        GENERATION_PROCESSING_KEY,
        "LEFT",
        "RIGHT",
    )
    return raw_id


async def _ack_job(raw_id: str) -> None:
    await redis_client.lrem(GENERATION_PROCESSING_KEY, 1, raw_id)


async def run_worker() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("AuRoom generation worker started; queue uses reserve/ack recovery")
    await _recover_reserved_jobs()
    await _reconcile_database_jobs(settings)
    reconcile_tick = 0
    while True:
        try:
            reconcile_tick += 1
            if reconcile_tick >= 60:
                await _reconcile_database_jobs(settings)
                reconcile_tick = 0
            raw_id = await _reserve_job()
            if raw_id is None:
                await asyncio.sleep(1)
                continue
            try:
                await process_generation(UUID(raw_id), settings)
            except Exception:
                # Keep the reservation in the processing list. It will be recovered
                # on worker restart instead of silently losing a paid generation.
                logger.exception("Reserved generation %s crashed before terminal state", raw_id)
                await asyncio.sleep(2)
            else:
                await _ack_job(raw_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Generation worker iteration failed")
            await asyncio.sleep(2)


async def _main() -> None:
    try:
        await run_worker()
    finally:
        await redis_client.aclose()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
