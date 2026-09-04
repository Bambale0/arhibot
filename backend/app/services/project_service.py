from datetime import UTC, datetime
from uuid import UUID

from app.core.cursor import decode_cursor, encode_cursor
from app.core.errors import AppError
from app.db.models.projects import Project
from app.db.models.users import User
from app.repositories.projects import ProjectRepository
from app.schemas.projects import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)


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

    async def list(self, user: User, *, cursor: str | None, limit: int) -> ProjectListResponse:
        cursor_created_at = None
        cursor_id = None
        if cursor:
            cursor_created_at, cursor_id = decode_cursor(cursor)

        rows = await self.repository.list_owned(
            user.id,
            limit=limit + 1,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return ProjectListResponse(
            items=[self.to_response(item) for item in items],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def get(self, user: User, project_id: UUID) -> ProjectResponse:
        project = await self.get_owned_model(user, project_id)
        return self.to_response(project)

    async def get_owned_model(self, user: User, project_id: UUID) -> Project:
        project = await self.repository.get_owned(project_id, user.id)
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
        if "name" in fields and payload.name is not None:
            project.name = self._normalize_name(payload.name)
        if "description" in fields:
            project.description = payload.description
        if "status" in fields and payload.status is not None:
            project.status = payload.status
        if "context" in fields and payload.context is not None:
            project.context = payload.context.model_dump(exclude_none=True)
        await self.repository.session.commit()
        await self.repository.session.refresh(project)
        return self.to_response(project)

    async def delete(self, user: User, project_id: UUID) -> None:
        project = await self.get_owned_model(user, project_id)
        project.deleted_at = datetime.now(UTC)
        await self.repository.session.commit()
