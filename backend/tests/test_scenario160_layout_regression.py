import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.initial_layout_guide import build_initial_layout_guide
from app.questionnaires.catalog import build_catalog
from app.questionnaires.generation_prompt import build_initial_concept_prompt
from app.schemas.questionnaires import DesignSession


def scenario160_prompt() -> str:
    catalog = build_catalog()
    values = json.loads(
        (Path(__file__).parent / "fixtures/initial-layout-case7.json").read_text()
    )
    values["catalog_version"] = catalog["version"]
    values["selected_objects"] = ["eskez-doma", "basseyn", "izgorod"]
    values["survey_completed_objects"] = list(values["selected_objects"])
    values["plot_area_sotkas"] = 10
    values["answers"]["eskez-doma"].update(
        {
            "2": "Прямоугольник",
            "3": 200,
            "4": "2 этажа с мансардой",
            "7": "Ломаная мансардная",
        }
    )
    values["answers"]["basseyn"].update(
        {
            "1": "Выкопанный",
            "2": "Овал",
            "3": "Около 8×4 м",
            "4": "Навес",
            "5": "Отдельно во дворе",
            "6": "Сзади, во дворе",
        }
    )
    values["answers"]["izgorod"].update(
        {
            "1": "Цветущая",
            "2": "Около 1,5 м",
            "3": "Весь периметр внутри забора",
        }
    )
    return build_initial_concept_prompt(
        catalog,
        DesignSession(**values),
        input_asset_present=False,
    )


def _spec(prompt: str) -> dict:
    return json.JSONDecoder().raw_decode(
        prompt.split("STRUCTURED_SPEC:\n", 1)[1]
    )[0]


def test_scenario160_does_not_claim_exact_house_footprint_from_unknown_attic_area():
    spec = _spec(scenario160_prompt())

    assert spec["site_scale"]["house_total_area_m2"] == 200.0
    assert spec["site_scale"]["house_floor_count_reference"] == 2.5
    assert spec["site_scale"]["estimated_house_footprint_m2"] is None
    assert spec["site_scale"]["estimated_house_footprint_share_of_plot"] is None
    assert spec["site_scale"]["house_footprint_estimate_status"] == "unmeasured_attic_area"


def test_scenario160_keeps_relation_guide_for_oval_pool_with_canopy():
    guide = build_initial_layout_guide(scenario160_prompt())

    assert guide is not None
    instruction = guide.prompt.split("AUROOM_INITIAL_CONCEPT_V1", 1)[0]
    assert "house footprint scale is not certified" in instruction.lower()
    assert "oval" in instruction.lower()
    assert "canopy" in instruction.lower()
    assert "cover the blue water footprint" in instruction.lower()

    image = Image.open(BytesIO(guide.data)).convert("RGB")
    pixels = image.load()

    def color_bbox(color):
        points = [
            (x, y)
            for y in range(image.height)
            for x in range(image.width)
            if pixels[x, y] == color
        ]
        assert points
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return min(xs), min(ys), max(xs), max(ys)

    pool = color_bbox((57, 145, 186))
    canopy = color_bbox((210, 154, 68))
    assert canopy[0] <= pool[0] <= pool[2] <= canopy[2]
    assert canopy[1] <= pool[1] <= pool[3] <= canopy[3]
    assert abs((canopy[0] + canopy[2]) - (pool[0] + pool[2])) <= 2
    assert abs((canopy[1] + canopy[3]) - (pool[1] + pool[3])) <= 2
    assert (125, 124, 114) not in {
        color for _, color in image.getcolors(image.width * image.height)
    }
