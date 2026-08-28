"""Bake a non-destructive forward-lean variant of an existing Blender action."""

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
    parser.add_argument("--source-action", default="PF_Run")
    parser.add_argument("--output-action", default="PF_Run_ForwardLean")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--lower-spine", type=float, default=3.0)
    parser.add_argument("--middle-spine", type=float, default=2.0)
    parser.add_argument("--upper-spine", type=float, default=1.0)
    parser.add_argument("--neck-compensation", type=float, default=-4.0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def _armature() -> bpy.types.Object:
    matches = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one armature, found {[obj.name for obj in matches]}")
    return matches[0]


def _rotate_pose_bone_global_x(pose_bone: bpy.types.PoseBone, degrees: float) -> None:
    if degrees == 0.0:
        return
    current = pose_bone.matrix.copy()
    pivot = current.translation.copy()
    rotation = Matrix.Rotation(math.radians(degrees), 4, "X")
    pose_bone.matrix = Matrix.Translation(pivot) @ rotation @ Matrix.Translation(-pivot) @ current
    bpy.context.view_layer.update()


def _head_position(armature: bpy.types.Object) -> list[float]:
    head = armature.pose.bones.get("Head")
    if head is None:
        raise RuntimeError("Missing Head bone")
    position = armature.matrix_world @ head.head
    return [round(float(component), 6) for component in position]


def main() -> None:
    args = _args()
    source_blend = bpy.data.filepath
    for path in (args.output, args.manifest):
        if path.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {path}; pass --force")

    armature = _armature()
    if armature.animation_data is None:
        armature.animation_data_create()
    source = bpy.data.actions.get(args.source_action)
    if source is None:
        raise RuntimeError(f"Missing source action {args.source_action}")
    frame_start = int(round(source.frame_range[0]))
    frame_end = int(round(source.frame_range[1]))
    frames = list(range(frame_start, frame_end + 1))
    armature.animation_data.action = source

    samples: dict[int, dict[str, Matrix]] = {}
    original_head_positions: dict[int, list[float]] = {}
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        samples[frame] = {
            bone.name: bone.matrix_basis.copy() for bone in armature.pose.bones
        }
        original_head_positions[frame] = _head_position(armature)

    existing = bpy.data.actions.get(args.output_action)
    if existing is not None:
        if not args.force:
            raise RuntimeError(f"Action already exists: {args.output_action}")
        bpy.data.actions.remove(existing)
    corrected = bpy.data.actions.new(args.output_action)
    corrected.use_fake_user = True
    corrected["pf_source_action"] = source.name
    corrected["pf_correction_kind"] = "distributed_forward_lean"
    corrected["pf_lower_spine_degrees"] = args.lower_spine
    corrected["pf_middle_spine_degrees"] = args.middle_spine
    corrected["pf_upper_spine_degrees"] = args.upper_spine
    corrected["pf_neck_compensation_degrees"] = args.neck_compensation
    armature.animation_data.action = corrected

    corrections = (
        ("Spine02", args.lower_spine),
        ("Spine01", args.middle_spine),
        ("Spine", args.upper_spine),
        ("neck", args.neck_compensation),
    )
    corrected_head_positions: dict[int, list[float]] = {}
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        for bone in armature.pose.bones:
            bone.matrix_basis = samples[frame][bone.name]
        bpy.context.view_layer.update()
        for bone_name, degrees in corrections:
            bone = armature.pose.bones.get(bone_name)
            if bone is None:
                raise RuntimeError(f"Missing correction bone {bone_name}")
            _rotate_pose_bone_global_x(bone, degrees)
        corrected_head_positions[frame] = _head_position(armature)
        for bone in armature.pose.bones:
            bone.rotation_mode = "QUATERNION"
            bone.keyframe_insert(data_path="location", frame=frame, group=bone.name)
            bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=bone.name)
            bone.keyframe_insert(data_path="scale", frame=frame, group=bone.name)

    armature.animation_data.action = corrected
    bpy.context.scene.frame_start = frame_start
    bpy.context.scene.frame_end = frame_end
    bpy.context.scene.frame_set(frame_start)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()), check_existing=False)

    deltas = {}
    for frame in frames:
        before = Vector(original_head_positions[frame])
        after = Vector(corrected_head_positions[frame])
        delta = after - before
        deltas[str(frame)] = [round(float(component), 6) for component in delta]
    manifest = {
        "schema_version": 1,
        "source_blend": source_blend,
        "source_action": source.name,
        "output_action": corrected.name,
        "frame_start": frame_start,
        "frame_end": frame_end,
        "corrections_degrees": {name: degrees for name, degrees in corrections},
        "head_position_delta_by_frame": deltas,
        "output_blend": str(args.output.resolve()),
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.resolve()}")
    print(f"Wrote {args.manifest.resolve()}")


if __name__ == "__main__":
    main()
