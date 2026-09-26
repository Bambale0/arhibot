from json import loads
from uuid import uuid4

from app.questionnaires.catalog import build_catalog
from app.questionnaires.generation_prompt import (
    build_initial_concept_prompt,
    build_questionnaire_generation_prompt,
    question_is_active,
)
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
    assert "визуальный стиль принятого дома" in spec["inheritance"]


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


def test_explicit_carport_roof_overrides_house_style_inheritance() -> None:
    definition = _definition("naves")
    roof_question = next(
        question
        for question in definition["questions"]
        if question["phase"] == "pre_render" and "кров" in question["text"].lower()
    )
    polycarbonate = next(
        option for option in roof_question["options"] if "поликарбонат" in option.lower()
    )
    session = DesignSession(
        catalog_version=build_catalog()["version"],
        selected_objects=["eskez-doma", "naves"],
        source_step_completed=True,
        accepted_objects=["eskez-doma"],
        answers={
            "naves": {
                "1": "Как у дома",
                roof_question["id"]: polycarbonate,
            }
        },
        edit_regions={
            "naves": {"x": 0.55, "y": 0.18, "width": 0.42, "height": 0.66}
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

    assert {
        "question": roof_question["text"],
        "answer": polycarbonate,
    } in spec["questionnaire_constraints"]
    assert spec["questionnaire_semantics"]["explicit_selection_overrides_inheritance"] is True
    assert "безусловный приоритет" in spec["inheritance"]
    assert "точно наследовать стиль, материалы и кровлю" not in spec["inheritance"]


def test_full_house_rerender_ignores_stale_refinement_comment() -> None:
    definition = _definition("eskez-doma")
    session = DesignSession(
        catalog_version=build_catalog()["version"],
        selected_objects=["eskez-doma"],
        source_step_completed=True,
        answers={
            "eskez-doma": {
                "1": "Современный минимализм",
                "15": "Нет, хочу изменить",
                "15а": "Всё полностью, сделать заново",
            }
        },
        review_comments={
            "eskez-doma": "Старое точечное уточнение, которое не должно попасть в полный ререндер."
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

    assert spec["refinement_comment"] is None


def test_initial_concept_prompt_uses_paired_camera_and_real_plot_scale_for_two_objects() -> None:
    catalog = build_catalog()
    session = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma", "banya"],
        plot_area_sotkas=15,
        initial_concept_mode=True,
        survey_completed_objects=["eskez-doma", "banya"],
        source_step_completed=True,
        source_asset_id=uuid4(),
        answers={
            "eskez-doma": {
                "1": "Современный минимализм",
                "3": 200,
                "4": "2 этажа",
            },
            "banya": {"1": "Барнхаус"},
        },
    )

    prompt = build_initial_concept_prompt(
        catalog,
        session,
        input_asset_present=True,
    )
    spec = _spec(prompt)

    assert prompt.startswith("AUROOM_INITIAL_CONCEPT_V1")
    assert spec["schema"] == "auroom.initial_concept.v1"
    assert spec["task"]["selected_objects_count"] == 2
    assert [item["object_key"] for item in spec["task"]["objects"]] == [
        "eskez-doma",
        "banya",
    ]
    assert spec["camera"]["mode"] == "paired_object_context"
    assert spec["camera"]["altitude_m"] == {"min": 20, "max": 35}
    assert spec["camera"]["entire_plot_visible"] is False
    assert spec["camera"]["all_selected_objects_visible"] is True
    assert spec["camera"]["source_photo_camera_lock"] is False
    assert spec["source_scene"]["kind"] == "site_photo"
    assert spec["site_scale"]["plot_area_sotkas"] == 15
    assert spec["site_scale"]["plot_area_m2"] == 1500
    assert spec["site_scale"]["house_total_area_m2"] == 200.0
    assert spec["site_scale"]["estimated_house_footprint_m2"] == 100.0
    assert spec["site_scale"]["estimated_house_footprint_share_of_plot"] == 0.0667


def test_initial_concept_camera_is_hero_for_one_object_and_aerial_for_three_plus() -> None:
    catalog = build_catalog()
    single = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma"],
        plot_area_sotkas=8,
        initial_concept_mode=True,
        source_step_completed=True,
        answers={"eskez-doma": {"1": "Современный минимализм"}},
    )
    single_spec = _spec(
        build_initial_concept_prompt(catalog, single, input_asset_present=False)
    )
    assert single_spec["camera"]["mode"] == "single_object_hero"
    assert single_spec["camera"]["altitude_m"] == {"min": 8, "max": 20}
    assert single_spec["camera"]["entire_plot_visible"] is False

    multi = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma", "banya", "besedka"],
        plot_area_sotkas=8,
        initial_concept_mode=True,
        source_step_completed=True,
        answers={
            "eskez-doma": {"1": "Современный минимализм"},
            "banya": {"1": "Барнхаус"},
            "besedka": {"1": "Современный минимализм"},
        },
    )
    multi_spec = _spec(
        build_initial_concept_prompt(catalog, multi, input_asset_present=False)
    )
    assert multi_spec["camera"]["mode"] == "whole_site_aerial"
    assert multi_spec["camera"]["altitude_m"] == {"min": 50, "max": 70}
    assert multi_spec["camera"]["entire_plot_visible"] is True


def test_object_removal_prompt_is_explicit_and_drops_design_constraints() -> None:
    definition = _definition("banya")
    session = DesignSession(
        catalog_version=build_catalog()["version"],
        selected_objects=["eskez-doma", "banya"],
        initial_concept_mode=True,
        survey_completed_objects=["eskez-doma", "banya"],
        initial_generation_id=uuid4(),
        initial_concept_accepted=True,
        source_step_completed=True,
        scene_asset_id=uuid4(),
        scene_generation_id=uuid4(),
        accepted_objects=["eskez-doma", "banya"],
        pending_removal_object="banya",
        answers={"banya": {"1": "Как у дома"}},
        edit_regions={
            "banya": {"x": 0.55, "y": 0.18, "width": 0.42, "height": 0.66}
        },
        lock_regions={
            "eskez-doma": {"x": 0.1, "y": 0.1, "width": 0.4, "height": 0.5},
            "banya": {"x": 0.55, "y": 0.18, "width": 0.42, "height": 0.66},
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

    assert spec["source_scene"]["kind"] == "accepted_scene"
    assert spec["task"]["operation"] == "remove_object"
    assert spec["removal"]["enabled"] is True
    assert spec["removal"]["restore_background_naturally"] is True
    assert spec["questionnaire_constraints"] == []
    assert spec["spatial_constraints"]["edit_region_percent"] == {
        "left": 55,
        "top": 18,
        "width": 42,
        "height": 66,
    }
    assert "Полностью удалить" in spec["refinement_comment"]
    assert "Не применяется при удалении" in spec["inheritance"]

def test_initial_concept_skips_house_garage_branch_when_garage_is_separate_object() -> None:
    catalog = build_catalog()
    house = _definition("eskez-doma")
    session = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma", "garazh"],
        plot_area_sotkas=10,
        initial_concept_mode=True,
        source_step_completed=True,
        answers={
            "eskez-doma": {
                "6": "Да",
                "6а": "В доме",
            },
            "garazh": {"1": "Современный минимализм"},
        },
    )

    spec = _spec(build_initial_concept_prompt(catalog, session, input_asset_present=False))
    house_spec = next(
        item for item in spec["task"]["objects"] if item["object_key"] == "eskez-doma"
    )
    prompt_questions = {
        item["question"] for item in house_spec["questionnaire_constraints"]
    }
    garage_branch_questions = {
        question["text"]
        for question in house["questions"]
        if question["id"] in {"6", "6а", "6б", "6в"}
    }

    assert prompt_questions.isdisjoint(garage_branch_questions)
    assert any(item["object_key"] == "garazh" for item in spec["task"]["objects"])


def test_initial_concept_hardens_object_identity_and_detached_structures() -> None:
    catalog = build_catalog()
    session = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma", "garazh", "lavochka"],
        plot_area_sotkas=8,
        initial_concept_mode=True,
        source_step_completed=True,
        answers={
            "eskez-doma": {"1": "Современный минимализм"},
            "garazh": {
                "1": "Как у дома",
                "4": "Ближе к улице, у въезда",
            },
            "lavochka": {
                "1": "Металл + дерево",
                "2": "Слева от дома",
            },
        },
    )

    spec = _spec(build_initial_concept_prompt(catalog, session, input_asset_present=False))
    objects = {item["object_key"]: item for item in spec["task"]["objects"]}

    assert objects["garazh"]["visual_identity"] == {
        "must_be_recognizable_as": "Гараж, отдельный",
        "substitution_forbidden": True,
    }
    assert objects["garazh"]["structural_constraints"] == ["detached_from_house"]
    assert objects["lavochka"]["visual_identity"] == {
        "must_be_recognizable_as": "Лавочка",
        "substitution_forbidden": True,
    }
    assert objects["lavochka"]["structural_constraints"] == []
    assert spec["object_fidelity"]["strength"] == "hard_constraints"
    assert "замен" in spec["object_fidelity"]["identity_rule"].lower()
    assert "общая стена" in spec["object_fidelity"]["detached_structure_rule"].lower()


def test_house_followup_with_no_available_options_is_inactive() -> None:
    house = _definition("eskez-doma")
    questions = {question["id"]: question for question in house["questions"]}
    non_flat_roof = next(
        option for option in questions["7"]["options"] if option != "Плоская"
    )
    two_floors = next(
        option for option in questions["4"]["options"] if option.startswith("2 ")
    )
    answers = {
        "4": two_floors,
        "7": non_flat_roof,
        "12": next(option for option in questions["12"]["options"] if option != "Нет"),
        "12б": ["Второй этаж"],
    }

    assert question_is_active(
        "eskez-doma",
        questions["13"],
        answers,
        True,
        ["eskez-doma"],
    ) is False


def test_initial_concept_promotes_object_location_to_explicit_site_layout_constraint() -> None:
    catalog = build_catalog()
    bench = _definition("lavochka")
    location_question = next(
        question
        for question in bench["questions"]
        if "где" in question["text"].lower()
        or "относительно" in question["text"].lower()
        or "располож" in question["text"].lower()
    )
    location_answer = next(
        (
            option
            for option in location_question["options"]
            if any(marker in option.lower() for marker in ("сзади", "двор"))
        ),
        location_question["options"][0],
    )
    session = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma", "lavochka"],
        plot_area_sotkas=8,
        initial_concept_mode=True,
        source_step_completed=True,
        answers={
            "eskez-doma": {"1": "Современный минимализм"},
            "lavochka": {location_question["id"]: location_answer},
        },
    )

    spec = _spec(build_initial_concept_prompt(catalog, session, input_asset_present=False))

    assert spec["site_scale"]["plot_area_m2"] == 800
    assert spec["site_layout"]["strength"] == "hard_constraints"
    assert {
        "object_key": "lavochka",
        "object_name": "Лавочка",
        "question": location_question["text"],
        "answer": location_answer,
    } in spec["site_layout"]["placement_constraints"]
    assert "располож" in spec["site_layout"]["directive"].lower()



