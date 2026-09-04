from app.telegram_bot.main import configure_bot, menu_button, mini_app_keyboard, normalize_command


def test_mini_app_keyboard_uses_web_app_button() -> None:
    url = "https://archi.example.com"
    keyboard = mini_app_keyboard(url)

    button = keyboard["inline_keyboard"][0][0]
    assert button["text"] == "Открыть AuRoom"
    assert button["web_app"]["url"] == url


def test_menu_button_opens_same_web_app() -> None:
    url = "https://archi.example.com"
    button = menu_button(url)

    assert button == {
        "type": "web_app",
        "text": "Открыть AuRoom",
        "web_app": {"url": url},
    }


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

    configure_bot(FakeApi(), "https://archi.example.com")  # type: ignore[arg-type]

    assert calls[0] == "deleteWebhook"
    assert "setMyName" in calls
    assert "setChatMenuButton" in calls
