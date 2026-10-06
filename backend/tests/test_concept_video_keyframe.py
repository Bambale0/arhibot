from io import BytesIO

from PIL import Image, ImageDraw

from app.concept_video_keyframe import build_locked_video_end_frame


def _grid(width: int = 320, height: int = 180) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for x in range(0, width, 20):
        draw.line((x, 0, x, height), fill=(x % 255, 40, 80), width=2)
    for y in range(0, height, 20):
        draw.line((0, y, width, y), fill=(20, y % 255, 160), width=2)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_locked_video_keyframe_is_deterministic_pixel_transform() -> None:
    source = _grid()
    first = build_locked_video_end_frame(source, max_pixels=1_000_000)
    second = build_locked_video_end_frame(source, max_pixels=1_000_000)

    assert first.data == second.data
    assert (first.width, first.height) == (320, 180)
    assert first.crop_box == second.crop_box
    left, top, right, bottom = first.crop_box
    assert 0 <= left < right <= 320
    assert 0 <= top < bottom <= 180
    assert right - left < 320
    assert bottom - top < 180
    assert first.transform == "locked_bird_anchor_v1"


def test_locked_video_keyframe_does_not_invent_new_canvas_area() -> None:
    source = _grid(160, 90)
    result = build_locked_video_end_frame(source, max_pixels=1_000_000)

    image = Image.open(BytesIO(result.data))
    assert image.size == (160, 90)
    assert image.mode == "RGB"
    # The end frame is made only by cropping inside the accepted image and
    # resizing that crop back to the original canvas.
    left, top, right, bottom = result.crop_box
    assert left >= 0 and top >= 0
    assert right <= 160 and bottom <= 90


def test_locked_video_keyframe_rejects_oversized_input() -> None:
    source = _grid(200, 100)

    try:
        build_locked_video_end_frame(source, max_pixels=10_000)
    except ValueError as exc:
        assert "pixel" in str(exc).lower()
    else:
        raise AssertionError("expected max-pixel guard")
