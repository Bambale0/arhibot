from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.users import User
from app.repositories.admin import AdminRepository
from app.repositories.architecture_renders import ArchitectureRenderRepository
from app.repositories.projects import ProjectRepository
from app.schemas.architecture_renders import ArchitectureRenderBatchResponse
from app.services.architecture_render_service import ArchitectureRenderService


class ArchitectureIdeaRenderService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.admin_repository = AdminRepository(session)
        self.project_repository = ProjectRepository(session)
        self.render_service = ArchitectureRenderService(
            ArchitectureRenderRepository(session),
            self.project_repository,
            settings,
        )

    async def queue(self, actor: User, idea_id: UUID) -> ArchitectureRenderBatchResponse:
        idea = await self.admin_repository.get_idea(idea_id)
        if idea is None:
            raise AppError(
                type="idea_not_found",
                title="Idea not found",
                status=404,
                detail="Idea does not exist.",
            )
        if idea.architecture_project_id is None:
            raise AppError(
                type="idea_architecture_project_required",
                title="Architecture project required",
                status=422,
                detail="Select an architecture project for the Idea before rendering it.",
            )
        project = await self.project_repository.get_owned(idea.architecture_project_id, actor.id)
        if project is None:
            raise AppError(
                type="idea_architecture_project_not_found",
                title="Architecture project not found",
                status=404,
                detail="The Idea architecture project is not available to this administrator.",
            )
        response = await self.render_service.create_batch(
            actor,
            project.id,
            target_idea_id=idea.id,
        )
        self.admin_repository.add_audit(
            actor_user_id=actor.id,
            action="idea.architecture_render_batch.queue",
            entity_type="idea",
            entity_id=str(idea.id),
            details={
                "batch_id": str(response.batch_id),
                "project_id": str(project.id),
                "source_digest": response.source_digest,
                "camera_profiles": [render.camera_profile.value for render in response.renders],
            },
        )
        await self.session.commit()
        return response
