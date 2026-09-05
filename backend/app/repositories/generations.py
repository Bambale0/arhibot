from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.generations import Generation


class GenerationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, generation: Generation) -> None:
        self.session.add(generation)

    async def get_owned(self, generation_id: UUID, user_id: UUID) -> Generation | None:
        result = await self.session.execute(
            select(Generation).where(
                Generation.id == generation_id,
                Generation.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get(self, generation_id: UUID) -> Generation | None:
        return await self.session.get(Generation, generation_id)

    async def list_owned(
        self,
        user_id: UUID,
        *,
        project_id: UUID | None = None,
        cursor: tuple[datetime, UUID] | None = None,
        limit: int = 50,
    ) -> list[Generation]:
        query = select(Generation).where(Generation.user_id == user_id)
        if project_id is not None:
            query = query.where(Generation.project_id == project_id)
        if cursor is not None:
            created_at, item_id = cursor
            query = query.where(
                or_(
                    Generation.created_at < created_at,
                    and_(Generation.created_at == created_at, Generation.id < item_id),
                )
            )
        query = query.order_by(Generation.created_at.desc(), Generation.id.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
