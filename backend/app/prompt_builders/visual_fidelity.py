"""Provider-only visual constraints; stored canonical briefs stay reviewable across releases."""

from __future__ import annotations

from copy import deepcopy
from json import JSONDecoder, JSONDecodeError, dumps
from math import sqrt


def _answer(constraints: list[dict], marker: str) -> object:
    return next(
        (
            item.get("answer")
            for item in constraints
            if marker in str(item.get("question", "")).lower()
        ),
        None,
    )


def _house_footprint(spec: dict, objects: list[dict]) -> None:
    scale = spec.get("site_scale", {})
    house = next((obj for obj in objects if obj.get("object_key") == "eskez-doma"), None)
    if house is None:
        return
    shape = _answer(house.get("questionnaire_constraints", []), "форм")
    # Orthogonal silhouettes encode the requested volume, not a projecting porch.
    polygons = {
        "Г-образная": [(0, 0), (1, 0), (1, 0.5), (0.5, 0.5), (0.5, 1), (0, 1)],
        "П-образная": [(0, 0), (1, 0), (1, 1), (0.7, 1), (0.7, 0.4), (0.3, 0.4), (0.3, 1), (0, 1)],
    }
    shape_key = next((key for key in polygons if str(shape).startswith(key)), None)
    if shape_key is None and shape not in (None, "Квадрат", "Прямоугольник"):
        # A multi-volume house has no honest fixed bounding polygon. Preserve the
        # requested shape instead of silently turning it into a rectangle.
        house["footprint_shape"] = {
            "requested": shape,
            "directive": "Preserve the requested main building silhouette and ground footprint area; do not substitute a simple rectangle.",
        }
        if not spec.get("task", {}).get("objects"):
            spec["task"]["footprint_shape"] = house["footprint_shape"]
        return
    polygon = polygons.get(shape_key, [(0, 0), (1, 0), (1, 1), (0, 1)])
    fill = (
        abs(
            sum(
                x * polygon[(i + 1) % len(polygon)][1] - y * polygon[(i + 1) % len(polygon)][0]
                for i, (x, y) in enumerate(polygon)
            )
        )
        / 2
    )
    house["footprint_shape"] = {
        "requested": shape,
        "bounding_box_polygon": polygon,
        "filled_fraction": fill,
        "directive": "Use this silhouette for the main ground-level building footprint and roof volume. An entrance porch does not satisfy an L/U-shaped house. Preserve floor count and total floor area.",
    }
    if not spec.get("task", {}).get("objects"):
        spec["task"]["footprint_shape"] = house["footprint_shape"]
    share = scale.get("estimated_house_footprint_share_of_plot")
    if not isinstance(share, (int, float)) or isinstance(share, bool) or not 0 < share <= 1:
        return
    box_area = share / fill
    width = min(0.92, sqrt(box_area * (1.0 if shape == "Квадрат" else 1.5)))
    height = box_area / width
    scale["ground_footprint_contract"] = {
        "target_share": share,
        "bounding_box_share": box_area,
        "shape_fill_fraction": fill,
        "measurement_plane": "plot ground plane, exclude projected walls and roof overhangs",
        "directive": "Do not enlarge small houses to fill the frame. Keep the entire plot in view; preserve this ground-area ratio under perspective. No dimensions, labels or visible measuring grid.",
    }
    if height > 0.92:
        scale["ground_footprint_contract"]["layout_requires_review"] = True
        return
    for item in spec.get("site_plan", {}).get("objects", []):
        if item.get("object_key") == "eskez-doma":
            old = item["rect"]
            cx, cy = old["x"] + old["width"] / 2, old["y"] + old["height"] / 2
            item["rect"] = {
                "x": max(0.04, min(0.96 - width, cx - width / 2)),
                "y": max(0.04, min(0.96 - height, cy - height / 2)),
                "width": width,
                "height": height,
            }
            item["footprint_polygon"] = polygon
            item["ground_footprint_share"] = share


def build_visual_fidelity_prompt(prompt: str) -> str:
    if not prompt.startswith(("AUROOM_INITIAL_CONCEPT_V1\n", "AUROOM_RENDER_SPEC_V1\n")):
        return prompt
    marker = "STRUCTURED_SPEC:\n"
    if marker not in prompt:
        return prompt
    start = prompt.index(marker) + len(marker)
    try:
        raw, end = JSONDecoder().raw_decode(prompt[start:])
    except JSONDecodeError:
        return prompt
    if not isinstance(raw, dict):
        return prompt
    spec = deepcopy(raw)
    task = spec.get("task", {})
    removing = task.get("operation") == "remove_object"
    objects = task.get("objects") or [
        {
            "object_key": task.get("object_key"),
            "questionnaire_constraints": spec.get("questionnaire_constraints", []),
        }
    ]
    boundary = spec.get("boundary_policy", {})
    hedge_only = boundary.get("hedge_requested") and not boundary.get("built_fence_requested")
    required_chimneys = []
    if not removing:
        for obj in objects:
            key = obj.get("object_key")
            constraints = obj.get("questionnaire_constraints", [])
            if key == "banya" and any(
                "дровян" in str(item.get("answer", "")).lower()
                or "с трубой" in str(item.get("answer", "")).lower()
                for item in constraints
            ):
                required_chimneys.append("banya")
                obj["roof_chimney_required"] = True
            if hedge_only and key == "izgorod":
                for item in constraints:
                    if isinstance(item.get("answer"), str):
                        item["answer"] = (
                            item["answer"]
                            .replace("внутри забора", "по границе участка")
                            .replace("вдоль забора", "вдоль границы участка")
                        )
        if any(obj.get("object_key") == "eskez-doma" for obj in objects) and spec.get(
            "house_exterior_features", {}
        ).get("roof_chimney_required"):
            required_chimneys.append("eskez-doma")
        _house_footprint(spec, objects)
    spec["visual_acceptance_contract"] = {
        "required_roof_chimneys_on_objects": required_chimneys,
        "chimney_directive": "Every listed object must have its OWN visible chimney physically emerging from ITS roof. Only NEWLY ADDED objects must fit entirely inside the edit mask. During a local refinement preserve existing chimneys outside the selected area; do not move or recreate the whole building. A chimney on the main house cannot substitute for a bath wood-stove chimney. Do not show an interior stove/fireplace.",
        "hedge_is_only_requested_boundary": bool(hedge_only),
        "boundary_directive": "For a hedge-only synthetic site, the living hedge IS the boundary. Do not add mesh, solid panels, masonry walls, fence posts or duplicate hard fencing. In edits preserve existing pixels outside the allowed region.",
        "added_object_must_fit_inside_mask": not removing,
        "mask_directive": "For an ADDED object, fit its whole roof, overhangs, chimney and ground contact inside the white commit mask with space around it. For a LOCAL REFINEMENT of an existing building, change only the selected surface; preserve its unselected parts, scale and position. Never shrink or relocate the existing building to fit a local edit. Context outside the white mask is locked, never a placement area.",
        "verification": "provider_instruction_only_not_an_external_scene_measurement",
    }
    return (
        prompt[:start]
        + dumps(spec, ensure_ascii=False, separators=(",", ":"))
        + prompt[start + end :]
    )
