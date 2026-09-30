from io import BytesIO
import json
import pytest
from PIL import Image
from app.image_compositor import compose_masked_edit
from app.localized_edit import (
    choose_local_geometry,
    local_source,
    local_region,
    project_local_candidate,
    local_edit_prompt,
)


def png(image):
    b = BytesIO()
    image.save(b, format="PNG")
    return b.getvalue()


def test_fractional_crop_roundtrip_preserves_asymmetric_pixels_and_protected_holes():
    image = Image.new("RGB", (101, 79))
    for x in range(image.width):
        for y in range(image.height):
            image.putpixel((x, y), (x * 2, y * 3, (x + y) % 256))
    original = png(image)
    region = {"x": 0.69, "y": 0.61, "width": 0.3, "height": 0.37}
    geometry = choose_local_geometry(original, region, max_pixels=10000)
    crop = local_source(original, geometry, max_pixels=10000)
    assert Image.open(BytesIO(crop)).size != image.size
    projected = project_local_candidate(original, crop, geometry, max_pixels=10000)
    assert Image.open(BytesIO(projected)).tobytes() == image.tobytes()
    tile = Image.open(BytesIO(crop)).convert("RGB")
    tile.paste((240, 0, 0), (0, 0, *tile.size))
    projected = project_local_candidate(original, png(tile), geometry, max_pixels=10000)
    result = compose_masked_edit(
        base_data=original,
        candidate_data=projected,
        edit_region=region,
        protected_regions=[{"x": 0.8, "y": 0.7, "width": 0.1, "height": 0.1}],
        feather_px=0,
    )
    out = Image.open(BytesIO(result.data))
    assert out.getpixel((74, 52)) == (240, 0, 0)
    assert out.getpixel((85, 59)) == image.getpixel((85, 59))
    assert out.getpixel((0, 0)) == image.getpixel((0, 0))
    assert out.getpixel((100, 78)) == image.getpixel((100, 78))


def test_local_edit_rejects_full_frame_aspect_instead_of_stretching():
    base = png(Image.new("RGB", (160, 90)))
    geometry = choose_local_geometry(
        base, {"x": 0.4, "y": 0.3, "width": 0.2, "height": 0.3}, max_pixels=20000
    )
    with pytest.raises(ValueError, match="aspect ratio"):
        project_local_candidate(base, base, geometry, max_pixels=20000)


def test_local_geometry_uses_exif_orientation():
    image = Image.new("RGB", (80, 120))
    exif = Image.Exif()
    exif[274] = 6
    b = BytesIO()
    image.save(b, format="JPEG", exif=exif)
    geometry = choose_local_geometry(
        b.getvalue(), {"x": 0.5, "y": 0.2, "width": 0.2, "height": 0.3}, max_pixels=10000
    )
    assert geometry["base_size"] == [120, 80]
    assert Image.open(BytesIO(local_source(b.getvalue(), geometry, max_pixels=10000))).size == (
        geometry["box"][2] - geometry["box"][0],
        geometry["box"][3] - geometry["box"][1],
    )


def test_local_prompt_replaces_global_coordinates_and_white_mask_instructions():
    prompt = "AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n" + json.dumps(
        {
            "task": {"object_key": "banya"},
            "questionnaire_constraints": [{"question": "Печь", "answer": "Дровяная, с трубой"}],
        }
    )
    geometry = {
        "version": "local-tile.v1",
        "base_size": [100, 100],
        "box": [20, 20, 80, 80],
        "aspect_ratio": "1:1",
    }
    result = local_edit_prompt(
        prompt, geometry, {"x": 0.3, "y": 0.3, "width": 0.4, "height": 0.4}, []
    )
    spec = json.loads(result.split("STRUCTURED_SPEC:\n")[1])
    assert spec["spatial_constraints"]["allowed_region"]["x"] == pytest.approx(1 / 6)
    assert spec["spatial_constraints"]["allowed_region"]["width"] == pytest.approx(2 / 3)
    assert spec["visual_acceptance_contract"]["required_roof_chimneys_on_objects"] == ["banya"]
    assert "NO white mask" in spec["visual_acceptance_contract"]["mask_directive"]
    assert spec["output"]["aspect_ratio"] == "1:1"
    assert local_edit_prompt("unstructured legacy", geometry, {}, []) is None


