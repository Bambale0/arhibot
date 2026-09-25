from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from math import ceil, floor

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


DEFAULT_FEATHER_FRACTION = 0.015
DEFAULT_FEATHER_MIN_PX = 6
DEFAULT_FEATHER_MAX_PX = 24
EXPLICIT_FEATHER_MAX_PX = 32


@dataclass(frozen=True, slots=True)
class MaskedCompositeResult:
    data: bytes
    width: int
    height: int


def _read_rgb(data: bytes, *, max_pixels: int | None = None) -> Image.Image:
    with Image.open(BytesIO(data)) as image:
        width, height = image.size
        if max_pixels is not None and (width <= 0 or height <= 0 or width * height > max_pixels):
            raise ValueError("Composite image dimensions exceed the configured pixel limit")
        return ImageOps.exif_transpose(image).convert("RGB")


def _rect_box(rect: Mapping[str, float], width: int, height: int) -> tuple[int, int, int, int]:
    x = min(max(float(rect["x"]), 0.0), 1.0)
    y = min(max(float(rect["y"]), 0.0), 1.0)
    rect_width = min(max(float(rect["width"]), 0.0), 1.0 - x)
    rect_height = min(max(float(rect["height"]), 0.0), 1.0 - y)
    left = max(0, min(width - 1, floor(x * width)))
    top = max(0, min(height - 1, floor(y * height)))
    right = max(left + 1, min(width, ceil((x + rect_width) * width)))
    bottom = max(top + 1, min(height, ceil((y + rect_height) * height)))
    return left, top, right, bottom


def _region_mask(
    size: tuple[int, int],
    edit_region: Mapping[str, float],
    protected_regions: Sequence[Mapping[str, float]],
    *,
    feather_px: int,
) -> Image.Image:
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    left, top, right, bottom = _rect_box(edit_region, width, height)
    draw.rectangle((left, top, right - 1, bottom - 1), fill=255)

    if protected_regions:
        protected = Image.new("L", size, 0)
        protected_draw = ImageDraw.Draw(protected)
        for region in protected_regions:
            p_left, p_top, p_right, p_bottom = _rect_box(region, width, height)
            protected_draw.rectangle((p_left, p_top, p_right - 1, p_bottom - 1), fill=255)
        mask = ImageChops.subtract(mask, protected)

    # Feather only inward. Multiplying by the original binary mask guarantees
    # that every pixel outside the allowed edit region remains exactly zero.
    if feather_px > 0:
        blurred = mask.filter(ImageFilter.GaussianBlur(radius=feather_px))
        mask = ImageChops.multiply(mask, blurred)
    return mask


def build_edit_reference_guide(
    *,
    base_data: bytes,
    edit_region: Mapping[str, float],
    protected_regions: Sequence[Mapping[str, float]] = (),
    max_pixels: int | None = None,
) -> bytes:
    """Build a pixel-aligned provider guide for a masked edit.

    White pixels are editable; black pixels are locked. Protected regions always
    remain black even when they overlap the selected edit rectangle.
    """

    base = _read_rgb(base_data, max_pixels=max_pixels)
    mask = _region_mask(
        base.size,
        edit_region,
        protected_regions,
        feather_px=0,
    )
    guide = Image.merge("RGB", (mask, mask, mask))
    buffer = BytesIO()
    guide.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _default_feather_px(size: tuple[int, int]) -> int:
    shortest = max(1, min(size))
    return max(
        DEFAULT_FEATHER_MIN_PX,
        min(DEFAULT_FEATHER_MAX_PX, round(shortest * DEFAULT_FEATHER_FRACTION)),
    )


def compose_masked_edit(
    *,
    base_data: bytes,
    candidate_data: bytes,
    edit_region: Mapping[str, float],
    protected_regions: Sequence[Mapping[str, float]] = (),
    feather_px: int | None = None,
    max_pixels: int | None = None,
) -> MaskedCompositeResult:
    """Composite an AI candidate into a previous accepted scene.

    Outside ``edit_region`` and inside every protected region, output pixels are
    copied from ``base_data``. The result is encoded as lossless PNG so those
    pixels remain stable after persistence and in every later generation step.
    """

    base = _read_rgb(base_data, max_pixels=max_pixels)
    candidate = _read_rgb(candidate_data, max_pixels=max_pixels)
    if candidate.size != base.size:
        candidate = candidate.resize(base.size, Image.Resampling.LANCZOS)

    effective_feather_px = (
        _default_feather_px(base.size)
        if feather_px is None
        else max(0, min(int(feather_px), EXPLICIT_FEATHER_MAX_PX))
    )
    mask = _region_mask(
        base.size,
        edit_region,
        protected_regions,
        feather_px=effective_feather_px,
    )
    output = Image.composite(candidate, base, mask)
    buffer = BytesIO()
    output.save(buffer, format="PNG", optimize=True)
    return MaskedCompositeResult(data=buffer.getvalue(), width=base.width, height=base.height)
