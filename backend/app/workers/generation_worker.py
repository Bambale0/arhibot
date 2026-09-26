from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from datetime import UTC, datetime, timedelta
from json import JSONDecodeError, loads
from urllib.parse import urljoin, urlsplit
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.metrics import (
    record_generation_quality_retry_success,
    record_masked_edit_boundary_failure,
    record_masked_edit_quality_rejected,
    record_masked_edit_retry,
    record_masked_edit_started,
)
from app.core.redis import redis_client
from app.db.models.assets import Asset
from app.db.models.generations import Generation
from app.db.models.projects import Project
from app.db.session import dispose_engine, get_session_factory
from app.domain.assets.enums import AssetPurpose, AssetType
from app.domain.generations.enums import GenerationOrigin, GenerationStatus
from app.image_compositor import (
    build_edit_reference_guide,
    compose_masked_edit,
    expand_normalized_region,
)
from app.image_quality import analyze_masked_edit_quality
from app.image_flyover import FlyoverGif, build_flyover_gif
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
from app.workers.heartbeat import worker_heartbeat, worker_singleton

logger = logging.getLogger(__name__)
GENERATION_PROCESSING_KEY = "auroom:generation_processing"
QUESTIONNAIRE_PROMPT_PREFIX = "AUROOM_RENDER_SPEC_V1"
INITIAL_CONCEPT_PROMPT_PREFIX = "AUROOM_INITIAL_CONCEPT_V1"
ADMIN_SANDBOX_PROMPT_PREFIX = "AUROOM_ADMIN_SANDBOX_V1\n"
ADMIN_ORBIT_PROMPT_PREFIX = "AUROOM_ADMIN_ORBIT_V1\n"
ADMIN_FLYOVER_GIF_PROMPT_PREFIX = "AUROOM_ADMIN_FLYOVER_GIF_V1\n"
QUESTIONNAIRE_PROMPT_PREFIXES = (
    QUESTIONNAIRE_PROMPT_PREFIX,
    INITIAL_CONCEPT_PROMPT_PREFIX,
)
QUESTIONNAIRE_ASPECT_RATIOS = {"1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4, "16:9": 16 / 9, "9:16": 9 / 16}
RESERVED_PROVIDER_PARAMS = {"model_name", "prompt", "image_url", "image_urls"}
ADMIN_ORBIT_MAX_CONCURRENCY = 3
MASKED_EDIT_GUIDE_PROMPT = (
    "MASKED EDIT REFERENCE CONTRACT:\n"
    "Reference image 1 is the canonical accepted scene. "
    "Reference image 2 is a pixel-aligned binary edit guide for reference image 1: "
    "white pixels are the only area allowed to change; black pixels are locked and "
    "must remain visually unchanged. Make the requested edit only inside the white "
    "area. At the white/black boundary, preserve continuous geometry, perspective, "
    "materials, paving, rooflines, wall edges, vegetation and lighting so the edit "
    "joins the locked scene naturally. The binary guide is an instruction map only: "
    "never render its black/white colors, rectangle edges, or mask markings in the output."
)


def _masked_edit_provider_prompt(prompt: str) -> str:
    return f"{prompt}\n\n{MASKED_EDIT_GUIDE_PROMPT}"


class GenerationQualityRejected(RuntimeError):
    def __init__(self, report: dict[str, object]) -> None:
        super().__init__(
            "Не удалось аккуратно выполнить эту доработку без нарушения исходной сцены. "
            "Попробуйте выделить область немного шире или изменить запрос."
        )
        self.report = report


def _quality_retry_prompt(prompt: str, report: dict[str, object]) -> str:
    reasons: list[str] = []
    if int(report.get("changed_outside_pixels", 0) or 0) > 0:
        reasons.append("pixels outside the final commit region changed")
    if float(report.get("boundary_luma_excess", 0.0) or 0.0) > 0:
        reasons.append("the edit boundary has a luminance discontinuity")
    if float(report.get("boundary_color_excess", 0.0) or 0.0) > 0:
        reasons.append("the edit boundary has a color discontinuity")
    if float(report.get("straight_edge_fraction", 0.0) or 0.0) > 0:
        reasons.append("a straight rectangular edge is visible at the edit boundary")
    reason_text = "; ".join(reasons) or "the candidate failed the masked-edit quality gate"
    return (
        f"{prompt}\n\nPREVIOUS CANDIDATE REJECTED: {reason_text}. "
        "Maintain exact texture, illumination, material and geometry continuity at the edit "
        "boundary. Preserve the accepted scene outside the requested exterior change. "
        "If a fireplace and chimney are visible, preserve their existing architectural "
        "relationship and do not move the chimney to an unrelated roof area."
    )


def _admin_sandbox_request(
    generation: Generation,
    project: Project,
) -> tuple[str, str, dict[str, object]] | None:
    if generation.origin != GenerationOrigin.ADMIN_SANDBOX.value:
        return None
    if not generation.prompt.startswith(ADMIN_SANDBOX_PROMPT_PREFIX):
        raise ValueError("Admin sandbox generation has an invalid envelope.")
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
    if generation.origin != GenerationOrigin.ADMIN_ORBIT.value:
        return None
    if not generation.prompt.startswith(ADMIN_ORBIT_PROMPT_PREFIX):
        raise ValueError("Admin orbit generation has an invalid envelope.")
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


def _admin_flyover_gif_request(
    generation: Generation,
    project: Project,
) -> tuple[str, str, dict[str, object], int, int, int] | None:
    if generation.origin != GenerationOrigin.ADMIN_FLYOVER_GIF.value:
        return None
    if not generation.prompt.startswith(ADMIN_FLYOVER_GIF_PROMPT_PREFIX):
        raise ValueError("Admin flyover GIF generation has an invalid envelope.")
    if not bool((project.context or {}).get("admin_ai_sandbox")):
        raise ValueError("Admin flyover GIF envelope is outside the sandbox project.")
    if generation.input_asset_id is None:
        raise ValueError("Admin flyover GIF source image is missing.")

    model_name = (generation.model_name or "").strip()
    if not model_name:
        raise ValueError("Admin flyover GIF model is missing.")

    raw_payload = generation.prompt.removeprefix(ADMIN_FLYOVER_GIF_PROMPT_PREFIX)
    try:
        payload = loads(raw_payload)
    except JSONDecodeError as exc:
        raise ValueError("Admin flyover GIF envelope is invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Admin flyover GIF envelope must be an object.")

    prompt = payload.get("prompt", "")
    if not isinstance(prompt, str):
        raise ValueError("Admin flyover GIF prompt must be a string.")
    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("Admin flyover GIF params must be an object.")
    conflict = RESERVED_PROVIDER_PARAMS.intersection(params)
    if conflict:
        raise ValueError(
            "Admin flyover GIF params cannot override provider fields: "
            f"{', '.join(sorted(conflict))}"
        )

    keyframe_count = payload.get("keyframe_count")
    inbetween_frames = payload.get("inbetween_frames")
    frame_duration_ms = payload.get("frame_duration_ms")
    if not isinstance(keyframe_count, int) or not 4 <= keyframe_count <= 8:
        raise ValueError("Admin flyover GIF keyframe count must be between 4 and 8.")
    if not isinstance(inbetween_frames, int) or not 0 <= inbetween_frames <= 5:
        raise ValueError("Admin flyover GIF in-between frame count must be between 0 and 5.")
    if not isinstance(frame_duration_ms, int) or not 60 <= frame_duration_ms <= 500:
        raise ValueError("Admin flyover GIF frame duration is invalid.")
    return (
        model_name,
        prompt.strip(),
        params,
        keyframe_count,
        inbetween_frames,
        frame_duration_ms,
    )


def _flyover_frame_prompt(
    extra_prompt: str,
    *,
    index: int,
    keyframe_count: int,
) -> str:
    progress = index / (keyframe_count - 1)
    if progress <= 0.25:
        stage = (
            "Start the bird/drone flight by moving the camera forward and slightly upward "
            "into an elevated three-quarter approach; make the property read more aerial."
        )
    elif progress <= 0.45:
        stage = (
            "Continue forward toward the house, move slightly lower and closer, and create "
            "natural foreground/background parallax without changing the architecture."
        )
    elif progress <= 0.65:
        stage = (
            "Continue the forward flight above and diagonally across the roof, with the roof "
            "and site passing naturally beneath the camera."
        )
    elif progress <= 0.85:
        stage = (
            "Continue forward beyond the house so the camera has clearly passed the roofline; "
            "the building should begin to sit behind the flight path."
        )
    else:
        stage = (
            "Finish with a gentle rising exit while still moving forward, leaving the house "
            "and plot readable behind the camera path."
        )

    prompt = (
        "Create the next keyframe of one continuous photorealistic architectural bird/drone "
        "flyover from the reference image. Continue the camera forward through real 3D space; "
        "do not spin in place, do not make a 360-degree orbit, and do not create a turntable. "
        "Preserve the exact house and site geometry, object count, roof shape, windows, doors, "
        "materials, landscaping, lighting, weather, season and all design details. "
        "Move only the camera. No redesign, morphing, added/removed structures, object motion, "
        "text, labels or borders. Keep focal length and horizon stable. "
        f"Keyframe {index + 1} of {keyframe_count}. {stage}"
    )
    if extra_prompt:
        prompt += f" Additional operator instruction: {extra_prompt}"
    return prompt


def _questionnaire_aspect_ratio(asset: Asset | None) -> str:
    if asset is None or not asset.width or not asset.height:
        return "16:9"
    ratio = asset.width / asset.height
    return min(QUESTIONNAIRE_ASPECT_RATIOS, key=lambda item: abs(QUESTIONNAIRE_ASPECT_RATIOS[item] - ratio))


def _address_is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _validate_remote_image_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise RuntimeError("Generated image URL must use HTTPS and be absolute")
    if parsed.username is not None or parsed.password is not None:
        raise RuntimeError("Generated image URL must not contain credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("Generated image URL has an invalid port") from exc
    if port not in (None, 443):
        raise RuntimeError("Generated image URL must use the standard HTTPS port")

    hostname = parsed.hostname.rstrip(".").lower()
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            answers = await asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                443,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise RuntimeError("Generated image host could not be resolved") from exc
        addresses = {str(answer[4][0]).split("%", 1)[0] for answer in answers}
        if not addresses or any(not _address_is_public(address) for address in addresses):
            raise RuntimeError("Generated image host resolves to a non-public address")
    else:
        if not _address_is_public(str(literal)):
            raise RuntimeError("Generated image URL points to a non-public address")
    return url


def _validate_connected_peer(response: httpx.Response) -> None:
    stream = response.extensions.get("network_stream")
    if stream is None or not hasattr(stream, "get_extra_info"):
        raise RuntimeError("Generated image connection did not expose its peer address")
    server_addr = stream.get_extra_info("server_addr")
    if (
        not isinstance(server_addr, (tuple, list))
        or not server_addr
        or not isinstance(server_addr[0], str)
    ):
        raise RuntimeError("Generated image connection peer address is unavailable")
    address = server_addr[0].split("%", 1)[0]
    try:
        public = _address_is_public(address)
    except ValueError as exc:
        raise RuntimeError("Generated image connection peer address is invalid") from exc
    if not public:
        raise RuntimeError("Generated image connection reached a non-public address")


async def _download_image(url: str, settings: Settings) -> bytes:
    limit = settings.max_image_size_bytes
    current_url = await _validate_remote_image_url(url)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60.0),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        for redirect_count in range(6):
            async with client.stream("GET", current_url) as response:
                _validate_connected_peer(response)
                if response.is_redirect:
                    if redirect_count >= 5:
                        raise RuntimeError("Generated image exceeded redirect limit")
                    location = response.headers.get("location")
                    if not location:
                        raise RuntimeError("Generated image redirect is missing Location")
                    current_url = await _validate_remote_image_url(
                        urljoin(str(response.url), location)
                    )
                    continue

                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > limit:
                            raise RuntimeError("Generated image exceeds media size limit")
                    except ValueError:
                        # A malformed length header is not trusted; the streamed byte limit below
                        # remains authoritative.
                        pass

                chunks: list[bytes] = []
                received = 0
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > limit:
                        raise RuntimeError("Generated image exceeds media size limit")
                    chunks.append(chunk)
                return b"".join(chunks)
    raise RuntimeError("Generated image download did not produce a response")


async def _generate_orbit_frames(
    *,
    provider: NexusImageProvider,
    generation_id: UUID,
    model_name: str,
    prompt: str,
    params: dict[str, object],
    source_url: str,
    frame_count: int,
    settings: Settings,
) -> tuple[list[bytes], str | None]:
    semaphore = asyncio.Semaphore(ADMIN_ORBIT_MAX_CONCURRENCY)

    async def generate_frame(index: int) -> tuple[int, bytes, str]:
        async with semaphore:
            result = await provider.generate(
                model_name=model_name,
                prompt=_orbit_frame_prompt(
                    prompt,
                    index=index,
                    frame_count=frame_count,
                ),
                image_url=source_url,
                model_params=params,
                idempotency_key=f"auroom-{generation_id}-orbit-{index}",
            )
            data = await _download_image(result.image_url, settings)
        return index, data, result.task_id

    generated = await asyncio.gather(
        *(generate_frame(index) for index in range(1, frame_count))
    )
    generated.sort(key=lambda item: item[0])
    return [item[1] for item in generated], generated[-1][2] if generated else None


async def _generate_flyover_frames(
    *,
    provider: NexusImageProvider,
    generation_id: UUID,
    model_name: str,
    prompt: str,
    params: dict[str, object],
    source_url: str,
    keyframe_count: int,
    settings: Settings,
) -> tuple[list[bytes], str | None]:
    reference_url = source_url
    generated_frames: list[bytes] = []
    last_task_id: str | None = None
    for index in range(1, keyframe_count):
        result = await provider.generate(
            model_name=model_name,
            prompt=_flyover_frame_prompt(
                prompt,
                index=index,
                keyframe_count=keyframe_count,
            ),
            image_url=reference_url,
            model_params=params,
            idempotency_key=f"auroom-{generation_id}-flyover-{index}",
        )
        generated_frames.append(await _download_image(result.image_url, settings))
        reference_url = result.image_url
        last_task_id = result.task_id
    return generated_frames, last_task_id


async def _commit_output_or_cleanup(
    session,
    storage: LocalMediaStorage,
    relative_path: str,
) -> None:
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        target = storage.absolute_path(relative_path)
        try:
            if target.exists():
                await asyncio.to_thread(target.unlink)
        except OSError:
            logger.exception(
                "Could not remove orphaned generation output %s after DB failure",
                relative_path,
            )
        raise


async def _mark_failed_and_refund(generation_id: UUID, error: Exception | str) -> None:
    async with get_session_factory()() as session:
        generation = await session.get(Generation, generation_id)
        if generation is None or generation.status == GenerationStatus.COMPLETED:
            return
        generation.status = GenerationStatus.FAILED
        generation.error = str(error)[:1000] or "Generation failed"
        if isinstance(error, GenerationQualityRejected):
            generation.quality_status = "rejected"
            generation.quality_report = error.report
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
        if project is None or project.deleted_at is not None:
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
            flyover_request = _admin_flyover_gif_request(generation, project)
        except ValueError as exc:
            await session.rollback()
            await _mark_failed_and_refund(generation_id, exc)
            return

        if generation.origin == GenerationOrigin.LEGACY_INTERNAL.value:
            await session.rollback()
            await _mark_failed_and_refund(
                generation_id,
                "Legacy internal generation cannot be processed after the security migration.",
            )
            return

        admin_internal_generation = (
            sandbox_request is not None
            or orbit_request is not None
            or flyover_request is not None
        )
        admin_repository = AdminRepository(session)
        initial_concept_generation = (
            generation.origin == GenerationOrigin.QUESTIONNAIRE_INITIAL.value
        )
        questionnaire_generation = generation.origin in {
            GenerationOrigin.QUESTIONNAIRE.value,
            GenerationOrigin.QUESTIONNAIRE_INITIAL.value,
        }
        if initial_concept_generation and not generation.prompt.startswith(
            INITIAL_CONCEPT_PROMPT_PREFIX
        ):
            await session.rollback()
            await _mark_failed_and_refund(
                generation_id,
                "Initial questionnaire generation has an invalid server prompt.",
            )
            return
        if (
            generation.origin == GenerationOrigin.QUESTIONNAIRE.value
            and not generation.prompt.startswith(QUESTIONNAIRE_PROMPT_PREFIX)
        ):
            await session.rollback()
            await _mark_failed_and_refund(
                generation_id,
                "Questionnaire generation has an invalid server prompt.",
            )
            return
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
            primary_timeout_seconds: int | None = None
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
            primary_timeout_seconds = None
        elif flyover_request is not None:
            (
                primary_model,
                prompt,
                primary_params,
                _flyover_keyframe_count,
                _flyover_inbetween_frames,
                _flyover_frame_duration_ms,
            ) = flyover_request
            fallback_model = None
            fallback_params = {}
            primary_timeout_seconds = None
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
            primary_timeout_seconds = runtime.primary_timeout_seconds
        composition_mode = generation.composition_mode
        edit_region = dict(generation.edit_region) if generation.edit_region else None
        protected_regions = list(generation.protected_regions or [])
        edit_policy = dict(generation.edit_policy or {})
        quality_settings: dict[str, float | int] | None = None
        if composition_mode == "masked_edit" and edit_policy and runtime is not None:
            quality_settings = {
                "provider_margin": runtime.masked_edit_provider_context_margin_fraction,
                "feather_fraction": runtime.masked_edit_feather_fraction,
                "feather_min_px": runtime.masked_edit_feather_min_px,
                "feather_max_px": runtime.masked_edit_feather_max_px,
                "recomposite_multiplier": runtime.masked_edit_recomposite_feather_multiplier,
                "boundary_band_px": runtime.masked_edit_boundary_band_px,
                "max_luma_excess": runtime.masked_edit_max_luma_excess,
                "max_color_excess": runtime.masked_edit_max_color_excess,
                "max_straight_edge_fraction": runtime.masked_edit_max_straight_edge_fraction,
                "max_retries": runtime.generation_quality_max_retries,
            }
        input_storage_path = input_asset.storage_path if input_asset is not None else None

    provider = NexusImageProvider(settings)
    guide_storage = LocalMediaStorage(settings)
    guide_relative_path: str | None = None
    reference_image_urls: list[str] | None = None
    masked_base_data: bytes | None = None
    model_name = primary_model
    fallback_used = False
    provider_task_id: str | None = None
    flyover_gif: FlyoverGif | None = None
    quality_report: dict[str, object] | None = None
    provider_work_region = edit_region
    try:
        if composition_mode == "masked_edit":
            record_masked_edit_started()
            if source_url is None or input_storage_path is None or edit_region is None:
                raise RuntimeError(
                    "Masked questionnaire edit is missing its base scene or edit region"
                )
            base_path = guide_storage.absolute_path(input_storage_path)
            masked_base_data = await asyncio.to_thread(base_path.read_bytes)
            if quality_settings is not None:
                provider_work_region = expand_normalized_region(
                    edit_region,
                    margin_fraction=float(quality_settings["provider_margin"]),
                )
            guide_data = await asyncio.to_thread(
                build_edit_reference_guide,
                base_data=masked_base_data,
                edit_region=provider_work_region,
                protected_regions=protected_regions,
                max_pixels=settings.max_image_pixels,
            )
            guide_relative_path = f"internal/generation-guides/{generation_id}.png"
            await guide_storage.write(guide_relative_path, guide_data)
            reference_image_urls = [
                guide_storage.signed_url(
                    guide_relative_path,
                    ttl_seconds=max(
                        settings.media_url_ttl_seconds,
                        settings.nexus_task_timeout_seconds + 120,
                    ),
                )
            ]
            prompt = _masked_edit_provider_prompt(prompt)
            logger.info(
                "Generation %s masked edit policy=%s intent=%s commit_region=%s "
                "provider_work_region=%s protected_regions=%s quality_gate=%s",
                generation_id,
                edit_policy.get("version"),
                edit_policy.get("intent"),
                edit_region,
                provider_work_region,
                len(protected_regions),
                quality_settings is not None,
            )
        if flyover_request is not None:
            if source_url is None or input_storage_path is None:
                raise RuntimeError("Flyover GIF generation requires a source image.")
            (
                _,
                flyover_prompt,
                flyover_params,
                keyframe_count,
                inbetween_frames,
                frame_duration_ms,
            ) = flyover_request
            base_path = LocalMediaStorage(settings).absolute_path(input_storage_path)
            base_data = await asyncio.to_thread(base_path.read_bytes)
            generated_frames, provider_task_id = await _generate_flyover_frames(
                provider=provider,
                generation_id=generation_id,
                model_name=model_name,
                prompt=flyover_prompt,
                params=flyover_params,
                source_url=source_url,
                keyframe_count=keyframe_count,
                settings=settings,
            )
            flyover_gif = await asyncio.to_thread(
                build_flyover_gif,
                [base_data, *generated_frames],
                inbetween_frames=inbetween_frames,
                duration_ms=frame_duration_ms,
                max_pixels=settings.max_image_pixels,
            )
            data = flyover_gif.data
        elif orbit_request is not None:
            if source_url is None or input_storage_path is None:
                raise RuntimeError("Orbit generation requires a source image.")
            _, orbit_prompt, orbit_params, frame_count, frame_duration_ms = orbit_request
            base_path = LocalMediaStorage(settings).absolute_path(input_storage_path)
            base_data = await asyncio.to_thread(base_path.read_bytes)
            generated_frames, provider_task_id = await _generate_orbit_frames(
                provider=provider,
                generation_id=generation_id,
                model_name=model_name,
                prompt=orbit_prompt,
                params=orbit_params,
                source_url=source_url,
                frame_count=frame_count,
                settings=settings,
            )
            data = await asyncio.to_thread(
                build_orbit_animation,
                [base_data, *generated_frames],
                duration_ms=frame_duration_ms,
                max_pixels=settings.max_image_pixels,
            )
        else:
            max_quality_retries = (
                int(quality_settings["max_retries"]) if quality_settings is not None else 0
            )
            quality_attempts: list[dict[str, object]] = []
            previous_failure: dict[str, object] | None = None
            base_provider_prompt = prompt
            for quality_attempt in range(max_quality_retries + 1):
                if quality_attempt > 0:
                    record_masked_edit_retry()
                attempt_prompt = (
                    base_provider_prompt
                    if quality_attempt == 0 or previous_failure is None
                    else _quality_retry_prompt(base_provider_prompt, previous_failure)
                )
                attempt_suffix = (
                    "primary"
                    if quality_attempt == 0
                    else f"quality-{quality_attempt}-primary"
                )
                attempt_fallback_suffix = (
                    "fallback"
                    if quality_attempt == 0
                    else f"quality-{quality_attempt}-fallback"
                )
                model_name = primary_model
                try:
                    result = await provider.generate(
                        model_name=model_name,
                        prompt=attempt_prompt,
                        image_url=source_url,
                        model_params=primary_params,
                        idempotency_key=f"auroom-{generation_id}-{attempt_suffix}",
                        reference_image_urls=reference_image_urls,
                        timeout_seconds=primary_timeout_seconds,
                    )
                except NexusProviderError as primary_error:
                    if not primary_error.retryable or not fallback_model:
                        raise
                    logger.warning(
                        "Primary Nexus model failed for %s attempt=%s; using admin-configured "
                        "fallback: %s",
                        generation_id,
                        quality_attempt + 1,
                        primary_error,
                    )
                    model_name = fallback_model
                    fallback_used = True
                    result = await provider.generate(
                        model_name=model_name,
                        prompt=attempt_prompt,
                        image_url=source_url,
                        model_params=fallback_params,
                        idempotency_key=f"auroom-{generation_id}-{attempt_fallback_suffix}",
                        reference_image_urls=reference_image_urls,
                    )
                provider_task_id = result.task_id
                candidate_data = await _download_image(result.image_url, settings)

                if composition_mode != "masked_edit":
                    data = candidate_data
                    break
                if input_storage_path is None or edit_region is None:
                    raise RuntimeError(
                        "Masked questionnaire edit is missing its base scene or edit region"
                    )
                base_data = masked_base_data
                if base_data is None:
                    base_path = guide_storage.absolute_path(input_storage_path)
                    base_data = await asyncio.to_thread(base_path.read_bytes)

                if quality_settings is None:
                    composite = await asyncio.to_thread(
                        compose_masked_edit,
                        base_data=base_data,
                        candidate_data=candidate_data,
                        edit_region=edit_region,
                        protected_regions=protected_regions,
                        max_pixels=settings.max_image_pixels,
                    )
                    data = composite.data
                    break

                composite = await asyncio.to_thread(
                    compose_masked_edit,
                    base_data=base_data,
                    candidate_data=candidate_data,
                    edit_region=edit_region,
                    protected_regions=protected_regions,
                    feather_fraction=float(quality_settings["feather_fraction"]),
                    feather_min_px=int(quality_settings["feather_min_px"]),
                    feather_max_px=int(quality_settings["feather_max_px"]),
                    max_pixels=settings.max_image_pixels,
                )
                report = await asyncio.to_thread(
                    analyze_masked_edit_quality,
                    base_data=base_data,
                    final_data=composite.data,
                    edit_region=edit_region,
                    boundary_band_px=int(quality_settings["boundary_band_px"]),
                    max_luma_excess=float(quality_settings["max_luma_excess"]),
                    max_color_excess=float(quality_settings["max_color_excess"]),
                    max_straight_edge_fraction=float(
                        quality_settings["max_straight_edge_fraction"]
                    ),
                )
                initial_report = report.to_dict()
                boundary_failed = (
                    report.boundary_luma_excess
                    > float(quality_settings["max_luma_excess"])
                    or report.boundary_color_excess
                    > float(quality_settings["max_color_excess"])
                    or report.straight_edge_fraction
                    > float(quality_settings["max_straight_edge_fraction"])
                )
                if boundary_failed:
                    record_masked_edit_boundary_failure()
                attempt_report: dict[str, object] = {
                    "attempt": quality_attempt + 1,
                    "model": model_name,
                    "provider_task_id": provider_task_id,
                    "initial": initial_report,
                }

                if not report.passed:
                    shortest = min(composite.width, composite.height)
                    configured_min = int(quality_settings["feather_min_px"])
                    configured_max = int(quality_settings["feather_max_px"])
                    primary_feather = max(
                        configured_min,
                        min(
                            configured_max,
                            round(
                                shortest
                                * float(quality_settings["feather_fraction"])
                            ),
                        ),
                    )
                    wider_feather = min(
                        configured_max,
                        max(
                            primary_feather + 1,
                            round(
                                primary_feather
                                * float(quality_settings["recomposite_multiplier"])
                            ),
                        ),
                    )
                    if wider_feather > primary_feather:
                        wider = await asyncio.to_thread(
                            compose_masked_edit,
                            base_data=base_data,
                            candidate_data=candidate_data,
                            edit_region=edit_region,
                            protected_regions=protected_regions,
                            feather_px=wider_feather,
                            feather_max_px=configured_max,
                            max_pixels=settings.max_image_pixels,
                        )
                        wider_report = await asyncio.to_thread(
                            analyze_masked_edit_quality,
                            base_data=base_data,
                            final_data=wider.data,
                            edit_region=edit_region,
                            boundary_band_px=int(quality_settings["boundary_band_px"]),
                            max_luma_excess=float(quality_settings["max_luma_excess"]),
                            max_color_excess=float(quality_settings["max_color_excess"]),
                            max_straight_edge_fraction=float(
                                quality_settings["max_straight_edge_fraction"]
                            ),
                        )
                        attempt_report["recomposite"] = {
                            "feather_px": wider_feather,
                            **wider_report.to_dict(),
                        }
                        if wider_report.passed:
                            report = wider_report
                            composite = wider

                quality_attempts.append(attempt_report)
                if report.passed:
                    data = composite.data
                    quality_report = {
                        "version": "edit-quality.v1",
                        "attempts": quality_attempts,
                        "provider_work_region": provider_work_region,
                        "enforced_checks": list(
                            edit_policy.get("enforced_quality_checks")
                            or ("outside_region_integrity", "boundary_continuity")
                        ),
                        "deferred_checks": list(
                            edit_policy.get("deferred_quality_checks", [])
                        ),
                        "scene_analysis": (
                            "enforced"
                            if edit_policy.get("scene_analysis_enforced")
                            else "deferred"
                            if edit_policy.get("scene_analysis_required")
                            else "not_required"
                        ),
                        "final": "passed",
                    }
                    if quality_attempt > 0:
                        record_generation_quality_retry_success()
                    logger.info(
                        "Generation %s masked quality passed attempt=%s "
                        "outside_changed=%s boundary_luma=%.4f boundary_color=%.4f "
                        "straight_edge=%.4f",
                        generation_id,
                        quality_attempt + 1,
                        report.changed_outside_pixels,
                        report.boundary_luma_excess,
                        report.boundary_color_excess,
                        report.straight_edge_fraction,
                    )
                    break

                previous_failure = report.to_dict()
                logger.warning(
                    "Generation %s masked quality rejected attempt=%s/%s report=%s",
                    generation_id,
                    quality_attempt + 1,
                    max_quality_retries + 1,
                    previous_failure,
                )
                if quality_attempt >= max_quality_retries:
                    quality_report = {
                        "version": "edit-quality.v1",
                        "attempts": quality_attempts,
                        "provider_work_region": provider_work_region,
                        "enforced_checks": list(
                            edit_policy.get("enforced_quality_checks")
                            or ("outside_region_integrity", "boundary_continuity")
                        ),
                        "deferred_checks": list(
                            edit_policy.get("deferred_quality_checks", [])
                        ),
                        "scene_analysis": (
                            "enforced"
                            if edit_policy.get("scene_analysis_enforced")
                            else "deferred"
                            if edit_policy.get("scene_analysis_required")
                            else "not_required"
                        ),
                        "final": "rejected",
                    }
                    record_masked_edit_quality_rejected()
                    raise GenerationQualityRejected(quality_report)

        async with get_session_factory()() as session:
            generation = await GenerationRepository(session).get_for_update(generation_id)
            if generation is None or generation.status != GenerationStatus.PROCESSING:
                return
            project = await session.get(Project, generation.project_id)
            if project is None or project.deleted_at is not None:
                await session.rollback()
                await _mark_failed_and_refund(
                    generation_id,
                    "Generation project was deleted before provider completion.",
                )
                return
            asset_service = AssetService(
                AssetRepository(session),
                ProjectRepository(session),
                settings,
            )
            asset_id = uuid4()
            now = datetime.now(UTC)
            if flyover_gif is not None:
                output_data = flyover_gif.data
                extension = "gif"
                mime_type = "image/gif"
                width = flyover_gif.width
                height = flyover_gif.height
                original_filename = "auroom-bird-flyover.gif"
            else:
                image = asset_service._validate_image(data)
                output_data = image.data
                extension = image.extension
                mime_type = image.mime_type
                width = image.width
                height = image.height
                original_filename = (
                    f"auroom-orbit.{image.extension}"
                    if orbit_request is not None
                    else f"auroom-{generation.type.value}.{image.extension}"
                )
            relative_path = f"users/{generation.user_id}/{now:%Y/%m}/{asset_id}.{extension}"
            await asset_service.storage.write(relative_path, output_data)

            output = Asset(
                id=asset_id,
                user_id=generation.user_id,
                project_id=generation.project_id,
                type=AssetType.IMAGE,
                purpose=AssetPurpose.GENERATION_OUTPUT,
                original_filename=original_filename,
                mime_type=mime_type,
                size_bytes=len(output_data),
                width=width,
                height=height,
                storage_path=relative_path,
            )
            session.add(output)
            generation.output_asset_id = output.id
            generation.model_name = model_name
            generation.fallback_used = fallback_used
            generation.provider_task_id = provider_task_id
            if quality_report is not None:
                generation.quality_report = quality_report
                generation.quality_status = "passed"
            generation.status = GenerationStatus.COMPLETED
            generation.error = None
            generation.completed_at = datetime.now(UTC)
            await _commit_output_or_cleanup(
                session,
                asset_service.storage,
                relative_path,
            )
            logger.info(
                "Generation %s completed with %s%s%s%s%s",
                generation_id,
                model_name,
                " (fallback)" if fallback_used else "",
                " (masked composite)" if composition_mode == "masked_edit" else "",
                " (orbit loop)" if orbit_request is not None else "",
                " (bird flyover GIF)" if flyover_request is not None else "",
            )
    except Exception as exc:
        logger.exception("Generation %s failed", generation_id)
        await _mark_failed_and_refund(generation_id, exc)
    finally:
        if guide_relative_path is not None:
            guide_path = guide_storage.absolute_path(guide_relative_path)
            try:
                if guide_path.exists():
                    await asyncio.to_thread(guide_path.unlink)
            except OSError:
                logger.warning(
                    "Could not remove temporary edit guide for generation %s",
                    generation_id,
                    exc_info=True,
                )


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
        async with worker_singleton("generation"):
            async with worker_heartbeat("generation"):
                await run_worker()
    finally:
        await redis_client.aclose()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
