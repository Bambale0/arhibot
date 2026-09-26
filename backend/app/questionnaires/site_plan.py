from __future__ import annotations

from collections.abc import Sequence
from math import sqrt
from typing import Any

from app.schemas.questionnaires import DesignSession


_RELATION_ORDER = (
    "right_of_house",
    "left_of_house",
    "behind_house",
    "front_of_house",
    "entry_zone",
    "plot_center",
)

_RELATION_MARKERS: dict[str, tuple[str, ...]] = {
    "right_of_house": ("справа", "правее"),
    "left_of_house": ("слева", "левее"),
    "behind_house": ("сзади", "за дом", "во дворе", "в глубине", "задн"),
    "front_of_house": ("перед дом", "перед фасад", "у фасад"),
    "entry_zone": ("въезд", "улиц", "ворот"),
    "plot_center": ("центр участка", "по центру"),
}

_LARGE_RECREATION_MARKERS = ("бассейн", "пруд", "купель")
_SECONDARY_BUILDING_MARKERS = (
    "гараж",
    "навес",
    "баня",
    "гостевой",
    "теплица",
    "хозблок",
    "летняя кухня",
    "беседка",
    "домик",
)
_SMALL_OBJECT_MARKERS = ("лавоч", "качел", "батут", "обеденн")


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _round(value: float) -> float:
    return round(float(value), 4)


def _rect(
    *,
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    margin: float = 0.04,
) -> dict[str, float]:
    width = _clamp(width, 0.04, 1 - margin * 2)
    height = _clamp(height, 0.04, 1 - margin * 2)
    x = _clamp(center_x - width / 2, margin, 1 - margin - width)
    y = _clamp(center_y - height / 2, margin, 1 - margin - height)
    return {
        "x": _round(x),
        "y": _round(y),
        "width": _round(width),
        "height": _round(height),
    }


def _center(rect: dict[str, float]) -> tuple[float, float]:
    return (
        rect["x"] + rect["width"] / 2,
        rect["y"] + rect["height"] / 2,
    )


def _overlaps(left: dict[str, float], right: dict[str, float], *, gap: float = 0.012) -> bool:
    return not (
        left["x"] + left["width"] + gap <= right["x"]
        or right["x"] + right["width"] + gap <= left["x"]
        or left["y"] + left["height"] + gap <= right["y"]
        or right["y"] + right["height"] + gap <= left["y"]
    )


def _answer_text(value: object) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value).lower()
    return str(value or "").lower()


def _relations(constraints: object) -> list[str]:
    if not isinstance(constraints, list):
        return []
    matched: set[str] = set()
    for constraint in constraints:
        if not isinstance(constraint, dict):
            continue
        haystack = (
            str(constraint.get("question", "")).lower()
            + " "
            + _answer_text(constraint.get("answer"))
        )
        for relation, markers in _RELATION_MARKERS.items():
            if any(marker in haystack for marker in markers):
                matched.add(relation)
    return [relation for relation in _RELATION_ORDER if relation in matched]


def _zone(relations: Sequence[str]) -> str:
    values = set(relations)
    if "entry_zone" in values and "right_of_house" in values:
        return "entry_right"
    if "entry_zone" in values and "left_of_house" in values:
        return "entry_left"
    if "behind_house" in values and "right_of_house" in values:
        return "backyard_right"
    if "behind_house" in values and "left_of_house" in values:
        return "backyard_left"
    if "behind_house" in values:
        return "backyard"
    if "front_of_house" in values:
        return "front_yard"
    if "entry_zone" in values:
        return "entry_zone"
    if "right_of_house" in values:
        return "right_side"
    if "left_of_house" in values:
        return "left_side"
    if "plot_center" in values:
        return "plot_center"
    return "auto"


def _house_rect(site_scale: dict[str, object]) -> dict[str, float]:
    share = site_scale.get("estimated_house_footprint_share_of_plot")
    if isinstance(share, (int, float)) and not isinstance(share, bool) and share > 0:
        area_share = _clamp(float(share), 0.045, 0.30)
        aspect = 1.5
        width = _clamp(sqrt(area_share * aspect), 0.30, 0.55)
        height = _clamp(area_share / width, 0.20, 0.40)
    else:
        width, height = 0.38, 0.26
    return _rect(center_x=0.5, center_y=0.40, width=width, height=height)


def _object_size(object_name: str) -> tuple[float, float]:
    normalized = object_name.lower()
    if any(marker in normalized for marker in _LARGE_RECREATION_MARKERS):
        return 0.28, 0.15
    if any(marker in normalized for marker in _SECONDARY_BUILDING_MARKERS):
        return 0.22, 0.16
    if any(marker in normalized for marker in _SMALL_OBJECT_MARKERS):
        return 0.12, 0.08
    return 0.16, 0.11


def _target_center(
    relations: Sequence[str],
    *,
    house_rect: dict[str, float] | None,
    width: float,
    height: float,
) -> tuple[float, float]:
    values = set(relations)
    center_x, center_y = 0.5, 0.70 if house_rect is not None else 0.5
    if "plot_center" in values:
        center_x, center_y = 0.5, 0.5

    if house_rect is not None:
        house_center_x, house_center_y = _center(house_rect)
        house_right = house_rect["x"] + house_rect["width"]
        house_bottom = house_rect["y"] + house_rect["height"]
        if "right_of_house" in values:
            center_x = max(0.77, house_right + 0.035 + width / 2)
        elif "left_of_house" in values:
            center_x = min(0.23, house_rect["x"] - 0.035 - width / 2)
        else:
            center_x = house_center_x

        if "behind_house" in values:
            center_y = max(0.72, house_bottom + 0.04 + height / 2)
        elif "front_of_house" in values:
            center_y = min(0.16, house_rect["y"] - 0.04 - height / 2)
        elif "entry_zone" in values:
            center_y = min(0.13, house_rect["y"] - 0.04 - height / 2)
        elif "right_of_house" in values or "left_of_house" in values:
            center_y = house_center_y
    else:
        if "right_of_house" in values:
            center_x = 0.76
        elif "left_of_house" in values:
            center_x = 0.24
        if "behind_house" in values:
            center_y = 0.76
        elif "front_of_house" in values or "entry_zone" in values:
            center_y = 0.16

    return center_x, center_y