def test_local_frame_context_is_checked_before_compositor_hides_wrong_frame():
    original = png(Image.new("RGB", (120, 120), (20, 30, 40)))
    region = {"x": 0.3, "y": 0.3, "width": 0.4, "height": 0.4}
    geometry = choose_local_geometry(
        original, {"x": 0.2, "y": 0.2, "width": 0.6, "height": 0.6}, max_pixels=20000
    )
    candidate = png(Image.new("RGB", (72, 72), (240, 240, 240)))
    with pytest.raises(ValueError, match="locked context"):
        project_local_candidate(
            original,
            candidate,
            geometry,
            max_pixels=20000,
            edit_region=region,
            max_context_color_error=32,
        )


def test_global_location_answer_does_not_push_added_object_against_local_edge():
    prompt = "AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n" + json.dumps(
        {
            "task": {"object_key": "banya"},
            "questionnaire_constraints": [
                {"question": "Где на участке относительно дома?", "answer": "Справа от дома"},
                {"question": "Печь", "answer": "Дровяная, с трубой"},
            ],
        }
    )
    geometry = {
        "version": "local-tile.v1",
        "base_size": [100, 100],
        "box": [20, 20, 80, 80],
        "aspect_ratio": "1:1",
        "operation": "add",
    }
    result = local_edit_prompt(
        prompt, geometry, {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}, []
    )
    spec = json.loads(result.split("STRUCTURED_SPEC:\n")[1])
    assert spec["task"]["local_operation"] == "add"
    assert all(item["answer"] != "Справа от дома" for item in spec["questionnaire_constraints"])
    assert "Справа от дома" not in result
    assert spec["resolved_global_placement"]["resolved_by_selected_region"] is True
    assert "CENTER" in spec["visual_acceptance_contract"]["mask_directive"]


@pytest.mark.parametrize("garage_location", ["В доме", "Не в доме"])
def test_local_house_prompt_retains_structural_garage_location_from_catalog(garage_location):
    from app.questionnaires.catalog import build_catalog
    from app.questionnaires.generation_prompt import build_questionnaire_generation_prompt
    from app.schemas.questionnaires import DesignSession

    catalog = build_catalog()
    definition = next(item for item in catalog["questionnaires"] if item["key"] == "eskez-doma")
    state = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma"],
        current_object="eskez-doma",
        answers={"eskez-doma": {"6": "Да", "6а": garage_location}},
    )
    canonical = build_questionnaire_generation_prompt(
        definition, state, accepted_before=[], input_asset_present=True
    )
    geometry = {
        "version": "local-tile.v1", "base_size": [100, 100],
        "box": [10, 10, 90, 90], "aspect_ratio": "1:1",
        "operation": "add", "scene_context_reference": True,
    }
    result = local_edit_prompt(
        canonical, geometry, {"x": 0.2, "y": 0.2, "width": 0.6, "height": 0.6}, []
    )
    constraints = json.loads(result.split("STRUCTURED_SPEC:\n", 1)[1])["questionnaire_constraints"]
    assert {"question": "Нужен гараж?", "answer": "Да"} in constraints
    assert {"question": "Где гараж?", "answer": garage_location} in constraints
    assert canonical == build_questionnaire_generation_prompt(
        definition, state, accepted_before=[], input_asset_present=True
    )


