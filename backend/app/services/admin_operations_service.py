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
            auth_rate_limit_per_minute=row.auth_rate_limit_per_minute if row else 30,
            generation_rate_limit_per_minute=row.generation_rate_limit_per_minute if row else 10,
            payment_rate_limit_per_minute=row.payment_rate_limit_per_minute if row else 10,
            registration_rate_limit_per_day=(
                row.registration_rate_limit_per_day if row else 20
            ),
            yookassa_webhook_rate_limit_per_minute=(
                row.yookassa_webhook_rate_limit_per_minute if row else 120
            ),
            asset_upload_rate_limit_per_minute=(
                row.asset_upload_rate_limit_per_minute if row else 12
            ),
            asset_max_retained_count_per_user=(
                row.asset_max_retained_count_per_user if row else 200
            ),
            asset_max_retained_bytes_per_user=(
                row.asset_max_retained_bytes_per_user if row else 512 * 1024 * 1024
            ),
            generation_max_inflight_per_user=(
                row.generation_max_inflight_per_user if row else 2
            ),
            initial_concept_offer_limit_per_day=(
                row.initial_concept_offer_limit_per_day if row else 3
            ),
            starter_credits=row.starter_credits if row else 0,
            initial_concept_credits=row.initial_concept_credits if row else 0,
            media_retention_days=row.media_retention_days if row else None,
            backup_interval_hours=row.backup_interval_hours if row else None,
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
        for field, value in payload.model_dump(exclude_unset=True).items():
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