def _relation_ok(
    rect: dict[str, float],
    relations: Sequence[str],
    house_rect: dict[str, float] | None,
) -> bool:
    if house_rect is None:
        return True
    values = set(relations)
    center_x, center_y = _center(rect)
    house_center_x, house_center_y = _center(house_rect)
    house_right = house_rect["x"] + house_rect["width"]
    house_bottom = house_rect["y"] + house_rect["height"]

    if "right_of_house" in values and center_x <= house_right:
        return False
    if "left_of_house" in values and center_x >= house_rect["x"]:
        return False
    if "behind_house" in values and center_y <= house_bottom:
        return False
    if "front_of_house" in values and center_y >= house_rect["y"]:
        return False
    if "entry_zone" in values and center_y >= house_center_y:
        return False
    if "plot_center" in values and (abs(center_x - 0.5) > 0.25 or abs(center_y - 0.5) > 0.25):
        return False
    return True


def _place_rect(
    *,
    target_x: float,
    target_y: float,
    width: float,
    height: float,
    relations: Sequence[str],
    house_rect: dict[str, float] | None,
    occupied: Sequence[dict[str, float]],
) -> tuple[dict[str, float], bool]:
    offsets = (
        (0.0, 0.0),
        (0.0, 0.08),
        (0.0, -0.08),
        (0.08, 0.0),
        (-0.08, 0.0),
        (0.08, 0.08),
        (-0.08, 0.08),
        (0.08, -0.08),
        (-0.08, -0.08),
        (0.0, 0.16),
        (0.16, 0.0),
        (-0.16, 0.0),
    )
    fallback = _rect(
        center_x=target_x,
        center_y=target_y,
        width=width,
        height=height,
    )
    for dx, dy in offsets:
        candidate = _rect(
            center_x=target_x + dx,
            center_y=target_y + dy,
            width=width,
            height=height,
        )
        if not _relation_ok(candidate, relations, house_rect):
            continue
        if any(_overlaps(candidate, item) for item in occupied):
            continue
        return candidate, False
    return fallback, any(_overlaps(fallback, item) for item in occupied)


def build_site_plan(
    *,
    objects: Sequence[dict[str, object]],
    session: DesignSession,
    site_scale: dict[str, object],
) -> dict[str, object]:
    """Build a deterministic relative site topology for the initial concept.

    Coordinates are normalized to the plot rather than pretending that plot area alone
    provides exact side lengths. The resulting rectangles are semantic placement zones,
    not survey-grade building footprints.
    """

    plot_sotkas = session.plot_area_sotkas
    plot_m2 = plot_sotkas * 100 if plot_sotkas is not None else None
    warnings: list[dict[str, str]] = []
    planned: list[dict[str, object]] = []
    occupied: list[dict[str, float]] = []

    house_source = next(
        (item for item in objects if item.get("object_key") == "eskez-doma"),
        None,
    )
    house_rect = _house_rect(site_scale) if house_source is not None else None
    if house_source is not None and house_rect is not None:
        planned.append(
            {
                "object_key": "eskez-doma",
                "object_name": house_source.get("object_name"),
                "role": "house",
                "zone": "center_front",
                "relations": [],
                "rect": house_rect,
                "placement_source": "derived",
                "estimated_footprint_m2": site_scale.get("estimated_house_footprint_m2"),
            }
        )
        occupied.append(house_rect)

    for item in objects:
        object_key = str(item.get("object_key") or "")
        if not object_key or object_key == "eskez-doma":
            continue
        object_name = str(item.get("object_name") or object_key)
        relations = _relations(item.get("questionnaire_constraints"))
        width, height = _object_size(object_name)
        if house_rect is None and any(
            relation in {"left_of_house", "right_of_house", "behind_house", "front_of_house"}
            for relation in relations
        ):
            warnings.append(
                {
                    "object_key": object_key,
                    "code": "house_relative_constraint_without_house",
                }
            )
        target_x, target_y = _target_center(
            relations,
            house_rect=house_rect,
            width=width,
            height=height,
        )
        rect, overlap_unresolved = _place_rect(
            target_x=target_x,
            target_y=target_y,
            width=width,
            height=height,
            relations=relations,
            house_rect=house_rect,
            occupied=occupied,
        )
        if overlap_unresolved:
            warnings.append(
                {
                    "object_key": object_key,
                    "code": "placement_overlap_unresolved",
                }
            )
        planned.append(
            {
                "object_key": object_key,
                "object_name": object_name,
                "role": "site_object",
                "zone": _zone(relations),
                "relations": relations,
                "rect": rect,
                "placement_source": "questionnaire" if relations else "derived",
            }
        )
        occupied.append(rect)

    return {
        "schema": "auroom.site_plan.v1",
        "plot": {
            "area_sotkas": plot_sotkas,
            "area_m2": plot_m2,
            "coordinate_system": "normalized",
            "front_side": "y0",
            "geometry_accuracy": "relative",
        },
        "objects": planned,
        "warnings": warnings,
    }
