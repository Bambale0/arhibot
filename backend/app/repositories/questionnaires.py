from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.questionnaires import QuestionnaireApplication, QuestionnaireCatalogConfig


class QuestionnaireRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_catalog(self, *, for_update: bool = False) -> QuestionnaireCatalogConfig | None:
        stmt = select(QuestionnaireCatalogConfig).where(QuestionnaireCatalogConfig.id == 1)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def add_catalog(self, row: QuestionnaireCatalogConfig) -> None:
        self.session.add(row)

    async def get_application_by_session(self, session_id: UUID) -> QuestionnaireApplication | None:
        result = await self.session.execute(
            select(QuestionnaireApplication).where(QuestionnaireApplication.session_id == session_id)
        )
        return result.scalar_one_or_none()

    def add_application(self, row: QuestionnaireApplication) -> None:
        self.session.add(row)

    async def list_applications(self, *, limit: int = 200) -> list[QuestionnaireApplication]:
        result = await self.session.execute(
            select(QuestionnaireApplication)
            .order_by(QuestionnaireApplication.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
