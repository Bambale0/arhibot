from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx

from app.core.config import Settings, get_settings
from app.core.redis import redis_client
from app.db.models.assets import Asset
from app.db.models.generations import Generation
from app.db.models.projects import Project
from app.db.session import dispose_engine, get_session_factory
from app.domain.assets.enums import AssetPurpose, AssetType
from app.domain.generations.enums import GenerationStatus, GenerationType
from app.prompt_builders.generation import build_generation_prompt
from app.providers.nexus import NexusImageProvider, NexusProviderError
from app.repositories.assets import AssetRepository
from app.repositories.projects import ProjectRepository
from app.services.asset_service import AssetService
from app.services.generation_service import GENERATION_QUEUE_KEY

logger = logging.getLogger(__name__)

ASPECT_RATIOS: dict[GenerationType, str] = {
    GenerationType.FLOOR_PLAN: "1:1",
    GenerationType.FACADE: "16:9",
    GenerationType.MASTER_PLAN: "1:1",
    GenerationType.INTERIOR: "16:9",
}


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


async def _mark_failed(generation_id: UUID, error: Exception) -> None:
    async with get_session_factory()() as session:
        generation = await session.get(Generation, generation_id)
        if generation is None:
            return
        generation.status = GenerationStatus.FAILED
        generation.error = str(error)[:1000] or error.__class__.__name__
        generation.completed_at = datetime.now(UTC)
        await session.commit()


async def process_generation(generation_id: UUID, settings: Settings) -> None:
    async with get_session_factory()() as session:
        generation = await session.get(Generation, generation_id)
        if generation is None or generation.status != GenerationStatus.QUEUED:
            return
        project = await session.get(Project, generation.project_id)
        input_asset = await session.get(Asset, generation.input_asset_id)
        if project is None or input_asset is None or input_asset.deleted_at is not None:
            generation.status = GenerationStatus.FAILED
            generation.error = "Generation input is no longer available."
            generation.completed_at = datetime.now(UTC)
            await session.commit()
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
        source_url = asset_service.storage.public_url(input_asset.storage_path)
        prompt = build_generation_prompt(generation.type, generation.prompt, project)
        aspect_ratio = ASPECT_RATIOS[generation.type]

    provider = NexusImageProvider(settings)
    model_name = settings.nexus_primary_model
    fallback_used = False
    try:
        try:
            result = await provider.generate(
                model_name=model_name,
                prompt=prompt,
                image_url=source_url,
                aspect_ratio=aspect_ratio,
                idempotency_key=f"auroom-{generation_id}-primary",
            )
        except NexusProviderError as primary_error:
            if not primary_error.retryable:
                raise
            logger.warning(
                "Primary Nexus model failed for %s; using fallback: %s",
                generation_id,
                primary_error,
            )
            model_name = settings.nexus_fallback_model
            fallback_used = True
            result = await provider.generate(
                model_name=model_name,
                prompt=prompt,
                image_url=source_url,
                aspect_ratio=aspect_ratio,
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
        await _mark_failed(generation_id, exc)


async def run_worker() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info(
        "AuRoom generation worker started: primary=%s fallback=%s",
        settings.nexus_primary_model,
        settings.nexus_fallback_model,
    )
    while True:
        try:
            item = await redis_client.blpop(GENERATION_QUEUE_KEY, timeout=5)
            if item is None:
                continue
            _, raw_id = item
            await process_generation(UUID(raw_id), settings)
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
