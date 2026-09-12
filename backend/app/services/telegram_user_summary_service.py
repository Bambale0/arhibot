from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.generations import Generation
from app.db.models.projects import Project
from app.domain.generations.enums import GenerationStatus
from app.domain.users.enums import AuthProvider
from app.repositories.users import UserRepository
from app.schemas.telegram import TelegramUserSummaryResponse


class TelegramUserSummaryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def get(self, telegram_user_id: str) -> TelegramUserSummaryResponse | None:
        identity = await self.users.get_identity(
            AuthProvider.TELEGRAM, telegram_user_id
        )
        if identity is None or identity.user is None:
            return None
        user = identity.user
        project_count = await self.session.scalar(
            select(func.count(Project.id)).where(
                Project.user_id == user.id,
                Project.deleted_at.is_(None),
            )
        )
        generation_count = await self.session.scalar(
            select(func.count(Generation.id)).where(
                Generation.user_id == user.id,
                Generation.status.in_(
                    [GenerationStatus.QUEUED, GenerationStatus.PROCESSING]
                ),
            )
        )
        return TelegramUserSummaryResponse(
            display_name=user.display_name,
            credits_balance=user.credits_balance,
            active_projects=int(project_count or 0),
            active_generations=int(generation_count or 0),
        )
