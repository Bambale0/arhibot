from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

_LEGACY_RENDER_WIDTH = 1024
_LEGACY_RENDER_HEIGHT = 768


def _args() -> tuple[Path, Path, Path | None]:
    if "--" not in sys.argv:
        raise RuntimeError("Expected Blender script arguments after --")
    values = sys.argv[sys.argv.index("--") + 1 :]
    if len(values) not in {2, 3}:
        raise RuntimeError("Expected input GLB, output PNG and optional render config paths")
    config_path = Path(values[2]) if len(values) == 3 else None
    return Path(values[0]), Path(values[1]), config_path


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def _scene_bounds() -> tuple[Vector, Vector]:
    points: list[Vector] = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or not obj.bound_box:
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        raise RuntimeError("Imported GLB contains no mesh bounds")
    minimum = Vector(
        (min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))
    )
    maximum = Vector(
        (max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))
    )
    return minimum, maximum


def _look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _set_principled_input(principled, names: tuple[str, ...], value) -> None:
    for name in names:
        socket = principled.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return


def _build_material(name: str, spec: dict) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    color = tuple(float(value) for value in spec["base_color"])
    material.diffuse_color = color
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        _set_principled_input(principled, ("Base Color",), color)
        _set_principled_input(principled, ("Metallic",), float(spec.get("metallic", 0.0)))
        _set_principled_input(principled, ("Roughness",), float(spec.get("roughness", 0.5)))
        _set_principled_input(principled, ("IOR",), float(spec.get("ior", 1.45)))
        _set_principled_input(
            principled,
            ("Transmission Weight", "Transmission"),
            float(spec.get("transmission", 0.0)),
        )
        _set_principled_input(principled, ("Alpha",), float(spec.get("alpha", color[3])))

    alpha = float(spec.get("alpha", color[3]))
    if alpha < 0.999:
        if hasattr(material, "surface_render_method"):
            try:
                material.surface_render_method = "DITHERED"
            except (AttributeError, TypeError, ValueError):
                pass
        if hasattr(material, "blend_method"):
            try:
                material.blend_method = "BLEND"
            except (AttributeError, TypeError, ValueError):
                pass
        if hasattr(material, "use_screen_refraction"):
            material.use_screen_refraction = True
        if hasattr(material, "show_transparent_back"):
            material.show_transparent_back = True
    return material


def _matches_canonical_name(obj: bpy.types.Object, canonical_name: str) -> bool:
    candidates = [obj.name]
    if obj.data is not None and hasattr(obj.data, "name"):
        candidates.append(obj.data.name)
    return any(
        name == canonical_name or name.startswith(f"{canonical_name}.") for name in candidates
    )


def _apply_role_materials(config: dict) -> dict[str, bpy.types.Material]:
    materials = {
        role: _build_material(f"AuRoom {role}", spec)
        for role, spec in config["materials"].items()
    }
    for canonical_name, role in config["object_roles"].items():
        target_material = materials.get(role)
        if target_material is None:
            raise RuntimeError(f"Unknown material role in render config: {role}")
        matched = False
        for obj in bpy.context.scene.objects:
            if obj.type != "MESH" or not _matches_canonical_name(obj, canonical_name):
                continue
            obj.data.materials.clear()
            obj.data.materials.append(target_material)
            matched = True
        if not matched:
            print(f"AuRoom renderer warning: object role target was not found: {canonical_name}")
    return materials


def _add_ground_legacy(center: Vector, minimum: Vector, maximum: Vector) -> None:
    extent = max(maximum.x - minimum.x, maximum.y - minimum.y, 1.0)
    bpy.ops.mesh.primitive_plane_add(
        size=extent * 4.0,
        location=(center.x, center.y, minimum.z - 0.01),
    )
    ground = bpy.context.object
    ground.name = "AuRoom ground"
    material = bpy.data.materials.new("AuRoom ground material")
    material.diffuse_color = (0.11, 0.12, 0.11, 1.0)
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = (0.11, 0.12, 0.11, 1.0)
        principled.inputs["Roughness"].default_value = 0.92
    ground.data.materials.append(material)


def _add_ground_v2(
    center: Vector,
    minimum: Vector,
    maximum: Vector,
    material: bpy.types.Material,
) -> None:
    extent = max(maximum.x - minimum.x, maximum.y - minimum.y, 1.0)
    bpy.ops.mesh.primitive_plane_add(
        size=extent * 4.5,
        location=(center.x, center.y, minimum.z - 0.015),
    )
    ground = bpy.context.object
    ground.name = "AuRoom ground"
    ground.data.materials.append(material)


def _add_area_light(
    name: str,
    location: Vector,
    target: Vector,
    energy: float,
    size: float,
) -> None:
    light_data = bpy.data.lights.new(name=name, type="AREA")
    light_data.energy = energy
    light_data.shape = "DISK"
    light_data.size = size
    light = bpy.data.objects.new(name, light_data)
    bpy.context.collection.objects.link(light)
    light.location = location
    _look_at(light, target)


def _add_sun(target: Vector, *, energy: float = 2.0, angle: float = 0.12) -> None:
    light_data = bpy.data.lights.new(name="AuRoom sun", type="SUN")
    light_data.energy = energy
    light_data.angle = angle
    light = bpy.data.objects.new("AuRoom sun", light_data)
    bpy.context.collection.objects.link(light)
    light.location = target + Vector((8.0, -10.0, 14.0))
    _look_at(light, target)


