import json
import struct

from shapely.geometry import Point, Polygon

from app.architecture.facade import build_level_facade_mesh
from app.architecture.glb import CanonicalGlbBuilder
from app.architecture.rendering import MassingRenderer, PlanSheetRenderer
from app.architecture.schemas import ArchitecturePackage
from app.architecture.validation import GeometryValidator


def _package() -> ArchitecturePackage:
    return ArchitecturePackage.model_validate(
        {
            "program": {
                "living_area_sqm": 320,
                "bedrooms": 5,
                "bathrooms": 4,
                "storeys": 2,
                "garage_cars": 2,
            },
            "appearance": {
                "architecture_style": "fachwerk",
                "primary_material": "brick",
                "accent_materials": ["stone", "planken"],
                "glazing": "low-e glass",
                "lighting": "warmSunset",
            },
            "geometry": {
                "levels": [
                    {
                        "id": "ground",
                        "label": "GROUND FLOOR",
                        "z": 0,
                        "height": 3.2,
                        "footprint": {
                            "points": [
                                {"x": 0, "y": 0},
                                {"x": 14, "y": 0},
                                {"x": 14, "y": 7},
                                {"x": 20, "y": 7},
                                {"x": 20, "y": 16},
                                {"x": 0, "y": 16},
                            ]
                        },
                        "rooms": [
                            {
                                "id": "garage",
                                "name": "Garage",
                                "kind": "vehicle",
                                "polygon": {
                                    "points": [
                                        {"x": 0, "y": 9},
                                        {"x": 7, "y": 9},
                                        {"x": 7, "y": 16},
                                        {"x": 0, "y": 16},
                                    ]
                                },
                            },
                            {
                                "id": "living",
                                "name": "Living room",
                                "kind": "living",
                                "polygon": {
                                    "points": [
                                        {"x": 7, "y": 9},
                                        {"x": 14, "y": 9},
                                        {"x": 14, "y": 16},
                                        {"x": 7, "y": 16},
                                    ]
                                },
                            },
                        ],
                        "openings": [
                            {
                                "id": "living_window",
                                "kind": "window",
                                "edge_index": 0,
                                "offset_m": 2.0,
                                "width_m": 2.4,
                                "sill_height_m": 0.9,
                                "height_m": 1.5,
                            },
                            {
                                "id": "clerestory",
                                "kind": "window",
                                "edge_index": 0,
                                "offset_m": 2.4,
                                "width_m": 1.2,
                                "sill_height_m": 2.55,
                                "height_m": 0.45,
                            },
                            {
                                "id": "front_door",
                                "kind": "door",
                                "edge_index": 0,
                                "offset_m": 10.5,
                                "width_m": 1.1,
                                "sill_height_m": 0.0,
                                "height_m": 2.2,
                            },
                        ],
                    },
                    {
                        "id": "second",
                        "label": "SECOND FLOOR",
                        "z": 3.2,
                        "height": 3.0,
                        "footprint": {
                            "points": [
                                {"x": 0, "y": 0},
                                {"x": 14, "y": 0},
                                {"x": 14, "y": 7},
                                {"x": 20, "y": 7},
                                {"x": 20, "y": 16},
                                {"x": 0, "y": 16},
                            ]
                        },
                        "rooms": [],
                    },
                ],
                "external_objects": [
                    {
                        "id": "pool",
                        "label": "Outdoor pool",
                        "type": "pool",
                        "z": 0,
                        "height": 0.05,
                        "polygon": {
                            "points": [
                                {"x": 14, "y": -6},
                                {"x": 20, "y": -6},
                                {"x": 20, "y": -1},
                                {"x": 14, "y": -1},
                            ]
                        },
                    },
                    {
                        "id": "veranda",
                        "label": "Glazed veranda",
                        "type": "veranda",
                        "level_id": "ground",
                        "z": 0,
                        "height": 3.0,
                        "polygon": {
                            "points": [
                                {"x": 14, "y": 2},
                                {"x": 20, "y": 2},
                                {"x": 20, "y": 7},
                                {"x": 14, "y": 7},
                            ]
                        },
                    },
                ],
                "roof": {
                    "type": "gable",
                    "eave_z": 6.2,
                    "ridge_z": 9.2,
                    "ridge_start": {"x": 7, "y": 0},
                    "ridge_end": {"x": 7, "y": 16},
                    "overhang_m": 0.5,
                },
            },
        }
    )


def _glb_document(data: bytes) -> dict:
    magic, version, declared_length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF"
    assert version == 2
    assert declared_length == len(data)
    json_length, json_type = struct.unpack_from("<II", data, 12)
    assert json_type == 0x4E4F534A
    return json.loads(data[20 : 20 + json_length].decode("utf-8").rstrip(" "))


