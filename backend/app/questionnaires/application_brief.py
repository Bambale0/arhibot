from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.questionnaires.catalog import OBJECT_TITLES


def build_application_brief(
    *,
    selected_objects: Iterable[str],
    accepted_objects: Iterable[str],
    answers: dict[str, dict[str, object]],
    catalog: dict[str, Any] | None,
) -> list[dict[str, object]]:
    """Build a stable manager-facing brief without exposing generation prompts."""
    definitions = {
        str(item["key"]): item
        for item in (catalog or {}).get("questionnaires", [])
        if item.get("key") != "zayavka"
    }
    accepted = set(accepted_objects)
    keys = list(dict.fromkeys(selected_objects))
    for key in answers:
        if key != "zayavka" and key not in keys:
            keys.append(key)

    brief: list[dict[str, object]] = []
    for key in keys:
        object_answers = answers.get(key, {})
        if not object_answers and key not in accepted:
            continue
        definition = definitions.get(key)
        questions = definition.get("questions", []) if definition else []
        question_by_id = {str(item["id"]): item for item in questions}
        ordered_ids = [
            str(item["id"])
            for item in questions
            if item.get("phase") == "pre_render" and str(item["id"]) in object_answers
        ]
        ordered_ids.extend(
            question_id
            for question_id in object_answers
            if question_id not in ordered_ids
            and question_by_id.get(question_id, {}).get("phase") == "pre_render"
        )
        # Historical catalog data may be unavailable. Preserve raw answers instead of
        # dropping user context; the manager can still see the question id and value.
        if not ordered_ids and object_answers:
            ordered_ids = [
                question_id
                for question_id in object_answers
                if question_by_id.get(question_id, {}).get("phase") != "review"
            ]

        rows = []
        for question_id in ordered_ids:
            question = question_by_id.get(question_id)
            rows.append(
                {
                    "question_id": question_id,
                    "question": (
                        str(question.get("text", "")).strip()
                        if question
                        else f"Вопрос {question_id}"
                    ),
                    "answer": object_answers[question_id],
                }
            )
        brief.append(
            {
                "key": key,
                "title": (
                    str(definition.get("title", "")).strip()
                    if definition
                    else OBJECT_TITLES.get(key, key)
                ),
                "accepted": key in accepted,
                "answers": rows,
            }
        )
    return brief
