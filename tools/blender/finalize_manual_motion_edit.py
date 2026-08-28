"""Sanitize a manually edited sparse action without changing its visible poses."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.mannequin_semantics import sha256_path  # noqa: E402


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--action", default="PF_Walk_Meshy_Edit")
    parser.add_argument("--frame-count", type=int, default=8)
    parser.add_argument(
        "--fps", type=int,
        help="Output playback FPS; defaults to the saved scene FPS",
    )
    parser.add_argument("--output-blend", required=True, type=Path)
    parser.add_argument("--output-manifest", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def _armature() -> bpy.types.Object:
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected one armature, found {[obj.name for obj in armatures]}")
    return armatures[0]


def _curves(action: bpy.types.Action):
    for layer in action.layers:
        for strip in layer.strips:
            for slot in action.slots:
                bag = strip.channelbag(slot)
                if bag is not None:
                    yield from bag.fcurves


def _pose(armature: bpy.types.Object, frame: int) -> dict[str, tuple[float, ...]]:
    bpy.context.scene.frame_set(frame)
    return {
        bone.name: tuple(float(value) for row in bone.matrix_basis for value in row)
        for bone in armature.pose.bones
    }


def _pose_digest(poses: dict[int, dict[str, tuple[float, ...]]]) -> str:
    digest = hashlib.sha256()
    for frame, pose in sorted(poses.items()):
        digest.update(struct.pack("<i", frame))
        for name, values in sorted(pose.items()):
            digest.update(name.encode("utf-8") + b"\0")
            digest.update(struct.pack("<16f", *values))
    return digest.hexdigest()


def _matrix_close(first: tuple[float, ...], second: tuple[float, ...]) -> bool:
    return all(math.isclose(a, b, abs_tol=1e-5) for a, b in zip(first, second, strict=True))


def main() -> None:
    args = _args()
    if args.frame_count < 1:
        raise ValueError("frame-count must be positive")
    if args.fps is not None and not 1 <= args.fps <= 60:
        raise ValueError("fps must be between 1 and 60")
    if not args.blend.is_file():
        raise FileNotFoundError(args.blend)
    for path in (args.output_blend, args.output_manifest):
        if path.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {path}; pass --force")

    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    armature = _armature()
    if armature.animation_data is None:
        armature.animation_data_create()
    action = bpy.data.actions.get(args.action)
    if action is None:
        raise RuntimeError(f"Missing editable action {args.action}")
    armature.animation_data.action = action

    visible_frames = list(range(1, args.frame_count + 1))
    closure_frame = args.frame_count + 1
    output_fps = int(args.fps or bpy.context.scene.render.fps)
    if not 1 <= output_fps <= 60:
        raise ValueError(f"Saved scene FPS must be between 1 and 60, found {output_fps}")
    visible_before = {frame: _pose(armature, frame) for frame in visible_frames}
    visible_digest = _pose_digest(visible_before)
    frame_one = visible_before[1]
    bpy.context.scene.frame_set(1)
    frame_one_channels = {
        bone.name: (
            bone.location.copy(),
            bone.rotation_quaternion.copy(),
            bone.scale.copy(),
        )
        for bone in armature.pose.bones
    }

    removed = []
    for curve in _curves(action):
        remove_indices = []
        for index, point in enumerate(curve.keyframe_points):
            frame = float(point.co.x)
            if (
                frame < 1.0
                or frame > float(closure_frame)
                or math.isclose(frame, float(closure_frame), abs_tol=1e-6)
            ):
                removed.append({"data_path": curve.data_path, "array_index": curve.array_index, "frame": frame})
                remove_indices.append(index)
        for index in reversed(remove_indices):
            curve.keyframe_points.remove(curve.keyframe_points[index])
        curve.update()

    bpy.context.scene.frame_set(closure_frame)
    for bone in armature.pose.bones:
        location, rotation, scale = frame_one_channels[bone.name]
        bone.rotation_mode = "QUATERNION"
        bone.location = location
        bone.rotation_quaternion = rotation
        bone.scale = scale
        bone.keyframe_insert(data_path="location", frame=closure_frame, group=bone.name)
        bone.keyframe_insert(data_path="rotation_quaternion", frame=closure_frame, group=bone.name)
        bone.keyframe_insert(data_path="scale", frame=closure_frame, group=bone.name)

    visible_after = {frame: _pose(armature, frame) for frame in visible_frames}
    after_digest = _pose_digest(visible_after)
    if after_digest != visible_digest:
        raise RuntimeError(
            f"Finalization changed one or more visible poses on frames 1-{args.frame_count}"
        )
    closure = _pose(armature, closure_frame)
    mismatches = [
        name for name in frame_one
        if not _matrix_close(frame_one[name], closure[name])
    ]
    if mismatches:
        raise RuntimeError(f"Frame {closure_frame} does not close frame 1: {mismatches}")
    invalid_frames = sorted({
        float(point.co.x)
        for curve in _curves(action)
        for point in curve.keyframe_points
        if point.co.x < 1.0 or point.co.x > float(closure_frame)
    })
    if invalid_frames:
        raise RuntimeError(
            f"Keys remain outside frames 1-{closure_frame}: {invalid_frames}"
        )

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = args.frame_count
    scene.render.fps = output_fps
    scene.render.fps_base = 1.0
    scene.tool_settings.use_keyframe_insert_auto = False
    scene.frame_set(1)
    armature.animation_data.action = action
    action["pf_sample_frames_json"] = json.dumps(visible_frames)
    action["pf_loop_closure_frame"] = closure_frame
    action["pf_preview_fps"] = output_fps

    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend.resolve()), check_existing=False)
    output = {
        "schema_version": 1,
        "status": "manual_edit_finalized",
        "input_blend_sha256": sha256_path(args.blend),
        "output_blend": args.output_blend.name,
        "output_blend_sha256": sha256_path(args.output_blend),
        "action": action.name,
        "visible_frames": visible_frames,
        "visible_pose_sha256": visible_digest,
        "loop_closure_frame": closure_frame,
        "removed_keyframes": removed,
        "fps": output_fps,
    }
    args.output_manifest.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        f"Finalized {action.name}: preserved frames 1-{args.frame_count}, "
        f"rebuilt frame {closure_frame}, "
        f"removed {len(removed)} out-of-range/old-closure keys"
    )


if __name__ == "__main__":
    main()
