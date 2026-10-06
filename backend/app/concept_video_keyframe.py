from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


@dataclass(frozen=True, slots=True)
class LockedVideoKeyframe:
    data: bytes
    width: int
    height: int
    crop_box: tuple[int, int, int, int]
    transform: str = "locked_bird_anchor_v1"


def build_locked_video_end_frame(
    source: bytes,
    *,
    max_pixels: int,
    zoom: float = 1.09,
    pan_x: float = 0.62,
    pan_y: float = -0.72,
) -> LockedVideoKeyframe:
    """Create a deterministic framing anchor for a bounded bird flyover.

    No new scene content is synthesized. The function crops entirely inside
    the accepted image and resizes that crop back to the original canvas.
    The stronger upward/lateral framing cue encourages camera rise and parallax
    while every pixel still comes from the accepted concept.
    Positive pan_x moves the framing to the right; negative pan_y moves it upward.
    """

    if not 1.0 < zoom <= 1.15:
        raise ValueError("Locked video zoom must be between 1.0 and 1.15")
    if not -1.0 <= pan_x <= 1.0 or not -1.0 <= pan_y <= 1.0:
        raise ValueError("Locked video pan values must be between -1 and 1")

    try:
        with Image.open(BytesIO(source)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Locked video source image is invalid") from exc

    width, height = image.size
    if width <= 0 or height <= 0 or width * height > max_pixels:
        raise ValueError("Locked video source exceeds configured pixel limit")

    crop_width = max(2, min(width, round(width / zoom)))
    crop_height = max(2, min(height, round(height / zoom)))

    margin_x = width - crop_width
    margin_y = height - crop_height

    left = round((margin_x / 2) * (1 + pan_x))
    top = round((margin_y / 2) * (1 + pan_y))
    left = max(0, min(left, margin_x))
    top = max(0, min(top, margin_y))
    right = left + crop_width
    bottom = top + crop_height

    transformed = image.crop((left, top, right, bottom)).resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )

    buffer = BytesIO()
    transformed.save(buffer, format="PNG", optimize=True)
    return LockedVideoKeyframe(
        data=buffer.getvalue(),
        width=width,
        height=height,
        crop_box=(left, top, right, bottom),
    )
