from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from app.telegram_bot.generation_notifications import (
    generation_caption,
    generation_deep_link,
    generation_keyboard,
)


def test_generation_deep_links_target_exact_project_and_generation() -> None:
    project_id = uuid4()
    generation_id = uuid4()
    base = "https://app.example.test/app?idea=old&billing=return&keep=1"

    project_url = generation_deep_link(base, project_id=project_id)
    generation_url = generation_deep_link(base, generation_id=generation_id)

    project_query = parse_qs(urlsplit(project_url).query)
    generation_query = parse_qs(urlsplit(generation_url).query)

    assert project_query == {"keep": ["1"], "project": [str(project_id)]}
    assert generation_query == {"keep": ["1"], "generation": [str(generation_id)]}


def test_generation_keyboard_contains_two_mini_app_actions_without_prompt() -> None:
    project_id = uuid4()
    generation_id = uuid4()
    keyboard = generation_keyboard(
        "https://app.example.test/",
        project_id=project_id,
        generation_id=generation_id,
    )

    rows = keyboard["inline_keyboard"]
    assert rows[0][0]["text"] == "Продолжить проект"
    assert f"project={project_id}" in rows[0][0]["web_app"]["url"]
    assert rows[1][0]["text"] == "Открыть результат"
    assert f"generation={generation_id}" in rows[1][0]["web_app"]["url"]

    caption = generation_caption("Дом у озера")
    assert "Дом у озера" in caption
    assert "prompt" not in caption.lower()
