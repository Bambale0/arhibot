import json
import logging
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BOT_NAME = "AuRoom"
BOT_SHORT_DESCRIPTION = "AI-концепции фасадов и интерьеров"
BOT_DESCRIPTION = (
    "AuRoom — AI-сервис для архитектурных и интерьерных концепций. "
    "Загрузите фото и создайте вариант фасада, интерьера или редизайна."
)
START_TEXT = (
    "Привет! Это AuRoom — AI-сервис для концепций фасадов и интерьеров.\n\n"
    "Откройте AuRoom, создайте проект, загрузите фото и выберите сценарий."
)


def mini_app_keyboard(webapp_url: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "Открыть AuRoom",
                    "web_app": {"url": webapp_url},
                }
            ]
        ]
    }


def menu_button(webapp_url: str) -> dict[str, Any]:
    return {
        "type": "web_app",
        "text": "Открыть AuRoom",
        "web_app": {"url": webapp_url},
    }


class TelegramBotApi:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"

    def call(self, method: str, payload: dict[str, Any] | None = None, *, timeout: int = 15) -> Any:
        body = json.dumps(payload or {}).encode("utf-8")
        request = Request(
            f"{self.base_url}/{method}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed Telegram API host
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Telegram API request failed: {method}") from exc

        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error in {method}: {data.get('description', 'unknown error')}")
        return data.get("result")


def normalize_command(text: str) -> str:
    token = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    return token.split("@", maxsplit=1)[0].lower()


def send_start(api: TelegramBotApi, chat_id: int | str, webapp_url: str) -> None:
    api.call(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": START_TEXT,
            "reply_markup": mini_app_keyboard(webapp_url),
        },
    )


def _best_effort_setup(api: TelegramBotApi, method: str, payload: dict[str, Any]) -> None:
    try:
        api.call(method, payload)
    except RuntimeError as exc:
        logger.warning("Telegram setup skipped for %s: %s", method, exc)


def configure_bot(api: TelegramBotApi, webapp_url: str) -> None:
    # Polling requires webhook mode to be disabled. Branding/menu updates are
    # best-effort: Telegram can rate-limit these calls, and that must never stop
    # the bot from answering /start or /app.
    api.call("deleteWebhook", {"drop_pending_updates": False})
    _best_effort_setup(api, "setMyName", {"name": BOT_NAME})
    _best_effort_setup(
        api,
        "setMyShortDescription",
        {"short_description": BOT_SHORT_DESCRIPTION},
    )
    _best_effort_setup(api, "setMyDescription", {"description": BOT_DESCRIPTION})
    _best_effort_setup(
        api,
        "setMyCommands",
        {
            "commands": [
                {"command": "start", "description": "Открыть AuRoom"},
                {"command": "app", "description": "Запустить AuRoom"},
            ]
        },
    )
    _best_effort_setup(api, "setChatMenuButton", {"menu_button": menu_button(webapp_url)})


def run_polling() -> None:
    settings = get_settings()
    token = (settings.telegram_bot_token or "").strip()
    webapp_url = (settings.telegram_webapp_url or "").strip()

    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required for the bot process")
    if not webapp_url:
        raise RuntimeError("TELEGRAM_WEBAPP_URL is required for the bot process")
    if not webapp_url.startswith("https://"):
        raise RuntimeError("TELEGRAM_WEBAPP_URL must be an HTTPS URL for Telegram Mini Apps")

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    api = TelegramBotApi(token)
    configure_bot(api, webapp_url)
    logger.info("Telegram bot started with Mini App URL %s", webapp_url)

    offset: int | None = None
    while True:
        try:
            payload: dict[str, Any] = {
                "timeout": 30,
                "allowed_updates": ["message"],
            }
            if offset is not None:
                payload["offset"] = offset

            updates = api.call("getUpdates", payload, timeout=35) or []
            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1

                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                text = message.get("text")
                if chat_id is None or not isinstance(text, str):
                    continue

                if normalize_command(text) in {"/start", "/app"}:
                    send_start(api, chat_id, webapp_url)
        except Exception:
            logger.exception("Telegram polling iteration failed")
            time.sleep(3)


if __name__ == "__main__":
    run_polling()
