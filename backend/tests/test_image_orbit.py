from io import BytesIO

from PIL import Image

from app.image_orbit import build_orbit_animation


def _frame(index: int, *, size: tuple[int, int] = (1600, 900)) -> bytes:
    image = Image.new(
        "RGB",
        size,
        (40 + index * 20, 80 + index * 10, 120 + index * 5),
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_build_orbit_animation_creates_looping_animated_webp() -> None:
    data = build_orbit_animation(
        [_frame(index) for index in range(6)],
        duration_ms=180,
        max_pixels=20_000_000,
    )

    with Image.open(BytesIO(data)) as animation:
        assert animation.format == "WEBP"
        assert animation.is_animated is True
        assert animation.n_frames == 6
        assert animation.size == (1280, 720)
        assert animation.info["loop"] == 0


def test_build_orbit_animation_normalizes_frame_size() -> None:
    data = build_orbit_animation(
        [
            _frame(0, size=(800, 600)),
            _frame(1, size=(1200, 800)),
        ],
        duration_ms=220,
        max_pixels=20_000_000,
    )

    with Image.open(BytesIO(data)) as animation:
        assert animation.n_frames == 2
        assert animation.size == (800, 600)
