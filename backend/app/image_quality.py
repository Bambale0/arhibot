from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from io import BytesIO
from math import ceil, floor, sqrt

from PIL import Image, ImageOps


@dataclass(frozen=True, slots=True)
class MaskedEditQualityReport:
    passed: bool
    outside_integrity_passed: bool
    changed_outside_pixels: int
    boundary_luma_excess: float
    boundary_color_excess: float
    straight_edge_fraction: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _read_rgb(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data)) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def _rect_box(
    rect: Mapping[str, float],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    x = min(max(float(rect["x"]), 0.0), 1.0)
    y = min(max(float(rect["y"]), 0.0), 1.0)
    rect_width = min(max(float(rect["width"]), 0.0), 1.0 - x)
    rect_height = min(max(float(rect["height"]), 0.0), 1.0 - y)
    left = max(0, min(width - 1, floor(x * width)))
    top = max(0, min(height - 1, floor(y * height)))
    right = max(left + 1, min(width, ceil((x + rect_width) * width)))
    bottom = max(top + 1, min(height, ceil((y + rect_height) * height)))
    return left, top, right, bottom


def _changed_pixels(first: Image.Image, second: Image.Image) -> int:
    return sum(
        1
        for first_pixel, second_pixel in zip(first.getdata(), second.getdata(), strict=True)
        if first_pixel != second_pixel
    )


def _outside_change_count(
    base: Image.Image,
    final: Image.Image,
    box: tuple[int, int, int, int],
) -> int:
    left, top, right, bottom = box
    regions = (
        (0, 0, base.width, top),
        (0, bottom, base.width, base.height),
        (0, top, left, bottom),
        (right, top, base.width, bottom),
    )
    changed = 0
    for region in regions:
        if region[0] >= region[2] or region[1] >= region[3]:
            continue
        changed += _changed_pixels(base.crop(region), final.crop(region))
    return changed


def _luma(pixel: tuple[int, int, int]) -> float:
    red, green, blue = pixel
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _color_distance(
    first: tuple[int, int, int],
    second: tuple[int, int, int],
) -> float:
    return sqrt(sum((left - right) ** 2 for left, right in zip(first, second, strict=True)))


def _boundary_pairs(
    image: Image.Image,
    box: tuple[int, int, int, int],
    band_px: int,
) -> list[tuple[tuple[int, int, int], tuple[int, int, int]]]:
    left, top, right, bottom = box
    distance = max(1, band_px)
    pairs: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = []

    for y in range(top, bottom):
        if left > 0:
            outside_x = max(0, left - distance)
            inside_x = min(right - 1, left + distance - 1)
            pairs.append((image.getpixel((outside_x, y)), image.getpixel((inside_x, y))))
        if right < image.width:
            outside_x = min(image.width - 1, right + distance - 1)
            inside_x = max(left, right - distance)
            pairs.append((image.getpixel((outside_x, y)), image.getpixel((inside_x, y))))

    for x in range(left, right):
        if top > 0:
            outside_y = max(0, top - distance)
            inside_y = min(bottom - 1, top + distance - 1)
            pairs.append((image.getpixel((x, outside_y)), image.getpixel((x, inside_y))))
        if bottom < image.height:
            outside_y = min(image.height - 1, bottom + distance - 1)
            inside_y = max(top, bottom - distance)
            pairs.append((image.getpixel((x, outside_y)), image.getpixel((x, inside_y))))
    return pairs


def _boundary_metrics(
    base: Image.Image,
    final: Image.Image,
    box: tuple[int, int, int, int],
    band_px: int,
    max_luma_excess: float,
) -> tuple[float, float, float]:
    base_pairs = _boundary_pairs(base, box, band_px)
    final_pairs = _boundary_pairs(final, box, band_px)
    if not final_pairs:
        return 0.0, 0.0, 0.0

    excesses: list[float] = []
    color_excesses: list[float] = []
    straight_hits = 0
    straight_threshold = max(1.0, max_luma_excess * 0.5)
    for base_pair, final_pair in zip(base_pairs, final_pairs, strict=True):
        base_delta = abs(_luma(base_pair[0]) - _luma(base_pair[1]))
        final_delta = abs(_luma(final_pair[0]) - _luma(final_pair[1]))
        excess = max(0.0, final_delta - base_delta)
        excesses.append(excess)
        base_color = _color_distance(base_pair[0], base_pair[1])
        final_color = _color_distance(final_pair[0], final_pair[1])
        color_excesses.append(max(0.0, final_color - base_color))
        if excess > straight_threshold:
            straight_hits += 1

    mean_excess = sum(excesses) / len(excesses)
    mean_color_excess = sum(color_excesses) / len(color_excesses)
    straight_fraction = straight_hits / len(excesses)
    return mean_excess, mean_color_excess, straight_fraction


def analyze_masked_edit_quality(
    *,
    base_data: bytes,
    final_data: bytes,
    edit_region: Mapping[str, float],
    boundary_band_px: int,
    max_luma_excess: float,
    max_straight_edge_fraction: float,
    max_color_excess: float = 255.0,
) -> MaskedEditQualityReport:
    base = _read_rgb(base_data)
    final = _read_rgb(final_data)
    if final.size != base.size:
        return MaskedEditQualityReport(
            passed=False,
            outside_integrity_passed=False,
            changed_outside_pixels=base.width * base.height,
            boundary_luma_excess=float("inf"),
            boundary_color_excess=float("inf"),
            straight_edge_fraction=1.0,
        )

    box = _rect_box(edit_region, base.width, base.height)
    changed_outside = _outside_change_count(base, final, box)
    luma_excess, color_excess, straight_fraction = _boundary_metrics(
        base,
        final,
        box,
        max(1, int(boundary_band_px)),
        max_luma_excess,
    )
    outside_passed = changed_outside == 0
    boundary_passed = (
        luma_excess <= max_luma_excess
        and color_excess <= max_color_excess
        and straight_fraction <= max_straight_edge_fraction
    )
    return MaskedEditQualityReport(
        passed=outside_passed and boundary_passed,
        outside_integrity_passed=outside_passed,
        changed_outside_pixels=changed_outside,
        boundary_luma_excess=round(luma_excess, 4),
        boundary_color_excess=round(color_excess, 4),
        straight_edge_fraction=round(straight_fraction, 4),
    )
