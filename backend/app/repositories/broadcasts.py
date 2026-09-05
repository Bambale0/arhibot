from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin import BroadcastCampaign
from app.db.models.broadcasts import BroadcastDelivery
from app.db.models.users import AuthIdentity, User
from app.domain.users.enums import AuthProvider, UserStatus


class BroadcastRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_campaign(self, campaign: BroadcastCampaign) -> None:
        self.session.add(campaign)

    def add_delivery(self, delivery: BroadcastDelivery) -> None:
        self.session.add(delivery)

    async def get_campaign(self, campaign_id: UUID, *, for_update: bool = False) -> BroadcastCampaign | None:
        stmt = select(BroadcastCampaign).where(BroadcastCampaign.id == campaign_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_campaigns(self, *, limit: int = 100) -> list[BroadcastCampaign]:
        result = await self.session.execute(
            select(BroadcastCampaign).order_by(BroadcastCampaign.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def list_recipient_ids(self, segment: str) -> list[str]:
        stmt = (
            select(AuthIdentity.provider_user_id)
            .join(User, User.id == AuthIdentity.user_id)
            .where(
                AuthIdentity.provider == AuthProvider.TELEGRAM,
                User.status == UserStatus.ACTIVE,
            )
        )
        if segment == "with_credits":
            stmt = stmt.where(User.credits_balance > 0)
        elif segment == "without_credits":
            stmt = stmt.where(User.credits_balance == 0)
        result = await self.session.execute(stmt.order_by(AuthIdentity.created_at.asc()))
        return [value for value in result.scalars().all() if value]

    async def get_next_delivery(self, campaign_id: UUID, now: datetime) -> BroadcastDelivery | None:
        result = await self.session.execute(
            select(BroadcastDelivery)
            .where(
                BroadcastDelivery.campaign_id == campaign_id,
                BroadcastDelivery.status.in_(["pending", "retry"]),
                (BroadcastDelivery.next_attempt_at.is_(None) | (BroadcastDelivery.next_attempt_at <= now)),
            )
            .order_by(BroadcastDelivery.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_delivery_statuses(self, campaign_id: UUID) -> dict[str, int]:
        result = await self.session.execute(
            select(BroadcastDelivery.status, func.count(BroadcastDelivery.id))
            .where(BroadcastDelivery.campaign_id == campaign_id)
            .group_by(BroadcastDelivery.status)
        )
        return {str(status): int(count) for status, count in result.all()}


    async def list_recoverable_queued(self, *, limit: int = 500) -> list[BroadcastCampaign]:
        result = await self.session.execute(
            select(BroadcastCampaign)
            .where(BroadcastCampaign.status == "queued")
            .order_by(BroadcastCampaign.updated_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_due_scheduled(self, now: datetime, *, limit: int = 50) -> list[BroadcastCampaign]:
        result = await self.session.execute(
            select(BroadcastCampaign)
            .where(
                BroadcastCampaign.status == "scheduled",
                BroadcastCampaign.scheduled_at.is_not(None),
                BroadcastCampaign.scheduled_at <= now,
            )
            .order_by(BroadcastCampaign.scheduled_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def reset_failed_deliveries(self, campaign_id: UUID) -> int:
        rows = await self.session.execute(
            select(BroadcastDelivery).where(
                BroadcastDelivery.campaign_id == campaign_id,
                BroadcastDelivery.status == "failed",
            )
        )
        count = 0
        for row in rows.scalars().all():
            row.status = "retry"
            row.next_attempt_at = None
            row.last_error = None
            count += 1
        return count

    async def reset_interrupted_deliveries(self) -> int:
        rows = await self.session.execute(
            select(BroadcastDelivery).where(BroadcastDelivery.status == "sending")
        )
        count = 0
        for row in rows.scalars().all():
            row.status = "retry"
            row.next_attempt_at = None
            row.last_error = "Delivery interrupted by worker restart"
            count += 1
        return count
