from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.assets import Asset


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
