from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin import IdeaBookmark, IdeaPublication


class IdeaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, publication: IdeaPublication) -> None:
        self.session.add(publication)

    def add_bookmark(self, bookmark: IdeaBookmark) -> None:
        self.session.add(bookmark)

    async def get_bookmark(self, user_id: UUID, idea_id: UUID) -> IdeaBookmark | None:
        return await self.session.get(IdeaBookmark, (user_id, idea_id))

    async def list_bookmark_ids(self, user_id: UUID) -> list[UUID]:
        result = await self.session.execute(
            select(IdeaBookmark.idea_id)
            .where(IdeaBookmark.user_id == user_id)
            .order_by(IdeaBookmark.created_at.desc())
        )
        return list(result.scalars().all())

    async def remove_bookmark(self, user_id: UUID, idea_id: UUID) -> None:
        await self.session.execute(
            delete(IdeaBookmark).where(
                IdeaBookmark.user_id == user_id,
                IdeaBookmark.idea_id == idea_id,
            )
        )

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
