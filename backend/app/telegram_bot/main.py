import json
import logging
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings

logger = logging.getLogger(__name__)

START_TEXT = (
    "Привет! Я ArchiAI — помощник по архитектурным и интерьерным концепциям.\n\n"
    "Открой приложение, создай проект, загрузи фото и выбери сценарий генерации."
)


def mini_app_keyboard(webapp_url: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "Открыть приложение",
                    "web_app": {"url": webapp_url},
                }
            ]
        ]
    }


def menu_button(webapp_url: str) -> dict[str, Any]:
    return {
        "type": "web_app",
        "text": "Открыть приложение",
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


def configure_bot(api: TelegramBotApi, webapp_url: str) -> None:
    api.call("deleteWebhook", {"drop_pending_updates": False})
    api.call(
        "setMyCommands",
        {
            "commands": [
                {"command": "start", "description": "Открыть ArchiAI"},
                {"command": "app", "description": "Открыть приложение"},
            ]
        },
    )
    api.call("setChatMenuButton", {"menu_button": menu_button(webapp_url)})


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
