from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import hypot

from app.architecture.schemas import (
    FacadeOpening,
    GeometryValidationIssue,
    LevelGeometry,
    OpeningKind,
)

Vec3 = tuple[float, float, float]
Triangle = tuple[Vec3, Vec3, Vec3]

_DISTANCE_TOLERANCE = 0.05
_EPSILON = 1e-7


@dataclass(frozen=True, slots=True)
class OpeningSurface:
    opening_id: str
    kind: OpeningKind
    triangles: tuple[Triangle, ...]


@dataclass(frozen=True, slots=True)
class LevelFacadeMesh:
    wall_triangles: tuple[Triangle, ...]
    opening_surfaces: tuple[OpeningSurface, ...]


def _edges(level: LevelGeometry) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    points = [(point.x, point.y) for point in level.footprint.points]
    return list(zip(points, points[1:] + points[:1], strict=True))


def _edge_length(edge: tuple[tuple[float, float], tuple[float, float]]) -> float:
    (x1, y1), (x2, y2) = edge
    return hypot(x2 - x1, y2 - y1)


def _opening_vertical_bounds(opening: FacadeOpening) -> tuple[float, float]:
    return opening.sill_height_m, opening.sill_height_m + opening.height_m


def _opening_fits_edge(opening: FacadeOpening, edge_length: float, level_height: float) -> bool:
    _, top = _opening_vertical_bounds(opening)
    return (
        opening.offset_m >= -_DISTANCE_TOLERANCE
        and opening.offset_m + opening.width_m <= edge_length + _DISTANCE_TOLERANCE
        and top <= level_height + _DISTANCE_TOLERANCE
    )


def validate_level_openings(level: LevelGeometry) -> list[GeometryValidationIssue]:
    """Validate explicit exterior openings against their level wall coordinate system."""

    issues: list[GeometryValidationIssue] = []
    opening_ids = [opening.id for opening in level.openings]
    if len(opening_ids) != len(set(opening_ids)):
        issues.append(
            GeometryValidationIssue(
                severity="error",
                code="duplicate_opening_id",
                message=f"Opening ids on {level.label} must be unique.",
                path=f"geometry.levels[{level.id}].openings",
            )
        )

    edges = _edges(level)
    valid_for_overlap: list[FacadeOpening] = []
    for opening in level.openings:
        path = f"geometry.levels[{level.id}].openings[{opening.id}]"
        if opening.edge_index >= len(edges):
            issues.append(
                GeometryValidationIssue(
                    severity="error",
                    code="opening_edge_missing",
                    message=(
                        f"Opening {opening.id} references edge {opening.edge_index}, but "
                        f"{level.label} has {len(edges)} exterior edges."
                    ),
                    path=f"{path}.edge_index",
                )
            )
            continue

        edge_length = _edge_length(edges[opening.edge_index])
        if edge_length <= _EPSILON:
            issues.append(
                GeometryValidationIssue(
                    severity="error",
                    code="opening_edge_degenerate",
                    message=f"Opening {opening.id} references a zero-length exterior edge.",
                    path=f"{path}.edge_index",
                )
            )
            continue

        if opening.offset_m + opening.width_m > edge_length + _DISTANCE_TOLERANCE:
            issues.append(
                GeometryValidationIssue(
                    severity="error",
                    code="opening_outside_wall",
                    message=(
                        f"Opening {opening.id} extends beyond exterior edge {opening.edge_index} "
                        f"on {level.label}."
                    ),
                    path=path,
                )
            )

        _, top = _opening_vertical_bounds(opening)
        if top > level.height + _DISTANCE_TOLERANCE:
            issues.append(
                GeometryValidationIssue(
                    severity="error",
                    code="opening_above_level",
                    message=(
                        f"Opening {opening.id} reaches {top:.2f} m above the floor, above "
                        f"the {level.height:.2f} m wall height."
                    ),
                    path=path,
                )
            )

        if opening.kind in {OpeningKind.DOOR, OpeningKind.GARAGE_DOOR} and (
            opening.sill_height_m > _DISTANCE_TOLERANCE
        ):
            issues.append(
                GeometryValidationIssue(
                    severity="warning",
                    code="door_sill_above_floor",
                    message=(
                        f"Door opening {opening.id} starts {opening.sill_height_m:.2f} m "
                        "above the level floor."
                    ),
                    path=f"{path}.sill_height_m",
                )
            )

        if _opening_fits_edge(opening, edge_length, level.height):
            valid_for_overlap.append(opening)

    for first, second in combinations(valid_for_overlap, 2):
        if first.edge_index != second.edge_index:
            continue
        horizontal_overlap = min(
            first.offset_m + first.width_m,
            second.offset_m + second.width_m,
        ) - max(first.offset_m, second.offset_m)
        first_bottom, first_top = _opening_vertical_bounds(first)
        second_bottom, second_top = _opening_vertical_bounds(second)
        vertical_overlap = min(first_top, second_top) - max(first_bottom, second_bottom)
        if horizontal_overlap > _DISTANCE_TOLERANCE and vertical_overlap > _DISTANCE_TOLERANCE:
            issues.append(
                GeometryValidationIssue(
                    severity="error",
                    code="opening_overlap",
                    message=(
                        f"Openings {first.id} and {second.id} overlap on exterior edge "
                        f"{first.edge_index} of {level.label}."
                    ),
                    path=f"geometry.levels[{level.id}].openings",
                )
            )

    return issues


