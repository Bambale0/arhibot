from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.users import AuthIdentity, User
from app.db.session import dispose_engine, get_session_factory
from app.domain.users.enums import AuthProvider, UserStatus
from app.telegram_bot.main import TelegramBotApi


def send_broadcast(api: TelegramBotApi, recipient_ids: Iterable[str], text: str) -> tuple[int, int]:
    sent = 0
    failed = 0
    for recipient_id in recipient_ids:
        try:
            api.call("sendMessage", {"chat_id": recipient_id, "text": text})
            sent += 1
        except Exception:
            failed += 1
    return sent, failed


async def load_active_telegram_ids() -> list[str]:
    async with get_session_factory()() as session:
        rows = await session.execute(
            select(AuthIdentity.provider_user_id)
            .join(User, User.id == AuthIdentity.user_id)
            .where(
                AuthIdentity.provider == AuthProvider.TELEGRAM,
                User.status == UserStatus.ACTIVE,
            )
            .order_by(AuthIdentity.created_at.asc())
        )
        return [value for value in rows.scalars().all() if value]


async def run(text: str, *, dry_run: bool = False) -> int:
    recipient_ids = await load_active_telegram_ids()
    print(f"AuRoom broadcast recipients: {len(recipient_ids)}")
    if dry_run or not recipient_ids:
        return 0

    token = (get_settings().telegram_bot_token or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    sent, failed = send_broadcast(TelegramBotApi(token), recipient_ids, text)
    print(f"sent={sent} failed={failed}")
    return 0 if failed == 0 else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Send an AuRoom message to all active Telegram users")
    parser.add_argument("--text", required=True, help="Message text")
    parser.add_argument("--dry-run", action="store_true", help="Only print recipient count")
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(run(args.text, dry_run=args.dry_run)))
    finally:
        try:
            asyncio.run(dispose_engine())
        except RuntimeError:
            pass


if __name__ == "__main__":
    main()
