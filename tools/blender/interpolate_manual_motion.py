"""Densify a finalized manual animation by exposing Blender in-betweens."""

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
    parser.add_argument("--action", required=True)
    parser.add_argument("--source-frame-count", required=True, type=int)
    parser.add_argument("--subdivisions", type=int, default=2)
    parser.add_argument("--fps", required=True, type=int)
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
    return all(
        math.isclose(a, b, abs_tol=1e-5)
        for a, b in zip(first, second, strict=True)
    )


def main() -> None:
    args = _args()
    if args.source_frame_count < 1:
        raise ValueError("source-frame-count must be positive")
    if args.subdivisions < 2:
        raise ValueError("subdivisions must be at least 2")
    if not 1 <= args.fps <= 60:
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
        raise RuntimeError(f"Missing action {args.action}")
    armature.animation_data.action = action

    source_visible = list(range(1, args.source_frame_count + 1))
    source_closure = args.source_frame_count + 1
    source_poses = {frame: _pose(armature, frame) for frame in source_visible}
    source_closure_pose = _pose(armature, source_closure)
    mismatches = [
        name for name, matrix in source_poses[1].items()
        if not _matrix_close(matrix, source_closure_pose[name])
    ]
    if mismatches:
        raise RuntimeError(
            f"Source closure frame {source_closure} does not equal frame 1: {mismatches}"
        )

    source_key_frames = sorted({
        float(point.co.x)
        for curve in _curves(action)
        for point in curve.keyframe_points
    })
    invalid = [
        frame for frame in source_key_frames
        if frame < 1.0 or frame > float(source_closure)
    ]
    if invalid:
        raise RuntimeError(
            f"Source contains keys outside frames 1-{source_closure}: {invalid}"
        )

    factor = args.subdivisions
    for curve in _curves(action):
        for point in curve.keyframe_points:
            old_co_x = float(point.co.x)
            old_left_x = float(point.handle_left.x)
            old_right_x = float(point.handle_right.x)
            point.co.x = 1.0 + ((old_co_x - 1.0) * factor)
            point.handle_left.x = 1.0 + ((old_left_x - 1.0) * factor)
            point.handle_right.x = 1.0 + ((old_right_x - 1.0) * factor)
        curve.update()

    visible_count = args.source_frame_count * factor
    closure_frame = visible_count + 1
    authored_output_frames = [1 + ((frame - 1) * factor) for frame in source_visible]
    for source_frame, output_frame in zip(
        source_visible, authored_output_frames, strict=True
    ):
        output_pose = _pose(armature, output_frame)
        changed = [
            name for name, matrix in source_poses[source_frame].items()
            if not _matrix_close(matrix, output_pose[name])
        ]
        if changed:
            raise RuntimeError(
                f"Retiming changed authored pose {source_frame} at frame "
                f"{output_frame}: {changed}"
            )
    closure = _pose(armature, closure_frame)
    closure_mismatches = [
        name for name, matrix in source_poses[1].items()
        if not _matrix_close(matrix, closure[name])
    ]
    if closure_mismatches:
        raise RuntimeError(
            f"Output closure frame {closure_frame} does not equal frame 1: "
            f"{closure_mismatches}"
        )

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = visible_count
    scene.render.fps = args.fps
    scene.render.fps_base = 1.0
    scene.tool_settings.use_keyframe_insert_auto = False
    scene.frame_set(1)
    armature.animation_data.action = action
    action["pf_sample_frames_json"] = json.dumps(list(range(1, visible_count + 1)))
    action["pf_loop_closure_frame"] = closure_frame
    action["pf_preview_fps"] = args.fps
    action["pf_interpolation_source_frames_json"] = json.dumps(source_visible)
    action["pf_interpolation_authored_output_frames_json"] = json.dumps(
        authored_output_frames
    )
    action["pf_interpolation_subdivisions"] = factor

    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(
        filepath=str(args.output_blend.resolve()), check_existing=False
    )
    manifest = {
        "schema_version": 1,
        "status": "manual_motion_interpolated",
        "input_blend": args.blend.name,
        "input_blend_sha256": sha256_path(args.blend),
        "output_blend": args.output_blend.name,
        "output_blend_sha256": sha256_path(args.output_blend),
        "action": action.name,
        "source_visible_frames": source_visible,
        "source_pose_sha256": _pose_digest(source_poses),
        "authored_output_frames": authored_output_frames,
        "visible_frames": list(range(1, visible_count + 1)),
        "interpolated_frames": [
            frame for frame in range(1, visible_count + 1)
            if frame not in authored_output_frames
        ],
        "loop_closure_frame": closure_frame,
        "subdivisions": factor,
        "fps": args.fps,
        "duration_seconds": visible_count / args.fps,
    }
    args.output_manifest.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"Interpolated {args.source_frame_count} authored poses into "
        f"{visible_count} visible frames at {args.fps} FPS; closure {closure_frame}"
    )


if __name__ == "__main__":
    main()