def test_initial_concept_embeds_deterministic_normalized_site_plan() -> None:
    catalog = build_catalog()
    bench = _definition("lavochka")
    location_question = next(
        question
        for question in bench["questions"]
        if "относительно дома" in question["text"].lower()
    )
    right_answer = next(
        option for option in location_question["options"] if "справа" in option.lower()
    )
    session = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma", "lavochka"],
        plot_area_sotkas=8,
        initial_concept_mode=True,
        source_step_completed=True,
        answers={
            "eskez-doma": {
                "1": "Современный минимализм",
                "3": 200,
                "4": "2 этажа",
            },
            "lavochka": {location_question["id"]: right_answer},
        },
    )

    first = _spec(build_initial_concept_prompt(catalog, session, input_asset_present=False))
    second = _spec(build_initial_concept_prompt(catalog, session, input_asset_present=False))

    assert first["site_plan"] == second["site_plan"]
    site_plan = first["site_plan"]
    assert site_plan["schema"] == "auroom.site_plan.v1"
    assert site_plan["plot"] == {
        "area_sotkas": 8,
        "area_m2": 800,
        "coordinate_system": "normalized",
        "front_side": "y0",
        "geometry_accuracy": "relative",
    }

    objects = {item["object_key"]: item for item in site_plan["objects"]}
    assert set(objects) == {"eskez-doma", "lavochka"}
    house = objects["eskez-doma"]
    bench_item = objects["lavochka"]

    assert house["role"] == "house"
    assert house["placement_source"] == "derived"
    assert house["estimated_footprint_m2"] == 100.0
    assert bench_item["placement_source"] == "questionnaire"
    assert bench_item["relations"] == ["right_of_house"]

    for item in objects.values():
        rect = item["rect"]
        assert 0 <= rect["x"] < 1
        assert 0 <= rect["y"] < 1
        assert 0 < rect["width"] <= 1
        assert 0 < rect["height"] <= 1
        assert rect["x"] + rect["width"] <= 1
        assert rect["y"] + rect["height"] <= 1

    house_right = house["rect"]["x"] + house["rect"]["width"]
    bench_center_x = bench_item["rect"]["x"] + bench_item["rect"]["width"] / 2
    assert bench_center_x > house_right
    assert site_plan["warnings"] == []


