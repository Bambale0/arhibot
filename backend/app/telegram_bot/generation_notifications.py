from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.assets import Asset
from app.db.models.projects import Project
from app.db.models.users import AuthIdentity
from app.db.session import get_session_factory
from app.domain.users.enums import AuthProvider
from app.repositories.generations import GenerationRepository
from app.services.asset_service import LocalMediaStorage
from app.telegram_bot.links import webapp_deep_link
from app.telegram_bot.main import TelegramBotApi, canonicalize_webapp_url

logger = logging.getLogger(__name__)
DELIVERY_BATCH_SIZE = 20


def generation_keyboard(webapp_url: str, *, project_id: object, generation_id: object) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "Продолжить проект",
                    "web_app": {
                        "url": webapp_deep_link(
                            webapp_url,
                            project=project_id,
                        )
                    },
                }
            ],
            [
                {
                    "text": "Открыть результат",
                    "web_app": {
                        "url": webapp_deep_link(
                            webapp_url,
                            generation=generation_id,
                        )
                    },
                }
            ],
        ]
    }


def generation_caption(project_name: str) -> str:
    safe_name = project_name.strip()[:180] or "Проект AuRoom"
    return (
        "✨ Генерация готова\n\n"
        f"Проект: {safe_name}\n"
        "Результат уже в AuRoom. Продолжите проект или откройте эту генерацию."
    )


async def deliver_pending_generations_once(
    *,
    api: TelegramBotApi | None = None,
    webapp_url: str | None = None,
    limit: int = DELIVERY_BATCH_SIZE,
) -> tuple[int, int]:
    settings = get_settings()
    token = (settings.telegram_bot_token or "").strip()
    raw_webapp_url = (webapp_url or settings.telegram_webapp_url or "").strip()

    if api is None:
        if not token:
            logger.debug("Generation Telegram delivery is waiting for TELEGRAM_BOT_TOKEN")
            return 0, 0
        api = TelegramBotApi(token)
    if not raw_webapp_url:
        logger.debug("Generation Telegram delivery is waiting for TELEGRAM_WEBAPP_URL")
        return 0, 0
    try:
        canonicalize_webapp_url(raw_webapp_url)
    except ValueError:
        logger.error("Generation Telegram delivery requires a valid HTTPS TELEGRAM_WEBAPP_URL")
        return 0, 0

    delivered = 0
    failed = 0
    async with get_session_factory()() as session:
        repository = GenerationRepository(session)
        generations = await repository.list_pending_telegram_deliveries(limit=limit)

        for generation in generations:
            generation.telegram_delivery_attempts += 1
            identity_result = await session.execute(
                select(AuthIdentity.provider_user_id)
                .where(
                    AuthIdentity.user_id == generation.user_id,
                    AuthIdentity.provider == AuthProvider.TELEGRAM,
                )
                .order_by(AuthIdentity.created_at.desc())
                .limit(1)
            )
            chat_id = identity_result.scalar_one_or_none()
            if not chat_id:
                generation.telegram_delivery_status = "skipped"
                generation.telegram_delivery_error = "No Telegram identity is linked to this user"
                await session.commit()
                continue

            project = await session.get(Project, generation.project_id)
            output = (
                await session.get(Asset, generation.output_asset_id)
                if generation.output_asset_id is not None
                else None
            )
            if project is None or output is None or output.deleted_at is not None:
                generation.telegram_delivery_status = "skipped"
                generation.telegram_delivery_error = "Generation project or output asset is unavailable"
                await session.commit()
                continue

            photo_url = LocalMediaStorage(settings).signed_url(
                output.storage_path,
                ttl_seconds=3600,
            )
            try:
                await asyncio.to_thread(
                    api.call,
                    "sendPhoto",
                    {
                        "chat_id": chat_id,
                        "photo": photo_url,
                        "caption": generation_caption(project.name),
                        "reply_markup": generation_keyboard(
                            raw_webapp_url,
                            project_id=project.id,
                            generation_id=generation.id,
                        ),
                    },
                )
            except Exception as exc:
                generation.telegram_delivery_error = (
                    f"{type(exc).__name__}: {str(exc)[:420]}"
                )[:500]
                failed += 1
                await session.commit()
                continue

            generation.telegram_delivery_status = "sent"
            generation.telegram_delivery_error = None
            generation.telegram_notified_at = datetime.now(UTC)
            delivered += 1
            await session.commit()

    return delivered, failed
