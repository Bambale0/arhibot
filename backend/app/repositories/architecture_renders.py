from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.architecture_renders import ArchitectureRender


class ArchitectureRenderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, render: ArchitectureRender) -> None:
        self.session.add(render)

    def add_all(self, renders: list[ArchitectureRender]) -> None:
        self.session.add_all(renders)

    async def get_owned(self, render_id: UUID, user_id: UUID) -> ArchitectureRender | None:
        result = await self.session.execute(
            select(ArchitectureRender).where(
                ArchitectureRender.id == render_id,
                ArchitectureRender.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_batch_owned(self, batch_id: UUID, user_id: UUID) -> list[ArchitectureRender]:
        result = await self.session.execute(
            select(ArchitectureRender)
            .where(
                ArchitectureRender.batch_id == batch_id,
                ArchitectureRender.user_id == user_id,
            )
            .order_by(ArchitectureRender.created_at.asc(), ArchitectureRender.id.asc())
        )
        return list(result.scalars().all())

    async def get_for_update(self, render_id: UUID) -> ArchitectureRender | None:
        result = await self.session.execute(
            select(ArchitectureRender)
            .where(ArchitectureRender.id == render_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()
