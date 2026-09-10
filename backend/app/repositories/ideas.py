from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin import IdeaPublication
from app.db.models.generations import Generation
from app.db.models.projects import Project
from app.db.models.users import User
from app.domain.generations.enums import GenerationStatus
from app.domain.users.enums import UserRole


class IdeaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, publication: IdeaPublication) -> None:
        self.session.add(publication)

    async def get(self, idea_id: UUID) -> IdeaPublication | None:
        return await self.session.get(IdeaPublication, idea_id)

    async def get_by_generation(self, generation_id: UUID) -> IdeaPublication | None:
        result = await self.session.execute(
            select(IdeaPublication).where(IdeaPublication.generation_id == generation_id)
        )
        return result.scalar_one_or_none()

    async def list(self, *, active_only: bool = False, limit: int = 50) -> list[IdeaPublication]:
        stmt = select(IdeaPublication)
        if active_only:
            stmt = stmt.where(IdeaPublication.is_active.is_(True))
        result = await self.session.execute(
            stmt.order_by(
                IdeaPublication.sort_order.asc(),
                IdeaPublication.created_at.desc(),
            ).limit(limit)
        )
        return list(result.scalars().all())

    async def list_candidate_sources(
        self, *, limit: int = 200
    ) -> list[tuple[Generation, Project, User]]:
        result = await self.session.execute(
            select(Generation, Project, User)
            .join(Project, Project.id == Generation.project_id)
            .join(User, User.id == Generation.user_id)
            .where(
                Generation.status == GenerationStatus.COMPLETED,
                Generation.output_asset_id.is_not(None),
                Project.deleted_at.is_(None),
                User.role.in_([UserRole.ADMIN, UserRole.SUPERADMIN]),
            )
            .order_by(Generation.completed_at.desc(), Generation.created_at.desc())
            .limit(limit)
        )
        return [(row[0], row[1], row[2]) for row in result.all()]
