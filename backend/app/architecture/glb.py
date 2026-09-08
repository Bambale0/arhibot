from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import split, triangulate

from app.architecture.facade import build_level_facade_mesh
from app.architecture.schemas import (
    ArchitecturePackage,
    ExternalObjectType,
    OpeningKind,
    Polygon2D,
    RoofType,
)

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


def _ring_edges(shape: Polygon):
    coords = list(shape.exterior.coords)
    return zip(coords[:-1], coords[1:], strict=True)


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
    for first, second in _ring_edges(shape):
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
    parts = [
        geometry
        for geometry in split(footprint, cutter).geoms
        if isinstance(geometry, Polygon)
    ]
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

    warnings: list[str] = []
    for ridge_point in (ridge_start, ridge_end):
        matching_edge: tuple[tuple[float, float], tuple[float, float]] | None = None
        for first, second in _ring_edges(footprint):
            if _point_on_segment(ridge_point, LineString([first, second])):
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
    triangles: list[Triangle] = []
    for first, second in _ring_edges(footprint):
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
    glazing_name = package.appearance.glazing or "canonical glazing"
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
        {
            "name": glazing_name,
            "doubleSided": True,
            "alphaMode": "BLEND",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.42, 0.65, 0.78, 0.36],
                "metallicFactor": 0.05,
                "roughnessFactor": 0.08,
            },
        },
        {
            "name": f"{accent_name} door",
            "doubleSided": True,
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.30, 0.24, 0.18, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.68,
            },
        },
    ]