def test_initial_concept_site_plan_keeps_multiple_spatial_relations() -> None:
    catalog = build_catalog()
    synthetic_catalog = {
        **catalog,
        "questionnaires": [
            *[
                definition
                for definition in catalog["questionnaires"]
                if definition["key"] != "lavochka"
            ],
            {
                **_definition("lavochka"),
                "questions": [
                    {
                        **question,
                        "options": ["Справа от дома, у въезда"]
                        if question["id"] == "2"
                        else question["options"],
                    }
                    for question in _definition("lavochka")["questions"]
                ],
            },
        ],
    }
    session = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma", "lavochka"],
        plot_area_sotkas=8,
        initial_concept_mode=True,
        source_step_completed=True,
        answers={
            "eskez-doma": {"1": "Современный минимализм"},
            "lavochka": {"2": "Справа от дома, у въезда"},
        },
    )

    spec = _spec(
        build_initial_concept_prompt(
            synthetic_catalog,
            session,
            input_asset_present=False,
        )
    )
    objects = {item["object_key"]: item for item in spec["site_plan"]["objects"]}
    bench_item = objects["lavochka"]

    assert bench_item["relations"] == ["right_of_house", "entry_zone"]
    assert bench_item["zone"] == "entry_right"
    assert bench_item["rect"]["y"] < objects["eskez-doma"]["rect"]["y"]
