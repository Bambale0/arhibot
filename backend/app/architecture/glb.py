from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import split, triangulate

from app.architecture.schemas import ArchitecturePackage, ExternalObjectType, Polygon2D, RoofType

Vec3 = tuple[float, float, float]
Triangle = tuple[Vec3, Vec3, Vec3]

_JSON_CHUNK_TYPE = 0x4E4F534A
_BIN_CHUNK_TYPE = 0x004E4942
_ARRAY_BUFFER_TARGET = 34962
_FLOAT_COMPONENT_TYPE = 5126
_TRIANGLES_MODE = 4
_EPSILON = 1e-7


@dataclass(frozen=True, slots=True)
class GlbBuildResult:
    data: bytes
    warnings: tuple[str, ...]
    mesh_count: int


@dataclass(frozen=True, slots=True)
class _Primitive:
    name: str
    material_index: int
    triangles: tuple[Triangle, ...]


def _source_polygon(polygon: Polygon2D) -> Polygon:
    return Polygon([(point.x, point.y) for point in polygon.points])


def _to_gltf(point: Vec3) -> Vec3:
    # Canonical AuRoom is X=east, Y=north, Z=up. glTF is Y-up and right-handed.
    x, y, z = point
    return x, z, -y


def _triangle_normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length <= _EPSILON:
        return 0.0, 1.0, 0.0
    return nx / length, ny / length, nz / length


def _surface_triangles(shape: Polygon, z: float, *, reverse: bool = False) -> list[Triangle]:
    result: list[Triangle] = []
    for triangle in triangulate(shape):
        if triangle.area <= _EPSILON or not shape.covers(triangle):
            continue
        coords = list(triangle.exterior.coords)[:3]
        face: Triangle = (
            (float(coords[0][0]), float(coords[0][1]), z),
            (float(coords[1][0]), float(coords[1][1]), z),
            (float(coords[2][0]), float(coords[2][1]), z),
        )
        if reverse:
            face = (face[0], face[2], face[1])
        result.append(face)
    return result


def _extrude_shape(shape: Polygon, bottom_z: float, top_z: float) -> list[Triangle]:
    triangles = _surface_triangles(shape, top_z)
    triangles.extend(_surface_triangles(shape, bottom_z, reverse=True))
    coords = list(shape.exterior.coords)
    for first, second in zip(coords, coords[1:], strict=True):
        x1, y1 = float(first[0]), float(first[1])
        x2, y2 = float(second[0]), float(second[1])
        triangles.extend(
            [
                ((x1, y1, bottom_z), (x2, y2, bottom_z), (x2, y2, top_z)),
                ((x1, y1, bottom_z), (x2, y2, top_z), (x1, y1, top_z)),
            ]
        )
    return triangles


def _point_on_segment(point: tuple[float, float], segment: LineString) -> bool:
    return segment.distance(Point(point)) <= 1e-6


def _gable_roof_triangles(
    footprint: Polygon,
    *,
    eave_z: float,
    ridge_z: float,
    ridge_start: tuple[float, float],
    ridge_end: tuple[float, float],
) -> tuple[list[Triangle], list[str]]:
    warnings: list[str] = []
    ridge = LineString([ridge_start, ridge_end])
    if ridge.length <= _EPSILON:
        return [], ["gable_ridge_has_zero_length"]

    min_x, min_y, max_x, max_y = footprint.bounds
    extent = max(max_x - min_x, max_y - min_y, ridge.length, 1.0) * 8.0
    dx = (ridge_end[0] - ridge_start[0]) / ridge.length
    dy = (ridge_end[1] - ridge_start[1]) / ridge.length
    cutter = LineString(
        [
            (ridge_start[0] - dx * extent, ridge_start[1] - dy * extent),
            (ridge_end[0] + dx * extent, ridge_end[1] + dy * extent),
        ]
    )
    parts = [geometry for geometry in split(footprint, cutter).geoms if isinstance(geometry, Polygon)]
    if len(parts) < 2:
        return [], ["gable_ridge_does_not_split_footprint"]

    triangles: list[Triangle] = []
    for part in parts:
        for triangle in triangulate(part):
            if triangle.area <= _EPSILON or not part.covers(triangle):
                continue
            coords = list(triangle.exterior.coords)[:3]
            points: list[Vec3] = []
            for x_value, y_value in coords:
                xy = (float(x_value), float(y_value))
                z_value = ridge_z if _point_on_segment(xy, ridge) else eave_z
                points.append((xy[0], xy[1], z_value))
            triangles.append((points[0], points[1], points[2]))

    boundary_coords = list(footprint.exterior.coords)
    for ridge_point in (ridge_start, ridge_end):
        matching_edge: tuple[tuple[float, float], tuple[float, float]] | None = None
        for first, second in zip(boundary_coords, boundary_coords[1:], strict=True):
            edge = LineString([first, second])
            if _point_on_segment(ridge_point, edge):
                matching_edge = (
                    (float(first[0]), float(first[1])),
                    (float(second[0]), float(second[1])),
                )
                break
        if matching_edge is None:
            warnings.append("gable_ridge_endpoint_not_on_footprint_boundary")
            continue
        first, second = matching_edge
        triangles.append(
            (
                (first[0], first[1], eave_z),
                (second[0], second[1], eave_z),
                (ridge_point[0], ridge_point[1], ridge_z),
            )
        )
    return triangles, warnings


