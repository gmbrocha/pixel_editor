"""Render deterministic front/side pose diagnostics from a character master blend."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument(
        "--action",
        action="append",
        help="Render only this action; repeat to compare multiple actions",
    )
    return parser.parse_args(argv)


def _look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def _area_light(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    energy: float,
    size: float,
    target: Vector,
) -> None:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    _look_at(obj, target)
    collection.objects.link(obj)


def _setup_scene(size: int) -> bpy.types.Object:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.fps = 30
    scene.render.fps_base = 1.0
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 15
    if scene.world is None:
        scene.world = bpy.data.worlds.new("PF_Diagnostic_World")
    scene.world.color = (0.025, 0.028, 0.035)

    diagnostics = bpy.data.collections.new("PF_DIAGNOSTIC_RENDER")
    scene.collection.children.link(diagnostics)
    camera_data = bpy.data.cameras.new("PF_Diagnostic_Camera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 1.9
    camera_data.lens = 50
    camera = bpy.data.objects.new("PF_Diagnostic_Camera", camera_data)
    diagnostics.objects.link(camera)
    scene.camera = camera

    target = Vector((0.0, 0.0, 0.82))
    _area_light(diagnostics, "PF_Key", (-3.0, -4.0, 5.0), 900.0, 4.0, target)
    _area_light(diagnostics, "PF_Fill", (4.0, -2.0, 3.0), 500.0, 3.0, target)
    _area_light(diagnostics, "PF_Rim", (0.0, 4.0, 4.0), 700.0, 3.0, target)
    return camera


def _armature() -> bpy.types.Object:
    matches = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one armature, found {[obj.name for obj in matches]}")
    return matches[0]


def _pose_snapshot(armature: bpy.types.Object) -> dict[str, list[float]]:
    selected = (
        "Hips",
        "Spine",
        "neck",
        "Head",
        "LeftShoulder",
        "LeftArm",
        "LeftForeArm",
        "LeftHand",
        "RightShoulder",
        "RightArm",
        "RightForeArm",
        "RightHand",
        "LeftUpLeg",
        "LeftLeg",
        "LeftFoot",
        "RightUpLeg",
        "RightLeg",
        "RightFoot",
    )
    snapshot = {}
    for name in selected:
        bone = armature.pose.bones.get(name)
        if bone is None:
            continue
        head = armature.matrix_world @ bone.head
        tail = armature.matrix_world @ bone.tail
        snapshot[name] = [
            round(float(head.x), 6),
            round(float(head.y), 6),
            round(float(head.z), 6),
            round(float(tail.x), 6),
            round(float(tail.y), 6),
            round(float(tail.z), 6),
        ]
    return snapshot


def main() -> None:
    args = _args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    camera = _setup_scene(args.size)
    armature = _armature()
    if armature.animation_data is None:
        armature.animation_data_create()

    samples = {
        "PF_BindPose": [1],
        "PF_Walk": [1, 5, 9, 13, 17, 21, 25, 29, 32],
        "PF_Run": [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 20],
    }
    if bpy.data.actions.get("PF_Idle") is not None:
        samples["PF_Idle"] = [1, 7, 13, 19, 25, 31, 37, 43, 49]
    if bpy.data.actions.get("PF_Run_ForwardLean") is not None:
        samples["PF_Run_ForwardLean"] = [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 20]
    if bpy.data.actions.get("PF_Run_ForwardLean_HeadDown") is not None:
        samples["PF_Run_ForwardLean_HeadDown"] = [
            1,
            3,
            5,
            7,
            9,
            11,
            13,
            15,
            17,
            19,
            20,
        ]
    if args.action:
        samples = {}
        for action_name in args.action:
            action = bpy.data.actions.get(action_name)
            if action is None:
                raise RuntimeError(f"Missing action {action_name}")
            raw_samples = action.get("pf_sample_frames_json")
            if raw_samples:
                frames = [int(value) for value in json.loads(raw_samples)]
            else:
                start, end = (int(round(value)) for value in action.frame_range)
                unique_count = max(1, end - start)
                frames = [start + round(index * unique_count / 8) for index in range(8)]
            samples[action_name] = frames
    views = {
        "front": (0.0, -5.0, 0.82),
        "side": (-5.0, 0.0, 0.82),
    }
    target = Vector((0.0, 0.0, 0.82))
    report: dict[str, object] = {
        "blender_version": bpy.app.version_string,
        "blend": bpy.data.filepath,
        "size": args.size,
        "samples": [],
    }

    for action_name, frames in samples.items():
        action = bpy.data.actions.get(action_name)
        if action is None:
            raise RuntimeError(f"Missing action {action_name}")
        armature.animation_data.action = action
        action_slug = action_name.removeprefix("PF_").lower()
        for frame in frames:
            bpy.context.scene.frame_set(frame)
            pose = _pose_snapshot(armature)
            for view_name, location in views.items():
                camera.location = location
                _look_at(camera, target)
                output = args.output_dir / action_slug / view_name / f"frame_{frame:03d}.png"
                output.parent.mkdir(parents=True, exist_ok=True)
                bpy.context.scene.render.filepath = str(output.resolve())
                bpy.ops.render.render(write_still=True)
                report["samples"].append(
                    {
                        "action": action_name,
                        "frame": frame,
                        "view": view_name,
                        "path": str(output.resolve()),
                        "pose": pose,
                    }
                )

    report_path = args.output_dir / "render_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {report_path.resolve()}")


if __name__ == "__main__":
    main()
