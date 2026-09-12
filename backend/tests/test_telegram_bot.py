import pytest

from app.telegram_bot.main import (
    TelegramBotContent,
    TelegramUserSummary,
    canonicalize_webapp_url,
    configure_bot,
    menu_button,
    mini_app_keyboard,
    normalize_command,
    parse_bot_content,
    parse_user_summary,
    send_start,
    webapp_section_url,
)


def content() -> TelegramBotContent:
    return TelegramBotContent(
        bot_name="Test bot",
        short_description="Short",
        description="Description",
        start_text="Welcome",
        open_button_text="Open app",
        start_command_description="Open",
        app_command_description="Launch",
    )


def test_canonicalize_webapp_url_idna_encodes_unicode_hostname() -> None:
    url = canonicalize_webapp_url("https://archibot.нейроныч.online")

    assert url == "https://archibot.xn--e1aikcel5c5a.online/"
    assert url.isascii()


def test_canonicalize_webapp_url_preserves_path_and_query() -> None:
    url = canonicalize_webapp_url("https://нейроныч.online/app/start?source=telegram")

    assert url == "https://xn--e1aikcel5c5a.online/app/start?source=telegram"


def test_canonicalize_webapp_url_rejects_non_https_and_credentials() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        canonicalize_webapp_url("http://archi.example.com")
    with pytest.raises(ValueError, match="credentials"):
        canonicalize_webapp_url("https://user:password@archi.example.com")


def test_mini_app_keyboard_uses_admin_managed_button_text() -> None:
    url = "https://archi.example.com"
    keyboard = mini_app_keyboard(url, content())

    button = keyboard["inline_keyboard"][0][0]
    assert button["text"] == "Open app"
    assert button["web_app"]["url"] == "https://archi.example.com/"


def test_mini_app_keyboard_never_sends_unicode_hostname_to_telegram() -> None:
    keyboard = mini_app_keyboard("https://archibot.нейроныч.online", content())

    assert keyboard["inline_keyboard"][0][0]["web_app"]["url"] == (
        "https://archibot.xn--e1aikcel5c5a.online/"
    )


def test_menu_button_opens_same_web_app() -> None:
    url = "https://archi.example.com"
    button = menu_button(url, content())

    assert button == {
        "type": "web_app",
        "text": "Open app",
        "web_app": {"url": "https://archi.example.com/"},
    }


def test_parse_bot_content_requires_complete_config() -> None:
    payload = {
        "configured": True,
        "bot_name": "DB bot",
        "short_description": "Short",
        "description": "Description",
        "start_text": "Welcome",
        "open_button_text": "Open",
        "start_command_description": "Start",
        "app_command_description": "App",
    }
    parsed = parse_bot_content(payload)
    assert parsed is not None
    assert parsed.bot_name == "DB bot"
    assert parse_bot_content({**payload, "open_button_text": None}) is None
    assert parse_bot_content({**payload, "configured": False}) is None


def test_normalize_command_supports_bot_username_and_payload() -> None:
    assert normalize_command("/start@auroom_bot ref_123") == "/start"
    assert normalize_command(" /app ") == "/app"


def test_configure_bot_keeps_running_when_branding_is_rate_limited() -> None:
    calls: list[str] = []

    class FakeApi:
        def call(self, method: str, payload=None, *, timeout: int = 15):
            calls.append(method)
            if method == "setMyName":
                raise RuntimeError("Telegram API request failed: setMyName")
            if method.startswith("getMy") or method == "getChatMenuButton":
                return None
            return True

    configure_bot(FakeApi(), "https://archi.example.com", content())  # type: ignore[arg-type]

    assert calls[0] == "deleteWebhook"
    assert "setMyName" in calls
    assert "setChatMenuButton" in calls


