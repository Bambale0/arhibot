from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

ORBIT_MAX_SIDE = 1280
ORBIT_WEBP_QUALITY = 82
FLYOVER_GIF_MAX_SIDE = 960


def build_orbit_animation(
    frame_bytes: list[bytes],
    *,
    duration_ms: int,
    max_pixels: int,
    max_side: int = ORBIT_MAX_SIDE,
) -> bytes:
    if len(frame_bytes) < 2:
        raise ValueError("Orbit animation requires at least two frames.")
    if duration_ms <= 0:
        raise ValueError("Orbit frame duration must be positive.")
    if max_side <= 0:
        raise ValueError("Orbit maximum side must be positive.")

    frames: list[Image.Image] = []
    target_size: tuple[int, int] | None = None
    try:
        for raw in frame_bytes:
            if not raw:
                raise ValueError("Orbit frame is empty.")
            try:
                with Image.open(BytesIO(raw)) as source:
                    width, height = source.size
                    if width <= 0 or height <= 0 or width * height > max_pixels:
                        raise ValueError("Orbit frame dimensions are not supported.")
                    frame = ImageOps.exif_transpose(source).convert("RGB")
            except (UnidentifiedImageError, OSError, SyntaxError) as exc:
                raise ValueError("Orbit frame is not a valid image.") from exc

            if target_size is None:
                frame.thumbnail(
                    (max_side, max_side),
                    Image.Resampling.LANCZOS,
                    reducing_gap=3.0,
                )
                target_size = frame.size
            elif frame.size != target_size:
                frame = ImageOps.fit(
                    frame,
                    target_size,
                    method=Image.Resampling.LANCZOS,
                )
            frames.append(frame)

        output = BytesIO()
        frames[0].save(
            output,
            format="WEBP",
            save_all=True,
            append_images=frames[1:],
            duration=duration_ms,
            loop=0,
            quality=ORBIT_WEBP_QUALITY,
            method=4,
        )
        return output.getvalue()
    finally:
        for frame in frames:
            frame.close()



def build_flyover_gif(
    frame_bytes: list[bytes],
    *,
    duration_ms: int,
    inbetween_frames: int,
    max_pixels: int,
    max_side: int = FLYOVER_GIF_MAX_SIDE,
) -> bytes:
    if len(frame_bytes) < 2:
        raise ValueError("Flyover animation requires at least two keyframes.")
    if duration_ms <= 0:
        raise ValueError("Flyover frame duration must be positive.")
    if inbetween_frames < 0:
        raise ValueError("Flyover in-between frame count must not be negative.")
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
                frame = ImageOps.fit(
                    frame,
                    target_size,
                    method=Image.Resampling.LANCZOS,
                )
            keyframes.append(frame)

        animation_frames.append(keyframes[0].copy())
        steps = inbetween_frames + 1
        for start, end in zip(keyframes, keyframes[1:], strict=False):
            for step in range(1, steps):
                animation_frames.append(Image.blend(start, end, step / steps))
            animation_frames.append(end.copy())

        output = BytesIO()
        animation_frames[0].save(
            output,
            format="GIF",
            save_all=True,
            append_images=animation_frames[1:],
            duration=duration_ms,
            loop=0,
            disposal=2,
        )
        return output.getvalue()
    finally:
        for frame in animation_frames:
            frame.close()
        for frame in keyframes:
            frame.close()