def test_valid_geometry_is_one_source_for_plan_and_massing() -> None:
    package = _package()
    report = GeometryValidator().validate(package.geometry, package=package)

    assert report.valid is True
    assert report.level_areas_sqm["ground"] == 278.0
    assert report.room_areas_sqm["ground:garage"] == 49.0

    plan = PlanSheetRenderer().render(package)
    massing = MassingRenderer().render(package)
    assert 'data-source="canonical-geometry"' in plan
    assert 'data-source="canonical-geometry"' in massing
    assert "GROUND FLOOR" in plan
    assert "SECOND FLOOR" in plan
    assert "OUTDOOR POOL" in plan
    assert "49.0 SQ M" in plan
    assert "GEOMETRY-LOCKED MASSING" in massing


def test_canonical_geometry_exports_real_binary_gltf_mesh() -> None:
    result = CanonicalGlbBuilder().build(_package())
    document = _glb_document(result.data)

    assert document["asset"]["version"] == "2.0"
    assert document["asset"]["extras"]["source"] == "canonical-geometry"
    assert document["asset"]["extras"]["coordinate_mapping"] == (
        "architecture(x,y,z)->gltf(x,z,-y)"
    )
    assert document["asset"]["extras"]["opening_count"] == 3
    assert document["buffers"][0]["byteLength"] > 0
    assert result.mesh_count == len(document["meshes"])
    mesh_names = {mesh["name"] for mesh in document["meshes"]}
    assert {
        "level:ground",
        "level:second",
        "opening:ground:living_window",
        "opening:ground:clerestory",
        "opening:ground:front_door",
        "external:pool",
        "external:veranda",
        "roof",
    } <= mesh_names
    assert "pitched_roof_overhang_not_meshed_in_canonical_v1" in result.warnings

    ground_position_accessor = document["accessors"][0]
    assert ground_position_accessor["min"] == [0.0, 0.0, -16.0]
    assert ground_position_accessor["max"] == [20.0, 3.2, 0.0]

    window_mesh = next(
        mesh for mesh in document["meshes"] if mesh["name"] == "opening:ground:living_window"
    )
    window_material = document["materials"][window_mesh["primitives"][0]["material"]]
    assert window_material["name"] == "low-e glass"
    assert window_material["alphaMode"] == "BLEND"


def test_facade_mesh_removes_wall_surface_behind_explicit_openings() -> None:
    level = _package().geometry.levels[0]
    facade = build_level_facade_mesh(level)
    window_center = Point(3.2, 1.65)

    front_wall_triangles = [
        triangle
        for triangle in facade.wall_triangles
        if all(abs(vertex[1]) < 1e-9 for vertex in triangle)
    ]
    assert front_wall_triangles
    for triangle in front_wall_triangles:
        wall_triangle = Polygon([(vertex[0], vertex[2]) for vertex in triangle])
        assert not wall_triangle.buffer(1e-9).contains(window_center)

    opening_ids = {surface.opening_id for surface in facade.opening_surfaces}
    assert opening_ids == {"living_window", "clerestory", "front_door"}


def test_room_outside_footprint_is_rejected() -> None:
    package = _package()
    package.geometry.levels[0].rooms[0].polygon.points[0].x = -3

    report = GeometryValidator().validate(package.geometry, package=package)

    assert report.valid is False
    assert any(issue.code == "room_outside_footprint" for issue in report.issues)


def test_pool_cannot_intersect_building() -> None:
    package = _package()
    pool = package.geometry.external_objects[0]
    pool.polygon.points = [
        type(pool.polygon.points[0])(x=10, y=2),
        type(pool.polygon.points[0])(x=16, y=2),
        type(pool.polygon.points[0])(x=16, y=6),
        type(pool.polygon.points[0])(x=10, y=6),
    ]

    report = GeometryValidator().validate(package.geometry, package=package)

    assert report.valid is False
    assert any(issue.code == "pool_intersects_building" for issue in report.issues)


def test_opening_cannot_extend_beyond_its_wall_edge() -> None:
    package = _package()
    package.geometry.levels[0].openings[0].offset_m = 13.0

    report = GeometryValidator().validate(package.geometry, package=package)

    assert report.valid is False
    assert any(issue.code == "opening_outside_wall" for issue in report.issues)


def test_openings_may_stack_but_cannot_overlap_on_same_wall() -> None:
    package = _package()
    valid_report = GeometryValidator().validate(package.geometry, package=package)
    assert valid_report.valid is True

    package.geometry.levels[0].openings[1].sill_height_m = 1.4
    report = GeometryValidator().validate(package.geometry, package=package)

    assert report.valid is False
    assert any(issue.code == "opening_overlap" for issue in report.issues)