def _hip_roof_triangles(
    footprint: Polygon,
    *,
    eave_z: float,
    ridge_z: float,
) -> tuple[list[Triangle], list[str]]:
    if not footprint.equals(footprint.convex_hull):
        return [], ["concave_hip_roof_requires_richer_roof_geometry"]
    apex = footprint.representative_point()
    apex_point = (float(apex.x), float(apex.y), ridge_z)
    coords = list(footprint.exterior.coords)
    triangles: list[Triangle] = []
    for first, second in zip(coords, coords[1:], strict=True):
        triangles.append(
            (
                (float(first[0]), float(first[1]), eave_z),
                (float(second[0]), float(second[1]), eave_z),
                apex_point,
            )
        )
    return triangles, []


def _materials(package: ArchitecturePackage) -> list[dict]:
    facade_name = package.appearance.primary_material or "canonical facade"
    roof_name = package.appearance.roof_material or "canonical roof"
    accent_name = (
        package.appearance.accent_materials[0]
        if package.appearance.accent_materials
        else "canonical exterior"
    )
    return [
        {
            "name": facade_name,
            "doubleSided": True,
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.72, 0.68, 0.60, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.78,
            },
        },
        {
            "name": roof_name,
            "doubleSided": True,
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.18, 0.18, 0.19, 1.0],
                "metallicFactor": 0.05,
                "roughnessFactor": 0.72,
            },
        },
        {
            "name": accent_name,
            "doubleSided": True,
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.46, 0.39, 0.30, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.82,
            },
        },
        {
            "name": "water",
            "doubleSided": True,
            "alphaMode": "BLEND",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.18, 0.52, 0.72, 0.72],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.18,
            },
        },
    ]


