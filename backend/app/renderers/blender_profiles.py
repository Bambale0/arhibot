from __future__ import annotations

from copy import deepcopy

from app.architecture.schemas import (
    AccentMaterialPreset,
    ArchitecturePackage,
    FacadeMaterialPreset,
    GlazingMaterialPreset,
    OpeningKind,
    RoofMaterialPreset,
)
from app.domain.architecture.enums import ArchitectureCameraProfile


_FACADE_MATERIALS: dict[FacadeMaterialPreset, dict] = {
    FacadeMaterialPreset.WHITE_PLASTER: {
        "base_color": [0.82, 0.80, 0.75, 1.0],
        "metallic": 0.0,
        "roughness": 0.78,
    },
    FacadeMaterialPreset.WARM_STONE: {
        "base_color": [0.56, 0.46, 0.35, 1.0],
        "metallic": 0.0,
        "roughness": 0.84,
    },
    FacadeMaterialPreset.RED_BRICK: {
        "base_color": [0.43, 0.20, 0.12, 1.0],
        "metallic": 0.0,
        "roughness": 0.88,
    },
    FacadeMaterialPreset.GRAPHITE_PANEL: {
        "base_color": [0.12, 0.13, 0.14, 1.0],
        "metallic": 0.18,
        "roughness": 0.46,
    },
    FacadeMaterialPreset.WOOD_CLADDING: {
        "base_color": [0.42, 0.26, 0.13, 1.0],
        "metallic": 0.0,
        "roughness": 0.62,
    },
}

_ROOF_MATERIALS: dict[RoofMaterialPreset, dict] = {
    RoofMaterialPreset.DARK_METAL: {
        "base_color": [0.08, 0.09, 0.10, 1.0],
        "metallic": 0.68,
        "roughness": 0.34,
    },
    RoofMaterialPreset.GRAY_MEMBRANE: {
        "base_color": [0.20, 0.22, 0.23, 1.0],
        "metallic": 0.0,
        "roughness": 0.80,
    },
    RoofMaterialPreset.BROWN_TILE: {
        "base_color": [0.25, 0.13, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.74,
    },
}

_ACCENT_MATERIALS: dict[AccentMaterialPreset, dict] = {
    AccentMaterialPreset.NATURAL_OAK: {
        "base_color": [0.43, 0.27, 0.13, 1.0],
        "metallic": 0.0,
        "roughness": 0.58,
    },
    AccentMaterialPreset.CHARCOAL: {
        "base_color": [0.08, 0.09, 0.10, 1.0],
        "metallic": 0.05,
        "roughness": 0.52,
    },
    AccentMaterialPreset.WARM_STONE: {
        "base_color": [0.52, 0.42, 0.31, 1.0],
        "metallic": 0.0,
        "roughness": 0.82,
    },
    AccentMaterialPreset.BLACK_METAL: {
        "base_color": [0.04, 0.05, 0.05, 1.0],
        "metallic": 0.72,
        "roughness": 0.34,
    },
}

_GLAZING_MATERIALS: dict[GlazingMaterialPreset, dict] = {
    GlazingMaterialPreset.CLEAR_GLASS: {
        "base_color": [0.34, 0.52, 0.62, 0.26],
        "metallic": 0.0,
        "roughness": 0.08,
        "transmission": 0.62,
        "ior": 1.45,
        "alpha": 0.26,
    },
    GlazingMaterialPreset.LOW_E_GLASS: {
        "base_color": [0.24, 0.40, 0.50, 0.34],
        "metallic": 0.08,
        "roughness": 0.12,
        "transmission": 0.50,
        "ior": 1.45,
        "alpha": 0.34,
    },
    GlazingMaterialPreset.SMOKED_GLASS: {
        "base_color": [0.12, 0.17, 0.20, 0.42],
        "metallic": 0.08,
        "roughness": 0.16,
        "transmission": 0.34,
        "ior": 1.45,
        "alpha": 0.42,
    },
}

_CAMERA_PROFILES: dict[ArchitectureCameraProfile, dict] = {
    ArchitectureCameraProfile.HERO_CORNER: {
        "offset": [1.15, -1.45, 0.92],
        "lens_mm": 50.0,
        "target_height_factor": 0.08,
    },
    ArchitectureCameraProfile.REVERSE_CORNER: {
        "offset": [-1.15, 1.45, 0.88],
        "lens_mm": 50.0,
        "target_height_factor": 0.08,
    },
    ArchitectureCameraProfile.ELEVATED: {
        "offset": [1.05, -1.25, 1.65],
        "lens_mm": 55.0,
        "target_height_factor": 0.02,
    },
}

_WATER_MATERIAL = {
    "base_color": [0.12, 0.38, 0.56, 0.72],
    "metallic": 0.0,
    "roughness": 0.12,
    "transmission": 0.22,
    "ior": 1.333,
    "alpha": 0.72,
}

_GROUND_MATERIAL = {
    "base_color": [0.12, 0.13, 0.11, 1.0],
    "metallic": 0.0,
    "roughness": 0.92,
}


def _door_material(accent: dict) -> dict:
    result = deepcopy(accent)
    color = result["base_color"]
    result["base_color"] = [
        max(0.0, min(1.0, float(color[0]) * 0.78)),
        max(0.0, min(1.0, float(color[1]) * 0.78)),
        max(0.0, min(1.0, float(color[2]) * 0.78)),
        1.0,
    ]
    result["roughness"] = max(0.28, min(0.78, float(result["roughness"])))
    return result


def build_blender_v2_config(
    package: ArchitecturePackage,
    camera_profile: ArchitectureCameraProfile,
) -> dict:
    palette = package.appearance.pbr_materials
    accent = deepcopy(_ACCENT_MATERIALS[palette.accent])

    object_roles: dict[str, str] = {}
    for level in package.geometry.levels:
        object_roles[f"level:{level.id}"] = "facade"
        for opening in level.openings:
            role = "glazing" if opening.kind == OpeningKind.WINDOW else "door"
            object_roles[f"opening:{level.id}:{opening.id}"] = role
    for item in package.geometry.external_objects:
        object_roles[f"external:{item.id}"] = "water" if item.type.value == "pool" else "accent"
    if package.geometry.roof is not None:
        object_roles["roof"] = "roof"

    return {
        "schema_version": 1,
        "renderer_profile": "blender_eevee_v2",
        "camera_profile": camera_profile.value,
        "camera": deepcopy(_CAMERA_PROFILES[camera_profile]),
        "materials": {
            "facade": deepcopy(_FACADE_MATERIALS[palette.facade]),
            "roof": deepcopy(_ROOF_MATERIALS[palette.roof]),
            "accent": accent,
            "door": _door_material(accent),
            "glazing": deepcopy(_GLAZING_MATERIALS[palette.glazing]),
            "water": deepcopy(_WATER_MATERIAL),
            "ground": deepcopy(_GROUND_MATERIAL),
        },
        "object_roles": object_roles,
        "lighting": {
            "world_color": [0.055, 0.065, 0.085, 1.0],
            "world_strength": 0.48,
            "sun_energy": 2.2,
            "sun_angle": 0.18,
            "key_energy": 1450.0,
            "fill_energy": 720.0,
        },
        "render": {
            "width": 1280,
            "height": 960,
            "samples": 96,
            "exposure": 0.35,
        },
    }
