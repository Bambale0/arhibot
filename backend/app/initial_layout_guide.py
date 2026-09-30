"""Conservative provider-only layout references for supported synthetic whole-site briefs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from json import JSONDecoder
from math import isclose, isfinite, pi, sqrt

from PIL import Image, ImageDraw

from app.prompt_builders.visual_fidelity import build_visual_fidelity_prompt

GRASS = (112, 149, 79)
OUTSIDE = (133, 158, 108)
HOUSE = (193, 169, 135)
POOL = (57, 145, 186)\nPOOL_COVER = (210, 154, 68)
HEDGE = (48, 93, 49)
FENCE = (125, 124, 114)


def polygon_area(points):
    return (
        abs(
            sum(
                x * points[(i + 1) % len(points)][1] - y * points[(i + 1) % len(points)][0]
                for i, (x, y) in enumerate(points)
            )
        )
        / 2
    )


def _positive(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1e9:
        raise ValueError("Explicit positive numeric geometry required")
    return float(value)


def _inside(rect):
    raw = [rect[key] for key in ("x", "y", "width", "height")]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in raw):
        raise ValueError("Finite numeric rectangle required")
    x, y, w, h = map(float, raw)
    if not (0 <= x < x + w <= 1 and 0 <= y < y + h <= 1):
        raise ValueError("Layout extends beyond the conceptual plot")
    return x, y, w, h


def _geometry_from_spec(spec: dict) -> dict:
    if (
        spec.get("schema") != "auroom.initial_concept.v1"
        or spec.get("source_scene", {}).get("kind") != "synthetic_site"
    ):
        raise ValueError("A layout reference must never override a site photograph")
    if spec.get("camera", {}).get("mode") != "whole_site_aerial":
        raise ValueError("Whole-site camera required")
    objects = spec["task"]["objects"]
    if any(
        item["object_key"] not in {"eskez-doma", "basseyn", "izgorod", "zabor", "gazon"}
        for item in objects
    ):
        raise ValueError("Unsupported object in layout reference")
    keys = [item["object_key"] for item in objects]
    if len(keys) != len(set(keys)) or "eskez-doma" not in keys:
        raise ValueError("Unique objects and one house required")
    for item in objects:
        key = item["object_key"]
        if key == "gazon" and (
            _answer(item, "Какой характер") != "Минимализм, газон и гравий"
            or _answer(item, "Что видно") != ["Газон"]
        ):
            raise ValueError("Only a simple lawn has no additional unknown object geometry")
        if key not in {"izgorod", "zabor"}:
            continue
        placement = _answer(item, "Где")
        allowed = (
            "Весь периметр",
            "Весь периметр по границе участка",
            "Весь периметр внутри забора",
        )
        if placement not in allowed:
            raise ValueError("Partial or unspecified boundary placement is unsupported")
        policy_key = "hedge_requested" if key == "izgorod" else "built_fence_requested"
        if spec.get("boundary_policy", {}).get(policy_key) is not True:
            raise ValueError("Boundary policy contradicts selection")
    house_object = next(item for item in objects if item["object_key"] == "eskez-doma")
    requested_shape = _answer(house_object, "форм")
    if not isinstance(requested_shape, str) or not (
        requested_shape in {"Квадрат", "Прямоугольник"}
        or requested_shape.startswith(("Г-образная", "П-образная"))
    ):
        raise ValueError("Explicit supported house silhouette required")
    scale = spec["site_scale"]
    floors = _positive(scale["house_floor_count_reference"])
    house_scale_certified = floors.is_integer()
    if not house_scale_certified and scale.get("house_footprint_estimate_status") != "unmeasured_attic_area":
        raise ValueError("Partial upper floors require an explicit unmeasured-attic scale status")
    plan = spec["site_plan"]
    if plan.get("warnings") or spec["site_scale"].get("ground_footprint_contract", {}).get(
        "layout_requires_review"
    ):
        raise ValueError("Resolve existing layout warnings before drawing a guide")
    house = next(item for item in plan["objects"] if item["object_key"] == "eskez-doma")
    shape = house.get("footprint_polygon") or (
        house_object.get("footprint_shape", {}).get("bounding_box_polygon")
    )
    if not shape or any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in shape):
        raise ValueError("Enhanced supported house footprint polygon required")
    x, y, w, h = _inside(house["rect"])
    house_polygon = [(x + u * w, y + v * h) for u, v in shape]
    if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in house_polygon):
        raise ValueError("House polygon extends outside plot")
    share = None
    if house_scale_certified:
        share = _positive(scale["ground_footprint_contract"]["target_share"])
        if not 0 < share < 1 or not isclose(
            polygon_area(house_polygon), share, abs_tol=0.0001
        ):
            raise ValueError("House rect/polygon disagrees with ground footprint share")
    result = {
        "house_polygon": house_polygon,
        "house_share": share,
        "house_scale_certified": house_scale_certified,
        "pool_rect": None,
        "pool_shape": None,
        "pool_cover_relation": None,
    }
    pool = next((item for item in objects if item["object_key"] == "basseyn"), None)
    if pool:
        cover = _answer(pool, "Чем накрыть")
        if cover not in {"Открытый", "Навес"} or _answer(pool, "Как связан") != "Отдельно во дворе":
            raise ValueError("Only a separate open or canopy-covered pool has supported geometry")
        constraints = pool["questionnaire_constraints"]
        answer = next(
            (item["answer"] for item in constraints if "размер" in item["question"].lower()), None
        )
        shape_answer = next(
            (item["answer"] for item in constraints if "форма" in item["question"].lower()), None
        )
        if shape_answer not in {"Прямоугольник", "Овал"} or not isinstance(answer, str):
            raise ValueError("Only an explicitly rectangular or oval pool is supported")
        match = re.fullmatch(
            r"\s*(?:Около\s*)?(\d+(?:[.,]\d+)?)\s*[×xх]\s*(\d+(?:[.,]\d+)?)\s*м\s*",
            answer,
            flags=re.I,
        )
        if not match:
            raise ValueError("Explicit pool length and width in metres required")
        length, width = (_positive(float(part.replace(",", "."))) for part in match.groups())
        plot_area = _positive(scale["plot_area_m2"])
        pw, ph = length / sqrt(plot_area), width / sqrt(plot_area)
        fill_fraction = pi / 4 if shape_answer == "Овал" else 1.0
        pool_share = pw * ph * fill_fraction
        zone = next(item["rect"] for item in plan["objects"] if item["object_key"] == "basseyn")
        zx, zy, zw, zh = _inside(zone)
        if pw > zw or ph > zh:
            raise ValueError("Physical pool footprint exceeds its permitted semantic zone")
        rect = {
            "x": zx + zw / 2 - pw / 2,
            "y": zy + zh / 2 - ph / 2,
            "width": pw,
            "height": ph,
        }
        _inside(rect)
        result.update(
            pool_rect=rect,
            pool_share=pool_share,
            pool_shape="oval" if shape_answer == "Овал" else "rectangle",
            pool_cover_relation="above_water" if cover == "Навес" else "none",
        )
    return result


def _render(spec: dict, size=(1536, 864)) -> tuple[bytes, str]:
    """Return PNG bytes + a spatial-only directive; source photos are rejected.

    A square conceptual ground plane is used because area alone does not identify
    cadastral side lengths. This guide does not claim a surveyed plot shape.
    """
    geometry = _geometry_from_spec(spec)
    width, height = size
    side = int(min(width, height) * 0.84)
    left, top = (width - side) // 2, (height - side) // 2
    image = Image.new("RGB", size, OUTSIDE)
    draw = ImageDraw.Draw(image)
    draw.rectangle((left, top, left + side - 1, top + side - 1), fill=GRASS)

    def point(x, y):
        return (left + round(x * (side - 1)), top + round((1 - y) * (side - 1)))

    def rectangle(rect):
        x, y, w, h = _inside(rect)
        return [point(x, y), point(x + w, y), point(x + w, y + h), point(x, y + h)]

    house_points = [point(x, y) for x, y in geometry["house_polygon"]]
    # Separate masks catch overlaps instead of silently painting one object over another.
    house_mask = Image.new("1", size)
    ImageDraw.Draw(house_mask).polygon(house_points, fill=1)
    if geometry["pool_rect"]:
        pool_points = rectangle(geometry["pool_rect"])
        pool_box = (
            min(point[0] for point in pool_points),
            min(point[1] for point in pool_points),
            max(point[0] for point in pool_points),
            max(point[1] for point in pool_points),
        )
        pool_mask = Image.new("1", size)
        pool_mask_draw = ImageDraw.Draw(pool_mask)
        if geometry["pool_shape"] == "oval":
            pool_mask_draw.ellipse(pool_box, fill=1)
        else:
            pool_mask_draw.polygon(pool_points, fill=1)
        from PIL import ImageChops

        if ImageChops.logical_and(house_mask, pool_mask).getbbox():
            raise ValueError("Pool footprint overlaps the house")
        if geometry["pool_shape"] == "oval":
            draw.ellipse(pool_box, fill=POOL)
        else:
            draw.polygon(pool_points, fill=POOL)
        if geometry["pool_cover_relation"] == "above_water":
            draw.rectangle(
                pool_box,
                outline=POOL_COVER,
                width=max(3, round(side * 0.006)),
            )
    draw.polygon(house_points, fill=HOUSE)
    boundary = spec.get("boundary_policy", {})
    requested = {item["object_key"] for item in spec["task"]["objects"]}
    for enabled, key, color, stroke, inset in (
        (boundary.get("built_fence_requested"), "zabor", FENCE, 3, 0),
        (
            boundary.get("hedge_requested"),
            "izgorod",
            HEDGE,
            max(3, round(side * 0.016)),
            round(side * 0.012),
        ),
    ):
        if enabled and key in requested:
            # No generic plot border: a boundary is drawn only when explicitly selected.
            x0, y0, x1, y1 = (
                left + inset,
                top + inset,
                left + side - 1 - inset,
                top + side - 1 - inset,
            )
            draw.line([(x0, y1), (x0, y0), (x1, y0), (x1, y1)], fill=color, width=stroke)
            gap = round(side * 0.08)
            center = (x0 + x1) // 2
            draw.line([(x0, y1), (center - gap // 2, y1)], fill=color, width=stroke)
            draw.line([(center + gap // 2, y1), (x1, y1)], fill=color, width=stroke)
    output = BytesIO()
    image.save(output, format="PNG")
    legend = []
    if geometry["pool_rect"]:
        legend.append(
            "Blue is the selected "
            + ("oval" if geometry["pool_shape"] == "oval" else "rectangular")
            + " pool water footprint."
        )
        if geometry["pool_cover_relation"] == "above_water":
            legend.append(
                "The amber outline is the selected open canopy roof projection: it MUST cover "
                "the blue water footprint, never sit beside it; canopy supports stay outside the water."
            )
    if "izgorod" in requested:
        legend.append("Dark green is the selected living hedge.")
    if "zabor" in requested:
        legend.append("Gray is the selected built fence.")
    house_scale = (
        "the tan house shape is exactly "
        f"{geometry['house_share']:.1%} of its ground area. "
        if geometry["house_scale_certified"]
        else (
            "the tan house shape is a RELATIVE PLACEMENT ANCHOR only; house footprint scale "
            "is not certified because the selected attic-area split is unknown. Do not infer "
            "a numeric house footprint or percentage from this symbol. "
        )
    )
    directive = (
        "Use this unlabeled color layout only as a GROUND-PLANE geometry reference. "
        "The enclosed green square is the conceptual whole plot; "
        + house_scale
        + " ".join(legend)
        + " Keep the encoded relative placement and explicit pool-cover relationship "
        "when making the photorealistic architectural scene. Add only the requested building "
        "height/floors above these footprints. "
        "This is not an output style reference: replace flat diagram colors with realistic "
        "materials, grass and surroundings. Do not retain a diagram, white studio background, "
        "labels, numbers, measuring lines or grid. Do not add an unselected hard fence or gate. "
        "The conceptual square is not a measured cadastral boundary; no side lengths are supplied."
    )
    return output.getvalue(), directive


@dataclass(frozen=True)
class InitialLayoutGuide:
    data: bytes
    prompt: str


def _answer(item: dict, marker: str) -> object:
    return next(
        (
            constraint.get("answer")
            for constraint in item.get("questionnaire_constraints", [])
            if marker.lower() in str(constraint.get("question", "")).lower()
        ),
        None,
    )


def build_initial_layout_guide(canonical_prompt: str) -> InitialLayoutGuide | None:
    """Skip unsupported briefs rather than invent geometry or override a source photo.

    The PNG expresses requested relative ground areas, not surveyed side lengths or
    a guarantee that the generative provider will obey them. No canonical data changes.
    """
    if not canonical_prompt.startswith("AUROOM_INITIAL_CONCEPT_V1\n"):
        return None
    try:
        enhanced = build_visual_fidelity_prompt(canonical_prompt)
        spec = JSONDecoder().raw_decode(enhanced.split("STRUCTURED_SPEC:\n", 1)[1])[0]
        data, directive = _render(spec)
    except (ValueError, KeyError, TypeError, IndexError, StopIteration, OverflowError):
        return None
    return InitialLayoutGuide(data=data, prompt=directive + "\n" + enhanced)
