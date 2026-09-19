from io import BytesIO

from PIL import Image

from app.image_orbit import build_flyover_gif, build_orbit_animation


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



def test_build_flyover_gif_interpolates_between_keyframes_without_return_frame() -> None:
    data = build_flyover_gif(
        [_frame(0, size=(800, 450)), _frame(4, size=(800, 450))],
        duration_ms=90,
        inbetween_frames=2,
        max_pixels=20_000_000,
    )

    with Image.open(BytesIO(data)) as animation:
        assert animation.format == "GIF"
        assert animation.is_animated is True
        assert animation.n_frames == 4
        assert animation.size == (800, 450)
        assert animation.info["duration"] == 90

        animation.seek(0)
        first = animation.convert("RGB").getpixel((10, 10))
        animation.seek(animation.n_frames - 1)
        last = animation.convert("RGB").getpixel((10, 10))

        assert first == (40, 80, 120)
        assert last == (120, 120, 140)
        assert last != first


def test_build_flyover_gif_bounds_output_side_and_normalizes_keyframe_sizes() -> None:
    data = build_flyover_gif(
        [
            _frame(0, size=(1600, 900)),
            _frame(1, size=(1200, 800)),
            _frame(2, size=(1600, 900)),
        ],
        duration_ms=110,
        inbetween_frames=1,
        max_pixels=20_000_000,
        max_side=960,
    )

    with Image.open(BytesIO(data)) as animation:
        assert animation.format == "GIF"
        assert animation.n_frames == 5
        assert animation.size == (960, 540)


def test_build_flyover_gif_rejects_invalid_animation_settings() -> None:
    valid_frames = [_frame(0), _frame(1)]

    for kwargs in (
        {"duration_ms": 0, "inbetween_frames": 1},
        {"duration_ms": 90, "inbetween_frames": -1},
    ):
        try:
            build_flyover_gif(
                valid_frames,
                max_pixels=20_000_000,
                **kwargs,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for {kwargs}")
