from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.assets import Asset
from app.db.models.projects import Project
from app.db.models.questionnaires import QuestionnaireApplication
from app.db.models.users import AuthIdentity, User
from app.domain.users.enums import AuthProvider, UserRole, UserStatus
from app.questionnaires.application_brief import build_application_brief
from app.questionnaires.catalog import OBJECT_TITLES
from app.repositories.questionnaires import QuestionnaireRepository
from app.services.asset_service import LocalMediaStorage
from app.telegram_bot.main import TelegramBotApi

logger = logging.getLogger(__name__)
DELIVERY_BATCH_SIZE = 20
MAX_FIELD_LENGTH = 500
TELEGRAM_MESSAGE_LIMIT = 3900


def _display(value: object) -> str:
    if isinstance(value, list):
        rendered = ", ".join(str(item) for item in value)
    elif value is True:
        rendered = "Да"
    elif value is False:
        rendered = "Нет"
    elif value is None:
        rendered = "—"
    else:
        rendered = str(value)
    rendered = rendered.strip() or "—"
    return rendered[:MAX_FIELD_LENGTH]


def build_application_message(
    application: QuestionnaireApplication,
    *,
    project_name: str,
    user_name: str,
    catalog: dict | None = None,
) -> str:
    application_answers = application.answers.get("zayavka", {})
    accepted = ", ".join(
        OBJECT_TITLES.get(key, key) for key in application.accepted_objects
    ) or "—"
    lines = [
        "🏡 Новая заявка AuRoom",
        f"Проект: {_display(project_name)}",
        f"Клиент: {_display(user_name)}",
        f"Принятые объекты: {_display(accepted)}",
        f"Участок: {_display(application_answers.get('20'))}",
        f"Бюджет: {_display(application_answers.get('21'))}",
        f"Срок: {_display(application_answers.get('22'))}",
        f"Имя: {_display(application_answers.get('23'))}",
        f"Контакт: {_display(application_answers.get('24'))}",
        f"Согласие ПД: {_display(application_answers.get('25'))}",
        "",
        "📐 Архитектурный бриф",
    ]
    for item in build_application_brief(
        selected_objects=application.selected_objects,
        accepted_objects=application.accepted_objects,
        answers=application.answers,
        catalog=catalog,
    ):
        status = "принят" if item["accepted"] else "не принят"
        lines.append(f"\n{item['title']} ({status})")
        rows = item["answers"]
        if not rows:
            lines.append("• Ответов нет")
            continue
        for row in rows:
            lines.append(f"• {_display(row['question'])}: {_display(row['answer'])}")
    lines.extend(
        [
            "",
            f"Финальный эскиз asset: {_display(application.scene_asset_id)}",
            f"ID заявки: {application.id}",
        ]
    )
    return "\n".join(lines)


