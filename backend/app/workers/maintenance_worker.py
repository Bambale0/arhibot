from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import or_, select

from app.core.config import get_settings
from app.db.models.admin import IdeaTemplate
from app.db.models.assets import Asset
from app.db.models.generations import Generation
from app.db.session import dispose_engine, get_session_factory
from app.repositories.operations import OperationalSettingsRepository
from app.services.asset_service import LocalMediaStorage

logger = logging.getLogger(__name__)
MAINTENANCE_INTERVAL_SECONDS = 3600
CLEANUP_BATCH_SIZE = 100


async def _is_referenced(session, asset_id) -> bool:
    generation_ref = await session.execute(
        select(Generation.id)
        .where(
            or_(
                Generation.input_asset_id == asset_id,
                Generation.output_asset_id == asset_id,
            )
        )
        .limit(1)
    )
    if generation_ref.scalar_one_or_none() is not None:
        return True
    idea_ref = await session.execute(
        select(IdeaTemplate.id).where(IdeaTemplate.image_asset_id == asset_id).limit(1)
    )
    return idea_ref.scalar_one_or_none() is not None


async def cleanup_media_once() -> int:
    settings = get_settings()
    storage = LocalMediaStorage(settings)
    removed = 0
    async with get_session_factory()() as session:
        ops = await OperationalSettingsRepository(session).get()
        retention_days = ops.media_retention_days if ops else None
        if retention_days is None:
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await session.execute(
            select(Asset)
            .where(Asset.deleted_at.is_not(None), Asset.deleted_at < cutoff)
            .order_by(Asset.deleted_at.asc())
            .limit(CLEANUP_BATCH_SIZE)
        )
        for asset in result.scalars().all():
            if await _is_referenced(session, asset.id):
                continue
            path: Path = storage.absolute_path(asset.storage_path)
            try:
                if path.exists():
                    await asyncio.to_thread(path.unlink)
            except OSError:
                logger.exception("Could not delete media file for asset %s", asset.id)
                continue
            await session.delete(asset)
            removed += 1
        if removed:
            await session.commit()
    return removed


async def run_worker() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("AuRoom maintenance worker started; retention is DB-configured")
    while True:
        try:
            removed = await cleanup_media_once()
            if removed:
                logger.info("Removed %s expired soft-deleted media asset(s)", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Maintenance iteration failed")
        await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)


async def _main() -> None:
    try:
        await run_worker()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
