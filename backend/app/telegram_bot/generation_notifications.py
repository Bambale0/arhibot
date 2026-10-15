from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
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
MAX_DELIVERY_ATTEMPTS = 5
LIGHT_PREVIEW_MAX_BYTES = 650 * 1024
LIGHT_PREVIEW_MAX_SIDE = 1280


def build_light_generation_preview(source_path: Path) -> bytes:
    """Bounded Telegram JPEG preview; source PNG/JPEG/WebP remains untouched."""
    try:
        with Image.open(source_path) as opened:
            opened.thumbnail(
                (LIGHT_PREVIEW_MAX_SIDE, LIGHT_PREVIEW_MAX_SIDE),
                Image.Resampling.LANCZOS,
                reducing_gap=3.0,
            )
            original = ImageOps.exif_transpose(opened).convert("RGBA")
            canvas = Image.new("RGBA", original.size, (255, 255, 255, 255))
            canvas.alpha_composite(original)
            image = canvas.convert("RGB")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ValueError("Cannot create Telegram generation preview") from exc

    # Telegram's photo API rejects panoramas with a >20:1 aspect ratio.
    width, height = image.size
    if width > 20 * height:
        padded = Image.new("RGB", (width, (width + 19) // 20), "white")
        padded.paste(image, (0, (padded.height - height) // 2))
        image = padded
    elif height > 20 * width:
        padded = Image.new("RGB", ((height + 19) // 20, height), "white")
        padded.paste(image, ((padded.width - width) // 2, 0))
        image = padded

    for side in (1280, 1024, 800):
        image.thumbnail((side, side), Image.Resampling.LANCZOS, reducing_gap=3.0)
        for quality in (78, 70, 60, 50):
            preview = BytesIO()
            image.save(preview, format="JPEG", quality=quality, optimize=True)
            data = preview.getvalue()
            if len(data) <= LIGHT_PREVIEW_MAX_BYTES:
                return data
    raise ValueError("Cannot reduce Telegram generation preview below 650 KiB")


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
            checkpoint = generation.telegram_delivery_status
            if checkpoint == "sending":
                logger.warning(
                    "Retrying generation %s after an interrupted Telegram delivery; "
                    "the previous send may have reached Telegram",
                    generation.id,
                )
            # Once the preview was acknowledged, only retry the original.
            # This is at-least-once across a crash before the checkpoint commit.
            if checkpoint not in {"preview_sent", "preview_skipped"}:
                generation.telegram_delivery_status = "sending"
            generation.telegram_delivery_attempts += 1
            await session.commit()
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
            if (
                project is None
                or project.deleted_at is not None
                or output is None
                or output.deleted_at is not None
            ):
                generation.telegram_delivery_status = "skipped"
                generation.telegram_delivery_error = "Generation project or output asset is unavailable"
                await session.commit()
                continue

            document_path = LocalMediaStorage(settings).absolute_path(
                output.storage_path
            )
            keyboard = generation_keyboard(
                raw_webapp_url,
                project_id=project.id,
                generation_id=generation.id,
            )
            preview_sent = checkpoint == "preview_sent"
            preview_skipped = checkpoint == "preview_skipped"

            if not preview_sent and not preview_skipped:
                if output.mime_type.startswith("image/"):
                    try:
                        preview = await asyncio.to_thread(
                            build_light_generation_preview, document_path
                        )
                    except (ValueError, OSError) as exc:
                        logger.warning(
                            "Lightweight Telegram preview unavailable for generation %s: %s",
                            generation.id,
                            type(exc).__name__,
                        )
                        preview_skipped = True
                    else:
                        try:
                            await asyncio.to_thread(
                                api.send_photo_bytes,
                                chat_id=chat_id,
                                data=preview,
                                caption=generation_caption(project.name),
                                reply_markup=keyboard,
                            )
                        except Exception as exc:
                            if generation.telegram_delivery_attempts < MAX_DELIVERY_ATTEMPTS:
                                generation.telegram_delivery_status = "pending"
                                generation.telegram_delivery_error = (
                                    f"{type(exc).__name__}: {str(exc)[:420]}"
                                )[:500]
                                failed += 1
                                await session.commit()
                                continue
                            logger.warning(
                                "Telegram preview attempts exhausted for generation %s; "
                                "sending the original document instead",
                                generation.id,
                            )
                            preview_skipped = True
                        else:
                            preview_sent = True
                else:
                    # Video files and unsupported media retain the original-only flow.
                    preview_skipped = True

                generation.telegram_delivery_status = (
                    "preview_sent" if preview_sent else "preview_skipped"
                )
                generation.telegram_delivery_error = None
                await session.commit()

            try:
                await asyncio.to_thread(
                    api.send_document_file,
                    chat_id=chat_id,
                    path=document_path,
                    caption=(
                        "📎 Оригинал в полном качестве"
                        if preview_sent
                        else generation_caption(project.name)
                    ),
                    reply_markup=(
                        {"inline_keyboard": []} if preview_sent else keyboard
                    ),
                )
            except Exception as exc:
                generation.telegram_delivery_error = (
                    f"{type(exc).__name__}: {str(exc)[:420]}"
                )[:500]
                if generation.telegram_delivery_attempts >= MAX_DELIVERY_ATTEMPTS:
                    generation.telegram_delivery_status = "failed"
                else:
                    generation.telegram_delivery_status = (
                        "preview_sent" if preview_sent else "preview_skipped"
                    )
                failed += 1
                await session.commit()
                continue

            generation.telegram_delivery_status = "sent"
            generation.telegram_delivery_error = None
            generation.telegram_notified_at = datetime.now(UTC)
            delivered += 1
            await session.commit()

    return delivered, failed
