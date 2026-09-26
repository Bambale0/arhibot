"""Coordinate-safe local tiles for provider edits; canonical briefs stay unchanged."""

from __future__ import annotations

from io import BytesIO
from json import JSONDecoder, JSONDecodeError, dumps
from math import ceil, sqrt

from PIL import Image, ImageChops, ImageDraw, ImageStat

from app.image_compositor import _read_rgb, _rect_box, _region_mask
from app.prompt_builders.visual_fidelity import build_visual_fidelity_prompt

RATIOS = ((1, 1), (4, 3), (3, 4), (16, 9), (9, 16))


def _png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def choose_local_geometry(
    base_data: bytes, context_region: dict, *, max_pixels: int
) -> dict | None:
    image = _read_rgb(base_data, max_pixels=max_pixels)
    left, top, right, bottom = _rect_box(context_region, *image.size)
    options = []
    for a, b in RATIOS:
        unit = ceil(max((right - left) / a, (bottom - top) / b))
        width, height = a * unit, b * unit
        if width <= image.width and height <= image.height:
            options.append((width * height, width, height, f"{a}:{b}"))
    if not options:
        return None
    _, width, height, aspect = min(options)
    if (width, height) == image.size:
        return None
    x = max(0, min(image.width - width, (left + right - width) // 2))
    y = max(0, min(image.height - height, (top + bottom - height) // 2))
    return {
        "version": "local-tile.v1",
        "box": [x, y, x + width, y + height],
        "base_size": list(image.size),
        "aspect_ratio": aspect,
    }


def _checked_box(image: Image.Image, geometry: dict) -> tuple[int, int, int, int]:
    if geometry.get("version") != "local-tile.v1" or list(image.size) != geometry.get("base_size"):
        raise ValueError("Local edit source geometry changed")
    box = tuple(geometry["box"])
    if len(box) != 4 or not all(type(n) is int for n in box):
        raise ValueError("Invalid local edit box")
    if not (0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height):
        raise ValueError("Local edit box is outside the source")
    return box


def local_source(base_data: bytes, geometry: dict, *, max_pixels: int) -> bytes:
    base = _read_rgb(base_data, max_pixels=max_pixels)
    return _png(base.crop(_checked_box(base, geometry)))


def project_local_candidate(
    base_data: bytes,
    candidate_data: bytes,
    geometry: dict,
    *,
    max_pixels: int,
    edit_region: dict | None = None,
    protected_regions: list[dict] | None = None,
    max_context_color_error: float | None = None,
) -> bytes:
    base = _read_rgb(base_data, max_pixels=max_pixels)
    left, top, right, bottom = _checked_box(base, geometry)
    candidate = _read_rgb(candidate_data, max_pixels=max_pixels)
    width, height = right - left, bottom - top
    # Allow only output-dimension rounding, not a full-scene frame masquerading as a tile.
    if abs(candidate.width / candidate.height / (width / height) - 1) > 0.02:
        raise ValueError("Provider returned the wrong local edit aspect ratio")
    if candidate.size != (width, height):
        candidate = candidate.resize((width, height), Image.Resampling.LANCZOS)
    if edit_region is not None and max_context_color_error is not None:
        allowed = _region_mask(base.size, edit_region, protected_regions or [], feather_px=0)
        locked = ImageChops.invert(allowed.crop((left, top, right, bottom)))
        if locked.getbbox() is not None:
            original = base.crop((left, top, right, bottom))
            # Compare locked pixels directly. Blurring first would leak permitted
            # edits into thin locked bands and unchanged protected holes.
            difference = ImageChops.difference(original, candidate)
            # A small overrun on one side must not disappear in the average of
            # all four sides. Check each locked side and protected hole separately.
            x1, y1, x2, y2 = _rect_box(edit_region, *base.size)
            bands = [
                (0, 0, x1 - left, height),
                (x2 - left, 0, width, height),
                (0, 0, width, y1 - top),
                (0, y2 - top, width, height),
            ]
            masks = [locked]
            for box in bands:
                a, b, c, d = max(0, box[0]), max(0, box[1]), min(width, box[2]), min(height, box[3])
                if a < c and b < d:
                    mask = Image.new("L", (width, height))
                    ImageDraw.Draw(mask).rectangle((a, b, c - 1, d - 1), fill=255)
                    masks.append(ImageChops.multiply(mask, locked))
            for region in protected_regions or []:
                masks.append(
                    _region_mask(base.size, region, [], feather_px=0).crop(
                        (left, top, right, bottom)
                    )
                )
            for mask in masks:
                if mask.getbbox() is None:
                    continue
                mean = ImageStat.Stat(difference, mask=mask).mean
                if sqrt(sum(channel**2 for channel in mean)) > max_context_color_error:
                    raise ValueError("Provider local edit changed locked context or framing")
    base.paste(candidate, (left, top))
    return _png(base)


def local_region(region: dict, geometry: dict) -> dict | None:
    width, height = geometry["base_size"]
    left, top, right, bottom = _rect_box(region, width, height)
    x, y, x2, y2 = geometry["box"]
    left, top, right, bottom = max(left, x), max(top, y), min(right, x2), min(bottom, y2)
    if left >= right or top >= bottom:
        return None
    return {
        "x": (left - x) / (x2 - x),
        "y": (top - y) / (y2 - y),
        "width": (right - left) / (x2 - x),
        "height": (bottom - top) / (y2 - y),
    }


def local_edit_prompt(
    prompt: str, geometry: dict, edit_region: dict, protected_regions: list[dict]
) -> str | None:
    marker = "STRUCTURED_SPEC:\n"
    if not prompt.startswith("AUROOM_RENDER_SPEC_V1\n") or marker not in prompt:
        return None
    enhanced = build_visual_fidelity_prompt(prompt)
    try:
        spec, _ = JSONDecoder().raw_decode(enhanced.split(marker, 1)[1])
    except (ValueError, JSONDecodeError):
        return None
    if not isinstance(spec, dict) or not isinstance(spec.get("task"), dict):
        return None
    operation = geometry.get("operation", "add_or_refine")
    spec["task"]["local_operation"] = operation
    allowed = local_region(edit_region, geometry)
    spec["source_scene"] = {
        "kind": "local_tile_of_accepted_scene",
        "directive": "The ONLY reference image is a local crop, not the full site. Return exactly this local framing. Do not invent or reveal the rest of the plot. Match materials to any existing building fragment and house_style_reference when given.",
    }
    if geometry.get("scene_context_reference"):
        spec["source_scene"]["directive"] = (
            "Reference image 1 is the ONLY output frame. Return that exact crop with the local edit, same camera and boundaries. Reference image 2 is the accepted full scene: use it ONLY to match the house roof color, roofing material, facade and real-world building scale. NEVER return the full scene from image 2."
        )
        spec["appearance_context"] = {
            "reference_image": 2,
            "tile_box_in_full_scene_pixels": geometry["box"],
            "full_scene_pixels": geometry["base_size"],
            "directive": "For objects matching the house, copy its visible roofing and facade appearance. Keep normal building height and requested floor area relative to the existing house. Work only in image 1 allowed_region.",
        }
    spec["spatial_constraints"] = {
        "coordinate_frame": "reference_image_1_local_tile_normalized_0_to_1",
        "allowed_region": allowed,
        "locked_regions": [r for item in protected_regions if (r := local_region(item, geometry))],
        "outside_edit_region": "preserve_exactly",
    }
    constraints = spec.get("questionnaire_constraints", [])
    location_answers = [
        item
        for item in constraints
        if str(item.get("question", "")).lower().startswith("где на участке относительно дома")
    ]
    spec["questionnaire_constraints"] = [
        item for item in constraints if item not in location_answers
    ]
    spec["resolved_global_placement"] = {
        "resolved_by_selected_region": True,
        "directive": "Already resolved by the user's selected crop location. Do NOT shift the object to the right/left edge of this tile to satisfy a global placement answer.",
    }
    spec["house_style_reference"] = geometry.get("house_style_reference", {})
    scale = spec.get("site_scale", {})
    if "ground_footprint_contract" in scale:
        scale["ground_footprint_contract"]["directive"] = (
            "Global ground-area context only. Preserve existing scale in this local tile; never show the entire plot or shrink an existing building into the tile."
        )
    if operation == "add":
        spec.setdefault("edit_policy", {}).update(
            {
                "geometry_preservation_scope": "existing_scene_not_new_target",
                "new_target_creation_allowed": True,
                "new_target_directive": (
                    "Preserve the geometry and chimney positions of EXISTING scene objects. "
                    "The target object does not exist yet: create its requested geometry and "
                    "required exterior features inside the allowed region. A required new roof "
                    "chimney belongs to the new target and is not relocation of an existing chimney. "
                    "Do not interpret geometry preservation as a ban on adding the target."
                ),
            }
        )
    elif operation == "refine" or spec.get("edit_policy", {}).get("preserve_building_geometry"):
        spec["task"].pop("footprint_shape", None)
    spec["scene_policy"] = {
        "camera": "exact viewpoint and framing of reference image 1; do not zoom out or reframe"
    }
    contract = spec.get("visual_acceptance_contract", {})
    contract["chimney_directive"] = (
        "An ADDED wood-stove bath must have its own visible roof chimney inside the allowed region. For local refinements preserve existing chimneys outside the tile and change only explicitly requested exterior features; never add an interior stove."
    )
    extended_surface = spec["task"].get("object_key") in {
        "zabor",
        "izgorod",
        "vorota",
        "dorozhki",
        "gazon",
        "prud",
        "podsvetka",
        "podpornye",
    }
    placement = (
        "For boundary, path and landscape edits, follow the existing ground and perimeter alignment. Maintain continuity with unchanged segments beyond the rectangle; gates connect to their boundary. Do not move a boundary or path into the middle of the ground."
        if extended_surface
        else "CENTER an ADDED object within that rectangle. For a new building the selected rectangle is its intended exterior bounding box, not a search area: its roof and walls should occupy most of the selected width and height, with only a small natural margin. Do not create a tiny model, miniature shed or icon in a large empty selection. Maintain normal full-size building wall height. Its ENTIRE roof, chimney and ground contact must remain visible and inside the rectangle, never cut off at an image edge."
    )
    contract["mask_directive"] = (
        "There is NO white mask image. The allowed_region is a rectangle in reference image 1, measured from its top-left. "
        + placement
        + " A local refinement must keep unselected parts of existing objects fixed. Never render cards, white backgrounds, borders, panels, guide marks, text or dimensions."
    )
    spec["output"] = {
        "type": "single_photorealistic_local_tile",
        "aspect_ratio": geometry["aspect_ratio"],
        "framing": "same boundaries, camera and ground alignment as reference image 1",
    }
    return (
        "AUROOM_LOCALIZED_EDIT_V1\nModify ONLY reference image 1 and return the same local photograph, with the requested edit naturally integrated. Do not return the full site, collage or object cutout.\nSTRUCTURED_SPEC:\n"
        + dumps(spec, ensure_ascii=False, separators=(",", ":"))
    )
