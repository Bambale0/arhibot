from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.telegram import TelegramContentSettings


class TelegramContentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, *, for_update: bool = False) -> TelegramContentSettings | None:
        stmt = select(TelegramContentSettings).where(TelegramContentSettings.id == 1)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, row: TelegramContentSettings) -> None:
        self.session.add(row)
