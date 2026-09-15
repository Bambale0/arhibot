from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.generations import Generation
from app.db.models.projects import Project
from app.domain.generations.enums import GenerationStatus


class GenerationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, generation: Generation) -> None:
        self.session.add(generation)

    async def get_owned(self, generation_id: UUID, user_id: UUID) -> Generation | None:
        result = await self.session.execute(
            select(Generation)
            .join(Project, Project.id == Generation.project_id)
            .where(
                Generation.id == generation_id,
                Generation.user_id == user_id,
                Project.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get(self, generation_id: UUID) -> Generation | None:
        return await self.session.get(Generation, generation_id)

    async def get_for_update(self, generation_id: UUID) -> Generation | None:
        result = await self.session.execute(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def count_inflight(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count(Generation.id)).where(
                Generation.user_id == user_id,
                Generation.status.in_(
                    [GenerationStatus.QUEUED, GenerationStatus.PROCESSING]
                ),
            )
        )
        return int(result.scalar_one() or 0)

    async def count_initial_offer_attempts_since(
        self,
        user_id: UUID,
        since: datetime,
    ) -> int:
        result = await self.session.execute(
            select(func.count(Generation.id)).where(
                Generation.user_id == user_id,
                Generation.created_at >= since,
                or_(
                    Generation.origin == "questionnaire_initial",
                    Generation.prompt.startswith("AUROOM_INITIAL_CONCEPT_V1"),
                ),
            )
        )
        return int(result.scalar_one() or 0)

    async def project_used_initial_offer(self, project_id: UUID) -> bool:
        result = await self.session.execute(
            select(
                exists().where(
                    Generation.project_id == project_id,
                    or_(
                        Generation.origin == "questionnaire_initial",
                        Generation.prompt.startswith("AUROOM_INITIAL_CONCEPT_V1"),
                    ),
                )
            )
        )
        return bool(result.scalar())


    async def project_has_origin(self, project_id: UUID, origin: str) -> bool:
        result = await self.session.execute(
            select(
                exists().where(
                    Generation.project_id == project_id,
                    Generation.origin == origin,
                )
            )
        )
        return bool(result.scalar())


    async def list_pending_telegram_deliveries(
        self, *, limit: int = 20
    ) -> list[Generation]:
        result = await self.session.execute(
            select(Generation)
            .where(
                Generation.status == GenerationStatus.COMPLETED,
                Generation.output_asset_id.is_not(None),
                Generation.telegram_delivery_status.in_(["pending", "sending"]),
            )
            .order_by(
                Generation.telegram_delivery_attempts.asc(),
                Generation.completed_at.asc(),
                Generation.created_at.asc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_owned(
        self,
        user_id: UUID,
        *,
        project_id: UUID | None = None,
        cursor: tuple[datetime, UUID] | None = None,
        limit: int = 50,
    ) -> list[Generation]:
        query = (
            select(Generation)
            .join(Project, Project.id == Generation.project_id)
            .where(
                Generation.user_id == user_id,
                Project.deleted_at.is_(None),
            )
        )
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
