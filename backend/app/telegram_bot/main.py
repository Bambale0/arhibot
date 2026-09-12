import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from app.core.config import get_settings

logger = logging.getLogger(__name__)
CONTENT_REFRESH_SECONDS = 30


@dataclass(frozen=True, slots=True)
class TelegramUserSummary:
    display_name: str
    credits_balance: int
    active_projects: int
    active_generations: int


@dataclass(frozen=True, slots=True)
class TelegramBotContent:
    bot_name: str
    short_description: str
    description: str
    start_text: str
    open_button_text: str
    start_command_description: str
    app_command_description: str


class TelegramApiError(RuntimeError):
    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def parse_bot_content(payload: object) -> TelegramBotContent | None:
    if not isinstance(payload, dict) or payload.get("configured") is not True:
        return None
    keys = (
        "bot_name",
        "short_description",
        "description",
        "start_text",
        "open_button_text",
        "start_command_description",
        "app_command_description",
    )
    values: dict[str, str] = {}
    for key in keys:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        values[key] = value.strip()
    return TelegramBotContent(**values)


def load_bot_content(url: str) -> TelegramBotContent | None:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=5) as response:  # noqa: S310 - configured AuRoom API URL
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        logger.warning("Could not load Telegram content from AuRoom API: %s", exc)
        return None
    return parse_bot_content(payload)


def parse_user_summary(payload: object) -> TelegramUserSummary | None:
    if not isinstance(payload, dict):
        return None
    try:
        display_name = str(payload["display_name"]).strip()
        credits_balance = int(payload["credits_balance"])
        active_projects = int(payload["active_projects"])
        active_generations = int(payload["active_generations"])
    except (KeyError, TypeError, ValueError):
        return None
    if not display_name or min(credits_balance, active_projects, active_generations) < 0:
        return None
    return TelegramUserSummary(
        display_name=display_name,
        credits_balance=credits_balance,
        active_projects=active_projects,
        active_generations=active_generations,
    )


