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

    async def get_owned(
        self, project_id: UUID, user_id: UUID, *, for_update: bool = False
    ) -> Project | None:
        query = select(Project).where(
            Project.id == project_id,
            Project.user_id == user_id,
            Project.deleted_at.is_(None),
        )
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_owned(
        self,
        user_id: UUID,
        *,
        limit: int,
        cursor_created_at: datetime | None = None,
        cursor_id: UUID | None = None,
        include_questionnaire_drafts: bool = False,
    ) -> list[Project]:
        query = select(Project).where(Project.user_id == user_id, Project.deleted_at.is_(None))
        if not include_questionnaire_drafts:
            query = query.where(
                Project.context["questionnaire_draft"].as_boolean().is_not(True),
                Project.context["admin_ai_sandbox"].as_boolean().is_not(True),
            )
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

    async def get_admin_ai_sandbox(self, user_id: UUID) -> Project | None:
        result = await self.session.execute(
            select(Project)
            .where(
                Project.user_id == user_id,
                Project.deleted_at.is_(None),
                Project.context["admin_ai_sandbox"].as_boolean().is_(True),
            )
            .order_by(Project.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_expired_questionnaire_drafts(
        self,
        *,
        cutoff: datetime,
        limit: int,
    ) -> list[Project]:
        result = await self.session.execute(
            select(Project)
            .where(
                Project.deleted_at.is_(None),
                Project.context["questionnaire_draft"].as_boolean().is_(True),
                Project.created_at < cutoff,
            )
            .order_by(Project.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
