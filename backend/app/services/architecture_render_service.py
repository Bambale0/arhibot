from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID

from app.architecture.schemas import ArchitecturePackage
from app.core.config import Settings
from app.core.errors import AppError
from app.core.redis import redis_client
from app.db.models.architecture_renders import ArchitectureRender
from app.db.models.users import User
from app.repositories.architecture_renders import ArchitectureRenderRepository
from app.repositories.projects import ProjectRepository
from app.schemas.architecture_renders import ArchitectureRenderResponse
from app.services.architecture_service import ArchitectureService
from app.services.asset_service import LocalMediaStorage

logger = logging.getLogger(__name__)
ARCHITECTURE_RENDER_QUEUE_KEY = "auroom:architecture_render_queue"
RENDERER_PROFILE = "blender_eevee_v1"


def snapshot_architecture(package: ArchitecturePackage) -> tuple[dict, str]:
    payload = package.model_dump(mode="json", exclude_none=True)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return payload, hashlib.sha256(canonical).hexdigest()


class ArchitectureRenderService:
    def __init__(
        self,
        repository: ArchitectureRenderRepository,
        project_repository: ProjectRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.settings = settings
        self.storage = LocalMediaStorage(settings)

    def _to_response(self, render: ArchitectureRender) -> ArchitectureRenderResponse:
        image_url = self.storage.public_url(render.storage_path) if render.storage_path else None
        return ArchitectureRenderResponse(
            id=render.id,
            project_id=render.project_id,
            status=render.status,
            source_digest=render.source_digest,
            renderer_profile=render.renderer_profile,
            renderer_version=render.renderer_version,
            image_url=image_url,
            width=render.width,
            height=render.height,
            error=render.error,
            created_at=render.created_at,
            started_at=render.started_at,
            completed_at=render.completed_at,
        )

    async def create(self, user: User, project_id: UUID) -> ArchitectureRenderResponse:
        architecture_service = ArchitectureService(self.project_repository)
        package = await architecture_service.get(user, project_id)
        validation = architecture_service.validate(package)
        if not validation.valid:
            raise AppError(
                type="invalid_architectural_geometry",
                title="Architectural geometry is invalid",
                status=422,
                detail="The saved architecture must pass canonical validation before rendering.",
            )
        snapshot, source_digest = snapshot_architecture(package)
        render = ArchitectureRender(
            user_id=user.id,
            project_id=project_id,
            architecture=snapshot,
            source_digest=source_digest,
            renderer_profile=RENDERER_PROFILE,
        )
        self.repository.add(render)
        await self.repository.session.commit()
        await self.repository.session.refresh(render)
        try:
            await redis_client.rpush(ARCHITECTURE_RENDER_QUEUE_KEY, str(render.id))
        except Exception:
            # PostgreSQL is authoritative. The renderer worker reconciles queued rows after
            # Redis/AOF loss or transient enqueue failure.
            logger.exception(
                "Failed to enqueue architecture render %s; reconciliation will recover it",
                render.id,
            )
        return self._to_response(render)

    async def get(
        self,
        user: User,
        project_id: UUID,
        render_id: UUID,
    ) -> ArchitectureRenderResponse:
        render = await self.repository.get_owned(render_id, user.id)
        if render is None or render.project_id != project_id:
            raise AppError(
                type="architecture_render_not_found",
                title="Architecture render not found",
                status=404,
                detail="The render does not exist or is not available to this user.",
            )
        return self._to_response(render)
