import json
from uuid import uuid4

from app.questionnaires.catalog import build_catalog
from app.questionnaires.generation_prompt import (
    build_initial_concept_prompt,
    build_questionnaire_generation_prompt,
)
from app.schemas.questionnaires import DesignSession
from app.services.edit_policy import build_edit_policy


def _definition(key: str) -> dict:
    return next(item for item in build_catalog()["questionnaires"] if item["key"] == key)


def _spec(prompt: str) -> dict:
    return json.loads(prompt.split("STRUCTURED_SPEC:\n", 1)[1].split("\nFINAL_CHECK:", 1)[0])


def test_house_refinement_prompt_locks_visible_interior_and_structural_link() -> None:
    definition = _definition("eskez-doma")
    policy = build_edit_policy(
        object_key="eskez-doma",
        edit_question_ids=["7"],
        review_comment="Сделай кровлю темнее. Переставь диван внутри.",
    )
    session = DesignSession(
        catalog_version=build_catalog()["version"],
        selected_objects=["eskez-doma"],
        initial_concept_mode=True,
        initial_concept_accepted=True,
        source_step_completed=True,
        scene_asset_id=uuid4(),
        accepted_objects=["eskez-doma"],
        current_object="eskez-doma",
        edit_question_ids=["7"],
        review_comments={
            "eskez-doma": "Сделай кровлю темнее. Переставь диван внутри.",
        },
        edit_regions={
            "eskez-doma": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
        },
        answers={"eskez-doma": {"7": "Двускатная"}},
    )

    prompt = build_questionnaire_generation_prompt(
        definition,
        session,
        accepted_before=[],
        input_asset_present=True,
        edit_policy=policy.to_dict(),
    )
    spec = _spec(prompt)

    assert spec["edit_policy"]["domain"] == "mixed"
    assert spec["edit_policy"]["intent"] == "roof_finish"
    assert spec["visible_interior_policy"] == {
        "interior_is_context_only": True,
        "redesign_forbidden": True,
        "furniture_relocation_forbidden": True,
        "fireplace_relocation_forbidden": True,
        "staircase_relocation_forbidden": True,
        "room_geometry_change_forbidden": True,
        "preserve_through_glazing": True,
    }
    assert spec["structural_consistency"]["relations"] == [
        {
            "type": "fireplace_chimney",
            "rule": "preserve_existing_relation",
        }
    ]
    assert "диван" not in (spec["refinement_comment"] or "").lower()
    assert "фас" not in (spec["refinement_comment"] or "").lower()
    assert "кров" in (spec["refinement_comment"] or "").lower()
    assert "VISIBLE INTERIOR IS LOCKED CONTEXT" in prompt


def test_initial_concept_prompt_requires_plausible_fireplace_chimney_relation() -> None:
    catalog = build_catalog()
    session = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma"],
        initial_concept_mode=True,
        source_step_completed=True,
        answers={"eskez-doma": {"11б": "Да"}},
    )

    prompt = build_initial_concept_prompt(
        catalog,
        session,
        input_asset_present=False,
    )
    spec = _spec(prompt)

    assert spec["structural_consistency"]["fireplace_chimney"] == (
        "If a visible fireplace is created, its chimney stack must be spatially "
        "and architecturally plausible as the exterior continuation of the same flue system."
    )
    assert "fireplace and chimney" in prompt.lower()


def test_current_catalog_uses_chimney_only_refinement_label() -> None:
    catalog = build_catalog()
    house = next(item for item in catalog["questionnaires"] if item["key"] == "eskez-doma")
    edit = next(question for question in house["questions"] if question["id"] == "15б")

    assert catalog["version"] == "2026-09-25.1"
    assert "Дымоход / труба" in edit["options"]
    assert "Камин, труба" not in edit["options"]
    assert edit["edit_targets"]["Дымоход / труба"] == ["11б"]
