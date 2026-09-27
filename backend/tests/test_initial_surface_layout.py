"""Full boundaries and a continuous lawn are not isolated interior buildings."""
from copy import deepcopy
import json

import pytest

from app.prompt_builders.visual_fidelity import build_visual_fidelity_prompt
from tests.test_initial_selected_details import canonical, parsed


def provider(spec):
    return parsed(build_visual_fidelity_prompt(
        "AUROOM_INITIAL_CONCEPT_V1\nSTRUCTURED_SPEC:\n" + json.dumps(spec, ensure_ascii=False)
    ))


def plan_keys(spec):
    return {obj["object_key"] for obj in spec["site_plan"]["objects"]}


def test_full_boundaries_and_simple_lawn_have_no_interior_proxy_rectangles():
    original = canonical(fence="Решётка / штакетик, видно двор")
    before = parsed(original)
    after = parsed(build_visual_fidelity_prompt(original))
    assert {"izgorod", "zabor", "gazon"} <= plan_keys(before)
    assert plan_keys(after) == {"eskez-doma", "basseyn"}
    assert {obj["object_key"] for obj in after["task"]["objects"]} == {
        "eskez-doma", "basseyn", "izgorod", "zabor", "gazon"
    }
    assert after["boundary_policy"] == before["boundary_policy"]
    assert original == canonical(fence="Решётка / штакетик, видно двор")


@pytest.mark.parametrize("key", ["izgorod", "zabor"])
@pytest.mark.parametrize("placement", ["Весь периметр", "Весь периметр внутри забора", "Весь периметр по границе участка"])
def test_every_supported_full_perimeter_choice_avoids_a_second_boundary(key, placement):
    spec = parsed(canonical(fence="Решётка / штакетик, видно двор"))
    obj = next(x for x in spec["task"]["objects"] if x["object_key"] == key)
    q = next(x for x in obj["questionnaire_constraints"] if "где" in x["question"].lower())
    q["answer"] = placement
    assert key not in plan_keys(provider(spec))


@pytest.mark.parametrize("placement", ["Со стороны улицы", "Слева от дома", "Неизвестно"])
def test_partial_or_unknown_boundary_placement_is_not_discarded(placement):
    spec = parsed(canonical())
    obj = next(x for x in spec["task"]["objects"] if x["object_key"] == "izgorod")
    next(x for x in obj["questionnaire_constraints"] if "где" in x["question"].lower())["answer"] = placement
    assert "izgorod" in plan_keys(provider(spec))


@pytest.mark.parametrize("scope", ["photo", "local", "remove"])
def test_source_and_local_scenes_keep_their_existing_placement_objects(scope):
    spec = parsed(canonical(photo=scope == "photo"))
    if scope != "photo":
        spec["schema"] = "auroom.render_spec.v1"
        spec["task"]["operation"] = "remove_object" if scope == "remove" else "add_object"
    assert plan_keys(provider(spec)) == plan_keys(spec)


def test_mixed_planting_keeps_its_discrete_placement_zone():
    spec = parsed(canonical(planting=["Газон", "Цветники"]))
    assert "gazon" in plan_keys(provider(spec))


def test_explicit_nonderived_boundary_zone_is_not_silently_removed():
    spec = parsed(canonical())
    next(x for x in spec["site_plan"]["objects"] if x["object_key"] == "izgorod")["placement_source"] = "questionnaire"
    assert "izgorod" in plan_keys(provider(spec))


def test_only_removed_proxy_placement_warnings_are_dropped():
    spec = parsed(canonical())
    keep = [
        {"object_key": "basseyn", "code": "house_relative_constraint_without_house"},
        {"object_key": "izgorod", "code": "unrecognized_boundary"},
    ]
    spec["site_plan"]["warnings"] = deepcopy(keep) + [
        {"object_key": "izgorod", "code": "placement_overlap_unresolved"},
        {"object_key": "gazon", "code": "placement_relation_unresolved"},
    ]
    assert provider(spec)["site_plan"]["warnings"] == keep
