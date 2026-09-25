from io import BytesIO

from PIL import Image

from app.image_compositor import (
    build_edit_reference_guide,
    compose_masked_edit,
    expand_normalized_region,
)


def _png(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _pixels(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data)).convert("RGB")


def test_masked_edit_preserves_every_pixel_outside_edit_region() -> None:
    result = compose_masked_edit(
        base_data=_png((100, 80), (10, 20, 30)),
        candidate_data=_png((100, 80), (220, 210, 200)),
        edit_region={"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5},
        feather_px=0,
    )
    output = _pixels(result.data)

    assert output.getpixel((5, 5)) == (10, 20, 30)
    assert output.getpixel((95, 75)) == (10, 20, 30)
    assert output.getpixel((50, 40)) == (220, 210, 200)


def test_protected_region_wins_even_when_it_overlaps_edit_region() -> None:
    result = compose_masked_edit(
        base_data=_png((100, 100), (1, 2, 3)),
        candidate_data=_png((100, 100), (250, 240, 230)),
        edit_region={"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
        protected_regions=[{"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2}],
        feather_px=0,
    )
    output = _pixels(result.data)

    assert output.getpixel((20, 20)) == (250, 240, 230)
    assert output.getpixel((50, 50)) == (1, 2, 3)
    assert output.getpixel((95, 95)) == (1, 2, 3)


def test_masked_edit_resizes_candidate_but_keeps_base_dimensions() -> None:
    result = compose_masked_edit(
        base_data=_png((120, 90), (9, 8, 7)),
        candidate_data=_png((60, 45), (100, 110, 120)),
        edit_region={"x": 0.0, "y": 0.0, "width": 0.25, "height": 0.25},
        feather_px=0,
    )
    output = _pixels(result.data)
    assert output.size == (120, 90)
    assert output.getpixel((5, 5)) == (100, 110, 120)
    assert output.getpixel((100, 80)) == (9, 8, 7)


def test_masked_edit_rejects_image_over_pixel_limit_before_compositing() -> None:
    try:
        compose_masked_edit(
            base_data=_png((100, 100), (1, 2, 3)),
            candidate_data=_png((100, 100), (4, 5, 6)),
            edit_region={"x": 0.1, "y": 0.1, "width": 0.4, "height": 0.4},
            max_pixels=9_999,
        )
    except ValueError as exc:
        assert "pixel limit" in str(exc)
    else:
        raise AssertionError("Expected compositor to enforce max_pixels")


def test_edit_reference_guide_marks_only_editable_pixels_white() -> None:
    guide = build_edit_reference_guide(
        base_data=_png((100, 100), (10, 20, 30)),
        edit_region={"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
        protected_regions=[{"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2}],
    )
    image = _pixels(guide)

    assert image.size == (100, 100)
    assert image.getpixel((5, 5)) == (0, 0, 0)
    assert image.getpixel((20, 20)) == (255, 255, 255)
    assert image.getpixel((50, 50)) == (0, 0, 0)


def test_masked_edit_default_feather_blends_a_wide_inward_boundary() -> None:
    result = compose_masked_edit(
        base_data=_png((500, 500), (0, 0, 0)),
        candidate_data=_png((500, 500), (255, 255, 255)),
        edit_region={"x": 0.2, "y": 0.2, "width": 0.6, "height": 0.6},
    )
    output = _pixels(result.data)

    assert output.getpixel((99, 250)) == (0, 0, 0)
    assert output.getpixel((106, 250))[0] < 240
    assert output.getpixel((250, 250)) == (255, 255, 255)


def test_provider_work_region_expands_without_mutating_commit_region() -> None:
    commit = {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2}

    work = expand_normalized_region(commit, margin_fraction=0.03)

    assert work == {
        "x": 0.37,
        "y": 0.37,
        "width": 0.26,
        "height": 0.26,
    }
    assert commit == {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2}


def test_provider_work_region_clamps_at_image_edges() -> None:
    work = expand_normalized_region(
        {"x": 0.01, "y": 0.02, "width": 0.25, "height": 0.3},
        margin_fraction=0.05,
    )

    assert work == {
        "x": 0.0,
        "y": 0.0,
        "width": 0.31,
        "height": 0.37,
    }


def test_runtime_feather_can_exceed_old_explicit_cap() -> None:
    result = compose_masked_edit(
        base_data=_png((200, 200), (0, 0, 0)),
        candidate_data=_png((200, 200), (255, 255, 255)),
        edit_region={"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
        feather_px=20,
        feather_max_px=24,
    )
    output = _pixels(result.data)

    assert output.getpixel((20, 100))[0] < 80
    assert output.getpixel((35, 100))[0] > 100
    assert output.getpixel((100, 100)) == (255, 255, 255)
