"""Render four-direction transparent sprite source frames from a master blend."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--render-size", type=int, default=512)
    parser.add_argument("--ortho-scale", type=float, default=1.95)
    parser.add_argument("--pitch", type=float, default=28.0)
    parser.add_argument("--idle-action", default="")
    parser.add_argument("--walk-action", default="PF_Walk")
    parser.add_argument("--run-action", default="PF_Run")
    parser.add_argument(
        "--only",
        action="append",
        choices=("idle", "walk", "run"),
        help="Render only the named sequence; repeat for more than one",
    )
    return parser.parse_args(argv)


def _look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def _armature() -> bpy.types.Object:
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected one armature, found {[obj.name for obj in armatures]}")
    return armatures[0]


def _light(
    collection: bpy.types.Collection,
    name: str,
    energy: float,
    size: float,
) -> bpy.types.Object:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    return obj


def _setup(size: int, ortho_scale: float) -> tuple[bpy.types.Object, bpy.types.Object, bpy.types.Object]:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 15
    scene.render.film_transparent = True
    scene.render.fps = 30
    scene.render.fps_base = 1.0
    if scene.world is None:
        scene.world = bpy.data.worlds.new("PF_Sprite_World")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.04, 0.045, 0.055, 1.0)
        background.inputs["Strength"].default_value = 0.35

    collection = bpy.data.collections.new("PF_SPRITE_RENDER")
    scene.collection.children.link(collection)
    camera_data = bpy.data.cameras.new("PF_Sprite_Camera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = ortho_scale
    camera = bpy.data.objects.new("PF_Sprite_Camera", camera_data)
    collection.objects.link(camera)
    scene.camera = camera
    key = _light(collection, "PF_Sprite_Key", 950.0, 4.0)
    fill = _light(collection, "PF_Sprite_Fill", 350.0, 3.0)
    return camera, key, fill


def _position_view(
    camera: bpy.types.Object,
    key: bpy.types.Object,
    fill: bpy.types.Object,
    horizontal: Vector,
    pitch: float,
) -> None:
    target = Vector((0.0, 0.0, 0.82))
    radius = 5.0
    camera_height = target.z + math.tan(math.radians(pitch)) * radius
    camera.location = target + horizontal.normalized() * radius
    camera.location.z = camera_height
    _look_at(camera, target)

    view_direction = (camera.location - target).normalized()
    screen_right = view_direction.cross(Vector((0.0, 0.0, 1.0))).normalized()
    key.location = target + view_direction * 2.5 - screen_right * 2.5 + Vector((0.0, 0.0, 3.2))
    fill.location = target + view_direction * 1.5 + screen_right * 2.7 + Vector((0.0, 0.0, 1.8))
    _look_at(key, target)
    _look_at(fill, target)


def main() -> None:
    args = _args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    camera, key, fill = _setup(args.render_size, args.ortho_scale)
    armature = _armature()
    if armature.animation_data is None:
        armature.animation_data_create()

    selected = set(args.only or ("idle", "walk", "run"))
    sequences = {}
    if args.idle_action and "idle" in selected:
        idle_action = bpy.data.actions.get(args.idle_action)
        if idle_action is None:
            raise RuntimeError(f"Missing action {args.idle_action}")
        raw_samples = idle_action.get("pf_sample_frames_json")
        sequences["idle"] = {
            "action": args.idle_action,
            "frames": json.loads(raw_samples) if raw_samples else [1, 7, 13, 19, 25, 31, 37, 43],
        }
    if "walk" in selected:
        walk_action = bpy.data.actions.get(args.walk_action)
        if walk_action is None:
            raise RuntimeError(f"Missing action {args.walk_action}")
        raw_samples = walk_action.get("pf_sample_frames_json")
        sequences["walk"] = {
            "action": args.walk_action,
            "frames": json.loads(raw_samples) if raw_samples else [1, 5, 9, 13, 17, 21, 25, 29],
        }
    if "run" in selected:
        run_action = bpy.data.actions.get(args.run_action)
        if run_action is None:
            raise RuntimeError(f"Missing action {args.run_action}")
        raw_samples = run_action.get("pf_sample_frames_json")
        sequences["run"] = {
            "action": args.run_action,
            "frames": json.loads(raw_samples) if raw_samples else [1, 3, 6, 8, 10, 13, 15, 18],
        }
    if not sequences:
        raise RuntimeError("No animation sequences were selected")
    directions = {
        "front": Vector((0.0, -1.0, 0.0)),
        "back": Vector((0.0, 1.0, 0.0)),
        "right": Vector((-1.0, 0.0, 0.0)),
        "left": Vector((1.0, 0.0, 0.0)),
    }
    manifest: dict[str, object] = {
        "schema_version": 1,
        "blender_version": bpy.app.version_string,
        "blend": bpy.data.filepath,
        "render_size": args.render_size,
        "ortho_scale": args.ortho_scale,
        "pitch_degrees": args.pitch,
        "direction_order": list(directions),
        "sequences": {},
    }

    for sequence_name, sequence in sequences.items():
        action = bpy.data.actions.get(sequence["action"])
        if action is None:
            raise RuntimeError(f"Missing action {sequence['action']}")
        armature.animation_data.action = action
        sequence_manifest = {
            "action": action.name,
            "source_frames": sequence["frames"],
            "directions": {},
        }
        for direction_name, horizontal in directions.items():
            _position_view(camera, key, fill, horizontal, args.pitch)
            outputs = []
            for frame_index, source_frame in enumerate(sequence["frames"]):
                bpy.context.scene.frame_set(source_frame)
                output = (
                    args.output_dir
                    / sequence_name
                    / direction_name
                    / f"frame_{frame_index:02d}_source_{source_frame:03d}.png"
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                bpy.context.scene.render.filepath = str(output.resolve())
                bpy.ops.render.render(write_still=True)
                outputs.append(str(output.resolve()))
            sequence_manifest["directions"][direction_name] = outputs
        manifest["sequences"][sequence_name] = sequence_manifest

    manifest_path = args.output_dir / "sprite_render_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path.resolve()}")


if __name__ == "__main__":
    main()