def _point_along(
    edge: tuple[tuple[float, float], tuple[float, float]],
    distance: float,
) -> tuple[float, float]:
    (x1, y1), (x2, y2) = edge
    length = _edge_length(edge)
    if length <= _EPSILON:
        raise ValueError("Cannot place facade geometry on a zero-length edge.")
    ratio = distance / length
    return x1 + (x2 - x1) * ratio, y1 + (y2 - y1) * ratio


def _wall_rectangle(
    edge: tuple[tuple[float, float], tuple[float, float]],
    start_m: float,
    end_m: float,
    bottom_z: float,
    top_z: float,
) -> list[Triangle]:
    if end_m - start_m <= _EPSILON or top_z - bottom_z <= _EPSILON:
        return []
    start = _point_along(edge, start_m)
    end = _point_along(edge, end_m)
    return [
        (
            (start[0], start[1], bottom_z),
            (end[0], end[1], bottom_z),
            (end[0], end[1], top_z),
        ),
        (
            (start[0], start[1], bottom_z),
            (end[0], end[1], top_z),
            (start[0], start[1], top_z),
        ),
    ]


def build_level_facade_mesh(level: LevelGeometry) -> LevelFacadeMesh:
    """Build wall surfaces with exact rectangular apertures and explicit window/door panels."""

    errors = [issue for issue in validate_level_openings(level) if issue.severity == "error"]
    if errors:
        raise ValueError("Cannot mesh invalid facade openings: " + "; ".join(i.code for i in errors))

    edges = _edges(level)
    openings_by_edge: dict[int, list[FacadeOpening]] = {}
    for opening in level.openings:
        openings_by_edge.setdefault(opening.edge_index, []).append(opening)

    walls: list[Triangle] = []
    surfaces: list[OpeningSurface] = []
    level_bottom = level.z
    level_top = level.z + level.height

    for edge_index, edge in enumerate(edges):
        edge_length = _edge_length(edge)
        openings = sorted(
            openings_by_edge.get(edge_index, []),
            key=lambda opening: (opening.offset_m, opening.sill_height_m, opening.id),
        )
        cursor = 0.0
        for opening in openings:
            opening_start = opening.offset_m
            opening_end = opening.offset_m + opening.width_m
            opening_bottom = level.z + opening.sill_height_m
            opening_top = opening_bottom + opening.height_m

            walls.extend(
                _wall_rectangle(edge, cursor, opening_start, level_bottom, level_top)
            )
            walls.extend(
                _wall_rectangle(edge, opening_start, opening_end, level_bottom, opening_bottom)
            )
            walls.extend(
                _wall_rectangle(edge, opening_start, opening_end, opening_top, level_top)
            )
            panel = _wall_rectangle(
                edge,
                opening_start,
                opening_end,
                opening_bottom,
                opening_top,
            )
            surfaces.append(
                OpeningSurface(
                    opening_id=opening.id,
                    kind=opening.kind,
                    triangles=tuple(panel),
                )
            )
            cursor = max(cursor, opening_end)

        walls.extend(_wall_rectangle(edge, cursor, edge_length, level_bottom, level_top))

    return LevelFacadeMesh(wall_triangles=tuple(walls), opening_surfaces=tuple(surfaces))