def load_user_summary(
    url: str, *, telegram_user_id: int | str, bot_token: str
) -> TelegramUserSummary | None:
    request = Request(
        f"{url.rstrip('/')}/{telegram_user_id}",
        headers={
            "Accept": "application/json",
            "X-Telegram-Bot-Token": bot_token,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=5) as response:  # noqa: S310 - configured AuRoom API URL
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None
    return parse_user_summary(payload)


def canonicalize_webapp_url(raw: str) -> str:
    """Return a Telegram-safe HTTPS URL with an ASCII/IDNA hostname.

    Telegram clients do not all handle Unicode IDN hosts consistently. Keep the
    human-readable URL in configuration if desired, but never send a Unicode
    hostname to Telegram: encode it to IDNA/punycode first.
    """

    parsed = urlsplit(raw.strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("Mini App URL must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Mini App URL must not contain credentials")

    try:
        ascii_host = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Mini App URL contains an invalid hostname") from exc

    host_for_netloc = f"[{ascii_host}]" if ":" in ascii_host else ascii_host
    netloc = host_for_netloc if port in (None, 443) else f"{host_for_netloc}:{port}"
    path = parsed.path or "/"
    return urlunsplit(("https", netloc, path, parsed.query, parsed.fragment))


def webapp_section_url(webapp_url: str, section: str) -> str:
    safe_url = canonicalize_webapp_url(webapp_url)
    parsed = urlsplit(safe_url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {"section", "billing", "project", "generation", "idea", "admin"}
    ]
    query.append(("section", section))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


def mini_app_keyboard(
    webapp_url: str,
    content: TelegramBotContent,
    summary: TelegramUserSummary | None = None,
) -> dict[str, Any]:
    safe_url = canonicalize_webapp_url(webapp_url)
    if summary is None:
        return {
            "inline_keyboard": [
                [
                    {
                        "text": content.open_button_text,
                        "web_app": {"url": safe_url},
                    }
                ]
            ]
        }
    return {
        "inline_keyboard": [
            [
                {"text": "Создать проект", "web_app": {"url": webapp_section_url(safe_url, "create")}},
                {"text": "Мои проекты", "web_app": {"url": webapp_section_url(safe_url, "home")}},
            ],
            [
                {"text": "История", "web_app": {"url": webapp_section_url(safe_url, "history")}},
                {"text": "Баланс", "web_app": {"url": webapp_section_url(safe_url, "profile")}},
            ],
            [
                {
                    "text": content.open_button_text,
                    "web_app": {"url": safe_url},
                }
            ],
        ]
    }


def menu_button(webapp_url: str, content: TelegramBotContent) -> dict[str, Any]:
    safe_url = canonicalize_webapp_url(webapp_url)
    return {
        "type": "web_app",
        "text": content.open_button_text,
        "web_app": {"url": safe_url},
    }


class TelegramBotApi:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"

    def call(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int = 15,
    ) -> Any:
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
        except HTTPError as exc:
            retry_after = None
            description = f"HTTP {exc.code}"
            try:
                payload_error = json.loads(exc.read().decode("utf-8"))
                description = str(payload_error.get("description") or description)
                parameters = payload_error.get("parameters") or {}
                raw_retry = parameters.get("retry_after")
                if isinstance(raw_retry, int) and raw_retry > 0:
                    retry_after = raw_retry
            except (ValueError, OSError):
                pass
            raise TelegramApiError(
                f"Telegram API request failed in {method}: {description}",
                retry_after=retry_after,
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise TelegramApiError(f"Telegram API request failed: {method}") from exc

        if not data.get("ok"):
            parameters = data.get("parameters") or {}
            raw_retry = parameters.get("retry_after")
            retry_after = raw_retry if isinstance(raw_retry, int) and raw_retry > 0 else None
            raise TelegramApiError(
                f"Telegram API error in {method}: {data.get('description', 'unknown error')}",
                retry_after=retry_after,
            )
        return data.get("result")


def normalize_command(text: str) -> str:
    token = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    return token.split("@", maxsplit=1)[0].lower()


def send_start(
    api: TelegramBotApi,
    chat_id: int | str,
    webapp_url: str,
    content: TelegramBotContent,
    summary: TelegramUserSummary | None = None,
) -> None:
    text = content.start_text
    if summary is not None:
        text = (
            f"{content.start_text}\n\n"
            f"Кредиты: {summary.credits_balance}\n"
            f"Проектов: {summary.active_projects}\n"
            f"Генераций в работе: {summary.active_generations}"
        )
    api.call(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": mini_app_keyboard(webapp_url, content, summary),
        },
    )


def _best_effort_setup(api: TelegramBotApi, method: str, payload: dict[str, Any]) -> None:
    try:
        api.call(method, payload)
    except RuntimeError as exc:
        logger.warning("Telegram setup skipped for %s: %s", method, exc)


def _telegram_state(api: TelegramBotApi, method: str) -> object | None:
    try:
        return api.call(method)
    except RuntimeError as exc:
        logger.warning("Telegram setup state check failed for %s: %s", method, exc)
        return None


def apply_bot_content(
    api: TelegramBotApi,
    webapp_url: str,
    content: TelegramBotContent,
) -> None:
    # Telegram branding endpoints are rate-limited independently of getUpdates.
    # Compare before writing so routine process restarts do not generate setter storms.
    name = _telegram_state(api, "getMyName")
    if not isinstance(name, dict) or name.get("name") != content.bot_name:
        _best_effort_setup(api, "setMyName", {"name": content.bot_name})

    short = _telegram_state(api, "getMyShortDescription")
    if not isinstance(short, dict) or short.get("short_description") != content.short_description:
        _best_effort_setup(
            api,
            "setMyShortDescription",
            {"short_description": content.short_description},
        )

    description = _telegram_state(api, "getMyDescription")
    if not isinstance(description, dict) or description.get("description") != content.description:
        _best_effort_setup(api, "setMyDescription", {"description": content.description})

    commands = [
        {"command": "start", "description": content.start_command_description},
        {"command": "app", "description": content.app_command_description},
    ]
    current_commands = _telegram_state(api, "getMyCommands")
    if current_commands != commands:
        _best_effort_setup(api, "setMyCommands", {"commands": commands})

    expected_menu = menu_button(webapp_url, content)
    current_menu = _telegram_state(api, "getChatMenuButton")
    if current_menu != expected_menu:
        _best_effort_setup(api, "setChatMenuButton", {"menu_button": expected_menu})


def configure_bot(
    api: TelegramBotApi,
    webapp_url: str,
    content: TelegramBotContent,
) -> None:
    # Polling requires webhook mode to be disabled. Branding/menu updates remain
    # best-effort because Telegram can rate-limit them independently of polling.
    api.call("deleteWebhook", {"drop_pending_updates": False})
    apply_bot_content(api, webapp_url, content)


def run_polling() -> None:
    settings = get_settings()
    token = (settings.telegram_bot_token or "").strip()
    raw_webapp_url = (settings.telegram_webapp_url or "").strip()

    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required for the bot process")
    if not raw_webapp_url:
        raise RuntimeError("TELEGRAM_WEBAPP_URL is required for the bot process")
    try:
        webapp_url = canonicalize_webapp_url(raw_webapp_url)
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_WEBAPP_URL must be a valid HTTPS URL for Telegram Mini Apps") from exc

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    api = TelegramBotApi(token)
    content_url = (
        f"{settings.bot_internal_api_base_url.rstrip('/')}"
        f"{settings.api_v1_prefix}/telegram/content"
    )
    summary_url = (
        f"{settings.bot_internal_api_base_url.rstrip('/')}"
        f"{settings.api_v1_prefix}/telegram/summary"
    )
    content = load_bot_content(content_url)
    api.call("deleteWebhook", {"drop_pending_updates": False})
    if content is not None:
        apply_bot_content(api, webapp_url, content)
    else:
        logger.warning("Telegram content is not configured yet; polling will stay online")
    logger.info("Telegram bot started with Mini App URL %s", webapp_url)

    offset: int | None = None
    last_content_refresh = time.monotonic()
    while True:
        try:
            now = time.monotonic()
            if now - last_content_refresh >= CONTENT_REFRESH_SECONDS:
                loaded = load_bot_content(content_url)
                last_content_refresh = now
                if loaded is not None and loaded != content:
                    content = loaded
                    apply_bot_content(api, webapp_url, content)
                    logger.info("Telegram bot content refreshed from control plane")

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
                    if content is None:
                        content = load_bot_content(content_url)
                        if content is not None:
                            apply_bot_content(api, webapp_url, content)
                    if content is not None:
                        summary = load_user_summary(
                            summary_url,
                            telegram_user_id=chat_id,
                            bot_token=token,
                        )
                        send_start(api, chat_id, webapp_url, content, summary)
                    else:
                        logger.warning("Cannot answer Telegram command until content is configured")
        except TelegramApiError as exc:
            logger.warning("Telegram polling error: %s", exc)
            time.sleep(max(exc.retry_after or 2, 1))
        except Exception:
            logger.exception("Unexpected Telegram polling failure")
            time.sleep(2)


if __name__ == "__main__":
    run_polling()
