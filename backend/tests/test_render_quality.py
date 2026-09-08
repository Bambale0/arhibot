from io import BytesIO

from PIL import Image, ImageDraw

from app.renderers.quality import score_render_quality


def _png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_quality_rejects_nearly_black_render() -> None:
    result = score_render_quality(_png(Image.new("RGB", (128, 96), (2, 2, 2))))

    assert result.report["technically_usable"] is False
    assert result.report["black_clip_ratio"] > 0.9


def test_quality_accepts_detailed_balanced_render() -> None:
    image = Image.new("RGB", (128, 96), (130, 135, 140))
    draw = ImageDraw.Draw(image)
    for x in range(0, 128, 8):
        draw.rectangle((x, 0, min(x + 3, 127), 95), fill=(70, 75, 80))
    for y in range(0, 96, 8):
        draw.line((0, y, 127, y), fill=(205, 210, 215), width=2)

    result = score_render_quality(_png(image))

    assert result.report["technically_usable"] is True
    assert result.score > 0.45
