"""Copy only published design answers; never consult the owner's mutable project."""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
from functools import lru_cache
from typing import Any

from app.core.errors import AppError
from app.questionnaires.catalog import user_question_title
from app.questionnaires.generation_prompt import question_is_active


def _legacy_value(question: dict, value: object) -> object:
    if not isinstance(value, str):
        return None if isinstance(value, float) and not isfinite(value) else value
    if question["kind"] == "number":
        try:
            number = float(value.replace(",", "."))
            return number if isfinite(number) else None
        except ValueError:
            return None
    if question["kind"] == "multi":
        if value == question.get("skip_default"):
            return deepcopy(question["skip_default"])
        options = tuple(question.get("options", []))

        @lru_cache(maxsize=256)
        def parse(remaining: str) -> tuple[tuple[str, ...], ...]:
            if not remaining:
                return ((),)
            paths = []
            for option in options:
                if remaining == option:
                    paths.append((option,))
                elif remaining.startswith(option + ", "):
                    paths.extend((option, *tail) for tail in parse(remaining[len(option) + 2 :]))
                if len(paths) > 1:
                    return tuple(paths[:2])
            return tuple(paths)

        matches = parse(value)
        return list(matches[0]) if len(matches) == 1 else None
    return value


def design_answers_from_snapshot(
    snapshot: dict[str, Any],
    catalog: dict[str, Any],
    selected: list[str],
    validator: Any,
) -> dict[str, dict[str, object]]:
    definitions = {item["key"]: item for item in catalog["questionnaires"]}
    template = snapshot.get("design_template")
    typed = template.get("answers", []) if isinstance(template, dict) else []
    records: dict[tuple[str, str], object] = {}
    objects = snapshot.get("objects", [])
    for obj in objects if isinstance(objects, list) else []:
        if not isinstance(obj, dict) or not isinstance(obj.get("key"), str):
            continue
        summaries = obj.get("answers", [])
        for item in summaries if isinstance(summaries, list) else []:
            if (
                isinstance(item, dict)
                and isinstance(item.get("question"), str)
                and "answer" in item
            ):
                records[(obj["key"], item["question"])] = item["answer"]
    for item in typed if isinstance(typed, list) else []:
        if (
            isinstance(item, dict)
            and isinstance(item.get("object_key"), str)
            and isinstance(item.get("question"), str)
            and "value" in item
        ):
            records[(item["object_key"], item["question"])] = deepcopy(item["value"])
    result = {}
    house = "eskez-doma" in selected
    for key in selected:
        definition = definitions.get(key)
        if definition is None or key == catalog.get("application_key", "zayavka"):
            continue
        answers: dict[str, object] = {}
        for question in definition["questions"]:
            if question.get("phase") != "pre_render":
                continue
            lookup = (key, user_question_title(question["text"]))
            if lookup not in records:
                continue
            value = _legacy_value(question, records[lookup])
            trial = {**answers, question["id"]: value}
            if not question_is_active(key, question, trial, house, selected):
                continue
            try:
                validator(question, value, trial, house)
            except AppError:
                continue
            answers[question["id"]] = value
        if answers:
            result[key] = answers
    return result
