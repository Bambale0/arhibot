from io import BytesIO

import pytest
from PIL import Image

from app.image_flyover import build_flyover_gif


def _frame(color: tuple[int, int, int], *, size: tuple[int, int] = (1600, 900)) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_build_flyover_gif_adds_local_inbetween_frames_without_infinite_loop() -> None:
    result = build_flyover_gif(
        [
            _frame((180, 40, 40)),
            _frame((40, 180, 40), size=(1200, 800)),
            _frame((40, 40, 180)),
        ],
        inbetween_frames=2,
        duration_ms=120,
        max_pixels=80_000_000,
        max_side=960,
    )

    assert result.data.startswith(b"GIF8")
    assert result.frame_count == 7
    assert result.width <= 960
    assert result.height <= 960

    with Image.open(BytesIO(result.data)) as animation:
        assert animation.format == "GIF"
        assert animation.is_animated is True
        assert animation.n_frames == 7
        assert animation.info.get("duration") == 120
        assert "loop" not in animation.info


@pytest.mark.parametrize(
    ("frames", "inbetween_frames", "duration_ms", "message"),
    [
        ([_frame((1, 2, 3))], 2, 120, "at least two"),
        ([_frame((1, 2, 3)), b""], 2, 120, "empty"),
        ([_frame((1, 2, 3)), _frame((4, 5, 6))], -1, 120, "in-between"),
        ([_frame((1, 2, 3)), _frame((4, 5, 6))], 2, 0, "duration"),
    ],
)
def test_build_flyover_gif_rejects_invalid_inputs(
    frames: list[bytes],
    inbetween_frames: int,
    duration_ms: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build_flyover_gif(
            frames,
            inbetween_frames=inbetween_frames,
            duration_ms=duration_ms,
            max_pixels=80_000_000,
        )
