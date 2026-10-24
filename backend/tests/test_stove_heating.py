import json

import pytest

from app.prompt_builders.visual_fidelity import selected_visual_constraints
from app.questionnaires.catalog import build_catalog
from app.questionnaires.generation_prompt import (
    build_initial_concept_prompt,
    build_questionnaire_generation_prompt,
)
from app.schemas.questionnaires import DesignSession


def test_house_heating_question_and_refinement_label():
    house = next(q for q in build_catalog()["questionnaires"] if q["key"] == "eskez-doma")
    questions = {q["id"]: q for q in house["questions"]}
    assert questions["11б"]["text"] == "Печное отопление?"
    assert set(questions["11б"]["options"]) == {"Да", "Нет"}
    assert questions["11б"]["skip_default"] == "Нет"
    assert questions["15б"]["edit_targets"]["Печное отопление, труба"] == ["11б"]
    assert "Камин, труба" not in questions["15б"]["options"]


@pytest.mark.parametrize("answer", ["Да", "Нет"])
@pytest.mark.parametrize("initial", [True, False])
def test_heating_chimney_is_explicit_for_initial_and_refinement(answer, initial):
    catalog = build_catalog()
    session = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma", "banya"],
        source_step_completed=True,
        initial_concept_mode=initial,
        answers={"eskez-doma": {"11б": answer}, "banya": {"5": "Дровяная, с трубой"}},
    )
    house = next(q for q in catalog["questionnaires"] if q["key"] == "eskez-doma")
    prompt = (
        build_initial_concept_prompt(catalog, session, input_asset_present=False)
        if initial
        else build_questionnaire_generation_prompt(
            house, session, accepted_before=[], input_asset_present=True
        )
    )
    spec = json.JSONDecoder().raw_decode(prompt.split("STRUCTURED_SPEC:\n", 1)[1])[0]
    feature = spec["house_exterior_features"]
    assert feature["roof_chimney_required"] is (answer == "Да")
    assert feature["roof_chimney_forbidden"] is (answer == "Нет")
    assert "печного отопления" in feature["directive"]
    assert "каминную трубу" not in feature["directive"]


@pytest.mark.parametrize("text", ["Печное отопление?", "Будет ли камин в доме?"])
@pytest.mark.parametrize("answer,expected", [("Да", "required"), ("Нет", "not_requested")])
def test_visual_adapter_supports_new_and_historical_heating_wording(text, answer, expected):
    assert (
        selected_visual_constraints("eskez-doma", [{"question": text, "answer": answer}])["chimney"]
        == expected
    )


def test_catalog_migration_preserves_operator_edits_and_old_snapshot():
    from copy import deepcopy
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    path = Path(__file__).parents[1] / "alembic/versions/20261024_0043_stove_heating.py"
    spec = spec_from_file_location("stove_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    catalog = deepcopy(build_catalog())
    catalog["version"] = "operator-custom-v1"
    catalog["questionnaires"][0]["questions"][0]["text"] = "Operator style question"
    house = catalog["questionnaires"][0]
    next(q for q in house["questions"] if q["id"] == "11б")["text"] = "Будет ли камин в доме?"
    sources = {
        "eskez-doma": {"filename": house["source_file"], "text": "11б. Будет ли камин в доме?"}
    }
    before, sources_before = deepcopy(catalog), deepcopy(sources)
    updated, updated_sources = migration._updated_content(catalog, sources)
    assert catalog == before
    assert sources == sources_before
    assert updated["version"] == migration.VERSION
    assert updated["questionnaires"][1:] == catalog["questionnaires"][1:]
    assert updated["questionnaires"][0]["questions"][0]["text"] == "Operator style question"
    heating = next(q for q in updated["questionnaires"][0]["questions"] if q["id"] == "11б")
    assert heating["text"] == "Печное отопление?"
    assert updated_sources["eskez-doma"]["text"] == "11б. Печное отопление?"
