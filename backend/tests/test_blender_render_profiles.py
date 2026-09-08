from app.architecture.schemas import ArchitecturePackage
from app.domain.architecture.enums import ArchitectureCameraProfile
from app.renderers.blender_profiles import build_blender_v2_config
from app.services.architecture_render_service import (
    digest_architecture_payload,
    snapshot_architecture,
)


def _package_payload() -> dict:
    return {
        "schema_version": "1.0",
        "appearance": {
            "architecture_style": "modern",
            "pbr_materials": {
                "facade": "graphite_panel",
                "roof": "dark_metal",
                "accent": "natural_oak",
                "glazing": "smoked_glass",
            },
        },
        "geometry": {
            "levels": [
                {
                    "id": "ground",
                    "label": "Ground floor",
                    "z": 0,
                    "height": 3.2,
                    "footprint": {
                        "points": [
                            {"x": 0, "y": 0},
                            {"x": 10, "y": 0},
                            {"x": 10, "y": 8},
                            {"x": 0, "y": 8},
                        ]
                    },
                    "openings": [
                        {
                            "id": "window_1",
                            "kind": "window",
                            "edge_index": 0,
                            "offset_m": 1.0,
                            "width_m": 2.0,
                            "sill_height_m": 0.9,
                            "height_m": 1.5,
                        },
                        {
                            "id": "entry",
                            "kind": "door",
                            "edge_index": 0,
                            "offset_m": 6.0,
                            "width_m": 1.1,
                            "sill_height_m": 0.0,
                            "height_m": 2.2,
                        },
                    ],
                }
            ],
            "external_objects": [
                {
                    "id": "pool",
                    "label": "Pool",
                    "type": "pool",
                    "z": 0,
                    "height": 0.05,
                    "polygon": {
                        "points": [
                            {"x": 12, "y": 0},
                            {"x": 16, "y": 0},
                            {"x": 16, "y": 3},
                            {"x": 12, "y": 3},
                        ]
                    },
                },
                {
                    "id": "terrace",
                    "label": "Terrace",
                    "type": "terrace",
                    "z": 0,
                    "height": 0.15,
                    "polygon": {
                        "points": [
                            {"x": 0, "y": 9},
                            {"x": 5, "y": 9},
                            {"x": 5, "y": 11},
                            {"x": 0, "y": 11},
                        ]
                    },
                },
            ],
            "roof": {
                "type": "flat",
                "eave_z": 3.2,
                "ridge_z": 3.2,
                "overhang_m": 0.4,
            },
        },
    }


def test_blender_v2_profile_resolves_materials_and_object_roles() -> None:
    package = ArchitecturePackage.model_validate(_package_payload())
    config = build_blender_v2_config(package, ArchitectureCameraProfile.HERO_CORNER)

    assert config["renderer_profile"] == "blender_eevee_v2"
    assert config["camera_profile"] == "hero_corner"
    assert config["camera"]["offset"] == [1.15, -1.45, 0.92]
    assert config["render"]["width"] == 1280
    assert config["render"]["height"] == 960

    assert config["object_roles"]["level:ground"] == "facade"
    assert config["object_roles"]["opening:ground:window_1"] == "glazing"
    assert config["object_roles"]["opening:ground:entry"] == "door"
    assert config["object_roles"]["external:pool"] == "water"
    assert config["object_roles"]["external:terrace"] == "accent"
    assert config["object_roles"]["roof"] == "roof"

    assert config["materials"]["facade"]["metallic"] == 0.18
    assert config["materials"]["roof"]["metallic"] == 0.68
    assert config["materials"]["glazing"]["alpha"] == 0.42
    assert config["materials"]["door"]["base_color"] != config["materials"]["accent"][
        "base_color"
    ]


def test_camera_profiles_are_deterministic_and_distinct() -> None:
    package = ArchitecturePackage.model_validate(_package_payload())
    hero = build_blender_v2_config(package, ArchitectureCameraProfile.HERO_CORNER)
    reverse = build_blender_v2_config(package, ArchitectureCameraProfile.REVERSE_CORNER)
    elevated = build_blender_v2_config(package, ArchitectureCameraProfile.ELEVATED)

    assert hero["camera"]["offset"] != reverse["camera"]["offset"]
    assert hero["camera"]["offset"] != elevated["camera"]["offset"]
    assert elevated["camera"]["offset"][2] > hero["camera"]["offset"][2]
    assert elevated["camera"]["lens_mm"] > hero["camera"]["lens_mm"]


def test_raw_snapshot_digest_survives_schema_default_evolution() -> None:
    old_payload = _package_payload()
    old_payload["appearance"] = {"architecture_style": "modern"}
    raw_digest = digest_architecture_payload(old_payload)

    upgraded = ArchitecturePackage.model_validate(old_payload)
    upgraded_payload, upgraded_digest = snapshot_architecture(upgraded)

    assert "pbr_materials" in upgraded_payload["appearance"]
    assert digest_architecture_payload(old_payload) == raw_digest
    assert upgraded_digest != raw_digest
