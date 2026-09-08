from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector

_RENDER_WIDTH = 1024
_RENDER_HEIGHT = 768


def _args() -> tuple[Path, Path]:
    if "--" not in sys.argv:
        raise RuntimeError("Expected Blender script arguments after --")
    values = sys.argv[sys.argv.index("--") + 1 :]
    if len(values) != 2:
        raise RuntimeError("Expected input GLB and output PNG paths")
    return Path(values[0]), Path(values[1])


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
    minimum = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maximum = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return minimum, maximum


def _look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _add_ground(center: Vector, minimum: Vector, maximum: Vector) -> None:
    extent = max(maximum.x - minimum.x, maximum.y - minimum.y, 1.0)
    bpy.ops.mesh.primitive_plane_add(size=extent * 4.0, location=(center.x, center.y, minimum.z - 0.01))
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


def _add_area_light(name: str, location: Vector, target: Vector, energy: float, size: float) -> None:
    light_data = bpy.data.lights.new(name=name, type="AREA")
    light_data.energy = energy
    light_data.shape = "DISK"
    light_data.size = size
    light = bpy.data.objects.new(name, light_data)
    bpy.context.collection.objects.link(light)
    light.location = location
    _look_at(light, target)


def _add_sun(target: Vector) -> None:
    light_data = bpy.data.lights.new(name="AuRoom sun", type="SUN")
    light_data.energy = 2.0
    light_data.angle = 0.12
    light = bpy.data.objects.new("AuRoom sun", light_data)
    bpy.context.collection.objects.link(light)
    light.location = target + Vector((8.0, -10.0, 14.0))
    _look_at(light, target)


def _add_camera(center: Vector, minimum: Vector, maximum: Vector) -> None:
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


def _configure_world() -> None:
    world = bpy.data.worlds.new("AuRoom world") if bpy.context.scene.world is None else bpy.context.scene.world
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.055, 0.065, 0.085, 1.0)
        background.inputs["Strength"].default_value = 0.45


def _configure_render(output_path: Path) -> None:
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = _RENDER_WIDTH
    scene.render.resolution_y = _RENDER_HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(output_path)


def main() -> None:
    input_path, output_path = _args()
    if not input_path.is_file():
        raise RuntimeError(f"Input GLB does not exist: {input_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(input_path))
    minimum, maximum = _scene_bounds()
    center = (minimum + maximum) * 0.5
    extent = max(maximum.x - minimum.x, maximum.y - minimum.y, 1.0)

    _configure_world()
    _add_ground(center, minimum, maximum)
    _add_camera(center, minimum, maximum)
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
    _configure_render(output_path)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
