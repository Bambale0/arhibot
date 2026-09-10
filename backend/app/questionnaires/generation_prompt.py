from __future__ import annotations

from collections.abc import Sequence
from math import floor
from typing import Any

from app.schemas.questionnaires import DesignSession


def condition_ok(
    condition: dict[str, Any] | None,
    answers: dict[str, object],
    house_accepted: bool,
) -> bool:
    if not condition:
        return True
    operator = condition.get("operator")
    if operator == "house_accepted":
        return house_accepted
    if operator == "all":
        return all(
            condition_ok(item, answers, house_accepted)
            for item in condition.get("conditions", [])
        )
    if operator == "any":
        return any(
            condition_ok(item, answers, house_accepted)
            for item in condition.get("conditions", [])
        )
    answer = answers.get(condition.get("question_id"))
    value = condition.get("value")
    if operator == "eq":
        return answer == value
    if operator == "neq":
        return answer != value
    if operator == "in":
        return isinstance(answer, str) and isinstance(value, list) and answer in value
    if operator == "contains":
        return isinstance(answer, list) and isinstance(value, str) and value in answer
    if operator == "starts_with":
        return isinstance(answer, str) and isinstance(value, str) and answer.startswith(value)
    if operator == "not_contains_any":
        return (
            not isinstance(answer, list)
            or not isinstance(value, list)
            or not any(item in answer for item in value)
        )
    return True


def _answer_text(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if value is True:
        return "Согласен"
    if value is False:
        return "false"
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _js_percent(value: float) -> int:
    # Normalized rectangles are non-negative. JS Math.round(x) is floor(x + .5).
    return floor(float(value) * 100 + 0.5)


def build_questionnaire_generation_prompt(
    definition: dict[str, Any],
    session: DesignSession,
    *,
    accepted_before: Sequence[str],
    input_asset_present: bool,
) -> str:
    object_key = str(definition["key"])
    answers = session.answers.get(object_key, {})
    house_accepted = "eskez-doma" in accepted_before
    lines: list[str] = []
    for question in definition["questions"]:
        if question.get("phase") != "pre_render":
            continue
        if not condition_ok(question.get("condition"), answers, house_accepted):
            continue
        rendered = _answer_text(answers.get(question["id"]))
        if rendered:
            lines.append(f"{question['id']}. {question['text']} — {rendered}")

    if accepted_before:
        scene = (
            "Используй исходное изображение как текущую принятую сцену. "
            "Сохрани существующий дом и все уже принятые объекты, их геометрию, "
            "пропорции, положение, окружение, ракурс и свет. Добавь или измени "
            "только текущий объект."
        )
    elif input_asset_present:
        scene = (
            "Используй фотографию участка как исходный контекст. Сохрани геометрию "
            "участка, перспективу, ракурс и существующее окружение. Создай или добавь "
            "только текущий проектируемый объект."
        )
    elif object_key == "eskez-doma":
        scene = "Создай внешний вид дома на участке. Камера: дрон 40–50 м, сверху угловой вид."
    else:
        scene = "Создай объект на участке. Камера: дрон сверху, угловой вид."

    region = session.edit_regions.get(object_key)
    region_instruction = ""
    if region is not None:
        region_instruction = (
            "Новый объект и все новые пиксели должны находиться внутри разрешённой "
            f"области кадра: слева {_js_percent(region.x)}%, сверху {_js_percent(region.y)}%, "
            f"ширина {_js_percent(region.width)}%, высота {_js_percent(region.height)}%. "
            "За пределами этой области ничего не менять."
        )

    parts = [
        f"AuRoom. Точный опросник: {definition['title']}.",
        scene,
        region_instruction,
        (
            "Планировок, комнат и внутренних помещений не придумывать."
            if object_key == "eskez-doma"
            else "Если выбран «Как у дома», наследуй стиль, материалы и кровлю принятого дома."
        ),
        *lines,
    ]
    review_comment = session.review_comments.get(object_key, "")
    if review_comment:
        parts.append(f"Комментарий к уточнению: {review_comment}")
    return "\n".join(part for part in parts if part)
