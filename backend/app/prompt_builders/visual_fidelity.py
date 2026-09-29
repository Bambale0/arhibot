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


def _hedge_boundary_answer(value: object) -> object:
    if isinstance(value, str):
        return value.replace("внутри забора", "по границе участка").replace(
            "вдоль забора", "вдоль границы участка"
        )
    if isinstance(value, list):
        return [_hedge_boundary_answer(item) for item in value]
    return value


def _initial_surface_layout(spec: dict, objects: list[dict]) -> None:
    """Do not give whole boundaries/continuous lawn a second, interior footprint."""
    source_kind = spec.get("source_scene", {}).get("kind")
    if spec.get("schema") != "auroom.initial_concept.v1" or source_kind not in {
        "synthetic_site", "site_photo"
    }:
        return
    plan = spec.get("site_plan")
    if not isinstance(plan, dict):
        return
    surfaces = set()
    for obj in objects:
        key = obj.get("object_key")
        constraints = obj.get("questionnaire_constraints", [])
        if key in {"izgorod", "zabor"} and _answer(constraints, "где") in (
            "Весь периметр", "Весь периметр внутри забора",
            "Весь периметр по границе участка",
        ):
            surfaces.add(key)
        if (
            source_kind == "synthetic_site"
            and key == "gazon"
            and _answer(constraints, "какой характер двора") == "Минимализм, газон и гравий"
            and _answer(constraints, "что видно из посадок") in (["Газон"], "Газон")
        ):
            surfaces.add(key)
    removed = {
        item["object_key"] for item in plan.get("objects", [])
        if item.get("object_key") in surfaces and item.get("placement_source") == "derived"
    }
    # Their selected placement remains in task.objects / boundary_policy. Keep
    # explicit zones and unsupported/partial selections under the existing policy.
    plan["objects"] = [
        item for item in plan.get("objects", []) if item.get("object_key") not in removed
    ]
    plan["warnings"] = [
        warning for warning in plan.get("warnings", [])
        if not (
            warning.get("object_key") in removed
            and warning.get("code") in {
                "placement_overlap_unresolved", "placement_relation_unresolved"
            }
        )
    ]


def _reflow_secondary_zones(spec: dict, house_rect: dict) -> None:
    from app.questionnaires.site_plan import (
        _overlaps,
        _place_rect,
        _relation_ok,
        _target_center,
    )

    plan = spec["site_plan"]
    secondary = [item for item in plan["objects"] if item.get("object_key") != "eskez-doma"]
    keys = {item["object_key"] for item in secondary}
    warnings = [
        warning
        for warning in plan.get("warnings", [])
        if not (
            warning.get("object_key") in keys
            and warning.get("code")
            in {
                "placement_overlap_unresolved",
                "placement_relation_unresolved",
            }
        )
    ]
    occupied = [house_rect]
    pending = []
    # Reserve valid zones first, so fixing one conflict cannot displace a zone
    # that already fits the final house. Never resize a secondary object.
    for item in secondary:
        rect, relations = item["rect"], item.get("relations", [])
        if _relation_ok(rect, relations, house_rect) and not any(
            _overlaps(rect, other) for other in occupied
        ):
            occupied.append(rect)
        else:
            pending.append(item)
    for item in pending:
        rect, relations = item["rect"], item.get("relations", [])
        width, height = rect["width"], rect["height"]
        tx, ty = _target_center(relations, house_rect=house_rect, width=width, height=height)
        # The existing placer searches locally. Also try the plot edges when
        # a larger footprint needs more than its local search radius.
        targets = [(tx, ty)]
        targets += [(tx, y) for y in (0.04 + height / 2, 0.96 - height / 2)]
        targets += [(x, ty) for x in (0.04 + width / 2, 0.96 - width / 2)]
        for x, y in targets:
            candidate, overlap = _place_rect(
                target_x=x,
                target_y=y,
                width=width,
                height=height,
                relations=relations,
                house_rect=house_rect,
                occupied=occupied,
            )
            # _place_rect's fallback may violate a relation without overlapping.
            if not overlap and _relation_ok(candidate, relations, house_rect):
                item["rect"] = rect = candidate
                break
        unresolved = []
        if any(_overlaps(rect, other) for other in occupied):
            unresolved.append("placement_overlap_unresolved")
        if not _relation_ok(rect, relations, house_rect):
            unresolved.append("placement_relation_unresolved")
        for code in unresolved:
            warnings.append({"object_key": item["object_key"], "code": code})
        if unresolved:
            spec["site_scale"]["ground_footprint_contract"]["layout_requires_review"] = True
        occupied.append(rect)
    plan["warnings"] = warnings


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
            _reflow_secondary_zones(spec, item["rect"])