def _pack_floats(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def _pad(data: bytes, fill: bytes) -> bytes:
    padding = (-len(data)) % 4
    return data if padding == 0 else data + fill * padding


class CanonicalGlbBuilder:
    """Build deterministic glTF 2.0 massing directly from canonical world geometry.

    The builder intentionally does not infer facade openings or photoreal textures that are absent
    from ArchitecturePackage. It produces real mesh geometry in meters and records any roof fidelity
    limits in GLB asset extras so a richer Blender renderer can replace this adapter later without
    changing the canonical input contract.
    """

    def build(self, package: ArchitecturePackage) -> GlbBuildResult:
        primitives: list[_Primitive] = []
        warnings: list[str] = []
        levels = sorted(package.geometry.levels, key=lambda item: item.z)

        for level in levels:
            shape = _source_polygon(level.footprint)
            triangles = _extrude_shape(shape, level.z, level.z + level.height)
            primitives.append(
                _Primitive(
                    name=f"level:{level.id}",
                    material_index=0,
                    triangles=tuple(triangles),
                )
            )

        for item in package.geometry.external_objects:
            shape = _source_polygon(item.polygon)
            height = max(item.height, 0.05)
            material_index = 3 if item.type == ExternalObjectType.POOL else 2
            primitives.append(
                _Primitive(
                    name=f"external:{item.id}",
                    material_index=material_index,
                    triangles=tuple(_extrude_shape(shape, item.z, item.z + height)),
                )
            )

        roof = package.geometry.roof
        if roof is not None:
            footprint = _source_polygon(levels[-1].footprint)
            roof_triangles: list[Triangle] = []
            roof_warnings: list[str] = []
            if roof.type == RoofType.FLAT:
                roof_shape = footprint
                if roof.overhang_m > 0:
                    buffered = footprint.buffer(roof.overhang_m, join_style="mitre")
                    if isinstance(buffered, Polygon):
                        roof_shape = buffered
                    else:
                        roof_warnings.append("flat_roof_overhang_buffer_is_not_single_polygon")
                roof_triangles = _extrude_shape(roof_shape, roof.eave_z, roof.eave_z + 0.15)
            elif roof.type == RoofType.GABLE:
                if roof.ridge_start is None or roof.ridge_end is None:
                    roof_warnings.append("gable_roof_missing_ridge")
                else:
                    roof_triangles, roof_warnings = _gable_roof_triangles(
                        footprint,
                        eave_z=roof.eave_z,
                        ridge_z=roof.ridge_z,
                        ridge_start=(roof.ridge_start.x, roof.ridge_start.y),
                        ridge_end=(roof.ridge_end.x, roof.ridge_end.y),
                    )
                    if roof.overhang_m > 0:
                        roof_warnings.append("pitched_roof_overhang_not_meshed_in_canonical_v1")
            else:
                roof_triangles, roof_warnings = _hip_roof_triangles(
                    footprint,
                    eave_z=roof.eave_z,
                    ridge_z=roof.ridge_z,
                )
                if roof.overhang_m > 0:
                    roof_warnings.append("pitched_roof_overhang_not_meshed_in_canonical_v1")
            warnings.extend(roof_warnings)
            if roof_triangles:
                primitives.append(
                    _Primitive(
                        name="roof",
                        material_index=1,
                        triangles=tuple(roof_triangles),
                    )
                )

        primitives = [primitive for primitive in primitives if primitive.triangles]
        if not primitives:
            raise ValueError("Architecture package produced no mesh geometry.")

        return self._encode(package, primitives, tuple(dict.fromkeys(warnings)))

    def _encode(
        self,
        package: ArchitecturePackage,
        primitives: list[_Primitive],
        warnings: tuple[str, ...],
    ) -> GlbBuildResult:
        binary = bytearray()
        buffer_views: list[dict] = []
        accessors: list[dict] = []
        meshes: list[dict] = []
        nodes: list[dict] = []

        for primitive in primitives:
            position_values: list[float] = []
            normal_values: list[float] = []
            position_vectors: list[Vec3] = []
            for source_triangle in primitive.triangles:
                triangle = tuple(_to_gltf(point) for point in source_triangle)
                normal = _triangle_normal(triangle[0], triangle[1], triangle[2])
                for point in triangle:
                    position_vectors.append(point)
                    position_values.extend(point)
                    normal_values.extend(normal)

            position_blob = _pack_floats(position_values)
            position_offset = len(binary)
            binary.extend(position_blob)
            while len(binary) % 4:
                binary.append(0)
            position_view = len(buffer_views)
            buffer_views.append(
                {
                    "buffer": 0,
                    "byteOffset": position_offset,
                    "byteLength": len(position_blob),
                    "target": _ARRAY_BUFFER_TARGET,
                }
            )
            xs = [point[0] for point in position_vectors]
            ys = [point[1] for point in position_vectors]
            zs = [point[2] for point in position_vectors]
            position_accessor = len(accessors)
            accessors.append(
                {
                    "bufferView": position_view,
                    "componentType": _FLOAT_COMPONENT_TYPE,
                    "count": len(position_vectors),
                    "type": "VEC3",
                    "min": [min(xs), min(ys), min(zs)],
                    "max": [max(xs), max(ys), max(zs)],
                }
            )

            normal_blob = _pack_floats(normal_values)
            normal_offset = len(binary)
            binary.extend(normal_blob)
            while len(binary) % 4:
                binary.append(0)
            normal_view = len(buffer_views)
            buffer_views.append(
                {
                    "buffer": 0,
                    "byteOffset": normal_offset,
                    "byteLength": len(normal_blob),
                    "target": _ARRAY_BUFFER_TARGET,
                }
            )
            normal_accessor = len(accessors)
            accessors.append(
                {
                    "bufferView": normal_view,
                    "componentType": _FLOAT_COMPONENT_TYPE,
                    "count": len(position_vectors),
                    "type": "VEC3",
                }
            )

            mesh_index = len(meshes)
            meshes.append(
                {
                    "name": primitive.name,
                    "primitives": [
                        {
                            "attributes": {
                                "POSITION": position_accessor,
                                "NORMAL": normal_accessor,
                            },
                            "material": primitive.material_index,
                            "mode": _TRIANGLES_MODE,
                        }
                    ],
                }
            )
            nodes.append({"name": primitive.name, "mesh": mesh_index})

        document = {
            "asset": {
                "version": "2.0",
                "generator": "AuRoom CanonicalGlbBuilder",
                "extras": {
                    "source": "canonical-geometry",
                    "schema_version": package.schema_version,
                    "coordinate_mapping": "architecture(x,y,z)->gltf(x,z,-y)",
                    "warnings": list(warnings),
                },
            },
            "scene": 0,
            "scenes": [{"name": "AuRoom canonical architecture", "nodes": list(range(len(nodes)))}],
            "nodes": nodes,
            "meshes": meshes,
            "materials": _materials(package),
            "buffers": [{"byteLength": len(binary)}],
            "bufferViews": buffer_views,
            "accessors": accessors,
        }
        json_blob = _pad(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            b" ",
        )
        binary_blob = _pad(bytes(binary), b"\x00")
        total_length = 12 + 8 + len(json_blob) + 8 + len(binary_blob)
        header = struct.pack("<4sII", b"glTF", 2, total_length)
        json_chunk = struct.pack("<II", len(json_blob), _JSON_CHUNK_TYPE) + json_blob
        binary_chunk = struct.pack("<II", len(binary_blob), _BIN_CHUNK_TYPE) + binary_blob
        return GlbBuildResult(
            data=header + json_chunk + binary_chunk,
            warnings=warnings,
            mesh_count=len(meshes),
        )
