from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.projects import Project
from app.db.models.questionnaires import QuestionnaireApplication
from app.db.models.users import AuthIdentity, User
from app.domain.users.enums import AuthProvider, UserRole, UserStatus
from app.questionnaires.catalog import OBJECT_TITLES
from app.repositories.questionnaires import QuestionnaireRepository
from app.telegram_bot.main import TelegramBotApi

logger = logging.getLogger(__name__)
DELIVERY_BATCH_SIZE = 20
MAX_FIELD_LENGTH = 500


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
) -> str:
    application_answers = application.answers.get("zayavka", {})
    accepted = ", ".join(
        OBJECT_TITLES.get(key, key) for key in application.accepted_objects
    ) or "—"
    return "\n".join(
        [
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
            f"ID заявки: {application.id}",
        ]
    )


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
    message: str,
) -> tuple[int, list[str]]:
    sent = 0
    errors: list[str] = []
    for recipient_id in recipient_ids:
        try:
            await asyncio.to_thread(
                api.call,
                "sendMessage",
                {"chat_id": recipient_id, "text": message},
            )
            sent += 1
        except Exception as exc:  # Telegram adapter failure must stay retryable.
            errors.append(f"{type(exc).__name__}: {str(exc)[:180]}")
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

            message = build_application_message(
                application,
                project_name=project.name,
                user_name=user.display_name,
            )
            sent, errors = await _send_to_admins(api, recipients, message)
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
