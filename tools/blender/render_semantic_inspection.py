"""Render six semantic views and non-destructive body-hide previews."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.mannequin_semantics import CHARACTER_SLOTS, sha256_path  # noqa: E402


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--size", type=int, default=384)
    return parser.parse_args(argv)


def _only_object(object_type: str) -> bpy.types.Object:
    matches = [obj for obj in bpy.data.objects if obj.type == object_type]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {object_type}, found {[obj.name for obj in matches]}")
    return matches[0]


def _look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def _setup(size: int) -> bpy.types.Object:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    collection = bpy.data.collections.get("PF_SEMANTIC_INSPECTION")
    if collection is None:
        collection = bpy.data.collections.new("PF_SEMANTIC_INSPECTION")
        scene.collection.children.link(collection)
    camera_data = bpy.data.cameras.new("PF_Semantic_Camera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 1.9
    camera = bpy.data.objects.new("PF_Semantic_Camera", camera_data)
    collection.objects.link(camera)
    scene.camera = camera
    material = bpy.data.materials.get("PF_Semantic_Debug")
    if material is None:
        raise RuntimeError("PF_Semantic_Debug material is missing")
    bpy.context.view_layer.material_override = material
    return camera


def _render(camera: bpy.types.Object, direction: Vector, output: Path) -> None:
    target = Vector((0.0, 0.0, 0.82))
    camera.location = target + direction.normalized() * 4.0 + Vector((0.0, 0.0, 0.25))
    _look_at(camera, target)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(output.resolve())
    bpy.ops.render.render(write_still=True)


def _hide_duplicate(mesh_obj: bpy.types.Object, slot: str) -> bpy.types.Object:
    attribute = mesh_obj.data.attributes.get(f"pf_hide_{slot}")
    if attribute is None:
        raise RuntimeError(f"Missing pf_hide_{slot}")
    hidden = {index for index, item in enumerate(attribute.data) if bool(item.value)}
    duplicate = mesh_obj.copy()
    duplicate.data = mesh_obj.data.copy()
    duplicate.name = f"PF_HidePreview_{slot}"
    duplicate.hide_render = False
    bpy.context.scene.collection.objects.link(duplicate)
    bm = bmesh.new()
    bm.from_mesh(duplicate.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(
        bm,
        geom=[face for face in bm.faces if face.index in hidden],
        context="FACES_ONLY",
    )
    bm.to_mesh(duplicate.data)
    bm.free()
    duplicate.data.update()
    return duplicate


def main() -> None:
    args = _args()
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    mesh_obj = _only_object("MESH")
    armature = _only_object("ARMATURE")
    if armature.animation_data is None:
        armature.animation_data_create()
    bind = bpy.data.actions.get("PF_BindPose")
    if bind is not None:
        armature.animation_data.action = bind
        bpy.context.scene.frame_set(int(round(bind.frame_range[0])))
    camera = _setup(args.size)
    views = {
        "front": Vector((0.0, -1.0, 0.0)),
        "back": Vector((0.0, 1.0, 0.0)),
        "right": Vector((-1.0, 0.0, 0.0)),
        "left": Vector((1.0, 0.0, 0.0)),
        "front_left_three_quarter": Vector((1.0, -1.0, 0.0)),
        "back_right_three_quarter": Vector((-1.0, 1.0, 0.0)),
    }
    outputs: dict[str, dict[str, object]] = {}
    for name, direction in views.items():
        output = args.output_dir / "views" / f"{name}.png"
        _render(camera, direction, output)
        outputs[f"view:{name}"] = {"file": str(output.relative_to(args.output_dir)), "sha256": sha256_path(output)}

    mesh_obj.hide_render = True
    for slot in CHARACTER_SLOTS:
        duplicate = _hide_duplicate(mesh_obj, slot)
        output = args.output_dir / "body_hide" / f"{slot}.png"
        _render(camera, Vector((1.0, -1.0, 0.0)), output)
        outputs[f"hide:{slot}"] = {"file": str(output.relative_to(args.output_dir)), "sha256": sha256_path(output)}
        bpy.data.objects.remove(duplicate, do_unlink=True)
    mesh_obj.hide_render = False

    manifest = {
        "schema_version": 1,
        "blend": args.blend.name,
        "blend_sha256": sha256_path(args.blend),
        "render_size": args.size,
        "view_count": len(views),
        "slot_hide_preview_count": len(CHARACTER_SLOTS),
        "outputs": outputs,
    }
    manifest_path = args.output_dir / "semantic_inspection_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path.resolve()}")


if __name__ == "__main__":
    main()
