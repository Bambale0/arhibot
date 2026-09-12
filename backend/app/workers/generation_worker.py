from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from json import JSONDecodeError, loads
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
from app.image_compositor import compose_masked_edit
from app.image_orbit import build_orbit_animation
from app.prompt_builders.generation import build_generation_prompt
from app.providers.nexus import NexusImageProvider, NexusProviderError
from app.repositories.admin import AdminRepository
from app.repositories.assets import AssetRepository
from app.repositories.generations import GenerationRepository
from app.repositories.projects import ProjectRepository
from app.services.asset_service import AssetService, LocalMediaStorage
from app.services.credit_service import CreditService
from app.services.generation_service import GENERATION_QUEUE_KEY
from app.workers.heartbeat import worker_heartbeat

logger = logging.getLogger(__name__)
GENERATION_PROCESSING_KEY = "auroom:generation_processing"
QUESTIONNAIRE_PROMPT_PREFIX = "AUROOM_RENDER_SPEC_V1"
INITIAL_CONCEPT_PROMPT_PREFIX = "AUROOM_INITIAL_CONCEPT_V1"
ADMIN_SANDBOX_PROMPT_PREFIX = "AUROOM_ADMIN_SANDBOX_V1\n"
ADMIN_ORBIT_PROMPT_PREFIX = "AUROOM_ADMIN_ORBIT_V1\n"
QUESTIONNAIRE_PROMPT_PREFIXES = (
    QUESTIONNAIRE_PROMPT_PREFIX,
    INITIAL_CONCEPT_PROMPT_PREFIX,
)
QUESTIONNAIRE_ASPECT_RATIOS = {"1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4, "16:9": 16 / 9, "9:16": 9 / 16}
RESERVED_PROVIDER_PARAMS = {"model_name", "prompt", "image_url", "image_urls"}


def _admin_sandbox_request(
    generation: Generation,
    project: Project,
) -> tuple[str, str, dict[str, object]] | None:
    if not generation.prompt.startswith(ADMIN_SANDBOX_PROMPT_PREFIX):
        return None
    if not bool((project.context or {}).get("admin_ai_sandbox")):
        raise ValueError("Admin sandbox envelope is outside the sandbox project.")
    model_name = (generation.model_name or "").strip()
    if not model_name:
        raise ValueError("Admin sandbox model is missing.")

    raw_payload = generation.prompt.removeprefix(ADMIN_SANDBOX_PROMPT_PREFIX)
    try:
        payload = loads(raw_payload)
    except JSONDecodeError as exc:
        raise ValueError("Admin sandbox envelope is invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Admin sandbox envelope must be an object.")

    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Admin sandbox prompt is missing.")
    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("Admin sandbox params must be an object.")
    conflict = RESERVED_PROVIDER_PARAMS.intersection(params)
    if conflict:
        raise ValueError(
            f"Admin sandbox params cannot override provider fields: {', '.join(sorted(conflict))}"
        )
    return model_name, prompt.strip(), params


def _admin_orbit_request(
    generation: Generation,
    project: Project,
) -> tuple[str, str, dict[str, object], int, int] | None:
    if not generation.prompt.startswith(ADMIN_ORBIT_PROMPT_PREFIX):
        return None
    if not bool((project.context or {}).get("admin_ai_sandbox")):
        raise ValueError("Admin orbit envelope is outside the sandbox project.")
    if generation.input_asset_id is None:
        raise ValueError("Admin orbit source image is missing.")

    model_name = (generation.model_name or "").strip()
    if not model_name:
        raise ValueError("Admin orbit model is missing.")

    raw_payload = generation.prompt.removeprefix(ADMIN_ORBIT_PROMPT_PREFIX)
    try:
        payload = loads(raw_payload)
    except JSONDecodeError as exc:
        raise ValueError("Admin orbit envelope is invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Admin orbit envelope must be an object.")

    prompt = payload.get("prompt", "")
    if not isinstance(prompt, str):
        raise ValueError("Admin orbit prompt must be a string.")
    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("Admin orbit params must be an object.")
    conflict = RESERVED_PROVIDER_PARAMS.intersection(params)
    if conflict:
        raise ValueError(
            f"Admin orbit params cannot override provider fields: {', '.join(sorted(conflict))}"
        )

    frame_count = payload.get("frame_count")
    frame_duration_ms = payload.get("frame_duration_ms")
    if not isinstance(frame_count, int) or not 6 <= frame_count <= 12:
        raise ValueError("Admin orbit frame count must be between 6 and 12.")
    if not isinstance(frame_duration_ms, int) or not 80 <= frame_duration_ms <= 1000:
        raise ValueError("Admin orbit frame duration is invalid.")
    return model_name, prompt.strip(), params, frame_count, frame_duration_ms


def _orbit_frame_prompt(extra_prompt: str, *, index: int, frame_count: int) -> str:
    azimuth = round((360 * index) / frame_count)
    prompt = (
        "Create one frame of a seamless clockwise 360-degree architectural drone orbit "
        "around the exact same scene shown in the reference image. "
        "Preserve the exact house and site geometry, object count, dimensions, roof, windows, "
        "materials, landscaping, lighting, weather, season and all design details. "
        "Move only the camera. Keep a consistent elevated drone height, focal length, horizon "
        "and subject scale across every frame. "
        f"This frame is {index + 1} of {frame_count}; camera azimuth is approximately "
        f"{azimuth} degrees clockwise from the reference view. "
        "Do not add, remove, redesign or relocate anything. No text, labels or borders."
    )
    if extra_prompt:
        prompt += f" Additional operator instruction: {extra_prompt}"
    return prompt


def _questionnaire_aspect_ratio(asset: Asset | None) -> str:
    if asset is None or not asset.width or not asset.height:
        return "16:9"
    ratio = asset.width / asset.height
    return min(QUESTIONNAIRE_ASPECT_RATIOS, key=lambda item: abs(QUESTIONNAIRE_ASPECT_RATIOS[item] - ratio))


async def _download_image(url: str, settings: Settings) -> bytes:
    if not url.startswith("https://"):
        raise RuntimeError("Generated image URL must use HTTPS")
    limit = settings.max_image_size_bytes
    chunks: list[bytes] = []
    received = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0), follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            if not str(response.url).startswith("https://"):
                raise RuntimeError("Generated image redirect must remain on HTTPS")
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > limit:
                        raise RuntimeError("Generated image exceeds media size limit")
                except ValueError:
                    # A malformed length header is not trusted; the streamed byte limit below
                    # remains authoritative.
                    pass
            async for chunk in response.aiter_bytes():
                received += len(chunk)
                if received > limit:
                    raise RuntimeError("Generated image exceeds media size limit")
                chunks.append(chunk)
    return b"".join(chunks)


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

        try:
            sandbox_request = _admin_sandbox_request(generation, project)
            orbit_request = _admin_orbit_request(generation, project)
        except ValueError as exc:
            await session.rollback()
            await _mark_failed_and_refund(generation_id, exc)
            return

        admin_internal_generation = (
            sandbox_request is not None or orbit_request is not None
        )
        admin_repository = AdminRepository(session)
        initial_concept_generation = generation.prompt.startswith(
            INITIAL_CONCEPT_PROMPT_PREFIX
        )
        questionnaire_generation = generation.prompt.startswith(
            QUESTIONNAIRE_PROMPT_PREFIXES
        )
        runtime = (
            None
            if admin_internal_generation
            else await admin_repository.get_generation_settings()
        )
        prompt_template = (
            None
            if questionnaire_generation or admin_internal_generation
            else await admin_repository.get_prompt_template(generation.type.value)
        )
        if not admin_internal_generation and (
            runtime is None
            or not runtime.primary_model.strip()
            or (
                not questionnaire_generation
                and (prompt_template is None or not prompt_template.template.strip())
            )
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
            asset_service.storage.signed_url(
                input_asset.storage_path,
                ttl_seconds=max(settings.media_url_ttl_seconds, settings.nexus_task_timeout_seconds + 120),
            )
            if input_asset is not None
            else None
        )
        if sandbox_request is not None:
            primary_model, prompt, primary_params = sandbox_request
            fallback_model = None
            fallback_params: dict[str, object] = {}
        elif orbit_request is not None:
            (
                primary_model,
                prompt,
                primary_params,
                _orbit_frame_count,
                _orbit_frame_duration_ms,
            ) = orbit_request
            fallback_model = None
            fallback_params = {}
        else:
            assert runtime is not None
            prompt = (
                generation.prompt
                if questionnaire_generation
                else build_generation_prompt(
                    prompt_template.template,
                    generation.prompt,
                    project,
                )
            )
            mode_params = dict((runtime.mode_params or {}).get(generation.type.value) or {})
            if questionnaire_generation:
                # Questionnaire renders are all exterior scene images. Legacy generation types are
                # an internal billing/provider detail and must not force a conflicting aspect ratio.
                mode_params["aspect_ratio"] = (
                    "16:9"
                    if initial_concept_generation
                    else _questionnaire_aspect_ratio(input_asset)
                )
            primary_params = {**dict(runtime.primary_params or {}), **mode_params}
            fallback_params = {**dict(runtime.fallback_params or {}), **mode_params}
            primary_model = runtime.primary_model
            fallback_model = runtime.fallback_model
        composition_mode = generation.composition_mode
        edit_region = dict(generation.edit_region) if generation.edit_region else None
        protected_regions = list(generation.protected_regions or [])
        input_storage_path = input_asset.storage_path if input_asset is not None else None

    provider = NexusImageProvider(settings)
    model_name = primary_model
    fallback_used = False
    provider_task_id: str | None = None
    try:
        if orbit_request is not None:
            if source_url is None or input_storage_path is None:
                raise RuntimeError("Orbit generation requires a source image.")
            _, orbit_prompt, orbit_params, frame_count, frame_duration_ms = orbit_request
            base_path = LocalMediaStorage(settings).absolute_path(input_storage_path)
            base_data = await asyncio.to_thread(base_path.read_bytes)
            frames = [base_data]
            for index in range(1, frame_count):
                result = await provider.generate(
                    model_name=model_name,
                    prompt=_orbit_frame_prompt(
                        orbit_prompt,
                        index=index,
                        frame_count=frame_count,
                    ),
                    image_url=source_url,
                    model_params=orbit_params,
                    idempotency_key=f"auroom-{generation_id}-orbit-{index}",
                )
                provider_task_id = result.task_id
                frames.append(await _download_image(result.image_url, settings))
            data = await asyncio.to_thread(
                build_orbit_animation,
                frames,
                duration_ms=frame_duration_ms,
                max_pixels=settings.max_image_pixels,
            )
        else:
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
            provider_task_id = result.task_id
            data = await _download_image(result.image_url, settings)
        if composition_mode == "masked_edit":
            if input_storage_path is None or edit_region is None:
                raise RuntimeError(
                    "Masked questionnaire edit is missing its base scene or edit region"
                )
            base_path = LocalMediaStorage(settings).absolute_path(input_storage_path)
            base_data = await asyncio.to_thread(base_path.read_bytes)
            composite = await asyncio.to_thread(
                compose_masked_edit,
                base_data=base_data,
                candidate_data=data,
                edit_region=edit_region,
                protected_regions=protected_regions,
                max_pixels=settings.max_image_pixels,
            )
            data = composite.data

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
                original_filename=(
                    f"auroom-orbit.{image.extension}"
                    if orbit_request is not None
                    else f"auroom-{generation.type.value}.{image.extension}"
                ),
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
            generation.provider_task_id = provider_task_id
            generation.status = GenerationStatus.COMPLETED
            generation.error = None
            generation.completed_at = datetime.now(UTC)
            await session.commit()
            logger.info(
                "Generation %s completed with %s%s%s%s",
                generation_id,
                model_name,
                " (fallback)" if fallback_used else "",
                " (masked composite)" if composition_mode == "masked_edit" else "",
                " (orbit loop)" if orbit_request is not None else "",
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
                await _recover_reserved_jobs()
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
                await _recover_reserved_jobs()
            else:
                await _ack_job(raw_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Generation worker iteration failed")
            await asyncio.sleep(2)


async def _main() -> None:
    try:
        async with worker_heartbeat("generation"):
            await run_worker()
    finally:
        await redis_client.aclose()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
