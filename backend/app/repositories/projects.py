from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.projects import Project


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, project: Project) -> None:
        self.session.add(project)

    async def get_owned(self, project_id: UUID, user_id: UUID) -> Project | None:
        result = await self.session.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id,
                Project.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_owned(
        self,
        user_id: UUID,
        *,
        limit: int,
        cursor_created_at: datetime | None = None,
        cursor_id: UUID | None = None,
    ) -> list[Project]:
        query = select(Project).where(Project.user_id == user_id, Project.deleted_at.is_(None))
        if cursor_created_at is not None and cursor_id is not None:
            query = query.where(
                or_(
                    Project.created_at < cursor_created_at,
                    and_(Project.created_at == cursor_created_at, Project.id < cursor_id),
                )
            )
        query = query.order_by(Project.created_at.desc(), Project.id.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
