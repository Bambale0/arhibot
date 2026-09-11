from json import loads
from uuid import uuid4

from app.questionnaires.catalog import build_catalog
from app.questionnaires.generation_prompt import build_questionnaire_generation_prompt
from app.schemas.questionnaires import DesignSession


def _definition(key: str) -> dict:
    catalog = build_catalog()
    return next(item for item in catalog["questionnaires"] if item["key"] == key)


def _spec(prompt: str) -> dict:
    payload = prompt.split("STRUCTURED_SPEC:\n", 1)[1].split("\nFINAL_CHECK:", 1)[0]
    return loads(payload)


def test_first_house_with_plot_photo_is_structured_and_preserves_source() -> None:
    definition = _definition("eskez-doma")
    answers = {}
    for question in definition["questions"]:
        if question["phase"] == "pre_render" and question.get("options"):
            answers[question["id"]] = question["options"][0]
    session = DesignSession(
        catalog_version=build_catalog()["version"],
        selected_objects=["eskez-doma"],
        source_step_completed=True,
        source_asset_id=uuid4(),
        answers={"eskez-doma": answers},
    )

    prompt = build_questionnaire_generation_prompt(
        definition,
        session,
        accepted_before=[],
        input_asset_present=True,
    )
    spec = _spec(prompt)

    assert prompt.startswith("AUROOM_RENDER_SPEC_V1")
    assert spec["schema"] == "auroom.questionnaire_render.v1"
    assert spec["task"]["object_name"] == "Дом, фасад"
    assert spec["source_scene"]["kind"] == "site_photo"
    assert spec["spatial_constraints"]["edit_region_percent"] is None
    assert spec["questionnaire_constraints"]
    assert all(set(item) == {"question", "answer"} for item in spec["questionnaire_constraints"])
    assert any(
        "Планировок, комнат" in rule
        for rule in spec["prohibitions"]
    )


def test_later_object_spec_contains_edit_lock_and_inheritance_rules() -> None:
    definition = _definition("banya")
    session = DesignSession(
        catalog_version=build_catalog()["version"],
        selected_objects=["eskez-doma", "banya"],
        source_step_completed=True,
        accepted_objects=["eskez-doma"],
        answers={"banya": {"1": "Как у дома"}},
        edit_regions={
            "banya": {"x": 0.125, "y": 0.255, "width": 0.333, "height": 0.444}
        },
        lock_regions={
            "eskez-doma": {"x": 0.1, "y": 0.1, "width": 0.7, "height": 0.7}
        },
    )

    prompt = build_questionnaire_generation_prompt(
        definition,
        session,
        accepted_before=["eskez-doma"],
        input_asset_present=True,
    )
    spec = _spec(prompt)

    assert spec["source_scene"]["kind"] == "accepted_scene"
    assert spec["spatial_constraints"]["edit_region_percent"] == {
        "left": 13,
        "top": 26,
        "width": 33,
        "height": 44,
    }
    assert spec["source_scene"]["accepted_house"] is True
    assert spec["spatial_constraints"]["locked_regions_count"] == 1
    assert spec["spatial_constraints"]["locked_regions_enforced_by_compositor"] is True
    assert spec["questionnaire_semantics"]["strength"] == "hard_constraints"
    assert spec["questionnaire_constraints"] == [
        {"question": "Стиль как у дома или свой?", "answer": "Как у дома"}
    ]
    assert spec["inheritance"]["enabled"] is True
    assert spec["inheritance"]["fields"] == ["architectural_style", "roof"]
    assert spec["inheritance"]["explicit_questionnaire_answers_override"] is True


def test_canopy_house_style_does_not_override_explicit_polycarbonate_roof() -> None:
    definition = _definition("naves")
    roof_question = next(
        question
        for question in definition["questions"]
        if question["phase"] == "pre_render"
        and any("поликарбонат" in option.lower() for option in question.get("options", []))
    )
    polycarbonate = next(
        option for option in roof_question["options"] if "поликарбонат" in option.lower()
    )
    session = DesignSession(
        catalog_version=build_catalog()["version"],
        selected_objects=["eskez-doma", "naves"],
        source_step_completed=True,
        accepted_objects=["eskez-doma"],
        answers={"naves": {"1": "Как у дома", roof_question["id"]: polycarbonate}},
        edit_regions={
            "naves": {"x": 0.55, "y": 0.18, "width": 0.4, "height": 0.6}
        },
        lock_regions={
            "eskez-doma": {"x": 0.1, "y": 0.1, "width": 0.7, "height": 0.7}
        },
    )

    spec = _spec(
        build_questionnaire_generation_prompt(
            definition,
            session,
            accepted_before=["eskez-doma"],
            input_asset_present=True,
        )
    )

    assert spec["inheritance"]["enabled"] is True
    assert spec["inheritance"]["fields"] == ["architectural_style"]
    assert spec["inheritance"]["explicit_questionnaire_answers_override"] is True
    assert {
        "question": roof_question["text"],
        "answer": polycarbonate,
    } in spec["questionnaire_constraints"]


def test_full_house_rerender_ignores_stale_refinement_comment() -> None:
    definition = _definition("eskez-doma")
    session = DesignSession(
        catalog_version=build_catalog()["version"],
        selected_objects=["eskez-doma"],
        source_step_completed=True,
        answers={
            "eskez-doma": {
                "1": "Современный минимализм",
                "15а": "Всё полностью, сделать заново",
            }
        },
        review_comments={"eskez-doma": "Старый комментарий, который не должен применяться"},
    )

    spec = _spec(
        build_questionnaire_generation_prompt(
            definition,
            session,
            accepted_before=[],
            input_asset_present=False,
        )
    )

    assert spec["refinement_comment"] is None


def test_prompt_excludes_inactive_and_review_answers() -> None:
    definition = _definition("eskez-doma")
    session = DesignSession(
        catalog_version=build_catalog()["version"],
        selected_objects=["eskez-doma"],
        source_step_completed=True,
        answers={
            "eskez-doma": {
                "1": "Современный минимализм",
                "15": "Да, всё подходит",
            }
        },
    )

    spec = _spec(
        build_questionnaire_generation_prompt(
            definition,
            session,
            accepted_before=[],
            input_asset_present=False,
        )
    )

    assert spec["questionnaire_constraints"] == [
        {"question": "Какой стиль вам нравится?", "answer": "Современный минимализм"}
    ]
