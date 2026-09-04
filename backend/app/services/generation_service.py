from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.redis import redis_client
from app.db.models.generations import Generation
from app.db.models.users import User
from app.domain.generations.enums import GenerationStatus
from app.repositories.assets import AssetRepository
from app.repositories.generations import GenerationRepository
from app.repositories.projects import ProjectRepository
from app.schemas.assets import AssetResponse
from app.schemas.generations import GenerationCreate, GenerationListResponse, GenerationResponse
from app.services.asset_service import AssetService, build_asset_service

GENERATION_QUEUE_KEY = "auroom:generation_queue"


class GenerationService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = GenerationRepository(session)
        self.assets = AssetRepository(session)
        self.projects = ProjectRepository(session)
        self.asset_service: AssetService = build_asset_service(session, settings)

    async def create(self, user: User, payload: GenerationCreate) -> GenerationResponse:
        if not (self.settings.nexus_api_key or "").strip():
            raise AppError(
                type="generation_provider_not_configured",
                title="Generation provider not configured",
                status=503,
                detail="NexusAPI is not configured for this environment.",
            )

        project = await self.projects.get_owned(payload.project_id, user.id)
        if not project:
            raise AppError(
                type="project_not_found",
                title="Project not found",
                status=404,
                detail="The project does not exist or is not available to this user.",
            )
        asset = await self.assets.get_owned(payload.input_asset_id, user.id)
        if not asset or asset.project_id != project.id:
            raise AppError(
                type="asset_not_found",
                title="Asset not found",
                status=404,
                detail="The input asset does not belong to this project.",
            )

        generation = Generation(
            id=uuid4(),
            user_id=user.id,
            project_id=project.id,
            input_asset_id=asset.id,
            type=payload.type,
            status=GenerationStatus.QUEUED,
            prompt=payload.prompt.strip(),
        )
        self.repository.add(generation)
        await self.session.commit()
        await self.session.refresh(generation)

        try:
            await redis_client.rpush(GENERATION_QUEUE_KEY, str(generation.id))
        except Exception as exc:
            generation.status = GenerationStatus.FAILED
            generation.error = "Generation queue is unavailable."
            await self.session.commit()
            raise AppError(
                type="generation_queue_unavailable",
                title="Generation queue unavailable",
                status=503,
                detail="Generation could not be queued. Please try again.",
            ) from exc

        return await self.to_response(generation)

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
        limit: int = 50,
    ) -> GenerationListResponse:
        if project_id is not None and not await self.projects.get_owned(project_id, user.id):
            raise AppError(
                type="project_not_found",
                title="Project not found",
                status=404,
                detail="The project does not exist or is not available to this user.",
            )
        items = await self.repository.list_owned(user.id, project_id=project_id, limit=limit)
        return GenerationListResponse(items=[await self.to_response(item) for item in items])

    async def to_response(self, generation: Generation) -> GenerationResponse:
        output_asset: AssetResponse | None = None
        if generation.output_asset_id is not None:
            asset = await self.assets.get_owned(generation.output_asset_id, generation.user_id)
            if asset is not None:
                output_asset = self.asset_service.to_response(asset)
        return GenerationResponse(
            id=generation.id,
            project_id=generation.project_id,
            input_asset_id=generation.input_asset_id,
            output_asset=output_asset,
            type=generation.type,
            status=generation.status,
            prompt=generation.prompt,
            model_name=generation.model_name,
            fallback_used=generation.fallback_used,
            error=generation.error,
            created_at=generation.created_at,
            updated_at=generation.updated_at,
            started_at=generation.started_at,
            completed_at=generation.completed_at,
        )


def build_generation_service(session: AsyncSession, settings: Settings) -> GenerationService:
    return GenerationService(session, settings)