def _initial_selected_details(spec: dict, objects: list[dict]) -> None:
    # New synthetic concepts only: never reinterpret an accepted scene or local edit.
    if spec.get("schema") != "auroom.initial_concept.v1" or spec.get("source_scene", {}).get(
        "kind"
    ) != "synthetic_site":
        return
    for obj in objects:
        constraints = obj.get("questionnaire_constraints", [])
        if obj.get("object_key") == "eskez-doma":
            floors = {"1 этаж": 1, "2 этажа": 2, "3 этажа": 3}.get(
                str(_answer(constraints, "сколько этажей"))
            )
            shape = str(_answer(constraints, "форм"))
            regular_footprint = shape in {
                "Квадрат", "Прямоугольник", "Г-образная"
            } or shape.startswith("П-образная")
            if floors is not None and regular_footprint:
                obj["storey_directive"] = (
                    f"The main house has exactly {floors} full above-ground storeys in every main wing. "
                    "Keep the same main footprint on every storey, including both L-wings or all "
                    "three U-wings. No main wing may have fewer full storeys than this count; pitched "
                    "roof space must not replace a full storey. Small entrance porches and explicitly "
                    "selected ancillary garages/verandas are separate features, not substitutes for "
                    "a main wing. Preserve the specified total floor area and ground footprint; "
                    "do not enlarge the building to compensate for a missing upper floor."
                )
        if obj.get("object_key") == "zabor" and _answer(
            constraints, "какой забор"
        ) == "Решётка / штакетик, видно двор":
            obj["fence_openness_directive"] = (
                "The selected fence is see-through: spaced bars or narrow pickets with visible gaps "
                "showing the existing plot/background through the infill; no solid infill panels or continuous sheet-metal "
                "walls. Preserve the selected posts, material and height. Fence openness takes "
                "priority over architectural style and material variants."
            )
        if obj.get("object_key") == "eskez-doma" and _answer(
            constraints, "какое остекление"
        ) == "Стандартные окна":
            obj["glazing_directive"] = (
                "The main house has STANDARD WINDOWS: separate ordinary window openings with "
                "an opaque wall below each window and wall piers between windows; "
                "no floor-to-ceiling glazing, panoramic glass walls or continuous glass facades. "
                "Architectural style must not upgrade the selected glazing. Keep entrance doors "
                "and any explicitly selected winter garden, double-height room or glazed veranda "
                "as separate features; do not spread their glazing to ordinary house windows."
            )
        if (
            obj.get("object_key") == "gazon"
            and _answer(constraints, "какой характер двора") == "Минимализм, газон и гравий"
            and _answer(constraints, "что видно из посадок") in (["Газон"], "Газон")
        ):
            hedge_directive = (
                "Keep the selected living hedge at its requested boundary placement, including "
                "its flowers; this is separate from interior planting. "
                if any(item.get("object_key") == "izgorod" for item in objects)
                else ""
            )
            obj["planting_directive"] = (
                "The selected interior planting is LAWN ONLY: inside this plot add no decorative "
                "trees, conifers, ornamental shrubs, flower beds, vegetable beds, potted plants "
                "or planters, including beside the house entrance. "
                "Do not invent a garden to fill unused ground. "
                + hedge_directive
                + "Trees and landscape outside the plot are unaffected. Gravel allowed by the "
                "selected minimalist style and other explicitly selected site objects remain allowed."
            )


def _initial_scene_priority(spec: dict) -> str:
    if spec.get("schema") != "auroom.initial_concept.v1" or spec.get("source_scene", {}).get(
        "kind"
    ) != "synthetic_site":
        return ""
    requirements = []
    contract = spec.get("visual_acceptance_contract", {})
    if contract.get("hedge_is_only_requested_boundary"):
        requirements.append(
            "The living hedge alone forms this property's boundary. No hard fence, mesh, "
            "panels, masonry wall or fence posts anywhere on this property."
        )
        if contract.get("unrequested_gates_forbidden"):
            requirements.append(
                "Every entrance is an OPEN GAP in the hedge: no gate, wicket, gate leaves "
                "or entrance posts. Do not invent an entrance structure."
            )
    for obj in spec.get("task", {}).get("objects", []):
        for key in (
            "storey_directive", "glazing_directive",
            "planting_directive", "fence_openness_directive",
        ):
            if obj.get(key):
                requirements.append(obj[key])
    if not requirements:
        return ""
    return "MANDATORY COMPOSITION BEFORE STYLING:\n" + "\n".join(requirements) + (
        "\nAll measurements are invisible design constraints. Render no text, labels, "
        "digits, dimension lines or measuring grid.\n\n"
    )