def _pack_floats(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def _pad(data: bytes, fill: bytes) -> bytes:
    padding = (-len(data)) % 4
    return data if padding == 0 else data + fill * padding


class CanonicalGlbBuilder:
    """Build deterministic glTF 2.0 geometry directly from canonical world geometry.

    The builder meshes only facade openings explicitly present in ArchitecturePackage and never
    invents windows, doors, decorative details, or photoreal textures that are absent from the
    canonical model. Fidelity limits remain explicit in GLB asset extras so a richer Blender
    renderer can replace this adapter later without changing the canonical input contract.
    """

    def build(self, package: ArchitecturePackage) -> GlbBuildResult:
        primitives: list[_Primitive] = []
        warnings: list[str] = []
        levels = sorted(package.geometry.levels, key=lambda item: item.z)

        for level in levels:
            shape = _source_polygon(level.footprint)
            facade = build_level_facade_mesh(level)
            level_triangles = _surface_triangles(shape, level.z + level.height)
            level_triangles.extend(_surface_triangles(shape, level.z, reverse=True))
            level_triangles.extend(facade.wall_triangles)
            primitives.append(
                _Primitive(
                    name=f"level:{level.id}",
                    material_index=0,
                    triangles=tuple(level_triangles),
                )
            )
            for surface in facade.opening_surfaces:
                material_index = 4 if surface.kind == OpeningKind.WINDOW else 5
                primitives.append(
                    _Primitive(
                        name=f"opening:{level.id}:{surface.opening_id}",
                        material_index=material_index,
                        triangles=surface.triangles,
                    )
                )

        for item in package.geometry.external_objects:
            shape = _source_polygon(item.polygon)
            material_index = 3 if item.type == ExternalObjectType.POOL else 2
            primitives.append(
                _Primitive(
                    name=f"external:{item.id}",
                    material_index=material_index,
                    triangles=tuple(
                        _extrude_shape(shape, item.z, item.z + max(item.height, 0.05))
                    ),
                )
            )

        roof_primitive, roof_warnings = self._roof_primitive(package, levels[-1].footprint)
        warnings.extend(roof_warnings)
        if roof_primitive is not None:
            primitives.append(roof_primitive)

        primitives = [primitive for primitive in primitives if primitive.triangles]
        if not primitives:
            raise ValueError("Architecture package produced no mesh geometry.")
        unique_warnings = tuple(dict.fromkeys(warnings))
        return self._encode(package, primitives, unique_warnings)

    def _roof_primitive(
        self,
        package: ArchitecturePackage,
        top_footprint: Polygon2D,
    ) -> tuple[_Primitive | None, list[str]]:
        roof = package.geometry.roof
        if roof is None:
            return None, []
        footprint = _source_polygon(top_footprint)
        warnings: list[str] = []
        triangles: list[Triangle] = []

        if roof.type == RoofType.FLAT:
            roof_shape = footprint
            if roof.overhang_m > 0:
                buffered = footprint.buffer(roof.overhang_m, join_style="mitre")
                if isinstance(buffered, Polygon):
                    roof_shape = buffered
                else:
                    warnings.append("flat_roof_overhang_buffer_is_not_single_polygon")
            triangles = _extrude_shape(roof_shape, roof.eave_z, roof.eave_z + 0.15)
        elif roof.type == RoofType.GABLE:
            if roof.ridge_start is None or roof.ridge_end is None:
                warnings.append("gable_roof_missing_ridge")
            else:
                triangles, roof_warnings = _gable_roof_triangles(
                    footprint,
                    eave_z=roof.eave_z,
                    ridge_z=roof.ridge_z,
                    ridge_start=(roof.ridge_start.x, roof.ridge_start.y),
                    ridge_end=(roof.ridge_end.x, roof.ridge_end.y),
                )
                warnings.extend(roof_warnings)
                if roof.overhang_m > 0:
                    warnings.append("pitched_roof_overhang_not_meshed_in_canonical_v1")
        else:
            triangles, roof_warnings = _hip_roof_triangles(
                footprint,
                eave_z=roof.eave_z,
                ridge_z=roof.ridge_z,
            )
            warnings.extend(roof_warnings)
            if roof.overhang_m > 0:
                warnings.append("pitched_roof_overhang_not_meshed_in_canonical_v1")

        if not triangles:
            return None, warnings
        return _Primitive(name="roof", material_index=1, triangles=tuple(triangles)), warnings

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
            position_vectors, normal_vectors = self._vertex_data(primitive)
            position_accessor = self._append_vec3_accessor(
                binary,
                buffer_views,
                accessors,
                position_vectors,
                include_bounds=True,
            )
            normal_accessor = self._append_vec3_accessor(
                binary,
                buffer_views,
                accessors,
                normal_vectors,
                include_bounds=False,
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

        opening_count = sum(len(level.openings) for level in package.geometry.levels)
        document = {
            "asset": {
                "version": "2.0",
                "generator": "AuRoom CanonicalGlbBuilder",
                "extras": {
                    "source": "canonical-geometry",
                    "schema_version": package.schema_version,
                    "coordinate_mapping": "architecture(x,y,z)->gltf(x,z,-y)",
                    "opening_count": opening_count,
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

    def _vertex_data(self, primitive: _Primitive) -> tuple[list[Vec3], list[Vec3]]:
        positions: list[Vec3] = []
        normals: list[Vec3] = []
        for source_triangle in primitive.triangles:
            triangle = tuple(_to_gltf(point) for point in source_triangle)
            normal = _triangle_normal(triangle[0], triangle[1], triangle[2])
            positions.extend(triangle)
            normals.extend([normal, normal, normal])
        return positions, normals

    def _append_vec3_accessor(
        self,
        binary: bytearray,
        buffer_views: list[dict],
        accessors: list[dict],
        vectors: list[Vec3],
        *,
        include_bounds: bool,
    ) -> int:
        values = [component for vector in vectors for component in vector]
        blob = _pack_floats(values)
        offset = len(binary)
        binary.extend(blob)
        while len(binary) % 4:
            binary.append(0)

        view_index = len(buffer_views)
        buffer_views.append(
            {
                "buffer": 0,
                "byteOffset": offset,
                "byteLength": len(blob),
                "target": _ARRAY_BUFFER_TARGET,
            }
        )
        accessor: dict = {
            "bufferView": view_index,
            "componentType": _FLOAT_COMPONENT_TYPE,
            "count": len(vectors),
            "type": "VEC3",
        }
        if include_bounds:
            accessor["min"] = [min(vector[index] for vector in vectors) for index in range(3)]
            accessor["max"] = [max(vector[index] for vector in vectors) for index in range(3)]
        accessor_index = len(accessors)
        accessors.append(accessor)
        return accessor_index
