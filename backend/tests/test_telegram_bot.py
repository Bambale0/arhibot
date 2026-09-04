from app.telegram_bot.main import menu_button, mini_app_keyboard, normalize_command


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
