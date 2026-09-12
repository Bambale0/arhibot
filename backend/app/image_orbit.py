from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

ORBIT_MAX_SIDE = 1280
ORBIT_WEBP_QUALITY = 82


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