def _add_camera_legacy(center: Vector, minimum: Vector, maximum: Vector) -> None:
    size = maximum - minimum
    extent = max(size.x, size.y, size.z, 1.0)
    target = center + Vector((0.0, 0.0, size.z * 0.08))
    camera_data = bpy.data.cameras.new("AuRoom camera")
    camera_data.lens = 48.0
    camera = bpy.data.objects.new("AuRoom camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = target + Vector((extent * 1.15, -extent * 1.45, extent * 0.92))
    _look_at(camera, target)
    bpy.context.scene.camera = camera


def _add_camera_v2(center: Vector, minimum: Vector, maximum: Vector, config: dict) -> None:
    size = maximum - minimum
    extent = max(size.x, size.y, size.z, 1.0)
    camera_config = config["camera"]
    target = center + Vector(
        (0.0, 0.0, size.z * float(camera_config["target_height_factor"]))
    )
    offset = camera_config["offset"]
    camera_data = bpy.data.cameras.new("AuRoom camera")
    camera_data.lens = float(camera_config["lens_mm"])
    camera_data.sensor_width = 36.0
    camera = bpy.data.objects.new("AuRoom camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = target + Vector(
        (
            extent * float(offset[0]),
            extent * float(offset[1]),
            extent * float(offset[2]),
        )
    )
    _look_at(camera, target)
    bpy.context.scene.camera = camera


def _configure_world_legacy() -> None:
    world = (
        bpy.data.worlds.new("AuRoom world")
        if bpy.context.scene.world is None
        else bpy.context.scene.world
    )
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.055, 0.065, 0.085, 1.0)
        background.inputs["Strength"].default_value = 0.45


def _configure_world_v2(config: dict) -> None:
    world = (
        bpy.data.worlds.new("AuRoom world")
        if bpy.context.scene.world is None
        else bpy.context.scene.world
    )
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    lighting = config["lighting"]
    if background is not None:
        background.inputs["Color"].default_value = tuple(lighting["world_color"])
        background.inputs["Strength"].default_value = float(lighting["world_strength"])


def _set_high_contrast_look(scene) -> None:
    for candidate in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            scene.view_settings.look = candidate
            return
        except (AttributeError, TypeError, ValueError):
            continue


def _configure_render_legacy(output_path: Path) -> None:
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = _LEGACY_RENDER_WIDTH
    scene.render.resolution_y = _LEGACY_RENDER_HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(output_path)


def _configure_render_v2(output_path: Path, config: dict) -> None:
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    render = config["render"]
    if hasattr(scene, "eevee"):
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = int(render["samples"])
        if hasattr(scene.eevee, "use_gtao"):
            scene.eevee.use_gtao = True
        if hasattr(scene.eevee, "gtao_distance"):
            scene.eevee.gtao_distance = 3.0
        if hasattr(scene.eevee, "gtao_factor"):
            scene.eevee.gtao_factor = 1.2
    scene.render.resolution_x = int(render["width"])
    scene.render.resolution_y = int(render["height"])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(output_path)
    scene.view_settings.exposure = float(render["exposure"])
    _set_high_contrast_look(scene)


def _load_v2_config(config_path: Path) -> dict:
    if not config_path.is_file():
        raise RuntimeError(f"Render config does not exist: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise RuntimeError("Unsupported Blender render config schema")
    if config.get("renderer_profile") != "blender_eevee_v2":
        raise RuntimeError("Unsupported Blender renderer profile")
    required = {"camera", "materials", "object_roles", "lighting", "render"}
    if not required.issubset(config):
        raise RuntimeError("Blender render config is incomplete")
    return config


def _render_legacy(input_path: Path, output_path: Path) -> None:
    _clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(input_path))
    minimum, maximum = _scene_bounds()
    center = (minimum + maximum) * 0.5
    extent = max(maximum.x - minimum.x, maximum.y - minimum.y, 1.0)

    _configure_world_legacy()
    _add_ground_legacy(center, minimum, maximum)
    _add_camera_legacy(center, minimum, maximum)
    _add_sun(center)
    _add_area_light(
        "AuRoom key",
        center + Vector((-extent * 0.8, -extent * 0.7, extent * 1.4)),
        center,
        1500.0,
        extent * 0.75,
    )
    _add_area_light(
        "AuRoom fill",
        center + Vector((extent * 0.9, extent * 0.5, extent * 0.8)),
        center,
        800.0,
        extent * 0.6,
    )
    _configure_render_legacy(output_path)
    bpy.ops.render.render(write_still=True)


def _render_v2(input_path: Path, output_path: Path, config: dict) -> None:
    _clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(input_path))
    minimum, maximum = _scene_bounds()
    center = (minimum + maximum) * 0.5
    extent = max(maximum.x - minimum.x, maximum.y - minimum.y, 1.0)

    materials = _apply_role_materials(config)
    _configure_world_v2(config)
    _add_ground_v2(center, minimum, maximum, materials["ground"])
    _add_camera_v2(center, minimum, maximum, config)
    lighting = config["lighting"]
    _add_sun(
        center,
        energy=float(lighting["sun_energy"]),
        angle=float(lighting["sun_angle"]),
    )
    _add_area_light(
        "AuRoom key",
        center + Vector((-extent * 0.8, -extent * 0.7, extent * 1.4)),
        center,
        float(lighting["key_energy"]),
        extent * 0.78,
    )
    _add_area_light(
        "AuRoom fill",
        center + Vector((extent * 0.9, extent * 0.5, extent * 0.8)),
        center,
        float(lighting["fill_energy"]),
        extent * 0.62,
    )
    _configure_render_v2(output_path, config)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    input_path, output_path, config_path = _args()
    if not input_path.is_file():
        raise RuntimeError(f"Input GLB does not exist: {input_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path is None:
        _render_legacy(input_path, output_path)
        return
    _render_v2(input_path, output_path, _load_v2_config(config_path))


if __name__ == "__main__":
    main()
