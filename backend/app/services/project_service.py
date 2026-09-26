from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select

from app.core.cursor import decode_cursor, encode_cursor
from app.core.errors import AppError
from app.db.models.assets import Asset
from app.db.models.generations import Generation
from app.db.models.projects import Project
from app.db.models.users import User
from app.domain.generations.enums import GenerationStatus
from app.repositories.credits import CreditRepository
from app.repositories.projects import ProjectRepository
from app.schemas.projects import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from app.services.credit_service import CreditService

ProjectListSort = Literal["created", "updated"]


class ProjectService:
    def __init__(self, repository: ProjectRepository) -> None:
        self.repository = repository

    @staticmethod
    def _normalize_name(value: str) -> str:
        name = value.strip()
        if not name:
            raise AppError(
                type="validation_error",
                title="Request validation failed",
                status=422,
                detail="Project name must not be blank.",
            )
        return name

    @staticmethod
    def to_response(project: Project) -> ProjectResponse:
        return ProjectResponse.model_validate(project)

    async def create(self, user: User, payload: ProjectCreateRequest) -> ProjectResponse:
        project = Project(
            user_id=user.id,
            name=self._normalize_name(payload.name),
            description=payload.description,
            context=payload.context.model_dump(exclude_none=True),
        )
        self.repository.add(project)
        await self.repository.session.commit()
        await self.repository.session.refresh(project)
        return self.to_response(project)

    async def list(
        self,
        user: User,
        *,
        cursor: str | None,
        limit: int,
        sort: ProjectListSort = "created",
    ) -> ProjectListResponse:
        cursor_at = None
        cursor_id = None
        if cursor:
            cursor_at, cursor_id = decode_cursor(cursor)
        sort_by = "updated_at" if sort == "updated" else "created_at"

        rows = await self.repository.list_owned(
            user.id,
            limit=limit + 1,
            cursor_at=cursor_at,
            cursor_id=cursor_id,
            sort_by=sort_by,
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(
                last.updated_at if sort_by == "updated_at" else last.created_at,
                last.id,
            )
        return ProjectListResponse(
            items=[self.to_response(item) for item in items],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def get(self, user: User, project_id: UUID) -> ProjectResponse:
        project = await self.get_owned_model(user, project_id)
        return self.to_response(project)

    async def get_owned_model(
        self, user: User, project_id: UUID, *, for_update: bool = False,
    ) -> Project:
        project = await self.repository.get_owned(project_id, user.id, for_update=for_update)
        if not project:
            raise AppError(
                type="project_not_found",
                title="Project not found",
                status=404,
                detail="The project does not exist or is not available to this user.",
            )
        return project

    async def update(
        self, user: User, project_id: UUID, payload: ProjectUpdateRequest
    ) -> ProjectResponse:
        project = await self.get_owned_model(user, project_id)
        fields = payload.model_fields_set
        if (
            "context" in fields
            and payload.context is not None
            and (project.context or {}).get("questionnaire_draft") is True
        ):
            raise AppError(
                type="questionnaire_project_draft_locked",
                title="Questionnaire project draft is locked",
                status=409,
                detail="Complete or discard the questionnaire source step before editing project context.",
            )
        if "name" in fields and payload.name is not None:
            project.name = self._normalize_name(payload.name)
        if "description" in fields:
            project.description = payload.description
        if "status" in fields and payload.status is not None:
            project.status = payload.status
        if "context" in fields and payload.context is not None:
            updated_context = payload.context.model_dump(exclude_none=True)
            existing_architecture = (project.context or {}).get("architecture")
            if existing_architecture is not None and "architecture" not in updated_context:
                updated_context["architecture"] = existing_architecture
            existing_design_session = (project.context or {}).get("design_session")
            if existing_design_session is not None:
                updated_context["design_session"] = existing_design_session
            existing_questionnaire_draft = (project.context or {}).get("questionnaire_draft")
            if existing_questionnaire_draft is not None:
                updated_context["questionnaire_draft"] = existing_questionnaire_draft
            project.context = updated_context
        await self.repository.session.commit()
        await self.repository.session.refresh(project)
        return self.to_response(project)

    async def delete(self, user: User, project_id: UUID) -> None:
        session = self.repository.session

        # Keep the same lock order as generation creation: user -> project -> jobs.
        # This closes the race where a paid job could be accepted while deletion is
        # committing, and lets the refund ledger remain idempotent.
        locked_user = await CreditRepository(session).get_user_for_update(user.id)
        if locked_user is None:
            raise AppError(
                type="project_not_found",
                title="Project not found",
                status=404,
                detail="The project does not exist or is not available to this user.",
            )
        project = await self.repository.get_owned(project_id, user.id, for_update=True)
        if project is None:
            raise AppError(
                type="project_not_found",
                title="Project not found",
                status=404,
                detail="The project does not exist or is not available to this user.",
            )

        deleted_at = datetime.now(UTC)
        active_result = await session.execute(
            select(Generation)
            .where(
                Generation.project_id == project.id,
                Generation.status.in_(
                    [GenerationStatus.QUEUED, GenerationStatus.PROCESSING]
                ),
            )
            .with_for_update()
        )
        credit_service = CreditService(session)
        for generation in active_result.scalars().all():
            generation.status = GenerationStatus.FAILED
            generation.error = "Project was deleted before generation completed."
            generation.completed_at = deleted_at
            if generation.credits_charged > 0:
                await credit_service.apply(
                    user_id=generation.user_id,
                    amount=generation.credits_charged,
                    kind="generation_refund",
                    idempotency_key=f"generation:{generation.id}:refund",
                    reference_type="generation",
                    reference_id=str(generation.id),
                    reason="Project deleted",
                )

        assets_result = await session.execute(
            select(Asset)
            .where(
                Asset.project_id == project.id,
                Asset.deleted_at.is_(None),
            )
            .with_for_update()
        )
        for asset in assets_result.scalars().all():
            asset.deleted_at = deleted_at

        project.deleted_at = deleted_at
        await session.commit()
