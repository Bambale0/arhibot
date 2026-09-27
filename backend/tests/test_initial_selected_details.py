"""Actual catalog selections must survive styling of a new synthetic scene."""

import json
from pathlib import Path

import pytest

from app.initial_layout_guide import build_initial_layout_guide
from app.prompt_builders.visual_fidelity import build_visual_fidelity_prompt
from app.questionnaires.catalog import build_catalog
from app.questionnaires.generation_prompt import build_initial_concept_prompt
from app.schemas.questionnaires import DesignSession


def canonical(*, photo=False, window="Стандартные окна", planting=None, style=None, hedge=True):
    values = json.loads((Path(__file__).parent / "fixtures/initial-layout-case7.json").read_text())
    catalog = build_catalog()
    values["catalog_version"] = catalog["version"]
    if not hedge:
        values["selected_objects"].remove("izgorod")
        values["survey_completed_objects"].remove("izgorod")
    values["answers"]["eskez-doma"]["9"] = window
    if planting is not None:
        values["answers"]["gazon"]["2"] = planting
    if style is not None:
        values["answers"]["gazon"]["1"] = style
    return build_initial_concept_prompt(catalog, DesignSession(**values), input_asset_present=photo)


def parsed(prompt):
    return json.JSONDecoder().raw_decode(prompt.split("STRUCTURED_SPEC:\n", 1)[1])[0]


def object_spec(prompt, key):
    return next(obj for obj in parsed(prompt)["task"]["objects"] if obj["object_key"] == key)


def test_actual_standard_window_answer_requires_sills_not_panoramic_glass():
    original = canonical()
    provider = build_visual_fidelity_prompt(original)
    glazing = object_spec(provider, "eskez-doma")["glazing_directive"]
    assert "opaque wall below each window" in glazing
    assert "no floor-to-ceiling" in glazing
    assert "explicitly selected" in glazing
    assert glazing in provider.split("AUROOM_INITIAL_CONCEPT_V1")[0]
    assert (
        object_spec(provider, "eskez-doma")["questionnaire_constraints"]
        == object_spec(original, "eskez-doma")["questionnaire_constraints"]
    )
    assert original == canonical()


def test_actual_minimalist_lawn_only_preserves_selected_hedge_and_outside_trees():
    original = canonical()
    provider = build_visual_fidelity_prompt(original)
    planting = object_spec(provider, "gazon")["planting_directive"]
    assert "inside this plot" in planting and "no decorative trees" in planting
    assert "flower beds" in planting and "selected living hedge" in planting
    assert "potted plants" in planting and "planters" in planting
    assert "including beside the house entrance" in planting
    assert "outside the plot" in planting
    assert planting in provider.split("AUROOM_INITIAL_CONCEPT_V1")[0]
    assert (
        object_spec(provider, "gazon")["questionnaire_constraints"]
        == object_spec(original, "gazon")["questionnaire_constraints"]
    )
    assert "Цветущая" in str(object_spec(provider, "izgorod"))
    assert original == canonical()


def test_lawn_without_selected_hedge_never_receives_a_hedge_preservation_instruction():
    provider = build_visual_fidelity_prompt(canonical(hedge=False))
    planting = object_spec(provider, "gazon")["planting_directive"]
    assert "no decorative trees" in planting
    assert "hedge" not in planting
    assert parsed(provider)["boundary_policy"]["hedge_requested"] is False


@pytest.mark.parametrize(
    "window", ["Крупные панорамные окна", "Витражи в пол", "Угловое остекление", "Неизвестно"]
)
def test_other_window_selections_do_not_gain_standard_glazing_restriction(window):
    assert "glazing_directive" not in object_spec(
        build_visual_fidelity_prompt(canonical(window=window)), "eskez-doma"
    )


@pytest.mark.parametrize(
    "planting,style",
    [
        (["Газон", "Цветники"], None),
        (["Газон", "Лиственные деревья"], None),
        (["Хвойные"], None),
        ([], None),
        (["Неизвестно"], None),
        (["Газон"], "Лесной, хвойные"),
        (["Газон"], "Садовый, цветники"),
    ],
)
def test_mixed_unknown_or_nonminimalist_planting_is_not_restricted(planting, style):
    provider = build_visual_fidelity_prompt(canonical(planting=planting, style=style))
    assert "planting_directive" not in object_spec(provider, "gazon")


@pytest.mark.parametrize("scope", ["photo", "local", "remove"])
def test_new_scene_details_never_retrofit_source_or_local_operations(scope):
    original = canonical(photo=scope == "photo")
    if scope != "photo":
        spec = parsed(original)
        spec["schema"] = "auroom.render_spec.v1"
        spec["task"]["operation"] = "remove_object" if scope == "remove" else "refine_object"
        original = "AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n" + json.dumps(spec)
    provider = build_visual_fidelity_prompt(original)
    assert "glazing_directive" not in object_spec(provider, "eskez-doma")
    assert "planting_directive" not in object_spec(provider, "gazon")


def test_guide_carries_detail_constraints_without_changing_ground_geometry():
    guide = build_initial_layout_guide(canonical())
    panoramic = build_initial_layout_guide(canonical(window="Крупные панорамные окна"))
    assert guide and panoramic
    assert guide.data == panoramic.data
    assert "opaque wall below each window" in guide.prompt
    assert "no decorative trees" in guide.prompt