def _chunk_message(message: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in message.splitlines():
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= TELEGRAM_MESSAGE_LIMIT:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = line
        while len(current) > TELEGRAM_MESSAGE_LIMIT:
            chunks.append(current[:TELEGRAM_MESSAGE_LIMIT])
            current = current[TELEGRAM_MESSAGE_LIMIT:]
    if current:
        chunks.append(current)
    return chunks


async def load_admin_telegram_ids(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(AuthIdentity.provider_user_id)
        .join(User, User.id == AuthIdentity.user_id)
        .where(
            AuthIdentity.provider == AuthProvider.TELEGRAM,
            User.status == UserStatus.ACTIVE,
            User.role.in_([UserRole.ADMIN, UserRole.SUPERADMIN]),
        )
        .order_by(AuthIdentity.created_at.asc())
    )
    # Preserve deterministic order while protecting against duplicate identities.
    return list(dict.fromkeys(value for value in result.scalars().all() if value))


async def _send_to_admins(
    api: TelegramBotApi,
    recipient_ids: list[str],
    messages: list[str],
    *,
    session: AsyncSession,
    application: QuestionnaireApplication,
    photo_url: str | None = None,
) -> tuple[int, list[str]]:
    sent = 0
    errors: list[str] = []

    for recipient_id in recipient_ids:
        progress = dict(application.telegram_delivery_progress or {})
        recipient = dict(progress.get(recipient_id) or {})
        photo_sent = bool(recipient.get("photo_sent"))
        chunks_sent = max(0, int(recipient.get("chunks_sent") or 0))

        if (not photo_url or photo_sent) and chunks_sent >= len(messages):
            sent += 1
            continue

        if photo_url and not photo_sent:
            try:
                await asyncio.to_thread(
                    api.call,
                    "sendPhoto",
                    {
                        "chat_id": recipient_id,
                        "photo": photo_url,
                        "caption": f"Финальный эскиз AuRoom · заявка {application.id}",
                    },
                )
            except Exception as exc:  # Telegram adapter failure must stay retryable.
                errors.append(f"{type(exc).__name__}: {str(exc)[:180]}")
                continue
            recipient["photo_sent"] = True
            progress[recipient_id] = recipient
            application.telegram_delivery_progress = progress
            await session.commit()

        failed_recipient = False
        for index in range(chunks_sent, len(messages)):
            try:
                await asyncio.to_thread(
                    api.call,
                    "sendMessage",
                    {"chat_id": recipient_id, "text": messages[index]},
                )
            except Exception as exc:  # Telegram adapter failure must stay retryable.
                errors.append(f"{type(exc).__name__}: {str(exc)[:180]}")
                failed_recipient = True
                break

            progress = dict(application.telegram_delivery_progress or {})
            recipient = dict(progress.get(recipient_id) or {})
            recipient["chunks_sent"] = index + 1
            progress[recipient_id] = recipient
            application.telegram_delivery_progress = progress
            await session.commit()

        if not failed_recipient:
            sent += 1

    return sent, errors


async def deliver_pending_applications_once(
    *,
    api: TelegramBotApi | None = None,
    limit: int = DELIVERY_BATCH_SIZE,
) -> tuple[int, int]:
    token = (get_settings().telegram_bot_token or "").strip()
    if api is None:
        if not token:
            logger.warning("Questionnaire Telegram delivery is waiting for TELEGRAM_BOT_TOKEN")
            return 0, 0
        api = TelegramBotApi(token)

    delivered = 0
    failed = 0
    from app.db.session import get_session_factory  # local import keeps worker wiring at the edge

    async with get_session_factory()() as session:
        repository = QuestionnaireRepository(session)
        applications = await repository.list_pending_telegram_applications(limit=limit)
        if not applications:
            return 0, 0

        recipients = await load_admin_telegram_ids(session)
        if not recipients:
            logger.warning(
                "Questionnaire applications are pending, but no active admin has a Telegram identity"
            )
            return 0, len(applications)

        for application in applications:
            user = await session.get(User, application.user_id)
            project = await session.get(Project, application.project_id)
            application.telegram_delivery_attempts += 1

            if user is None or project is None:
                application.telegram_delivery_error = "Application owner or project is missing"
                failed += 1
                await session.commit()
                continue

            catalog_row = await repository.get_catalog()
            if catalog_row is not None and catalog_row.version == application.catalog_version:
                catalog = catalog_row.catalog
            else:
                catalog_revision = await repository.get_catalog_revision(
                    application.catalog_version
                )
                catalog = catalog_revision.catalog if catalog_revision is not None else None

            scene_asset = (
                await session.get(Asset, application.scene_asset_id)
                if application.scene_asset_id is not None
                else None
            )
            photo_url = (
                LocalMediaStorage(get_settings()).signed_url(
                    scene_asset.storage_path,
                    ttl_seconds=3600,
                )
                if scene_asset is not None
                else None
            )
            message = build_application_message(
                application,
                project_name=project.name,
                user_name=user.display_name,
                catalog=catalog,
            )
            sent, errors = await _send_to_admins(
                api,
                recipients,
                _chunk_message(message),
                session=session,
                application=application,
                photo_url=photo_url,
            )
            if sent > 0:
                application.telegram_delivery_status = "sent"
                application.telegram_delivery_error = None
                application.telegram_notified_at = datetime.now(UTC)
                delivered += 1
                if errors:
                    logger.warning(
                        "Questionnaire application %s reached an admin, but %s recipient(s) failed",
                        application.id,
                        len(errors),
                    )
            else:
                application.telegram_delivery_error = ("; ".join(errors) or "Telegram delivery failed")[:500]
                failed += 1
            await session.commit()

    return delivered, failed
