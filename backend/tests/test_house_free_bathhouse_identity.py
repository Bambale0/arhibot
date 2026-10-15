"""Regression for a real failure: selected sauna + gazebo, no house anchor.

All inputs are synthetic and contain no user/project identifiers.
"""
from __future__ import annotations

import json

from app.prompt_builders.visual_fidelity import build_visual_fidelity_prompt
from app.questionnaires.catalog import build_catalog
from app.questionnaires.generation_prompt import build_initial_concept_prompt
from app.schemas.questionnaires import DesignSession


def _prompt(*, objects=("banya", "besedka"), site_photo=False, stove="Дровяная, с трубой"):
    catalog = build_catalog()
    session = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=list(objects),
        plot_area_sotkas=10,
        initial_concept_mode=True,
        answers={
            "banya": {
                "4": "Финская сауна",
                "5": stove,
                "6": "Отдельное строение",
                "7": "Слева от дома",
            },
            "besedka": {"5": "Сзади, во дворе"},
        },
    )
    return build_initial_concept_prompt(
        catalog, session, input_asset_present=site_photo,
    )


def _spec(prompt):
    return json.JSONDecoder().raw_decode(prompt.split("STRUCTURED_SPEC:\n", 1)[1])[0]


def test_house_free_bathhouse_and_gazebo_have_distinct_identities_and_plot_fallback():
    original = _prompt()
    original_spec = _spec(original)
    enriched = build_visual_fidelity_prompt(original)
    spec = _spec(enriched)
    priority = enriched.split("AUROOM_INITIAL_CONCEPT_V1", 1)[0]

    assert [o["object_key"] for o in spec["task"]["objects"]] == ["banya", "besedka"]
    assert spec["source_scene"]["kind"] == "synthetic_site"
    fallback = spec["site_layout"]["house_relative_fallback"]
    assert fallback["approximate"] is True
    assert fallback["affected_object_keys"] == ["banya", "besedka"]
    assert fallback["direction_mapping"]["left_of_house"] == "plot_left"
    assert fallback["direction_mapping"]["behind_house"] == "plot_back"
    assert "HOUSE-FREE PLOT" in priority
    assert "ENCLOSED BATHHOUSE" in priority
    assert "BATHHOUSE AND GAZEBO MUST BE TWO VISIBLY DISTINCT OBJECTS" in priority
    assert "summer kitchen" in priority.lower()
    assert "banya" in spec["visual_acceptance_contract"]["required_roof_chimneys_on_objects"]
    assert set(spec["visual_acceptance_contract"]["required_selected_object_keys"]) == {
        "banya", "besedka",
    }
    assert _spec(original) == original_spec  # canonical questionnaire never rewritten


def test_house_photo_does_not_reinterpret_existing_house_placement():
    original = _prompt(site_photo=True)
    enriched = build_visual_fidelity_prompt(original)
    spec = _spec(enriched)
    assert spec["source_scene"]["kind"] == "site_photo"
    assert "house_relative_fallback" not in spec["site_layout"]
    assert "HOUSE-FREE PLOT" not in enriched.split("AUROOM_INITIAL_CONCEPT_V1", 1)[0]


def test_bath_with_selected_house_uses_actual_house_as_anchor():
    original = _prompt(objects=("eskez-doma", "banya"))
    enriched = build_visual_fidelity_prompt(original)
    spec = _spec(enriched)
    priority = enriched.split("AUROOM_INITIAL_CONCEPT_V1", 1)[0]
    assert "house_relative_fallback" not in spec["site_layout"]
    assert "HOUSE-FREE PLOT" not in priority
    assert "ENCLOSED BATHHOUSE" in priority
    assert [o["object_key"] for o in spec["task"]["objects"]] == ["eskez-doma", "banya"]


def test_electric_bath_has_no_unrequested_chimney():
    enhanced = build_visual_fidelity_prompt(_prompt(stove="Электрическая, без трубы"))
    spec = _spec(enhanced)
    assert "banya" not in spec["visual_acceptance_contract"]["required_roof_chimneys_on_objects"]
    assert "ENCLOSED BATHHOUSE" in enhanced


def test_gazebo_only_does_not_invent_bath_or_summer_kitchen():
    enhanced = build_visual_fidelity_prompt(_prompt(objects=("besedka",)))
    spec = _spec(enhanced)
    assert [o["object_key"] for o in spec["task"]["objects"]] == ["besedka"]
    priority = enhanced.split("AUROOM_INITIAL_CONCEPT_V1", 1)[0]
    assert "ENCLOSED BATHHOUSE" not in priority
    assert "BATHHOUSE AND GAZEBO" not in priority
