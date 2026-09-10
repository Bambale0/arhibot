from __future__ import annotations

import asyncio
import logging
import sys

from app.core.config import get_settings
from app.db.session import dispose_engine, get_session_factory
from app.telegram_bot.main import TelegramBotApi
from app.telegram_bot.questionnaire_notifications import load_admin_telegram_ids

logger = logging.getLogger(__name__)
MAX_ALERT_LENGTH = 3500


async def send_ops_alert(message: str) -> tuple[int, int]:
    text = message.strip()[:MAX_ALERT_LENGTH]
    if not text:
        raise ValueError('Operations alert message is empty')
    token = (get_settings().telegram_bot_token or '').strip()
    if not token:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is not configured')

    async with get_session_factory()() as session:
        recipients = await load_admin_telegram_ids(session)
    if not recipients:
        raise RuntimeError('No active admin Telegram recipients are configured')

    api = TelegramBotApi(token)
    sent = 0
    failed = 0
    for recipient_id in recipients:
        try:
            await asyncio.to_thread(
                api.call,
                'sendMessage',
                {'chat_id': recipient_id, 'text': text},
            )
            sent += 1
        except Exception:
            failed += 1
            logger.warning('Operations alert delivery failed for an admin recipient', exc_info=True)
    return sent, failed


async def _main() -> int:
    message = sys.stdin.read(MAX_ALERT_LENGTH + 1)
    if len(message) > MAX_ALERT_LENGTH:
        message = message[:MAX_ALERT_LENGTH]
    try:
        sent, failed = await send_ops_alert(message)
        print(f'ops_alert sent={sent} failed={failed}')
        return 0 if sent > 0 else 1
    finally:
        await dispose_engine()


if __name__ == '__main__':
    raise SystemExit(asyncio.run(_main()))
