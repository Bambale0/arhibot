from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.operations import OperationalSettings


class OperationalSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, *, for_update: bool = False) -> OperationalSettings | None:
        stmt = select(OperationalSettings).where(OperationalSettings.id == 1)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, row: OperationalSettings) -> None:
        self.session.add(row)
