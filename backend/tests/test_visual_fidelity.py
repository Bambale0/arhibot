import json
import pytest
from app.prompt_builders.visual_fidelity import build_visual_fidelity_prompt
from app.questionnaires.catalog import build_catalog
from app.questionnaires.generation_prompt import (
    build_initial_concept_prompt,
    build_questionnaire_generation_prompt,
)
from app.schemas.questionnaires import DesignSession


def spec(prompt):
    return json.JSONDecoder().raw_decode(prompt.split("STRUCTURED_SPEC:\n", 1)[1])[0]


def test_provider_constraints_require_bath_chimney_and_remove_fence_cue_without_changing_canonical():
    catalog = build_catalog()
    state = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma", "banya", "izgorod"],
        initial_concept_mode=True,
        plot_area_sotkas=10,
        answers={
            "eskez-doma": {"2": "Г-образная", "3": 200, "4": "2 этажа", "11б": "Да"},
            "banya": {"5": "Дровяная, с трубой"},
            "izgorod": {"1": "Цветущая", "3": "Весь периметр внутри забора"},
        },
    )
    canonical = build_initial_concept_prompt(catalog, state, input_asset_present=False)
    enriched = spec(build_visual_fidelity_prompt(canonical))
    assert "внутри забора" in canonical
    assert enriched["visual_acceptance_contract"]["required_roof_chimneys_on_objects"] == [
        "banya",
        "eskez-doma",
    ]
    hedge = next(o for o in enriched["task"]["objects"] if o["object_key"] == "izgorod")
    assert not any("внутри забора" in str(c["answer"]) for c in hedge["questionnaire_constraints"])
    house = next(o for o in enriched["site_plan"]["objects"] if o["object_key"] == "eskez-doma")
    assert house["rect"]["width"] * house["rect"]["height"] * 0.75 == pytest.approx(0.1)
    assert len(house["footprint_polygon"]) == 6
    assert canonical == build_initial_concept_prompt(catalog, state, input_asset_present=False)


def test_provider_does_not_enlarge_small_house_to_minimum_screen_size():
    catalog = build_catalog()
    state = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma"],
        initial_concept_mode=True,
        plot_area_sotkas=15,
        answers={"eskez-doma": {"2": "Прямоугольник", "3": 60, "4": "2 этажа"}},
    )
    result = spec(
        build_visual_fidelity_prompt(
            build_initial_concept_prompt(catalog, state, input_asset_present=False)
        )
    )
    house = result["site_plan"]["objects"][0]
    assert house["rect"]["width"] * house["rect"]["height"] == pytest.approx(0.02)


def test_removing_bath_does_not_request_its_chimney():
    catalog = build_catalog()
    definition = next(d for d in catalog["questionnaires"] if d["key"] == "banya")
    state = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["banya"],
        current_object="banya",
        pending_removal_object="banya",
        accepted_objects=["banya"],
        answers={"banya": {"5": "Дровяная, с трубой"}},
    )
    result = spec(
        build_visual_fidelity_prompt(
            build_questionnaire_generation_prompt(
                definition, state, accepted_before=[], input_asset_present=True
            )
        )
    )
    assert result["visual_acceptance_contract"]["required_roof_chimneys_on_objects"] == []


@pytest.mark.parametrize(
    "shape,vertices,fill",
    [
        ("П-образная, двор внутри — эскиз может быть неточным", 8, 0.76),
        ("Квадрат", 4, 1.0),
        ("Г-образная", 6, 0.75),
    ],
)
def test_catalog_shape_is_preserved_with_exact_ground_area(shape, vertices, fill):
    catalog = build_catalog()
    state = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma"],
        initial_concept_mode=True,
        plot_area_sotkas=10,
        answers={"eskez-doma": {"2": shape, "3": 200, "4": "2 этажа"}},
    )
    result = spec(
        build_visual_fidelity_prompt(
            build_initial_concept_prompt(catalog, state, input_asset_present=False)
        )
    )
    house = result["site_plan"]["objects"][0]
    assert len(house["footprint_polygon"]) == vertices
    assert house["rect"]["width"] * house["rect"]["height"] * fill == pytest.approx(0.1)
    if shape == "Квадрат":
        assert house["rect"]["width"] == pytest.approx(house["rect"]["height"])


def test_bath_edit_does_not_request_main_house_chimney_inside_bath_mask():
    catalog = build_catalog()
    definition = next(d for d in catalog["questionnaires"] if d["key"] == "banya")
    state = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma", "banya"],
        current_object="banya",
        accepted_objects=["eskez-doma"],
        answers={"eskez-doma": {"11б": "Да"}, "banya": {"5": "Дровяная, с трубой"}},
    )
    result = spec(
        build_visual_fidelity_prompt(
            build_questionnaire_generation_prompt(
                definition, state, accepted_before=["eskez-doma"], input_asset_present=True
            )
        )
    )
    assert result["visual_acceptance_contract"]["required_roof_chimneys_on_objects"] == ["banya"]
