from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.operations import OperationalSettings
from app.db.models.users import User
from app.repositories.admin import AdminRepository
from app.repositories.operations import OperationalSettingsRepository
from app.schemas.admin import OperationalSettingsResponse, OperationalSettingsUpdate


class AdminOperationsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = OperationalSettingsRepository(session)
        self.audit = AdminRepository(session)

    @staticmethod
    def response(row: OperationalSettings | None) -> OperationalSettingsResponse:
        return OperationalSettingsResponse(
            auth_rate_limit_per_minute=row.auth_rate_limit_per_minute if row else None,
            generation_rate_limit_per_minute=row.generation_rate_limit_per_minute if row else None,
            payment_rate_limit_per_minute=row.payment_rate_limit_per_minute if row else None,
            media_retention_days=row.media_retention_days if row else None,
            backup_retention_days=row.backup_retention_days if row else None,
            updated_at=row.updated_at if row else None,
        )

    async def get(self) -> OperationalSettingsResponse:
        return self.response(await self.repository.get())

    async def update(self, actor: User, payload: OperationalSettingsUpdate) -> OperationalSettingsResponse:
        row = await self.repository.get(for_update=True)
        if row is None:
            row = OperationalSettings(id=1)
            self.repository.add(row)
        for field, value in payload.model_dump().items():
            setattr(row, field, value)
        row.updated_by_user_id = actor.id
        self.audit.add_audit(
            actor_user_id=actor.id,
            action="operations.settings.update",
            entity_type="operational_settings",
            entity_id="1",
            details={"fields": sorted(payload.model_fields_set)},
        )
        await self.session.commit()
        await self.session.refresh(row)
        return self.response(row)