@pytest.mark.parametrize("with_context", [True, False])
def test_scene_reference_is_appearance_context_never_the_output_frame(with_context):
    prompt = 'AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n{"task":{"object_key":"banya"}}'
    geometry = {
        "version": "local-tile.v1",
        "base_size": [120, 100],
        "box": [20, 20, 80, 80],
        "aspect_ratio": "1:1",
        "operation": "add",
    }
    if with_context:
        geometry["scene_context_reference"] = True
    result = local_edit_prompt(
        prompt, geometry, {"x": 0.25, "y": 0.25, "width": 0.3, "height": 0.4}, []
    )
    data = json.loads(result.split("STRUCTURED_SPEC:\n")[1])
    if with_context:
        assert data["appearance_context"]["reference_image"] == 2
        assert data["appearance_context"]["tile_box_in_full_scene_pixels"] == [20, 20, 80, 80]
        assert "image 1 is the ONLY output frame" in data["source_scene"]["directive"]
    else:
        assert "appearance_context" not in data
        assert "image 2" not in result


def test_local_house_refinement_never_requires_whole_plot_or_house_in_tile():
    prompt = "AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n" + json.dumps(
        {
            "task": {"object_key": "eskez-doma"},
            "site_scale": {"estimated_house_footprint_share_of_plot": 0.1},
            "questionnaire_constraints": [{"question": "Форма дома", "answer": "Г-образная"}],
        }
    )
    geometry = {
        "version": "local-tile.v1",
        "base_size": [100, 100],
        "box": [20, 20, 80, 80],
        "aspect_ratio": "1:1",
        "operation": "refine",
    }
    result = local_edit_prompt(
        prompt, geometry, {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}, []
    )
    spec = json.loads(result.split("STRUCTURED_SPEC:\n")[1])
    assert "Keep the entire plot in view" not in result
    assert "footprint_shape" not in spec["task"]
    assert spec["site_scale"]["ground_footprint_contract"]["target_share"] == 0.1


@pytest.mark.parametrize("operation", ["add", "refine", "remove"])
def test_geometry_preservation_does_not_forbid_creating_a_new_bath(operation):
    from app.services.edit_policy import build_edit_policy, build_object_removal_policy

    policy = (
        build_object_removal_policy("banya")
        if operation == "remove"
        else build_edit_policy(object_key="banya", edit_question_ids=[], review_comment="")
    ).to_dict()
    canonical_spec = {
        "task": {
            "object_key": "banya",
            "operation": "remove_object" if operation == "remove" else "render_or_refine",
        },
        "edit_policy": policy,
        "questionnaire_constraints": [{"question": "Какая печь?", "answer": "Дровяная, с трубой"}],
    }
    prompt = "AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n" + json.dumps(canonical_spec)
    geometry = {
        "version": "local-tile.v1",
        "base_size": [100, 100],
        "box": [20, 20, 80, 80],
        "aspect_ratio": "1:1",
        "operation": operation,
    }
    result = local_edit_prompt(
        prompt, geometry, {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}, []
    )
    spec = json.loads(result.split("STRUCTURED_SPEC:\n")[1])
    if operation == "add":
        assert spec["edit_policy"]["preserve_building_geometry"] is True
        assert spec["edit_policy"]["geometry_preservation_scope"] == "existing_scene_not_new_target"
        assert spec["edit_policy"]["new_target_creation_allowed"] is True
        assert "new roof chimney" in spec["edit_policy"]["new_target_directive"]
        assert spec["visual_acceptance_contract"]["required_roof_chimneys_on_objects"] == ["banya"]
    else:
        assert spec["edit_policy"] == policy
    assert json.loads(prompt.split("STRUCTURED_SPEC:\n")[1]) == canonical_spec


def test_new_house_keeps_requested_footprint_when_existing_scene_is_preserved():
    prompt = "AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n" + json.dumps(
        {
            "task": {"object_key": "eskez-doma", "operation": "render_or_refine"},
            "edit_policy": {"preserve_building_geometry": True},
            "questionnaire_constraints": [{"question": "Форма дома?", "answer": "Г-образная"}],
        }
    )
    geometry = {
        "version": "local-tile.v1",
        "base_size": [100, 100],
        "box": [20, 20, 80, 80],
        "aspect_ratio": "1:1",
        "operation": "add",
    }
    result = local_edit_prompt(
        prompt, geometry, {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}, []
    )
    spec = json.loads(result.split("STRUCTURED_SPEC:\n")[1])
    assert spec["task"]["footprint_shape"]["requested"] == "Г-образная"


