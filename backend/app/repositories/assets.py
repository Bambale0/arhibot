from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.assets import Asset
from app.db.models.users import User


class AssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, asset: Asset) -> None:
        self.session.add(asset)

    async def get_owned(self, asset_id: UUID, user_id: UUID) -> Asset | None:
        result = await self.session.execute(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.user_id == user_id,
                Asset.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def lock_owner(self, user_id: UUID) -> None:
        await self.session.execute(
            select(User.id).where(User.id == user_id).with_for_update()
        )

    async def retained_usage(self, user_id: UUID) -> tuple[int, int]:
        result = await self.session.execute(
            select(
                func.count(Asset.id),
                func.coalesce(func.sum(Asset.size_bytes), 0),
            ).where(Asset.user_id == user_id)
        )
        count, size_bytes = result.one()
        return int(count or 0), int(size_bytes or 0)

    async def list_active_for_project(self, project_id: UUID) -> list[Asset]:
        result = await self.session.execute(
            select(Asset).where(
                Asset.project_id == project_id,
                Asset.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())
