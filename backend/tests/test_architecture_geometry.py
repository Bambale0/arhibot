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
