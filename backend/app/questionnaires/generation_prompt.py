from __future__ import annotations

from collections.abc import Sequence
from json import dumps
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


def _answer_value(value: object) -> object:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is True:
        return "Да"
    if value is False:
        return "Нет"
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _js_percent(value: float) -> int:
    # Normalized rectangles are non-negative. JS Math.round(x) is floor(x + .5).
    return floor(float(value) * 100 + 0.5)


def _region_percent(region: object | None) -> dict[str, int] | None:
    if region is None:
        return None
    return {
        "left": _js_percent(region.x),
        "top": _js_percent(region.y),
        "width": _js_percent(region.width),
        "height": _js_percent(region.height),
    }


def build_questionnaire_generation_prompt(
    definition: dict[str, Any],
    session: DesignSession,
    *,
    accepted_before: Sequence[str],
    input_asset_present: bool,
) -> str:
    """Build a deterministic, model-facing render specification.

    The prompt is intentionally machine-structured rather than a user-facing transcript.
    Only active pre-render answers are included. Spatial preservation rules outrank design
    choices because the compositor enforces them after generation as well.
    """
    object_key = str(definition["key"])
    answers = session.answers.get(object_key, {})
    house_accepted = "eskez-doma" in accepted_before

    questionnaire_constraints: list[dict[str, object]] = []
    for question in definition["questions"]:
        if question.get("phase") != "pre_render":
            continue
        if not condition_ok(question.get("condition"), answers, house_accepted):
            continue
        if question["id"] not in answers:
            continue
        value = _answer_value(answers[question["id"]])
        if value in (None, "", []):
            continue
        questionnaire_constraints.append(
            {
                "question": str(question["text"]).strip(),
                "answer": value,
            }
        )

    if accepted_before:
        source_kind = "accepted_scene"
        source_directive = (
            "Используй входное изображение как уже принятую сцену. Сохрани без изменений "
            "существующий дом, ранее принятые объекты, их геометрию и пропорции, участок, "
            "перспективу, ракурс и свет. Создавай или изменяй только текущий объект."
        )
    elif input_asset_present:
        source_kind = "site_photo"
        source_directive = (
            "Используй фотографию участка как исходную сцену. Сохрани геометрию участка, "
            "перспективу, ракурс и существующее окружение. Добавь только текущий объект."
        )
    else:
        source_kind = "synthetic_scene"
        source_directive = (
            "Сформируй новую внешнюю сцену для текущего объекта. Для дома используй дрон "
            "40–50 м, угловой вид сверху; для остальных объектов — дрон сверху, угловой вид."
        )

    edit_region = _region_percent(session.edit_regions.get(object_key))
    locked_objects = [
        key for key in accepted_before if session.lock_regions.get(key) is not None
    ]
    refinement = session.review_comments.get(object_key, "").strip() or None

    prohibitions = [
        "Не показывать на изображении текст, подписи, размеры, UI или технические аннотации.",
        "Не заменять явно выбранные параметры собственными предположениями.",
        "Не менять ранее принятую сцену вне разрешённой области изменения.",
    ]
    if object_key == "eskez-doma":
        prohibitions.append(
            "Визуализировать только внешний вид дома. Планировок, комнат и "
            "внутренних помещений не придумывать."
        )

    inheritance_rule = (
        "Не применяется к основному дому."
        if object_key == "eskez-doma"
        else (
            "Если в ответах выбрано «Как у дома», точно наследовать стиль, "
            "материалы и кровлю принятого дома."
        )
    )

    spec = {
        "schema": "auroom.questionnaire_render.v1",
        "task": {
            "object_key": object_key,
            "object_name": str(definition["title"]).strip(),
            "goal": "Создать одну точную фотореалистичную внешнюю архитектурную визуализацию.",
        },
        "source_scene": {
            "kind": source_kind,
            "directive": source_directive,
            "accepted_objects_count": len(accepted_before),
            "accepted_house": house_accepted,
        },
        "spatial_constraints": {
            "edit_region_percent": edit_region,
            "locked_regions_count": len(locked_objects),
            "locked_regions_enforced_by_compositor": bool(locked_objects),
            "outside_edit_region": "preserve_exactly" if edit_region else "not_applicable",
        },
        "scene_policy": definition.get("scene_policy") or {},
        "questionnaire_semantics": {
            "strength": "hard_constraints",
            "yes": "Требование должно явно присутствовать в изображении.",
            "no": "Соответствующий элемент или свойство не добавлять.",
            "number": "Считать указанное число целевым параметром, а не приблизительной подсказкой.",
            "multi_select": "Использовать выбранный набор без самовольного добавления невыбранных вариантов.",
            "custom_text": "Следовать пользовательской формулировке буквально, если она не конфликтует с более высоким приоритетом.",
        },
        "questionnaire_constraints": questionnaire_constraints,
        "inheritance": inheritance_rule,
        "refinement_comment": refinement,
        "prohibitions": prohibitions,
        "output": {
            "type": "single_photorealistic_image",
            "priority": "questionnaire_fidelity_over_creative_variation",
        },
    }

    priorities = (
        "ПРИОРИТЕТЫ ВЫПОЛНЕНИЯ:\n"
        "1. Сохранение исходной/принятой сцены и пространственных блокировок.\n"
        "2. Точное выполнение каждого активного ответа опросника как обязательного ограничения.\n"
        "3. Правила камеры, света и размещения из scene_policy, если они не "
        "конфликтуют с сохранением исходного кадра.\n"
        "4. Фотореализм и эстетика только после выполнения пунктов 1–3."
    )
    return (
        "AUROOM_RENDER_SPEC_V1\n"
        "СЧИТАЙ STRUCTURED_SPEC единственным источником параметров проектирования. "
        "Не додумывай параметры, которые противоречат данным спецификации.\n"
        f"{priorities}\n"
        "STRUCTURED_SPEC:\n"
        f"{dumps(spec, ensure_ascii=False, separators=(',', ':'))}\n"
        "FINAL_CHECK: перед выдачей изображения мысленно сверь объект, геометрию, этажность, "
        "габариты, материалы, цвета, кровлю, остекление, расположение и свет со всеми "
        "questionnaire_constraints и не нарушай spatial_constraints."
    )
