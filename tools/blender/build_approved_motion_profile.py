"""Build a deterministic rest-normalized correction profile from approved elf actions."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector


WALK_SOURCE_FRAMES = [1, 5, 9, 13, 17, 21, 25, 29]
RUN_SOURCE_FRAMES = [1, 3, 6, 8, 10, 13, 15, 18]
LEG_BONES = ("LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot")


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _armature() -> bpy.types.Object:
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected one armature, found {[obj.name for obj in armatures]}")
    return armatures[0]


def _qvalues(quaternion: Quaternion) -> list[float]:
    value = quaternion.normalized()
    if value.w < 0.0:
        value = Quaternion((-value.w, -value.x, -value.y, -value.z))
    return [round(float(component), 9) for component in value]


def _vvalues(vector: Vector) -> list[float]:
    return [round(float(component), 9) for component in vector]


def _rest_relative_quaternion(bone: bpy.types.Bone) -> Quaternion:
    matrix = bone.parent.matrix_local.inverted() @ bone.matrix_local if bone.parent else bone.matrix_local
    return matrix.to_quaternion().normalized()


def _metrics(armature: bpy.types.Object) -> dict[str, float]:
    bones = armature.data.bones
    z_values = [value for bone in bones for value in (bone.head_local.z, bone.tail_local.z)]
    ground = min(
        bones[name].head_local.z
        for name in ("LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase")
    )
    return {
        "height": round(max(z_values) - min(z_values), 9),
        "hip_height": round(bones["Hips"].head_local.z - ground, 9),
        "mean_leg_length": round(sum(bones[name].length for name in LEG_BONES) / 2.0, 9),
        "ground_z": round(ground, 9),
    }


def _capture(
    armature: bpy.types.Object,
    action: bpy.types.Action,
    frame: int,
) -> dict[str, object]:
    armature.animation_data.action = action
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    return {
        "bones": {
            bone.name: {
                "rotation": bone.matrix_basis.to_quaternion().normalized(),
                "location": bone.location.copy(),
                "armature_translation": bone.matrix.translation.copy(),
            }
            for bone in armature.pose.bones
        },
        "contacts": {
            side: _contact_point(armature, side)
            for side in ("Left", "Right")
        },
    }


def _contact_point(armature: bpy.types.Object, side: str) -> Vector:
    foot = armature.pose.bones[f"{side}Foot"].head
    toe = armature.pose.bones[f"{side}ToeBase"].head
    return (foot + toe) * 0.5


def _detect_contacts(
    armature: bpy.types.Object,
    action: bpy.types.Action,
    frames: list[int],
    height: float,
    idle: bool,
) -> dict[str, list[str]]:
    if idle:
        return {str(frame): ["Left", "Right"] for frame in frames}
    positions: dict[str, list[Vector]] = {"Left": [], "Right": []}
    armature.animation_data.action = action
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        for side in positions:
            positions[side].append(_contact_point(armature, side))
    contacts = {str(frame): [] for frame in frames}
    for side, points in positions.items():
        minimum = min(point.z for point in points)
        candidates = [index for index, point in enumerate(points) if point.z <= minimum + height * 0.025]
        if not candidates:
            candidates = [min(range(len(points)), key=lambda index: points[index].z)]
        for index in candidates:
            contacts[str(frames[index])].append(side)
    return contacts


def _sequence_profile(
    armature: bpy.types.Object,
    original: bpy.types.Action,
    approved: bpy.types.Action,
    original_frames: list[int],
    approved_frames: list[int],
    fps: int,
    idle: bool = False,
) -> dict[str, object]:
    frames: dict[str, object] = {}
    max_rotation_error = 0.0
    max_hips_error = 0.0
    for original_frame, approved_frame in zip(original_frames, approved_frames, strict=True):
        baseline = _capture(armature, original, original_frame)
        edited = _capture(armature, approved, approved_frame)
        bones = {}
        for name in sorted(baseline["bones"]):
            original_q = baseline["bones"][name]["rotation"]
            approved_q = edited["bones"][name]["rotation"]
            delta_q = approved_q @ original_q.conjugated()
            reconstructed = (delta_q @ original_q).normalized()
            max_rotation_error = max(
                max_rotation_error,
                float(reconstructed.rotation_difference(approved_q).angle),
            )
            bones[name] = {"rotation_delta": _qvalues(delta_q)}
        hips_delta = (
            edited["bones"]["Hips"]["armature_translation"]
            - baseline["bones"]["Hips"]["armature_translation"]
        )
        reconstructed_hips = baseline["bones"]["Hips"]["armature_translation"] + hips_delta
        max_hips_error = max(
            max_hips_error,
            float((reconstructed_hips - edited["bones"]["Hips"]["armature_translation"]).length),
        )
        frames[str(approved_frame)] = {
            "original_frame": original_frame,
            "bones": bones,
            "hips_delta_armature": _vvalues(hips_delta),
            "contact_offsets_armature": {
                side: _vvalues(edited["contacts"][side] - baseline["contacts"][side])
                for side in ("Left", "Right")
            },
        }
    height = float(_metrics(armature)["height"])
    if max_rotation_error > 1e-5 or max_hips_error > 1e-5:
        raise RuntimeError(
            f"{approved.name} source self-check failed: rotation={max_rotation_error}, "
            f"hips={max_hips_error}"
        )
    return {
        "original_action": original.name,
        "approved_action": approved.name,
        "visible_frames": approved_frames,
        "closure_frame": approved_frames[-1] + 1,
        "fps": fps,
        "contacts": _detect_contacts(armature, approved, approved_frames, height, idle),
        "source_self_check": {
            "max_rotation_error_radians": max_rotation_error,
            "max_hips_translation_error": max_hips_error,
        },
        "frames": frames,
    }


def main() -> None:
    args = _args()
    if not args.blend.is_file():
        raise FileNotFoundError(args.blend)
    if args.output.exists() and not args.force:
        raise FileExistsError(f"Refusing to overwrite {args.output}; pass --force")
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    armature = _armature()
    if armature.animation_data is None:
        armature.animation_data_create()
    required = [
        "PF_BindPose", "PF_Walk", "PF_Run",
        "PF_Idle_Approved", "PF_Walk_Approved", "PF_Run_Approved",
    ]
    missing = [name for name in required if bpy.data.actions.get(name) is None]
    if missing:
        raise RuntimeError(f"Missing required actions: {missing}")
    bones = list(armature.data.bones)
    hierarchy = {
        bone.name: {
            "parent": bone.parent.name if bone.parent else None,
            "rest_relative_rotation": _qvalues(_rest_relative_quaternion(bone)),
            "length": round(float(bone.length), 9),
        }
        for bone in bones
    }
    bind = bpy.data.actions["PF_BindPose"]
    idle_frames = list(range(1, 27))
    profile = {
        "schema_version": 1,
        "kind": "approved_motion_transfer_profile",
        "source_blend": str(args.blend.resolve()),
        "source_blend_sha256": _sha256(args.blend),
        "armature": armature.name,
        "bone_order": [bone.name for bone in bones],
        "hierarchy": hierarchy,
        "metrics": _metrics(armature),
        "sequences": {
            "idle": _sequence_profile(
                armature, bind, bpy.data.actions["PF_Idle_Approved"],
                [1] * len(idle_frames), idle_frames, 12, idle=True,
            ),
            "walk": _sequence_profile(
                armature, bpy.data.actions["PF_Walk"], bpy.data.actions["PF_Walk_Approved"],
                WALK_SOURCE_FRAMES, list(range(1, 9)), 10,
            ),
            "run": _sequence_profile(
                armature, bpy.data.actions["PF_Run"], bpy.data.actions["PF_Run_Approved"],
                RUN_SOURCE_FRAMES, list(range(1, 9)), 10,
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.resolve()}")


if __name__ == "__main__":
    main()
