from app.telegram_bot.main import (
    TelegramBotContent,
    configure_bot,
    menu_button,
    mini_app_keyboard,
    normalize_command,
    parse_bot_content,
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


def test_mini_app_keyboard_uses_admin_managed_button_text() -> None:
    url = "https://archi.example.com"
    keyboard = mini_app_keyboard(url, content())

    button = keyboard["inline_keyboard"][0][0]
    assert button["text"] == "Open app"
    assert button["web_app"]["url"] == url


def test_menu_button_opens_same_web_app() -> None:
    url = "https://archi.example.com"
    button = menu_button(url, content())

    assert button == {
        "type": "web_app",
        "text": "Open app",
        "web_app": {"url": url},
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
            return True

    configure_bot(FakeApi(), "https://archi.example.com", content())  # type: ignore[arg-type]

    assert calls[0] == "deleteWebhook"
    assert "setMyName" in calls
    assert "setChatMenuButton" in calls
