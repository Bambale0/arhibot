"""Telegram user result preview is JPEG-sized; the original stays lossless."""
from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app.telegram_bot.generation_notifications import (
    LIGHT_PREVIEW_MAX_BYTES,
    LIGHT_PREVIEW_MAX_SIDE,
    build_light_generation_preview,
)


def _complex_png(size: tuple[int, int] = (2400, 1400)) -> bytes:
    image = Image.new("RGB", size, "gray")
    draw = ImageDraw.Draw(image)
    for offset in range(0, size[0], 18):
        draw.rectangle(
            (offset, 0, offset + 9, size[1] - 1),
            fill=(offset % 255, (offset * 3) % 255, (offset * 5) % 255),
        )
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


@pytest.mark.parametrize("size", [(2400, 1400), (600, 1800), (1500, 1500)])
def test_generation_preview_is_small_true_jpeg_with_original_unchanged(tmp_path, size):
    original = _complex_png(size)
    source = tmp_path / "generation.png"
    source.write_bytes(original)
    preview = build_light_generation_preview(source)
    assert preview.startswith(b"\\xff\\xd8")
    assert 0 < len(preview) <= LIGHT_PREVIEW_MAX_BYTES
    with Image.open(BytesIO(preview)) as im:
        assert im.format == "JPEG"
        assert max(im.size) <= LIGHT_PREVIEW_MAX_SIDE
        assert im.width / im.height == pytest.approx(size[0] / size[1], rel=0.04)
    assert source.read_bytes() == original


def test_transparent_png_preview_is_white_not_black(tmp_path):
    source = tmp_path / "transparent.png"
    rgba = Image.new("RGBA", (400, 200), (255, 0, 0, 0))
    rgba.save(source, "PNG")
    preview = build_light_generation_preview(source)
    with Image.open(BytesIO(preview)) as image:
        r, g, b = image.convert("RGB").getpixel((50, 50))
    assert min(r, g, b) >= 245


def test_generation_preview_invalid_image_raises_for_original_fallback(tmp_path):
    source = tmp_path / "corrupt.png"
    source.write_bytes(b"not a real png")
    with pytest.raises(ValueError, match="preview"):
        build_light_generation_preview(source)


def test_high_entropy_render_stays_under_telegram_preview_budget(tmp_path):
    from random import Random

    size = (1600, 1200)
    noisy = Image.frombytes("RGB", size, Random(17).randbytes(size[0] * size[1] * 3))
    source = tmp_path / "large-random-render.png"
    noisy.save(source, "PNG")
    preview = build_light_generation_preview(source)
    assert len(preview) <= LIGHT_PREVIEW_MAX_BYTES
    with Image.open(BytesIO(preview)) as image:
        assert image.format == "JPEG"
        assert max(image.size) <= LIGHT_PREVIEW_MAX_SIDE


def test_extreme_panorama_is_padded_for_telegram_photo_rules(tmp_path):
    source = tmp_path / "panorama.png"
    Image.new("RGB", (4000, 100), "cyan").save(source, "PNG")
    preview = build_light_generation_preview(source)
    with Image.open(BytesIO(preview)) as image:
        width, height = image.size
        assert max(width / height, height / width) <= 20
        assert max(image.size) <= LIGHT_PREVIEW_MAX_SIDE
