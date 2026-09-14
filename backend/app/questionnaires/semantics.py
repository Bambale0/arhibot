from __future__ import annotations

from copy import deepcopy
from typing import Any

PRIMARY_HOUSE = "primary_house"
APPLICATION = "application"

HOUSE_STYLE = "house_style"
HOUSE_AREA = "house_area"
HOUSE_FLOORS = "house_floors"
HOUSE_REVIEW_ACCEPT = "house_review_accept"
HOUSE_REVIEW_SCOPE = "house_review_scope"
HOUSE_REVIEW_TARGETS = "house_review_targets"

LEAD_PLOT = "lead_plot"
LEAD_BUDGET = "lead_budget"
LEAD_TIMELINE = "lead_timeline"
LEAD_NAME = "lead_name"
LEAD_CONTACT = "lead_contact"
PRIVACY_CONSENT = "privacy_consent"

_LEGACY_DEFINITION_ROLES = {
    "eskez-doma": PRIMARY_HOUSE,
    "zayavka": APPLICATION,
}

_LEGACY_QUESTION_ROLES = {
    PRIMARY_HOUSE: {
        "1": HOUSE_STYLE,
        "3": HOUSE_AREA,
        "4": HOUSE_FLOORS,
        "15": HOUSE_REVIEW_ACCEPT,
        "15а": HOUSE_REVIEW_SCOPE,
        "15б": HOUSE_REVIEW_TARGETS,
    },
    APPLICATION: {
        "20": LEAD_PLOT,
        "21": LEAD_BUDGET,
        "22": LEAD_TIMELINE,
        "23": LEAD_NAME,
        "24": LEAD_CONTACT,
        "25": PRIVACY_CONSENT,
    },
}


def definition_role(definition: dict[str, Any], *, application_key: str | None = None) -> str | None:
    role = definition.get("semantic_role")
    if isinstance(role, str) and role.strip():
        return role.strip()
    key = str(definition.get("key") or "")
    if application_key and key == application_key:
        return APPLICATION
    return _LEGACY_DEFINITION_ROLES.get(key)


def question_role(
    definition: dict[str, Any],
    question: dict[str, Any],
    *,
    application_key: str | None = None,
) -> str | None:
    role = question.get("semantic_role")
    if isinstance(role, str) and role.strip():
        return role.strip()
    def_role = definition_role(definition, application_key=application_key)
    return _LEGACY_QUESTION_ROLES.get(def_role or "", {}).get(str(question.get("id") or ""))


def find_definition(
    catalog: dict[str, Any],
    role: str,
) -> dict[str, Any] | None:
    application_key = str(catalog.get("application_key") or "") or None
    return next(
        (
            item
            for item in catalog.get("questionnaires", [])
            if definition_role(item, application_key=application_key) == role
        ),
        None,
    )


def find_question(
    definition: dict[str, Any] | None,
    role: str,
    *,
    application_key: str | None = None,
) -> dict[str, Any] | None:
    if definition is None:
        return None
    return next(
        (
            question
            for question in definition.get("questions", [])
            if question_role(
                definition,
                question,
                application_key=application_key,
            )
            == role
        ),
        None,
    )


def question_id(
    definition: dict[str, Any] | None,
    role: str,
    *,
    application_key: str | None = None,
) -> str | None:
    question = find_question(definition, role, application_key=application_key)
    return str(question["id"]) if question is not None else None


def answer_by_role(
    definition: dict[str, Any] | None,
    answers: dict[str, object],
    role: str,
    *,
    application_key: str | None = None,
) -> object | None:
    qid = question_id(definition, role, application_key=application_key)
    return answers.get(qid) if qid is not None else None


def inherited_house_style_selected(
    definition: dict[str, Any],
    answers: dict[str, object],
) -> bool:
    for question in definition.get("questions", []):
        answer = answers.get(str(question.get("id") or ""))
        if not isinstance(answer, str):
            continue
        rule = (question.get("option_rules") or {}).get(answer)
        if isinstance(rule, dict) and rule.get("operator") == "house_accepted":
            return True
    return False


def enrich_catalog_semantics(catalog: dict[str, Any]) -> dict[str, Any]:
    enriched = deepcopy(catalog)
    application_key = str(enriched.get("application_key") or "") or None
    for definition in enriched.get("questionnaires", []):
        role = definition_role(definition, application_key=application_key)
        if role and not definition.get("semantic_role"):
            definition["semantic_role"] = role
        for question in definition.get("questions", []):
            role = question_role(
                definition,
                question,
                application_key=application_key,
            )
            if role and not question.get("semantic_role"):
                question["semantic_role"] = role
    return enriched
