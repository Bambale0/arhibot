from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin import IdeaPublication, IdeaSave


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
            stmt = stmt.where(
                IdeaPublication.is_active.is_(True),
                IdeaPublication.owner_published.is_(True),
            )
        result = await self.session.execute(
            stmt.order_by(
                IdeaPublication.sort_order.asc(),
                IdeaPublication.created_at.desc(),
            ).limit(limit)
        )
        return list(result.scalars().all())


    async def saved_publication_ids(self, user_id: UUID) -> set[UUID]:
        result = await self.session.execute(
            select(IdeaSave.idea_publication_id).where(IdeaSave.user_id == user_id)
        )
        return set(result.scalars().all())

    async def get_save(self, user_id: UUID, idea_id: UUID) -> IdeaSave | None:
        result = await self.session.execute(
            select(IdeaSave).where(
                IdeaSave.user_id == user_id,
                IdeaSave.idea_publication_id == idea_id,
            )
        )
        return result.scalar_one_or_none()

    def add_save(self, save: IdeaSave) -> None:
        self.session.add(save)

    async def remove_save(self, user_id: UUID, idea_id: UUID) -> None:
        await self.session.execute(
            delete(IdeaSave).where(
                IdeaSave.user_id == user_id,
                IdeaSave.idea_publication_id == idea_id,
            )
        )
