from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.assets import Asset
from app.db.models.projects import Project
from app.db.models.questionnaires import (
    QuestionnaireApplication,
    QuestionnaireCatalogConfig,
    QuestionnaireCatalogRevision,
)
from app.db.models.users import User


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

    async def get_catalog_revision(self, version: str) -> QuestionnaireCatalogRevision | None:
        return await self.session.get(QuestionnaireCatalogRevision, version)

    def add_catalog_revision(self, row: QuestionnaireCatalogRevision) -> None:
        self.session.add(row)

    async def get_application_by_session(self, session_id: UUID) -> QuestionnaireApplication | None:
        result = await self.session.execute(
            select(QuestionnaireApplication).where(QuestionnaireApplication.session_id == session_id)
        )
        return result.scalar_one_or_none()

    def add_application(self, row: QuestionnaireApplication) -> None:
        self.session.add(row)

    async def list_applications_with_context(
        self, *, limit: int = 200
    ) -> list[tuple[QuestionnaireApplication, str | None, str | None, str | None]]:
        result = await self.session.execute(
            select(
                QuestionnaireApplication,
                Project.name,
                User.display_name,
                Asset.storage_path,
            )
            .outerjoin(Project, Project.id == QuestionnaireApplication.project_id)
            .outerjoin(User, User.id == QuestionnaireApplication.user_id)
            .outerjoin(Asset, Asset.id == QuestionnaireApplication.scene_asset_id)
            .order_by(QuestionnaireApplication.created_at.desc())
            .limit(limit)
        )
        return list(result.tuples().all())

    async def get_catalog_revisions(
        self, versions: set[str]
    ) -> dict[str, QuestionnaireCatalogRevision]:
        if not versions:
            return {}
        result = await self.session.execute(
            select(QuestionnaireCatalogRevision).where(
                QuestionnaireCatalogRevision.version.in_(versions)
            )
        )
        return {row.version: row for row in result.scalars().all()}

    async def list_pending_telegram_applications(
        self, *, limit: int = 20
    ) -> list[QuestionnaireApplication]:
        result = await self.session.execute(
            select(QuestionnaireApplication)
            .where(QuestionnaireApplication.telegram_delivery_status == "pending")
            .order_by(QuestionnaireApplication.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
