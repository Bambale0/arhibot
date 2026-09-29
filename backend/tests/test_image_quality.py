from io import BytesIO

from PIL import Image, ImageDraw

from app.image_quality import analyze_masked_edit_quality


def _png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_quality_gate_rejects_rectangular_exposure_seam() -> None:
    base = Image.new("RGB", (120, 120), (100, 100, 100))
    final = base.copy()
    ImageDraw.Draw(final).rectangle((30, 30, 89, 89), fill=(180, 180, 180))

    report = analyze_masked_edit_quality(
        base_data=_png(base),
        final_data=_png(final),
        edit_region={"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5},
        boundary_band_px=4,
        max_luma_excess=20.0,
        max_straight_edge_fraction=0.65,
    )

    assert report.passed is False
    assert report.changed_outside_pixels == 0
    assert report.boundary_luma_excess > 20.0
    assert report.straight_edge_fraction >= 0.65


def test_quality_gate_rejects_any_pixel_change_outside_commit_region() -> None:
    base = Image.new("RGB", (80, 80), (20, 30, 40))
    final = base.copy()
    final.putpixel((2, 2), (21, 30, 40))

    report = analyze_masked_edit_quality(
        base_data=_png(base),
        final_data=_png(final),
        edit_region={"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5},
        boundary_band_px=3,
        max_luma_excess=30.0,
        max_straight_edge_fraction=0.8,
    )

    assert report.passed is False
    assert report.changed_outside_pixels == 1
    assert report.outside_integrity_passed is False


def test_quality_gate_accepts_unchanged_scene() -> None:
    base = Image.new("RGB", (64, 64), (90, 100, 110))

    report = analyze_masked_edit_quality(
        base_data=_png(base),
        final_data=_png(base),
        edit_region={"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5},
        boundary_band_px=3,
        max_luma_excess=10.0,
        max_straight_edge_fraction=0.7,
    )

    assert report.passed is True
    assert report.changed_outside_pixels == 0
    assert report.boundary_luma_excess == 0.0


def test_quality_gate_rejects_color_temperature_rectangle_with_similar_luma() -> None:
    base = Image.new("RGB", (100, 100), (100, 100, 100))
    final = base.copy()
    ImageDraw.Draw(final).rectangle((25, 25, 74, 74), fill=(130, 91, 100))

    report = analyze_masked_edit_quality(
        base_data=_png(base),
        final_data=_png(final),
        edit_region={"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5},
        boundary_band_px=3,
        max_luma_excess=10.0,
        max_color_excess=20.0,
        max_straight_edge_fraction=0.95,
    )

    assert report.passed is False
    assert report.boundary_luma_excess < 10.0
    assert report.boundary_color_excess > 20.0


def test_quality_gate_rejects_one_clipped_side_hidden_by_other_three() -> None:
    base = Image.new('RGB', (160, 120), (60, 80, 60))
    final = base.copy()
    ImageDraw.Draw(final).rectangle((90, 37, 119, 82), fill=(180, 180, 160))
    report = analyze_masked_edit_quality(
        base_data=_png(base), final_data=_png(final),
        edit_region={'x': .25, 'y': .25, 'width': .5, 'height': .5},
        boundary_band_px=3, max_luma_excess=35,
        max_color_excess=80, max_straight_edge_fraction=.65,
    )
    assert not report.passed, 'One cropped wall must not be averaged away by three good sides'


def test_short_clipped_shadow_cannot_be_diluted_by_rest_of_same_edge() -> None:
    base = Image.new('RGB', (400, 400), (100, 100, 100))
    final = base.copy()
    ImageDraw.Draw(final).rectangle((100, 180, 145, 229), fill=(45, 45, 45))
    report = analyze_masked_edit_quality(
        base_data=_png(base), final_data=_png(final),
        edit_region={'x': .25, 'y': .25, 'width': .5, 'height': .5},
        boundary_band_px=4, max_luma_excess=20,
        max_color_excess=32, max_straight_edge_fraction=.65,
    )
    assert report.changed_outside_pixels == 0
    assert not report.passed


def test_isolated_boundary_noise_and_existing_shadow_are_not_new_seams() -> None:
    base = Image.new('RGB', (400, 400), (100, 100, 100))
    ImageDraw.Draw(base).rectangle((100, 180, 145, 229), fill=(45, 45, 45))
    final = base.copy()
    final.putpixel((103, 150), (0, 0, 0))
    report = analyze_masked_edit_quality(
        base_data=_png(base), final_data=_png(final),
        edit_region={'x': .25, 'y': .25, 'width': .5, 'height': .5},
        boundary_band_px=4, max_luma_excess=20,
        max_color_excess=32, max_straight_edge_fraction=.65,
    )
    assert report.passed
