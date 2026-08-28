"""Bake a restrained seamless Idle action from a clean bind-pose action."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-action", default="PF_BindPose")
    parser.add_argument("--output-action", default="PF_Idle")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--frame-start", type=int, default=1)
    parser.add_argument("--frame-end", type=int, default=49)
    parser.add_argument("--upper-spine-breath", type=float, default=-0.8)
    parser.add_argument("--middle-spine-breath", type=float, default=-0.35)
    parser.add_argument("--neck-breath-compensation", type=float, default=0.45)
    parser.add_argument("--lower-spine-sway", type=float, default=0.25)
    parser.add_argument("--middle-spine-sway", type=float, default=0.35)
    parser.add_argument("--upper-spine-sway", type=float, default=0.45)
    parser.add_argument("--neck-sway-compensation", type=float, default=-0.55)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def _armature() -> bpy.types.Object:
    matches = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one armature, found {[obj.name for obj in matches]}")
    return matches[0]


def _rotate_pose_bone_global(
    pose_bone: bpy.types.PoseBone,
    axis: str,
    degrees: float,
) -> None:
    if abs(degrees) < 1e-12:
        return
    current = pose_bone.matrix.copy()
    pivot = current.translation.copy()
    rotation = Matrix.Rotation(math.radians(degrees), 4, axis)
    pose_bone.matrix = Matrix.Translation(pivot) @ rotation @ Matrix.Translation(-pivot) @ current
    bpy.context.view_layer.update()


def _positions(armature: bpy.types.Object) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for name in ("Hips", "Spine02", "neck", "Head", "LeftHand", "RightHand", "LeftFoot", "RightFoot"):
        bone = armature.pose.bones.get(name)
        if bone is None:
            raise RuntimeError(f"Missing diagnostic bone {name}")
        position = armature.matrix_world @ bone.head
        result[name] = [round(float(component), 6) for component in position]
    return result


def main() -> None:
    args = _args()
    if args.frame_end <= args.frame_start:
        raise ValueError("frame-end must be greater than frame-start")
    for path in (args.output, args.manifest):
        if path.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {path}; pass --force")

    source_blend = bpy.data.filepath
    armature = _armature()
    if armature.animation_data is None:
        armature.animation_data_create()
    source = bpy.data.actions.get(args.source_action)
    if source is None:
        raise RuntimeError(f"Missing source action {args.source_action}")
    armature.animation_data.action = source
    bpy.context.scene.frame_set(int(round(source.frame_range[0])))
    base = {bone.name: bone.matrix_basis.copy() for bone in armature.pose.bones}
    base_positions = _positions(armature)

    existing = bpy.data.actions.get(args.output_action)
    if existing is not None:
        if not args.force:
            raise RuntimeError(f"Action already exists: {args.output_action}")
        bpy.data.actions.remove(existing)
    idle = bpy.data.actions.new(args.output_action)
    idle.use_fake_user = True
    idle["pf_source_action"] = source.name
    idle["pf_correction_kind"] = "restrained_bind_pose_idle"
    idle["pf_loop_frame_start"] = args.frame_start
    idle["pf_loop_frame_end_duplicate"] = args.frame_end
    idle["pf_upper_spine_breath_degrees"] = args.upper_spine_breath
    idle["pf_middle_spine_breath_degrees"] = args.middle_spine_breath
    idle["pf_neck_breath_compensation_degrees"] = args.neck_breath_compensation
    idle["pf_lower_spine_sway_degrees"] = args.lower_spine_sway
    idle["pf_middle_spine_sway_degrees"] = args.middle_spine_sway
    idle["pf_upper_spine_sway_degrees"] = args.upper_spine_sway
    idle["pf_neck_sway_compensation_degrees"] = args.neck_sway_compensation
    armature.animation_data.action = idle

    frames = list(range(args.frame_start, args.frame_end + 1))
    positions: dict[str, dict[str, list[float]]] = {}
    span = args.frame_end - args.frame_start
    for frame in frames:
        phase = math.tau * (frame - args.frame_start) / span
        inhale = 0.5 - 0.5 * math.cos(phase)
        sway = math.sin(phase)
        bpy.context.scene.frame_set(frame)
        for bone in armature.pose.bones:
            bone.matrix_basis = base[bone.name]
        bpy.context.view_layer.update()

        corrections = (
            ("Spine01", "X", args.middle_spine_breath * inhale),
            ("Spine02", "X", args.upper_spine_breath * inhale),
            ("neck", "X", args.neck_breath_compensation * inhale),
            ("Spine", "Y", args.lower_spine_sway * sway),
            ("Spine01", "Y", args.middle_spine_sway * sway),
            ("Spine02", "Y", args.upper_spine_sway * sway),
            ("neck", "Y", args.neck_sway_compensation * sway),
        )
        for bone_name, axis, degrees in corrections:
            bone = armature.pose.bones.get(bone_name)
            if bone is None:
                raise RuntimeError(f"Missing correction bone {bone_name}")
            _rotate_pose_bone_global(bone, axis, degrees)

        if frame in {
            args.frame_start,
            args.frame_start + span // 4,
            args.frame_start + span // 2,
            args.frame_start + (span * 3) // 4,
            args.frame_end,
        }:
            positions[str(frame)] = _positions(armature)
        for bone in armature.pose.bones:
            bone.rotation_mode = "QUATERNION"
            bone.keyframe_insert(data_path="location", frame=frame, group=bone.name)
            bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=bone.name)
            bone.keyframe_insert(data_path="scale", frame=frame, group=bone.name)

    armature.animation_data.action = idle
    bpy.context.scene.frame_start = args.frame_start
    bpy.context.scene.frame_end = args.frame_end
    bpy.context.scene.frame_set(args.frame_start)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()), check_existing=False)

    manifest = {
        "schema_version": 1,
        "source_blend": source_blend,
        "source_action": source.name,
        "output_action": idle.name,
        "frame_start": args.frame_start,
        "frame_end_duplicate": args.frame_end,
        "unique_loop_frames": span,
        "sample_frames": [args.frame_start + index * (span // 8) for index in range(8)],
        "corrections_degrees": {
            "upper_spine_breath": args.upper_spine_breath,
            "middle_spine_breath": args.middle_spine_breath,
            "neck_breath_compensation": args.neck_breath_compensation,
            "lower_spine_sway": args.lower_spine_sway,
            "middle_spine_sway": args.middle_spine_sway,
            "upper_spine_sway": args.upper_spine_sway,
            "neck_sway_compensation": args.neck_sway_compensation,
        },
        "bind_positions": base_positions,
        "sample_positions": positions,
        "output_blend": str(args.output.resolve()),
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.resolve()}")
    print(f"Wrote {args.manifest.resolve()}")


if __name__ == "__main__":
    main()
