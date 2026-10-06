from collections.abc import Callable
from json import dumps
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.cursor import decode_cursor, encode_cursor
from app.core.errors import AppError
from app.core.redis import redis_client
from app.db.models.generations import Generation
from app.db.models.projects import Project
from app.db.models.users import User
from app.domain.assets.enums import AssetType
from app.domain.generations.enums import GenerationOrigin, GenerationStatus, GenerationType
from app.domain.users.enums import UserRole
from app.repositories.admin import AdminRepository
from app.repositories.assets import AssetRepository
from app.repositories.credits import CreditRepository
from app.repositories.generations import GenerationRepository
from app.repositories.operations import OperationalSettingsRepository
from app.repositories.projects import ProjectRepository
from app.schemas.assets import AssetResponse
from app.schemas.generations import GenerationCreate, GenerationListResponse, GenerationResponse
from app.services.asset_service import AssetService, build_asset_service
from app.services.credit_service import CreditService
from app.services.rate_limit_service import RateLimitService

GENERATION_QUEUE_KEY = "auroom:generation_queue"
REFERENCE_REQUIRED_TYPES = {GenerationType.FACADE, GenerationType.INTERIOR}
FREE_GENERATION_ROLES = {UserRole.ADMIN, UserRole.SUPERADMIN}
RESERVED_INTERNAL_PROMPT_PREFIXES = (
    "AUROOM_RENDER_SPEC_V1",
    "AUROOM_INITIAL_CONCEPT_V1",
    "AUROOM_ADMIN_SANDBOX_V1",
    "AUROOM_ADMIN_ORBIT_V1",
    "AUROOM_ADMIN_FLYOVER_GIF_V1",
    "AUROOM_CONCEPT_VIDEO_V1",
)


def _public_quality_report(report: dict | None) -> dict | None:
    if not report:
        return report
    public = dict(report)
    checkpoint = public.get("provider_request")
    if isinstance(checkpoint, dict):
        public["provider_request"] = {
            key: value
            for key, value in checkpoint.items()
            if key not in {"key", "request_body", "request_id"}
        }
    frame_checkpoints = public.get("provider_frame_requests")
    if isinstance(frame_checkpoints, dict):
        public["provider_frame_requests"] = {
            slot: {
                key: value
                for key, value in item.items()
                if key not in {"key", "request_body", "request_id"}
            }
            for slot, item in frame_checkpoints.items()
            if isinstance(item, dict)
        }
    identity_request = public.get("video_identity_request")
    if isinstance(identity_request, dict):
        public["video_identity_request"] = {
            key: value for key, value in identity_request.items() if key != "key"
        }
    video_request = public.get("video_request")
    if isinstance(video_request, dict):
        public["video_request"] = {
            key: value
            for key, value in video_request.items()
            if key not in {"key", "request_body", "request_id"}
        }
    return public


