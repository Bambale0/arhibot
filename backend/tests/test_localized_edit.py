from io import BytesIO
import json
import pytest
from PIL import Image
from app.image_compositor import compose_masked_edit
from app.localized_edit import (
    choose_local_geometry,
    local_source,
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
    assert spec["resolved_global_placement"]["answers"][0]["answer"] == "Справа от дома"
    assert "CENTER" in spec["visual_acceptance_contract"]["mask_directive"]


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