@pytest.mark.parametrize("operation,object_key,site_preparation", [
    ("add", "banya", True), ("add", "eskez-doma", True),
    ("add", "gostevoy", True), ("add", "garazh", True),
    ("add", "naves", True), ("add", "letnyaya-kuhnya", True),
    ("add", "besedka", True), ("add", "hozblok", True),
    ("add", "teplica", True), ("add", "detskiy-domik", True),
    ("refine", "banya", False), ("remove", "banya", False),
    ("add", "izgorod", False), ("add", "gazon", False),
    ("add", "prud", False), ("add", "dorozhki", False),
    ("add", "basseyn", False), ("add", "unknown-object", False),
])
def test_only_new_buildings_may_replace_unprotected_vegetation_in_their_footprint(
    operation, object_key, site_preparation,
):
    original = {
        "task": {"object_key": object_key, "object_name": "Requested building"},
        "edit_policy": {"preserve_building_geometry": True},
        "questionnaire_constraints": [{"question": "Площадь?", "answer": "25 м²"}],
    }
    prompt = "AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n" + json.dumps(original)
    geometry = {
        "version": "local-tile.v1", "base_size": [100, 100],
        "box": [20, 20, 80, 80], "aspect_ratio": "1:1", "operation": operation,
    }
    region = {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}
    protected = [{"x": 0.3, "y": 0.3, "width": 0.1, "height": 0.1}]
    rendered = local_edit_prompt(prompt, geometry, region, protected)
    spec = json.loads(rendered.split("STRUCTURED_SPEC:\n", 1)[1])
    priority = rendered.split("STRUCTURED_SPEC:\n", 1)[0]
    policy = spec["edit_policy"]
    if site_preparation:
        preparation = policy["site_preparation"]
        assert preparation["scope"] == "new_building_footprint_within_allowed_region"
        assert preparation["protected_regions"] == "preserve_exactly"
        assert preparation["outside_edit_region"] == "preserve_exactly"
        assert "trees" in preparation["directive"]
        assert "Do not shrink" in preparation["directive"]
        assert "EXISTING BUILDINGS" in policy["new_target_directive"]
        assert "new roof chimney" in policy["new_target_directive"]
        assert policy["preserve_building_geometry"] is True
        assert "SAME CAMERA AND CROP" in priority
        assert "aerial" in priority
        assert "Requested building" in priority
        assert "25 м²" in priority
        assert "dark" not in priority and "metal" not in priority
    else:
        assert "site_preparation" not in policy
        assert "replace vegetation" not in rendered
        assert "SAME CAMERA AND CROP" not in priority
    assert spec["spatial_constraints"]["outside_edit_region"] == "preserve_exactly"
    assert spec["spatial_constraints"]["locked_regions"] == [local_region(protected[0], geometry)]
    assert json.loads(prompt.split("STRUCTURED_SPEC:\n", 1)[1]) == original


@pytest.mark.parametrize(
    "object_key",
    ["zabor", "izgorod", "vorota", "dorozhki", "gazon", "prud", "podsvetka", "podpornye"],
)
def test_linear_and_landscape_objects_keep_alignment_instead_of_being_centered(object_key):
    prompt = "AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n" + json.dumps(
        {"task": {"object_key": object_key}}
    )
    geometry = {
        "version": "local-tile.v1",
        "base_size": [100, 100],
        "box": [20, 20, 80, 80],
        "aspect_ratio": "1:1",
        "operation": "add",
    }
    result = local_edit_prompt(
        prompt, geometry, {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}, []
    )
    assert "CENTER an ADDED" not in result
    assert "Maintain continuity" in result


