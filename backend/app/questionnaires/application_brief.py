from __future__ import annotations

from typing import Any

from app.questionnaires.catalog import user_question_title
from app.questionnaires.generation_prompt import condition_ok


def display_answer(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if value is True:
        return "Да"
    if value is False:
        return "Нет"
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def build_application_brief(
    catalog: dict[str, Any],
    *,
    accepted_objects: list[str],
    answers: dict[str, dict[str, object]],
) -> list[dict[str, Any]]:
    definitions = {item["key"]: item for item in catalog["questionnaires"]}
    result: list[dict[str, Any]] = []
    accepted_before: list[str] = []

    for object_key in accepted_objects:
        definition = definitions.get(object_key)
        if definition is None:
            accepted_before.append(object_key)
            continue

        object_answers = answers.get(object_key, {})
        house_accepted = "eskez-doma" in accepted_before
        rendered_answers: list[dict[str, str]] = []
        for question in definition["questions"]:
            if question.get("phase") != "pre_render":
                continue
            if not condition_ok(question.get("condition"), object_answers, house_accepted):
                continue
            value = display_answer(object_answers.get(question["id"]))
            if not value:
                continue
            rendered_answers.append(
                {
                    "question": user_question_title(str(question["text"])),
                    "answer": value,
                }
            )

        result.append(
            {
                "key": object_key,
                "title": str(definition["title"]),
                "answers": rendered_answers,
            }
        )
        accepted_before.append(object_key)

    return result
