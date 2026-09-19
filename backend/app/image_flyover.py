from __future__ import annotations

from dataclasses import dataclass


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
    max_side: int = 960,
) -> FlyoverGif:
    raise NotImplementedError("Bird flyover GIF assembler is not implemented.")
