import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.initial_layout_guide import build_initial_layout_guide
from app.questionnaires.catalog import build_catalog
from app.questionnaires.generation_prompt import build_initial_concept_prompt
from app.schemas.questionnaires import DesignSession


def canonical(*, photo=False, **changes):
    catalog = build_catalog()
    # Sanitized QA prepared_session from 07-final-l-house-pool-hedge (2026-09-26):
    # exact answers from the successful paid guide probe, no IDs or user metadata.
    values = json.loads((Path(__file__).parent / "fixtures/initial-layout-case7.json").read_text())
    values["catalog_version"] = catalog["version"]
    values.update(changes)
    values["survey_completed_objects"] = [
        key for key in values["survey_completed_objects"] if key in values["selected_objects"]
    ]
    return build_initial_concept_prompt(catalog, DesignSession(**values), input_asset_present=photo)


def test_guide_encodes_ground_areas_without_labels_or_fence_and_keeps_canonical(monkeypatch):
    original = canonical()

    def forbidden_text(*args, **kwargs):
        pytest.fail("Layout reference must contain no text or numbers")

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", forbidden_text)
    guide = build_initial_layout_guide(original)
    assert guide is not None
    assert original == canonical()
    image = Image.open(BytesIO(guide.data)).convert("RGB")
    assert image.size == (1536, 864)
    colors = {color: count for count, color in image.getcolors(image.width * image.height)}
    plot_area = int(min(image.size) * 0.84) ** 2
    assert colors[(193, 169, 135)] / plot_area == pytest.approx(0.1, abs=0.001)
    assert colors[(57, 145, 186)] / plot_area == pytest.approx(0.018, abs=0.001)
    assert (125, 124, 114) not in colors
    assert "10.0%" in guide.prompt
    spec = json.JSONDecoder().raw_decode(guide.prompt.split("STRUCTURED_SPEC:\n", 1)[1])[0]
    assert spec["site_scale"]["ground_footprint_contract"]["target_share"] == 0.1


@pytest.mark.parametrize(
    "change",
    [
        "photo",
        "one",
        "unknown",
        "gate",
        "partial_hedge",
        "partial_fence",
        "unknown_size",
        "pavilion",
        "attached",
        "complex_house",
        "missing_house_shape",
        "oversize",
    ],
)
def test_unsupported_geometry_leaves_existing_provider_flow_unchanged(change):
    base = json.JSONDecoder().raw_decode(canonical().split("STRUCTURED_SPEC:\n", 1)[1])[0]
    question_ids = {
        o["key"]: {q["text"]: q["id"] for q in o["questions"]}
        for o in build_catalog()["questionnaires"]
    }
    answers = {
        o["object_key"]: {
            question_ids[o["object_key"]][c["question"]]: c["answer"]
            for c in o["questionnaire_constraints"]
        }
        for o in base["task"]["objects"]
    }
    selected = ["eskez-doma", "basseyn", "izgorod"]
    if change == "one":
        selected = ["eskez-doma"]
    if change == "unknown":
        selected += ["banya"]
    if change == "gate":
        selected += ["vorota"]
    if change == "partial_hedge":
        answers["izgorod"]["3"] = "Справа"
    if change == "partial_fence":
        selected += ["zabor"]
        answers["zabor"] = {"6": "Только улица, фасад участка"}
    if change == "unknown_size":
        answers["basseyn"]["3"] = "Побольше"
    if change == "oval":
        answers["basseyn"]["2"] = "Овал"
    if change == "pavilion":
        answers["basseyn"]["4"] = "Павильон"
    if change == "attached":
        answers["basseyn"]["5"] = "Пристроен к дому с переходом"
    if change == "complex_house":
        answers["eskez-doma"]["2"] = "Сложная форма"
    if change == "missing_house_shape":
        answers["eskez-doma"].pop("2")
    if change == "mansard":
        answers["eskez-doma"]["4"] = "2 этажа + мансарда"
    if change == "oversize":
        answers["eskez-doma"]["3"] = 1800
    assert (
        build_initial_layout_guide(
            canonical(photo=change == "photo", selected_objects=selected, answers=answers)
        )
        is None
    )


@pytest.mark.parametrize(
    "selected",
    [
        ["eskez-doma", "basseyn", "zabor"],
        ["eskez-doma", "izgorod", "zabor"],
    ],
)
def test_legend_names_only_selected_objects(selected):
    values = json.loads((Path(__file__).parent / "fixtures/initial-layout-case7.json").read_text())
    values["answers"]["zabor"] = {"6": "Весь периметр"}
    guide = build_initial_layout_guide(
        canonical(selected_objects=selected, answers=values["answers"])
    )
    assert guide is not None
    instruction = guide.prompt.split("AUROOM_INITIAL_CONCEPT_V1", 1)[0]
    assert ("pool water footprint" in instruction) == ("basseyn" in selected)
    assert ("Dark green is the selected living hedge." in instruction) == ("izgorod" in selected)
    assert "Gray is the selected built fence." in instruction


@pytest.mark.parametrize("plants", [["Газон", "Хвойные"], ["Огород / грядки"], []])
def test_unlocated_plantings_are_not_replaced_by_plain_lawn(plants):
    values = json.loads((Path(__file__).parent / "fixtures/initial-layout-case7.json").read_text())
    values["answers"]["gazon"]["2"] = plants
    assert build_initial_layout_guide(canonical(answers=values["answers"])) is None


def test_large_pool_outside_its_semantic_zone_keeps_existing_flow():
    values = json.loads((Path(__file__).parent / "fixtures/initial-layout-case7.json").read_text())
    values["answers"]["basseyn"]["3"] = "Около 10×5 м"
    assert build_initial_layout_guide(canonical(answers=values["answers"])) is None