def test_one_clipped_side_cannot_average_away_in_other_locked_context():
    original = png(Image.new("RGB", (120, 120), (20, 30, 40)))
    region = {"x": 0.3, "y": 0.3, "width": 0.4, "height": 0.4}
    geometry = choose_local_geometry(
        original, {"x": 0.2, "y": 0.2, "width": 0.6, "height": 0.6}, max_pixels=20000
    )
    candidate = Image.new("RGB", (72, 72), (20, 30, 40))
    candidate.paste((100, 110, 120), (60, 12, 72, 60))
    with pytest.raises(ValueError, match="locked context"):
        project_local_candidate(
            original,
            png(candidate),
            geometry,
            max_pixels=20000,
            edit_region=region,
            max_context_color_error=32,
        )


def test_unchanged_protected_hole_and_context_pass_despite_adjacent_edit():
    base = Image.new("RGB", (120, 120), (20, 30, 40))
    original = png(base)
    region = {"x": 0.3, "y": 0.3, "width": 0.4, "height": 0.4}
    geometry = {
        "version": "local-tile.v1",
        "base_size": [120, 120],
        "box": [30, 30, 90, 90],
        "aspect_ratio": "1:1",
    }
    candidate = base.crop((30, 30, 90, 90))
    candidate.paste((220, 220, 220), (6, 6, 54, 54))
    # Cover ceil-rounded normalized coordinates too (62.000... becomes 63).
    candidate.paste((20, 30, 40), (28, 28, 33, 33))
    result = project_local_candidate(
        original,
        png(candidate),
        geometry,
        max_pixels=20000,
        edit_region=region,
        protected_regions=[{"x": 58 / 120, "y": 58 / 120, "width": 4 / 120, "height": 4 / 120}],
        max_context_color_error=32,
    )
    assert Image.open(BytesIO(result)).getpixel((59, 59)) == (20, 30, 40)


@pytest.mark.parametrize('operation', ['add', 'refine', 'remove'])
def test_new_bath_has_exterior_identity_and_room_for_shadow_without_altering_refinements(operation):
    prompt = 'AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n{"task":{"object_key":"banya"}}'
    geometry = {'version':'local-tile.v1', 'base_size':[120,100], 'box':[20,20,80,80],
                'aspect_ratio':'1:1', 'operation':operation}
    result = local_edit_prompt(prompt, geometry, {'x':.25,'y':.25,'width':.3,'height':.4}, [])
    if operation == 'add':
        assert 'complete cast shadow' in result
        assert 'recognizable exterior entrance' in result
        assert 'blank sealed box' in result
        assert 'occupy most of the selected width and height' not in result
    else:
        assert 'recognizable exterior entrance' not in result


@pytest.mark.parametrize("operation", ["add", "refine", "remove"])
def test_only_new_building_prioritizes_its_selected_roof_over_style_reference(operation):
    original = {
        "task": {"object_key": "banya", "object_name": "Баня"},
        "questionnaire_constraints": [
            {"question": "Стиль как у дома или свой?", "answer": "Шале"},
            {"question": "Какая кровля?", "answer": "Односкатная"},
            {"question": "Чем отделать фасад?", "answer": ["Бревно / брус"]},
        ],
    }
    prompt = "AUROOM_RENDER_SPEC_V1\nSTRUCTURED_SPEC:\n" + json.dumps(original)
    geometry = {
        "version": "local-tile.v1", "base_size": [100, 100],
        "box": [20, 20, 80, 80], "aspect_ratio": "1:1", "operation": operation,
        "house_style_reference": {"roof": "Ломаная мансардная", "style": "Средиземноморский"},
    }
    rendered = local_edit_prompt(prompt, geometry, {"x": .25, "y": .25, "width": .5, "height": .5}, [])
    priority = rendered.split("STRUCTURED_SPEC:\n", 1)[0]
    assert ("one sloping plane" in priority) is (operation == "add")
    assert ("take priority over architectural style" in priority) is (operation == "add")
    assert json.loads(prompt.split("STRUCTURED_SPEC:\n", 1)[1]) == original
