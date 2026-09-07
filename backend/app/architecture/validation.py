from __future__ import annotations

from itertools import combinations

from shapely.geometry import Point, Polygon
from shapely.validation import explain_validity

from app.architecture.schemas import (
    ArchitecturePackage,
    ExternalObjectType,
    GeometryValidationIssue,
    GeometryValidationReport,
    HouseGeometry,
    Polygon2D,
    RoofType,
)

_AREA_TOLERANCE = 0.01
_DISTANCE_TOLERANCE = 0.05


def _polygon(value: Polygon2D) -> Polygon:
    return Polygon([(point.x, point.y) for point in value.points])


class GeometryValidator:
    """Validate the canonical geometry through one public interface."""

    def validate(
        self,
        geometry: HouseGeometry,
        *,
        package: ArchitecturePackage | None = None,
    ) -> GeometryValidationReport:
        issues: list[GeometryValidationIssue] = []
        level_areas: dict[str, float] = {}
        room_areas: dict[str, float] = {}
        level_polygons: dict[str, Polygon] = {}

        level_ids = [level.id for level in geometry.levels]
        if len(level_ids) != len(set(level_ids)):
            issues.append(
                GeometryValidationIssue(
                    severity="error",
                    code="duplicate_level_id",
                    message="Every level id must be unique.",
                    path="geometry.levels",
                )
            )

        sorted_levels = sorted(geometry.levels, key=lambda item: item.z)
        for index, level in enumerate(sorted_levels):
            path = f"geometry.levels[{level.id}]"
            footprint = _polygon(level.footprint)
            level_polygons[level.id] = footprint
            if footprint.is_empty or footprint.area <= _AREA_TOLERANCE:
                issues.append(
                    GeometryValidationIssue(
                        severity="error",
                        code="empty_level_footprint",
                        message=f"Level {level.label} has no usable footprint area.",
                        path=f"{path}.footprint",
                    )
                )
                continue
            if not footprint.is_valid:
                issues.append(
                    GeometryValidationIssue(
                        severity="error",
                        code="invalid_level_footprint",
                        message=f"Level {level.label}: {explain_validity(footprint)}",
                        path=f"{path}.footprint",
                    )
                )
                continue
            level_areas[level.id] = round(float(footprint.area), 3)

            if index:
                previous = sorted_levels[index - 1]
                expected_min_z = previous.z + previous.height
                if level.z < expected_min_z - _DISTANCE_TOLERANCE:
                    issues.append(
                        GeometryValidationIssue(
                            severity="error",
                            code="level_vertical_overlap",
                            message=(
                                f"Level {level.label} starts at Z={level.z:.2f}, below the top "
                                f"of {previous.label} at Z={expected_min_z:.2f}."
                            ),
                            path=f"{path}.z",
                        )
                    )

            room_ids = [room.id for room in level.rooms]
            if len(room_ids) != len(set(room_ids)):
                issues.append(
                    GeometryValidationIssue(
                        severity="error",
                        code="duplicate_room_id",
                        message=f"Room ids on {level.label} must be unique.",
                        path=f"{path}.rooms",
                    )
                )

            room_shapes: list[tuple[str, Polygon]] = []
            for room in level.rooms:
                room_path = f"{path}.rooms[{room.id}]"
                shape = _polygon(room.polygon)
                if shape.is_empty or shape.area <= _AREA_TOLERANCE:
                    issues.append(
                        GeometryValidationIssue(
                            severity="error",
                            code="empty_room_polygon",
                            message=f"Room {room.name} has no usable area.",
                            path=f"{room_path}.polygon",
                        )
                    )
                    continue
                if not shape.is_valid:
                    issues.append(
                        GeometryValidationIssue(
                            severity="error",
                            code="invalid_room_polygon",
                            message=f"Room {room.name}: {explain_validity(shape)}",
                            path=f"{room_path}.polygon",
                        )
                    )
                    continue
                room_areas[f"{level.id}:{room.id}"] = round(float(shape.area), 3)
                if not footprint.buffer(_DISTANCE_TOLERANCE).covers(shape):
                    issues.append(
                        GeometryValidationIssue(
                            severity="error",
                            code="room_outside_footprint",
                            message=f"Room {room.name} extends outside {level.label}.",
                            path=f"{room_path}.polygon",
                        )
                    )
                room_shapes.append((room.id, shape))

            for (first_id, first), (second_id, second) in combinations(room_shapes, 2):
                overlap = first.intersection(second).area
                if overlap > _AREA_TOLERANCE:
                    issues.append(
                        GeometryValidationIssue(
                            severity="error",
                            code="room_overlap",
                            message=(
                                f"Rooms {first_id} and {second_id} overlap by {overlap:.2f} m² "
                                f"on {level.label}."
                            ),
                            path=f"{path}.rooms",
                        )
                    )

        all_level_shapes = [shape for shape in level_polygons.values() if shape.is_valid]
        for item in geometry.external_objects:
            path = f"geometry.external_objects[{item.id}]"
            shape = _polygon(item.polygon)
            if not shape.is_valid or shape.area <= _AREA_TOLERANCE:
                issues.append(
                    GeometryValidationIssue(
                        severity="error",
                        code="invalid_external_object",
                        message=f"External object {item.label} has invalid geometry.",
                        path=f"{path}.polygon",
                    )
                )
                continue
            if item.level_id is not None and item.level_id not in level_polygons:
                issues.append(
                    GeometryValidationIssue(
                        severity="error",
                        code="external_object_level_missing",
                        message=(
                            f"External object {item.label} references unknown level "
                            f"{item.level_id}."
                        ),
                        path=f"{path}.level_id",
                    )
                )
            if item.type == ExternalObjectType.POOL:
                if any(
                    shape.intersection(level_shape).area > _AREA_TOLERANCE
                    for level_shape in all_level_shapes
                ):
                    issues.append(
                        GeometryValidationIssue(
                            severity="error",
                            code="pool_intersects_building",
                            message=f"Pool {item.label} intersects the building footprint.",
                            path=f"{path}.polygon",
                        )
                    )
            elif item.type in {
                ExternalObjectType.VERANDA,
                ExternalObjectType.TERRACE,
                ExternalObjectType.WINTER_GARDEN,
            }:
                target = (
                    level_polygons.get(item.level_id)
                    if item.level_id is not None
                    else (all_level_shapes[0] if all_level_shapes else None)
                )
                if target is not None and shape.distance(target) > _DISTANCE_TOLERANCE:
                    issues.append(
                        GeometryValidationIssue(
                            severity="warning",
                            code="addition_not_attached",
                            message=f"{item.label} is not attached to its building footprint.",
                            path=f"{path}.polygon",
                        )
                    )

        roof = geometry.roof
        if roof is not None and geometry.levels:
            highest_level = max(geometry.levels, key=lambda item: item.z + item.height)
            roof_base = level_polygons.get(highest_level.id)
            if roof.eave_z < highest_level.z + highest_level.height - _DISTANCE_TOLERANCE:
                issues.append(
                    GeometryValidationIssue(
                        severity="error",
                        code="roof_below_top_level",
                        message="Roof eave is below the top of the highest level.",
                        path="geometry.roof.eave_z",
                    )
                )
            if roof.type == RoofType.GABLE and roof_base is not None:
                ridge_points = [roof.ridge_start, roof.ridge_end]
                for ridge_point in ridge_points:
                    if ridge_point is None:
                        continue
                    if not roof_base.buffer(max(roof.overhang_m, 0.1)).covers(
                        Point(ridge_point.x, ridge_point.y)
                    ):
                        issues.append(
                            GeometryValidationIssue(
                                severity="warning",
                                code="roof_ridge_outside_footprint",
                                message=(
                                    "A gable ridge endpoint lies outside the highest footprint."
                                ),
                                path="geometry.roof",
                            )
                        )
                        break

        gross_area = round(sum(level_areas.values()), 3)
        if package is not None and package.program.storeys is not None:
            if package.program.storeys != len(geometry.levels):
                issues.append(
                    GeometryValidationIssue(
                        severity="warning",
                        code="program_storey_mismatch",
                        message=(
                            f"Program requests {package.program.storeys} levels, while geometry "
                            f"contains {len(geometry.levels)}."
                        ),
                        path="program.storeys",
                    )
                )

        return GeometryValidationReport(
            valid=not any(issue.severity == "error" for issue in issues),
            issues=issues,
            level_areas_sqm=level_areas,
            room_areas_sqm=room_areas,
            gross_floor_area_sqm=gross_area,
        )