def test_configure_bot_does_not_rewrite_unchanged_branding() -> None:
    calls: list[str] = []
    expected = content()

    class FakeApi:
        def call(self, method: str, payload=None, *, timeout: int = 15):
            calls.append(method)
            states = {
                "getMyName": {"name": expected.bot_name},
                "getMyShortDescription": {"short_description": expected.short_description},
                "getMyDescription": {"description": expected.description},
                "getMyCommands": [
                    {"command": "start", "description": expected.start_command_description},
                    {"command": "app", "description": expected.app_command_description},
                ],
                "getChatMenuButton": menu_button("https://archi.example.com", expected),
            }
            return states.get(method, True)

    configure_bot(FakeApi(), "https://archi.example.com", expected)  # type: ignore[arg-type]

    assert calls[0] == "deleteWebhook"
    assert not any(method.startswith("setMy") for method in calls)
    assert "setChatMenuButton" not in calls


def test_configure_bot_updates_only_changed_branding_field() -> None:
    calls: list[tuple[str, object]] = []
    expected = content()

    class FakeApi:
        def call(self, method: str, payload=None, *, timeout: int = 15):
            calls.append((method, payload))
            states = {
                "getMyName": {"name": "Old name"},
                "getMyShortDescription": {"short_description": expected.short_description},
                "getMyDescription": {"description": expected.description},
                "getMyCommands": [
                    {"command": "start", "description": expected.start_command_description},
                    {"command": "app", "description": expected.app_command_description},
                ],
                "getChatMenuButton": menu_button("https://archi.example.com", expected),
            }
            return states.get(method, True)

    configure_bot(FakeApi(), "https://archi.example.com", expected)  # type: ignore[arg-type]

    setter_calls = [(method, payload) for method, payload in calls if method.startswith("set")]
    assert setter_calls == [("setMyName", {"name": expected.bot_name})]


def test_personalized_start_keyboard_routes_to_product_sections() -> None:
    summary = TelegramUserSummary(
        display_name="Игорь",
        credits_balance=7,
        active_projects=2,
        active_generations=1,
    )
    keyboard = mini_app_keyboard("https://archi.example.com", content(), summary)

    assert keyboard["inline_keyboard"][0][0]["text"] == "Создать проект"
    assert keyboard["inline_keyboard"][0][0]["web_app"]["url"].endswith("?section=create")
    assert keyboard["inline_keyboard"][0][1]["web_app"]["url"].endswith("?section=home")
    assert keyboard["inline_keyboard"][1][0]["web_app"]["url"].endswith("?section=history")
    assert keyboard["inline_keyboard"][1][1]["web_app"]["url"].endswith("?section=profile")


def test_send_start_includes_safe_personal_summary_when_available() -> None:
    sent: list[tuple[str, object]] = []

    class FakeApi:
        def call(self, method: str, payload=None, *, timeout: int = 15):
            sent.append((method, payload))
            return True

    summary = TelegramUserSummary(
        display_name="Игорь",
        credits_balance=9,
        active_projects=3,
        active_generations=2,
    )
    send_start(
        FakeApi(), 123, "https://archi.example.com", content(), summary  # type: ignore[arg-type]
    )

    method, payload = sent[0]
    assert method == "sendMessage"
    assert "Кредиты: 9" in payload["text"]
    assert "Проектов: 3" in payload["text"]
    assert "Генераций в работе: 2" in payload["text"]


def test_user_summary_parser_rejects_incomplete_payloads() -> None:
    parsed = parse_user_summary(
        {
            "display_name": "Игорь",
            "credits_balance": 5,
            "active_projects": 1,
            "active_generations": 0,
        }
    )
    assert parsed is not None
    assert parsed.credits_balance == 5
    assert parse_user_summary({"display_name": "Игорь"}) is None


def test_webapp_section_url_replaces_stale_navigation() -> None:
    url = webapp_section_url(
        "https://archi.example.com/app?generation=old&section=history&keep=1",
        "create",
    )
    assert "generation=" not in url
    assert "section=create" in url
    assert "keep=1" in url