class GenerationService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = GenerationRepository(session)
        self.assets = AssetRepository(session)
        self.projects = ProjectRepository(session)
        self.credit_repository = CreditRepository(session)
        self.operations = OperationalSettingsRepository(session)
        self.credit_service = CreditService(session)
        self.asset_service: AssetService = build_asset_service(session, settings)

    async def create(
        self,
        user: User,
        payload: GenerationCreate,
        *,
        before_commit: Callable[[Generation, Project], None] | None = None,
        skip_pricing: bool = False,
        credits_override: int | None = None,
        origin: GenerationOrigin = GenerationOrigin.GENERIC,
    ) -> GenerationResponse:
        await RateLimitService(self.session).enforce("generation", str(user.id))
        # Serialize generation admission for one account. This makes the inflight
        # cap authoritative even when the client submits several requests in parallel.
        await self.credit_repository.get_user_for_update(user.id)
        operations = await self.operations.get()
        max_inflight = (
            operations.generation_max_inflight_per_user
            if operations is not None
            else 2
        )
        if await self.repository.count_inflight(user.id) >= max_inflight:
            raise AppError(
                type="generation_inflight_limit_exceeded",
                title="Too many active generations",
                status=429,
                detail="Wait for an active generation to finish before starting another.",
                meta={"max_inflight": max_inflight},
            )
        normalized_prompt = payload.prompt.strip()
        if origin == GenerationOrigin.GENERIC and payload.type == GenerationType.VIDEO:
            raise AppError(
                type="video_generation_endpoint_required",
                title="Video continuation endpoint required",
                status=422,
                detail="Create concept video from a completed AuRoom generation.",
            )
        if origin == GenerationOrigin.GENERIC and normalized_prompt.startswith(
            RESERVED_INTERNAL_PROMPT_PREFIXES
        ):
            raise AppError(
                type="reserved_generation_prompt",
                title="Reserved generation prompt",
                status=422,
                detail="This prompt prefix is reserved for server-managed generation flows.",
            )
        if not (
            (self.settings.neironych_api_key or "").strip()
            or (self.settings.nexus_api_key or "").strip()
        ):
            raise AppError(
                type="generation_provider_not_configured",
                title="Generation provider not configured",
                status=503,
                detail="No image generation provider is configured for this environment.",
            )

        project = await self.projects.get_owned(
            payload.project_id, user.id, for_update=True
        )
        if not project:
            raise AppError(
                type="project_not_found",
                title="Project not found",
                status=404,
                detail="The project does not exist or is not available to this user.",
            )

        asset = None
        if payload.input_asset_id is not None:
            asset = await self.assets.get_owned(payload.input_asset_id, user.id)
            if not asset or asset.project_id != project.id:
                raise AppError(
                    type="asset_not_found",
                    title="Asset not found",
                    status=404,
                    detail="The input asset does not belong to this project.",
                )
        elif payload.type in REFERENCE_REQUIRED_TYPES:
            raise AppError(
                type="generation_reference_required",
                title="Reference image required",
                status=422,
                detail="Facade and interior generation require a reference image.",
            )

        credits_charged = 0
        if not skip_pricing:
            configured_credits = credits_override
            if configured_credits is None:
                price = await self.credit_repository.get_price(payload.type.value)
                if price is None or not price.is_active:
                    raise AppError(
                        type="generation_price_not_configured",
                        title="Generation price not configured",
                        status=503,
                        detail="The credit price for this generation scenario is not configured.",
                    )
                configured_credits = price.credits
            if configured_credits < 0:
                raise ValueError("Generation credits override must not be negative.")
            credits_charged = (
                0 if user.role in FREE_GENERATION_ROLES else configured_credits
            )

        generation = Generation(
            id=uuid4(),
            user_id=user.id,
            project_id=project.id,
            input_asset_id=asset.id if asset else None,
            type=payload.type,
            status=GenerationStatus.QUEUED,
            origin=origin.value,
            prompt=normalized_prompt,
            credits_charged=credits_charged,
            composition_mode=payload.composition_mode,
            edit_region=(
                payload.edit_region.model_dump(mode="json") if payload.edit_region else None
            ),
            protected_regions=[
                item.model_dump(mode="json") for item in payload.protected_regions
            ],
            edit_policy=dict(getattr(payload, "edit_policy", {}) or {}),
            quality_status=(
                "pending"
                if payload.composition_mode == "masked_edit"
                and bool(getattr(payload, "edit_policy", {}))
                else None
            ),
        )
        self.repository.add(generation)
        try:
            if generation.credits_charged > 0:
                await self.credit_service.apply(
                    user_id=user.id,
                    amount=-generation.credits_charged,
                    kind="generation_reserve",
                    idempotency_key=f"generation:{generation.id}:reserve",
                    reference_type="generation",
                    reference_id=str(generation.id),
                    reason=f"AuRoom generation: {payload.type.value}",
                )
            if before_commit is not None:
                before_commit(generation, project)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(generation)

        try:
            await redis_client.rpush(GENERATION_QUEUE_KEY, str(generation.id))
        except Exception as exc:
            generation.status = GenerationStatus.FAILED
            generation.error = "Generation queue is unavailable."
            if generation.credits_charged > 0:
                await self.credit_service.apply(
                    user_id=user.id,
                    amount=generation.credits_charged,
                    kind="generation_refund",
                    idempotency_key=f"generation:{generation.id}:refund",
                    reference_type="generation",
                    reference_id=str(generation.id),
                    reason="Generation queue unavailable",
                )
            await self.session.commit()
            raise AppError(
                type="generation_queue_unavailable",
                title="Generation queue unavailable",
                status=503,
                detail="Generation could not be queued.",
            ) from exc

        return await self.to_response(generation)

    async def create_video(
        self, user: User, source_generation_id: UUID
    ) -> GenerationResponse:
        # Serialize the continuation decision with other credit/generation admission.
        await self.credit_repository.get_user_for_update(user.id)
        source = await self.repository.get_owned_for_update(source_generation_id, user.id)
        if source is None:
            raise AppError(
                type="video_source_not_found",
                title="Concept not found",
                status=404,
                detail="The source generation does not exist or is not available.",
            )
        if source.status != GenerationStatus.COMPLETED or source.output_asset_id is None:
            raise AppError(
                type="video_source_not_ready",
                title="Concept is not ready",
                status=409,
                detail="Wait until the concept image is completed before creating video.",
            )
        if source.origin not in {
            GenerationOrigin.QUESTIONNAIRE.value,
            GenerationOrigin.QUESTIONNAIRE_INITIAL.value,
        }:
            raise AppError(
                type="video_source_not_questionnaire",
                title="Concept video is unavailable",
                status=422,
                detail="Video continuation is available for questionnaire concepts.",
            )

        source_asset = await self.assets.get_owned(source.output_asset_id, user.id)
        if source_asset is None or source_asset.type != AssetType.IMAGE:
            raise AppError(
                type="video_source_asset_invalid",
                title="Concept image is unavailable",
                status=409,
                detail="The completed concept image is not available for video generation.",
            )

        existing = await self.repository.get_active_video_for_source_asset(
            source_asset.id, user.id
        )
        if existing is not None:
            return await self.to_response(existing)

        runtime = await AdminRepository(self.session).get_generation_settings()
        if (
            runtime is None
            or not runtime.video_enabled
            or not (runtime.video_model or "").strip()
        ):
            raise AppError(
                type="video_generation_not_configured",
                title="Video generation is not configured",
                status=503,
                detail="Video continuation is temporarily unavailable.",
            )
        if not (self.settings.neironych_api_key or "").strip():
            raise AppError(
                type="video_provider_not_configured",
                title="Video provider is unavailable",
                status=503,
                detail="Neironych is not configured for Grok and Seedance.",
            )

        envelope = "AUROOM_CONCEPT_VIDEO_V1\n" + dumps(
            {"source_generation_id": str(source.id)},
            ensure_ascii=False,
            separators=(",", ":"),
        )

        def bind_video(generation: Generation, _project: Project) -> None:
            generation.model_name = (runtime.video_model or "").strip()
            generation.quality_status = "pending"
            generation.quality_report = {
                "video_runtime": {
                    "keyframe_strategy": "locked_pan_zoom_v1",
                    "judge_model": (runtime.quality_judge_model or "").strip(),
                    "video_model": (runtime.video_model or "").strip(),
                    "video_params": dict(runtime.video_params or {}),
                }
            }

        return await self.create(
            user,
            GenerationCreate(
                project_id=source.project_id,
                input_asset_id=source_asset.id,
                type=GenerationType.VIDEO,
                prompt=envelope,
            ),
            before_commit=bind_video,
            origin=GenerationOrigin.QUESTIONNAIRE_VIDEO,
        )

    async def get_video(
        self, user: User, source_generation_id: UUID
    ) -> GenerationResponse | None:
        source = await self.repository.get_owned(source_generation_id, user.id)
        if source is None:
            raise AppError(
                type="video_source_not_found",
                title="Concept not found",
                status=404,
                detail="The source generation does not exist or is not available.",
            )
        if source.output_asset_id is None:
            return None
        existing = await self.repository.get_active_video_for_source_asset(
            source.output_asset_id, user.id
        )
        return await self.to_response(existing) if existing is not None else None

    async def get_video(
        self, user: User, source_generation_id: UUID
    ) -> GenerationResponse | None:
        source = await self.repository.get_owned(source_generation_id, user.id)
        if source is None:
            raise AppError(
                type="video_source_not_found",
                title="Concept not found",
                status=404,
                detail="The source generation does not exist or is not available.",
            )
        if source.output_asset_id is None:
            return None
        video = await self.repository.get_active_video_for_source_asset(
            source.output_asset_id, user.id
        )
        return await self.to_response(video) if video is not None else None

    async def repeat(self, user: User, generation_id: UUID) -> GenerationResponse:
        source = await self.repository.get_owned(generation_id, user.id)
        if source is None:
            raise AppError(
                type="generation_not_found",
                title="Generation not found",
                status=404,
                detail="The generation does not exist or is not available to this user.",
            )
        if source.origin != GenerationOrigin.GENERIC.value:
            raise AppError(
                type="generation_repeat_not_allowed",
                title="Generation cannot be repeated here",
                status=409,
                detail="Server-managed generations must be repeated through their product workflow.",
            )
        return await self.create(
            user,
            GenerationCreate(
                project_id=source.project_id,
                input_asset_id=source.input_asset_id,
                type=source.type,
                prompt=source.prompt,
                composition_mode=source.composition_mode,
                edit_region=source.edit_region,
                protected_regions=source.protected_regions or [],
            ),
        )

    async def get(self, user: User, generation_id: UUID) -> GenerationResponse:
        generation = await self.repository.get_owned(generation_id, user.id)
        if not generation:
            raise AppError(
                type="generation_not_found",
                title="Generation not found",
                status=404,
                detail="The generation does not exist or is not available to this user.",
            )
        return await self.to_response(generation)

    async def list(
        self,
        user: User,
        *,
        project_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> GenerationListResponse:
        if project_id is not None and not await self.projects.get_owned(project_id, user.id):
            raise AppError(
                type="project_not_found",
                title="Project not found",
                status=404,
                detail="The project does not exist or is not available to this user.",
            )
        decoded_cursor = decode_cursor(cursor) if cursor else None
        rows = await self.repository.list_owned(
            user.id,
            project_id=project_id,
            cursor=decoded_cursor,
            limit=limit + 1,
        )
        has_more = len(rows) > limit
        visible = rows[:limit]
        next_cursor = (
            encode_cursor(visible[-1].created_at, visible[-1].id)
            if has_more and visible
            else None
        )
        return GenerationListResponse(
            items=[await self.to_response(item) for item in visible],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def to_response(self, generation: Generation) -> GenerationResponse:
        output_asset: AssetResponse | None = None
        if generation.output_asset_id is not None:
            asset = await self.assets.get_owned(generation.output_asset_id, generation.user_id)
            if asset is not None:
                output_asset = self.asset_service.to_response(asset)
        quality_report = _public_quality_report(generation.quality_report)
        if quality_report and isinstance(quality_report.get("initial_layout_guide"), dict):
            # Recovery snapshots contain operator parameters and the full provider
            # request. Public diagnostics expose only the non-sensitive identity.
            snapshot = quality_report["initial_layout_guide"]
            quality_report = {
                **quality_report,
                "initial_layout_guide": {
                    key: snapshot[key]
                    for key in ("version", "sha256", "reference_role")
                    if key in snapshot
                },
            }
        return GenerationResponse(
            id=generation.id,
            project_id=generation.project_id,
            input_asset_id=generation.input_asset_id,
            output_asset=output_asset,
            type=generation.type,
            status=generation.status,
            prompt=(
                generation.prompt
                if generation.origin == GenerationOrigin.GENERIC.value
                else ""
            ),
            credits_charged=generation.credits_charged,
            model_name=generation.model_name,
            fallback_used=generation.fallback_used,
            composition_mode=generation.composition_mode,
            edit_region=generation.edit_region,
            protected_regions=generation.protected_regions or [],
            edit_policy=generation.edit_policy or {},
            quality_report=quality_report,
            quality_status=generation.quality_status,
            error=generation.error,
            created_at=generation.created_at,
            updated_at=generation.updated_at,
            started_at=generation.started_at,
            completed_at=generation.completed_at,
        )


def build_generation_service(session: AsyncSession, settings: Settings) -> GenerationService:
    return GenerationService(session, settings)
