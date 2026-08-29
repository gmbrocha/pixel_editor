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
    parser.add_argument(
        "--framing-scale",
        type=float,
        default=1.0,
        help="Multiply the orthographic framing scale; values above 1 render smaller",
    )
    parser.add_argument("--pitch", type=float, default=28.0)
    parser.add_argument(
        "--timing-config",
        type=Path,
        help="Optional approved-motion timing JSON that overrides action metadata",
    )
    parser.add_argument(
        "--auto-frame",
        action="store_true",
        help="Use one union framing for every selected action and direction",
    )
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
    target: Vector | None = None,
) -> None:
    target = target or Vector((0.0, 0.0, 0.82))
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


def _auto_frame(
    armature: bpy.types.Object,
    sequences: dict[str, dict[str, object]],
    pitch: float,
) -> tuple[Vector, float]:
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("Cannot auto-frame a scene without a mesh")
    minimum = Vector((float("inf"),) * 3)
    maximum = Vector((float("-inf"),) * 3)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for sequence in sequences.values():
        action = bpy.data.actions.get(str(sequence["action"]))
        if action is None:
            raise RuntimeError(f"Missing action {sequence['action']}")
        armature.animation_data.action = action
        for frame in sequence["frames"]:
            bpy.context.scene.frame_set(int(frame))
            bpy.context.view_layer.update()
            for mesh in meshes:
                evaluated = mesh.evaluated_get(depsgraph)
                for corner in evaluated.bound_box:
                    point = evaluated.matrix_world @ Vector(corner)
                    minimum.x = min(minimum.x, point.x)
                    minimum.y = min(minimum.y, point.y)
                    minimum.z = min(minimum.z, point.z)
                    maximum.x = max(maximum.x, point.x)
                    maximum.y = max(maximum.y, point.y)
                    maximum.z = max(maximum.z, point.z)
    extent = maximum - minimum
    radians = math.radians(pitch)
    vertical = extent.z * math.cos(radians) + max(extent.x, extent.y) * math.sin(radians)
    ortho_scale = max(extent.x, extent.y, vertical) * 1.18
    if not math.isfinite(ortho_scale) or ortho_scale <= 0.0:
        raise RuntimeError(f"Invalid auto-frame bounds: {minimum} .. {maximum}")
    return (minimum + maximum) * 0.5, ortho_scale


def _timing_spec(path: Path | None) -> dict[str, dict[str, object]]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Timing config {path} must contain an object")
    return {
        str(name): value
        for name, value in data.items()
        if name != "schema_version" and isinstance(value, dict)
    }


def _frame_durations(
    action: bpy.types.Action,
    frame_count: int,
    fps: int,
    sequence_name: str,
    timing: dict[str, dict[str, object]],
) -> list[int]:
    override = timing.get(sequence_name)
    if override is not None:
        runtime = "runtime_source_frames" in override
        configured_count = (
            len(override["runtime_source_frames"])
            if runtime else int(override.get("frame_count", 0))
        )
        configured_fps = int(
            override.get("runtime_fps" if runtime else "fps", 0)
        )
        if configured_count != frame_count or configured_fps != fps:
            raise RuntimeError(
                f"Timing config for {sequence_name} expects {configured_count} frames "
                f"at {configured_fps} FPS, rendered action has {frame_count} at {fps} FPS"
            )
        default_duration = int(override.get(
            "runtime_default_frame_duration_ms" if runtime
            else "default_frame_duration_ms", 0
        ))
        durations = [default_duration] * frame_count
        raw_overrides = override.get(
            "runtime_frame_duration_overrides_ms" if runtime
            else "frame_duration_overrides_ms", {}
        )
        if not isinstance(raw_overrides, dict):
            raise RuntimeError(
                f"Timing config for {sequence_name} has invalid duration overrides"
            )
        for raw_frame, raw_duration in raw_overrides.items():
            frame_number = int(raw_frame)
            if not 1 <= frame_number <= frame_count:
                raise RuntimeError(
                    f"Timing override frame {frame_number} is outside {sequence_name}"
                )
            durations[frame_number - 1] = int(raw_duration)
    else:
        raw = action.get("pf_frame_durations_ms_json")
        durations = (
            [int(value) for value in json.loads(raw)]
            if raw
            else [round(1000 / fps)] * frame_count
        )
    if len(durations) != frame_count or any(value < 1 for value in durations):
        raise RuntimeError(
            f"{action.name} has invalid frame duration metadata: {durations}"
        )
    return durations


def main() -> None:
    args = _args()
    if args.framing_scale <= 0.0:
        raise ValueError("framing-scale must be greater than zero")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timing = _timing_spec(args.timing_config)
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
            "fps": int(idle_action.get("pf_preview_fps", 10)),
        }
    if "walk" in selected:
        walk_action = bpy.data.actions.get(args.walk_action)
        if walk_action is None:
            raise RuntimeError(f"Missing action {args.walk_action}")
        raw_samples = walk_action.get("pf_sample_frames_json")
        sequences["walk"] = {
            "action": args.walk_action,
            "frames": json.loads(raw_samples) if raw_samples else [1, 5, 9, 13, 17, 21, 25, 29],
            "fps": int(walk_action.get("pf_preview_fps", 10)),
        }
    if "run" in selected:
        run_action = bpy.data.actions.get(args.run_action)
        if run_action is None:
            raise RuntimeError(f"Missing action {args.run_action}")
        raw_samples = run_action.get("pf_sample_frames_json")
        sequences["run"] = {
            "action": args.run_action,
            "frames": json.loads(raw_samples) if raw_samples else [1, 3, 6, 8, 10, 13, 15, 18],
            "fps": int(run_action.get("pf_preview_fps", 10)),
        }
    if not sequences:
        raise RuntimeError("No animation sequences were selected")
    for sequence_name, sequence in sequences.items():
        override = timing.get(sequence_name)
        if override and "runtime_source_frames" in override:
            sequence["frames"] = [
                int(value) for value in override["runtime_source_frames"]
            ]
            sequence["fps"] = int(override.get("runtime_fps", sequence["fps"]))
    target = Vector((0.0, 0.0, 0.82))
    if args.auto_frame:
        target, ortho_scale = _auto_frame(armature, sequences, args.pitch)
        camera.data.ortho_scale = ortho_scale * args.framing_scale
    else:
        camera.data.ortho_scale *= args.framing_scale
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
        "ortho_scale": float(camera.data.ortho_scale),
        "framing_scale": args.framing_scale,
        "target": [float(value) for value in target],
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
            "fps": sequence["fps"],
            "frame_durations_ms": _frame_durations(
                action,
                len(sequence["frames"]),
                int(sequence["fps"]),
                sequence_name,
                timing,
            ),
            "directions": {},
        }
        for direction_name, horizontal in directions.items():
            _position_view(camera, key, fill, horizontal, args.pitch, target)
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
