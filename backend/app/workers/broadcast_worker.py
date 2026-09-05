from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.config import get_settings
from app.core.redis import redis_client
from app.db.models.broadcasts import BroadcastDelivery
from app.db.session import dispose_engine, get_session_factory
from app.repositories.broadcasts import BroadcastRepository
from app.services.broadcast_service import BROADCAST_QUEUE_KEY
from app.telegram_bot.main import TelegramApiError, TelegramBotApi

logger = logging.getLogger(__name__)
MAX_DELIVERY_ATTEMPTS = 3
BROADCAST_PROCESSING_KEY = "auroom:broadcast_processing"


async def _prepare_campaign(campaign_id: UUID) -> bool:
    async with get_session_factory()() as session:
        repository = BroadcastRepository(session)
        campaign = await repository.get_campaign(campaign_id, for_update=True)
        if campaign is None or campaign.status in {"sent", "canceled"}:
            return False
        if campaign.recipient_count == 0:
            recipients = await repository.list_recipient_ids(campaign.segment)
            for recipient_id in recipients:
                repository.add_delivery(
                    BroadcastDelivery(campaign_id=campaign.id, recipient_id=recipient_id)
                )
            campaign.recipient_count = len(recipients)
        campaign.status = "queued"
        campaign.scheduled_at = None
        await session.commit()
        return True


async def _schedule_due_campaigns() -> None:
    async with get_session_factory()() as session:
        repository = BroadcastRepository(session)
        due = await repository.list_due_scheduled(datetime.now(UTC))
        ids = [campaign.id for campaign in due]
    for campaign_id in ids:
        if await _prepare_campaign(campaign_id):
            await redis_client.rpush(BROADCAST_QUEUE_KEY, str(campaign_id))


async def _refresh_campaign_counts(campaign_id: UUID) -> bool:
    async with get_session_factory()() as session:
        repository = BroadcastRepository(session)
        campaign = await repository.get_campaign(campaign_id, for_update=True)
        if campaign is None or campaign.status == "canceled":
            return True
        counts = await repository.count_delivery_statuses(campaign.id)
        campaign.sent_count = counts.get("sent", 0)
        campaign.failed_count = counts.get("failed", 0)
        pending = counts.get("pending", 0) + counts.get("retry", 0) + counts.get("sending", 0)
        if pending == 0:
            campaign.status = "sent" if campaign.failed_count == 0 else "partial"
            campaign.sent_at = datetime.now(UTC)
            await session.commit()
            return True
        campaign.status = "queued"
        await session.commit()
        return False


async def _deliver_one(campaign_id: UUID, api: TelegramBotApi) -> bool:
    now = datetime.now(UTC)
    async with get_session_factory()() as session:
        repository = BroadcastRepository(session)
        campaign = await repository.get_campaign(campaign_id, for_update=True)
        if campaign is None or campaign.status == "canceled":
            return False
        delivery = await repository.get_next_delivery(campaign_id, now)
        if delivery is None:
            return False
        delivery.status = "sending"
        delivery.attempts += 1
        attempt = delivery.attempts
        delivery_id = delivery.id
        recipient_id = delivery.recipient_id
        text = campaign.text
        await session.commit()

    try:
        await asyncio.to_thread(api.call, "sendMessage", {"chat_id": recipient_id, "text": text})
    except TelegramApiError as exc:
        async with get_session_factory()() as session:
            delivery = await session.get(BroadcastDelivery, delivery_id)
            if delivery is None:
                return True
            delivery.last_error = str(exc)[:1000]
            if attempt >= MAX_DELIVERY_ATTEMPTS:
                delivery.status = "failed"
                delivery.next_attempt_at = None
            else:
                retry_seconds = exc.retry_after or min(60, 2**attempt)
                delivery.status = "retry"
                delivery.next_attempt_at = datetime.now(UTC) + timedelta(seconds=retry_seconds)
            await session.commit()
        return True
    except Exception as exc:
        async with get_session_factory()() as session:
            delivery = await session.get(BroadcastDelivery, delivery_id)
            if delivery is None:
                return True
            delivery.last_error = str(exc)[:1000]
            if attempt >= MAX_DELIVERY_ATTEMPTS:
                delivery.status = "failed"
                delivery.next_attempt_at = None
            else:
                delivery.status = "retry"
                delivery.next_attempt_at = datetime.now(UTC) + timedelta(seconds=min(60, 2**attempt))
            await session.commit()
        return True

    async with get_session_factory()() as session:
        delivery = await session.get(BroadcastDelivery, delivery_id)
        if delivery is not None:
            delivery.status = "sent"
            delivery.last_error = None
            delivery.next_attempt_at = None
            delivery.sent_at = datetime.now(UTC)
            await session.commit()
    await asyncio.sleep(0.05)
    return True


async def _process_campaign(campaign_id: UUID, api: TelegramBotApi) -> None:
    if not await _prepare_campaign(campaign_id):
        return
    delivered = await _deliver_one(campaign_id, api)
    terminal = await _refresh_campaign_counts(campaign_id)
    if not terminal:
        await redis_client.rpush(BROADCAST_QUEUE_KEY, str(campaign_id))
        if not delivered:
            await asyncio.sleep(1)


async def _recover_interrupted_work() -> None:
    async with get_session_factory()() as session:
        repository = BroadcastRepository(session)
        reset = await repository.reset_interrupted_deliveries()
        if reset:
            await session.commit()
            logger.warning("Recovered %s interrupted broadcast delivery record(s)", reset)

    reserved = await redis_client.lrange(BROADCAST_PROCESSING_KEY, 0, -1)
    recovered = 0
    for raw_id in reserved:
        await redis_client.lrem(BROADCAST_PROCESSING_KEY, 0, raw_id)
        try:
            UUID(raw_id)
        except (TypeError, ValueError):
            continue
        await redis_client.rpush(BROADCAST_QUEUE_KEY, raw_id)
        recovered += 1
    if recovered:
        logger.warning("Recovered %s reserved broadcast campaign(s)", recovered)


async def _reserve_campaign() -> str | None:
    return await redis_client.lmove(
        BROADCAST_QUEUE_KEY,
        BROADCAST_PROCESSING_KEY,
        "LEFT",
        "RIGHT",
    )


async def _ack_campaign(raw_id: str) -> None:
    await redis_client.lrem(BROADCAST_PROCESSING_KEY, 1, raw_id)


async def run_worker() -> None:
    settings = get_settings()
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required for broadcast worker")
    api = TelegramBotApi(token)
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("AuRoom broadcast worker started; queue uses reserve/ack recovery")
    await _recover_interrupted_work()
    schedule_tick = 0
    while True:
        try:
            schedule_tick += 1
            if schedule_tick >= 5:
                await _schedule_due_campaigns()
                schedule_tick = 0
            raw_id = await _reserve_campaign()
            if raw_id is None:
                await asyncio.sleep(1)
                continue
            try:
                await _process_campaign(UUID(raw_id), api)
            finally:
                await _ack_campaign(raw_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Broadcast worker iteration failed")
            await asyncio.sleep(2)


async def _main() -> None:
    try:
        await run_worker()
    finally:
        await redis_client.aclose()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
