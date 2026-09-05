from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.redis import redis_client
from app.db.models.admin import BroadcastCampaign
from app.db.models.broadcasts import BroadcastDelivery
from app.db.models.users import User
from app.repositories.admin import AdminRepository
from app.repositories.broadcasts import BroadcastRepository
from app.schemas.admin import BroadcastCreate, BroadcastResponse

BROADCAST_QUEUE_KEY = "auroom:broadcast_queue"


class BroadcastService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = BroadcastRepository(session)
        self.audit = AdminRepository(session)

    @staticmethod
    def response(row: BroadcastCampaign) -> BroadcastResponse:
        return BroadcastResponse(
            id=row.id,
            text=row.text,
            status=row.status,
            segment=row.segment,
            recipient_count=row.recipient_count,
            sent_count=row.sent_count,
            failed_count=row.failed_count,
            scheduled_at=row.scheduled_at,
            canceled_at=row.canceled_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            sent_at=row.sent_at,
        )

    async def list(self) -> list[BroadcastResponse]:
        return [self.response(row) for row in await self.repository.list_campaigns()]

    async def create(self, actor: User, payload: BroadcastCreate) -> BroadcastResponse:
        scheduled_at = payload.scheduled_at
        if scheduled_at is not None and scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=UTC)
        status = "scheduled" if scheduled_at and scheduled_at > datetime.now(UTC) else "draft"
        row = BroadcastCampaign(
            created_by_user_id=actor.id,
            text=payload.text.strip(),
            segment=payload.segment,
            status=status,
            scheduled_at=scheduled_at,
        )
        self.repository.add_campaign(row)
        self.audit.add_audit(
            actor_user_id=actor.id,
            action="broadcast.create",
            entity_type="broadcast",
            entity_id=str(row.id),
            details={"segment": row.segment, "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None},
        )
        await self.session.commit()
        await self.session.refresh(row)
        if status == "scheduled" and row.scheduled_at and row.scheduled_at <= datetime.now(UTC):
            await self.queue(actor, row.id)
        return self.response(row)

    async def _ensure_deliveries(self, campaign: BroadcastCampaign) -> int:
        recipients = await self.repository.list_recipient_ids(campaign.segment)
        for recipient_id in recipients:
            self.repository.add_delivery(
                BroadcastDelivery(campaign_id=campaign.id, recipient_id=recipient_id)
            )
        campaign.recipient_count = len(recipients)
        return len(recipients)

    async def queue(self, actor: User, campaign_id: UUID) -> BroadcastResponse:
        campaign = await self.repository.get_campaign(campaign_id, for_update=True)
        if campaign is None:
            raise AppError(type="broadcast_not_found", title="Broadcast not found", status=404, detail="Broadcast does not exist.")
        if campaign.status in {"sent", "canceled"}:
            raise AppError(type="broadcast_not_queueable", title="Broadcast cannot be queued", status=409, detail="This campaign is already terminal.")
        if campaign.recipient_count == 0:
            await self._ensure_deliveries(campaign)
        campaign.status = "queued"
        campaign.scheduled_at = None
        campaign.canceled_at = None
        self.audit.add_audit(
            actor_user_id=actor.id,
            action="broadcast.queue",
            entity_type="broadcast",
            entity_id=str(campaign.id),
            details={"recipients": campaign.recipient_count},
        )
        await self.session.commit()
        await redis_client.rpush(BROADCAST_QUEUE_KEY, str(campaign.id))
        await self.session.refresh(campaign)
        return self.response(campaign)

    async def retry_failed(self, actor: User, campaign_id: UUID) -> BroadcastResponse:
        campaign = await self.repository.get_campaign(campaign_id, for_update=True)
        if campaign is None:
            raise AppError(type="broadcast_not_found", title="Broadcast not found", status=404, detail="Broadcast does not exist.")
        reset = await self.repository.reset_failed_deliveries(campaign.id)
        if reset == 0:
            raise AppError(type="broadcast_nothing_to_retry", title="Nothing to retry", status=409, detail="There are no failed deliveries.")
        campaign.status = "queued"
        campaign.failed_count = 0
        self.audit.add_audit(
            actor_user_id=actor.id,
            action="broadcast.retry",
            entity_type="broadcast",
            entity_id=str(campaign.id),
            details={"deliveries": reset},
        )
        await self.session.commit()
        await redis_client.rpush(BROADCAST_QUEUE_KEY, str(campaign.id))
        await self.session.refresh(campaign)
        return self.response(campaign)

    async def cancel(self, actor: User, campaign_id: UUID) -> BroadcastResponse:
        campaign = await self.repository.get_campaign(campaign_id, for_update=True)
        if campaign is None:
            raise AppError(type="broadcast_not_found", title="Broadcast not found", status=404, detail="Broadcast does not exist.")
        if campaign.status == "sent":
            raise AppError(type="broadcast_already_sent", title="Broadcast already sent", status=409, detail="A completed broadcast cannot be canceled.")
        campaign.status = "canceled"
        campaign.canceled_at = datetime.now(UTC)
        self.audit.add_audit(
            actor_user_id=actor.id,
            action="broadcast.cancel",
            entity_type="broadcast",
            entity_id=str(campaign.id),
        )
        await self.session.commit()
        await self.session.refresh(campaign)
        return self.response(campaign)
