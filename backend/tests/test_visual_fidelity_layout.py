import json

import pytest

from app.prompt_builders.visual_fidelity import build_visual_fidelity_prompt
from app.questionnaires.catalog import build_catalog
from app.questionnaires.generation_prompt import build_initial_concept_prompt
from app.schemas.questionnaires import DesignSession


def _spec(prompt):
    return json.JSONDecoder().raw_decode(prompt.split("STRUCTURED_SPEC:\n", 1)[1])[0]


def _prompt(shape, area, floors, location):
    catalog = build_catalog()
    state = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma", "banya"],
        initial_concept_mode=True,
        plot_area_sotkas=10,
        answers={
            "eskez-doma": {"2": shape, "3": area, "4": floors},
            "banya": {"7": location},
        },
    )
    return build_initial_concept_prompt(catalog, state, input_asset_present=False)


def _separated(a, b):
    return (
        a["x"] + a["width"] + 0.012 <= b["x"]
        or b["x"] + b["width"] + 0.012 <= a["x"]
        or a["y"] + a["height"] + 0.012 <= b["y"]
        or b["y"] + b["height"] + 0.012 <= a["y"]
    )


@pytest.mark.parametrize("location", ["Справа от дома", "Слева от дома"])
def test_expanded_l_house_repositions_bath_without_changing_side_or_size(location):
    canonical = _prompt("Г-образная", 300, "2 этажа", location)
    original = _spec(canonical)
    result = _spec(build_visual_fidelity_prompt(canonical))
    house, bath = result["site_plan"]["objects"]
    a, b = house["rect"], bath["rect"]
    assert _separated(a, b)
    assert a["width"] * a["height"] * 0.75 == pytest.approx(0.15)
    assert b["width"] == original["site_plan"]["objects"][1]["rect"]["width"]
    assert b["height"] == original["site_plan"]["objects"][1]["rect"]["height"]
    if location.startswith("Справа"):
        assert b["x"] + b["width"] / 2 > a["x"] + a["width"]
    else:
        assert b["x"] + b["width"] / 2 < a["x"]
    assert result["site_plan"]["warnings"] == []
    assert _spec(canonical) == original


@pytest.mark.parametrize("shape,area", [("Квадрат", 200), ("Прямоугольник", 60)])
def test_valid_bath_stays_in_place_when_house_changes(shape, area):
    canonical = _prompt(shape, area, "2 этажа", "Справа от дома")
    original = _spec(canonical)
    result = _spec(build_visual_fidelity_prompt(canonical))
    assert result["site_plan"]["objects"][1] == original["site_plan"]["objects"][1]
    assert result["site_plan"]["warnings"] == []


def test_impossible_side_layout_remains_explicitly_unresolved():
    canonical = _prompt("Квадрат", 800, "1 этаж", "Справа от дома")
    result = _spec(build_visual_fidelity_prompt(canonical))
    warnings = result["site_plan"]["warnings"]
    assert {"object_key": "banya", "code": "placement_overlap_unresolved"} in warnings
    assert {"object_key": "banya", "code": "placement_relation_unresolved"} in warnings
    assert result["site_scale"]["ground_footprint_contract"]["layout_requires_review"] is True


def test_relocated_bath_respects_already_valid_zones_and_keeps_other_warnings():
    original = _spec(_prompt("Г-образная", 300, "2 этажа", "Справа от дома"))
    bench = {
        "object_key": "lavochka",
        "relations": [],
        "rect": {"x": 0.74, "y": 0.04, "width": 0.22, "height": 0.16},
    }
    original["site_plan"]["objects"].append(bench)
    preserved_warning = {"object_key": "banya", "code": "existing_other_diagnostic"}
    original["site_plan"]["warnings"].append(preserved_warning)
    canonical = "AUROOM_INITIAL_CONCEPT_V1\nSTRUCTURED_SPEC:\n" + json.dumps(original)
    result = _spec(build_visual_fidelity_prompt(canonical))
    house, bath, unchanged_bench = result["site_plan"]["objects"]
    assert unchanged_bench == bench
    assert _separated(house["rect"], bath["rect"])
    assert _separated(bath["rect"], unchanged_bench["rect"])
    assert result["site_plan"]["warnings"] == [preserved_warning]