def _initial_photo_priority(spec: dict) -> str:
    """A new concept uses the photo as site context, not an accepted building."""
    source = spec.get("source_scene", {})
    if spec.get("schema") != "auroom.initial_concept.v1" or source.get("kind") != "site_photo":
        return ""
    source["selected_objects_override_existing_geometry"] = True
    source["directive"] = (
        "Use the source photograph for the plot boundary, terrain and surrounding context. "
        "For every selected object, the NEW questionnaire brief takes priority over its old "
        "appearance in the photograph, including footprint shape, floor count, roof and materials. "
        "Replace the existing counterpart with the requested design; do not add a second house "
        "or preserve old building geometry when it conflicts with the brief. Keep unrelated "
        "site context, including existing planting and boundaries unless explicitly changed. "
        "Do not invent extra interior planting, isolated hedge fragments, furniture or decorations "
        "absent from both the source and selected brief. A requested whole-perimeter hedge or "
        "fence follows the property edge only, not a second isolated interior footprint. "
        "Follow camera.mode and camera.directive for the requested viewpoint."
    )
    return (
        "NEW BRIEF TAKES PRIORITY OVER EXISTING BUILDINGS IN THE SOURCE PHOTO:\n"
        + source["directive"]
        + "\nSelected object requirements: "
        + dumps(
            [
                {
                    "object_key": obj.get("object_key"),
                    "questionnaire_constraints": obj.get("questionnaire_constraints", []),
                }
                for obj in spec.get("task", {}).get("objects", [])
            ],
            ensure_ascii=False,
        )
        + "\nRender no text, labels, digits, dimension lines or measuring grid.\n\n"
    )


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
                for item in constraints:
                    if (
                        "что еще видно снаружи"
                        in str(item.get("question", "")).lower().replace("ё", "е")
                        and str(item.get("answer", "")).strip().lower() == "ничего"
                    ):
                        item["answer"] = (
                            "Ничего дополнительного. Обязательную трубу выбранной дровяной печи показать на крыше самой бани."
                        )
            if hedge_only and key == "izgorod":
                for item in constraints:
                    item["answer"] = _hedge_boundary_answer(item.get("answer"))
        if hedge_only:
            for item in spec.get("site_layout", {}).get("placement_constraints", []):
                if item.get("object_key") == "izgorod":
                    item["answer"] = _hedge_boundary_answer(item.get("answer"))
        if any(obj.get("object_key") == "eskez-doma" for obj in objects) and spec.get(
            "house_exterior_features", {}
        ).get("roof_chimney_required"):
            required_chimneys.append("eskez-doma")
        _initial_surface_layout(spec, objects)
        _house_footprint(spec, objects)
    spec["visual_acceptance_contract"] = {
        "required_roof_chimneys_on_objects": required_chimneys,
        "chimney_directive": "Every listed object must have its OWN visible chimney physically emerging from ITS roof. Only NEWLY ADDED objects must fit entirely inside the edit mask. During a local refinement preserve existing chimneys outside the selected area; do not move or recreate the whole building. A chimney on the main house cannot substitute for a bath wood-stove chimney. Do not show an interior stove/fireplace.",
        "hedge_is_only_requested_boundary": bool(hedge_only),
        "unrequested_gates_forbidden": bool(
            hedge_only and not any(obj.get("object_key") == "vorota" for obj in objects)
        ),
        "boundary_directive": "For a hedge-only synthetic site, the living hedge IS the boundary. Do not add mesh, solid panels, masonry walls, fence posts or duplicate hard fencing. When unrequested_gates_forbidden=true, leave entrances as open gaps: no gates, wickets, gate leaves or entrance posts. Preserve an existing source-photo boundary and existing pixels outside an edit region unless removal is requested; do not interpret this new-object restriction as permission to remove them.",
        "added_object_must_fit_inside_mask": not removing,
        "mask_directive": "For an ADDED object, fit its whole roof, overhangs, chimney and ground contact inside the white commit mask with space around it. For a LOCAL REFINEMENT of an existing building, change only the selected surface; preserve its unselected parts, scale and position. Never shrink or relocate the existing building to fit a local edit. Context outside the white mask is locked, never a placement area.",
        "verification": "provider_instruction_only_not_an_external_scene_measurement",
    }
    if not removing:
        _initial_selected_details(spec, objects)
    photo_priority = _initial_photo_priority(spec)
    return (
        photo_priority
        + _initial_scene_priority(spec)
        + prompt[:start]
        + dumps(spec, ensure_ascii=False, separators=(",", ":"))
        + prompt[start + end :]
    )
