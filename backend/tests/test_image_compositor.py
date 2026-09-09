from io import BytesIO

from PIL import Image

from app.image_compositor import compose_masked_edit


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
