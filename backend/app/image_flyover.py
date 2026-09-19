from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

FLYOVER_GIF_MAX_SIDE = 960


@dataclass(frozen=True, slots=True)
class FlyoverGif:
    data: bytes
    width: int
    height: int
    frame_count: int


def build_flyover_gif(
    frame_bytes: list[bytes],
    *,
    inbetween_frames: int,
    duration_ms: int,
    max_pixels: int,
    max_side: int = FLYOVER_GIF_MAX_SIDE,
) -> FlyoverGif:
    if len(frame_bytes) < 2:
        raise ValueError("Flyover GIF requires at least two keyframes.")
    if inbetween_frames < 0:
        raise ValueError("Flyover in-between frame count must not be negative.")
    if duration_ms <= 0:
        raise ValueError("Flyover frame duration must be positive.")
    if max_side <= 0:
        raise ValueError("Flyover maximum side must be positive.")

    keyframes: list[Image.Image] = []
    animation_frames: list[Image.Image] = []
    target_size: tuple[int, int] | None = None
    try:
        for raw in frame_bytes:
            if not raw:
                raise ValueError("Flyover keyframe is empty.")
            try:
                with Image.open(BytesIO(raw)) as source:
                    width, height = source.size
                    if width <= 0 or height <= 0 or width * height > max_pixels:
                        raise ValueError("Flyover keyframe dimensions are not supported.")
                    frame = ImageOps.exif_transpose(source).convert("RGB")
            except (UnidentifiedImageError, OSError, SyntaxError) as exc:
                raise ValueError("Flyover keyframe is not a valid image.") from exc

            if target_size is None:
                frame.thumbnail(
                    (max_side, max_side),
                    Image.Resampling.LANCZOS,
                    reducing_gap=3.0,
                )
                target_size = frame.size
            elif frame.size != target_size:
                fitted = ImageOps.fit(
                    frame,
                    target_size,
                    method=Image.Resampling.LANCZOS,
                )
                frame.close()
                frame = fitted
            keyframes.append(frame)

        assert target_size is not None
        animation_frames.append(keyframes[0].copy())
        for previous, current in zip(keyframes, keyframes[1:], strict=False):
            for step in range(1, inbetween_frames + 1):
                alpha = step / (inbetween_frames + 1)
                animation_frames.append(Image.blend(previous, current, alpha))
            animation_frames.append(current.copy())

        output = BytesIO()
        animation_frames[0].save(
            output,
            format="GIF",
            save_all=True,
            append_images=animation_frames[1:],
            duration=duration_ms,
            disposal=2,
            optimize=False,
        )
        return FlyoverGif(
            data=output.getvalue(),
            width=target_size[0],
            height=target_size[1],
            frame_count=len(animation_frames),
        )
    finally:
        for frame in animation_frames:
            frame.close()
        for frame in keyframes:
            frame.close()
