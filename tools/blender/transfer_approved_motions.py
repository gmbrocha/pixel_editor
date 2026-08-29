"""Apply approved elf motion corrections to a compatible Meshy character rig."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector


LEG_BONES = ("LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot")
OUTPUT_ACTIONS = {
    "idle": "PF_Idle_Transfer",
    "walk": "PF_Walk_Transfer",
    "run": "PF_Run_Transfer",
}


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-blend", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--output-blend", required=True, type=Path)
    parser.add_argument("--output-manifest", required=True, type=Path)
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


def _rest_relative_quaternion(bone) -> Quaternion:
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
        "height": max(z_values) - min(z_values),
        "hip_height": bones["Hips"].head_local.z - ground,
        "mean_leg_length": sum(bones[name].length for name in LEG_BONES) / 2.0,
        "ground_z": ground,
    }


def _contact_point(armature: bpy.types.Object, side: str) -> Vector:
    return (
        armature.pose.bones[f"{side}Foot"].head
        + armature.pose.bones[f"{side}ToeBase"].head
    ) * 0.5


def _capture(armature: bpy.types.Object, action: bpy.types.Action, frame: int) -> dict[str, object]:
    armature.animation_data.action = action
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    return {
        "bones": {
            bone.name: {
                "location": bone.location.copy(),
                "rotation": bone.matrix_basis.to_quaternion().normalized(),
                "scale": bone.scale.copy(),
                "armature_translation": bone.matrix.translation.copy(),
            }
            for bone in armature.pose.bones
        },
        "contacts": {side: _contact_point(armature, side) for side in ("Left", "Right")},
    }


def _pose_digest(armature: bpy.types.Object, action: bpy.types.Action, frames: list[int]) -> str:
    armature.animation_data.action = action
    digest = hashlib.sha256()
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        for bone in sorted(armature.pose.bones, key=lambda item: item.name):
            digest.update(bone.name.encode("utf-8") + b"\0")
            digest.update(struct.pack("<16f", *(value for row in bone.matrix_basis for value in row)))
    return digest.hexdigest()


def _set_pose(
    armature: bpy.types.Object,
    values: dict[str, dict[str, object]],
    frame: int,
) -> None:
    bpy.context.scene.frame_set(frame)
    for bone in armature.pose.bones:
        value = values[bone.name]
        bone.rotation_mode = "QUATERNION"
        bone.location = value["location"]
        bone.rotation_quaternion = value["rotation"]
        bone.scale = value["scale"]
        bone.keyframe_insert(data_path="location", frame=frame, group=bone.name)
        bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=bone.name)
        bone.keyframe_insert(data_path="scale", frame=frame, group=bone.name)


def _qfrom(values: list[float]) -> Quaternion:
    return Quaternion(tuple(float(value) for value in values)).normalized()


def _validate_hierarchy(armature: bpy.types.Object, profile: dict[str, object]) -> None:
    expected = profile["bone_order"]
    actual = [bone.name for bone in armature.data.bones]
    if actual != expected:
        raise RuntimeError(f"Target bone order differs: expected {expected}, found {actual}")
    for bone in armature.data.bones:
        parent = bone.parent.name if bone.parent else None
        if parent != profile["hierarchy"][bone.name]["parent"]:
            raise RuntimeError(f"Target parent mismatch for {bone.name}: {parent}")


def _build_action(
    armature: bpy.types.Object,
    profile: dict[str, object],
    sequence_name: str,
    target_baseline: bpy.types.Action,
    target_metrics: dict[str, float],
    force: bool,
) -> tuple[bpy.types.Action, dict[str, object]]:
    sequence = profile["sequences"][sequence_name]
    output_name = OUTPUT_ACTIONS[sequence_name]
    existing = bpy.data.actions.get(output_name)
    if existing is not None:
        if not force:
            raise RuntimeError(f"Action {output_name} already exists; pass --force")
        bpy.data.actions.remove(existing)
    visible_frames = [int(frame) for frame in sequence["visible_frames"]]
    baseline_frames: dict[int, dict[str, object]] = {}
    for frame in visible_frames:
        source_frame = int(sequence["frames"][str(frame)]["original_frame"])
        baseline_frames[frame] = _capture(armature, target_baseline, source_frame)

    source_metrics = profile["metrics"]
    horizontal_scale = target_metrics["mean_leg_length"] / float(source_metrics["mean_leg_length"])
    vertical_scale = target_metrics["hip_height"] / float(source_metrics["hip_height"])
    action = bpy.data.actions.new(output_name)
    action.use_fake_user = True
    armature.animation_data.action = action
    for frame in visible_frames:
        baseline = baseline_frames[frame]
        frame_profile = sequence["frames"][str(frame)]
        values = {}
        for bone in armature.pose.bones:
            original = baseline["bones"][bone.name]
            delta = _qfrom(frame_profile["bones"][bone.name]["rotation_delta"])
            values[bone.name] = {
                "location": original["location"].copy(),
                # matrix_basis is already expressed in the bone's own
                # rest-local coordinate system. Applying the source delta to
                # the target basis performs the required rest-basis mapping;
                # conjugating again would double-rotate differing rest axes.
                "rotation": (delta @ original["rotation"]).normalized(),
                "scale": original["scale"].copy(),
            }
        _set_pose(armature, values, frame)
        bpy.context.view_layer.update()
        delta = Vector(frame_profile["hips_delta_armature"])
        scaled_delta = Vector((delta.x * horizontal_scale, delta.y * horizontal_scale, delta.z * vertical_scale))
        hips = armature.pose.bones["Hips"]
        hips_matrix = hips.matrix.copy()
        hips_matrix.translation = baseline["bones"]["Hips"]["armature_translation"] + scaled_delta
        hips.matrix = hips_matrix
        hips.keyframe_insert(data_path="location", frame=frame, group="Hips")

    contact_corrections = {}
    cap = target_metrics["height"] * 0.03
    armature.animation_data.action = action
    idle_anchors = None
    if sequence_name == "idle":
        bpy.context.scene.frame_set(1)
        bpy.context.view_layer.update()
        idle_anchors = {
            side: _contact_point(armature, side).copy()
            for side in ("Left", "Right")
        }
    for frame in visible_frames:
        sides = sequence["contacts"].get(str(frame), [])
        if not sides:
            continue
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        current = sum((_contact_point(armature, side) for side in sides), Vector()) / len(sides)
        frame_profile = sequence["frames"][str(frame)]
        anchors = []
        for side in sides:
            if idle_anchors is not None:
                source_offset = Vector(frame_profile["contact_offsets_armature"][side])
                first_offset = Vector(
                    sequence["frames"]["1"]["contact_offsets_armature"][side]
                )
                relative = source_offset - first_offset
                anchors.append(idle_anchors[side] + Vector((
                    relative.x * horizontal_scale,
                    relative.y * horizontal_scale,
                    relative.z * vertical_scale,
                )))
                continue
            source_offset = Vector(frame_profile["contact_offsets_armature"][side])
            scaled_offset = Vector((
                source_offset.x * horizontal_scale,
                source_offset.y * horizontal_scale,
                source_offset.z * vertical_scale,
            ))
            anchors.append(baseline_frames[frame]["contacts"][side] + scaled_offset)
        anchor = sum(anchors, Vector()) / len(anchors)
        offset = anchor - current
        if offset.length > cap + 1e-6:
            raise RuntimeError(
                f"{sequence_name} frame {frame} contact correction {offset.length:.6f} "
                f"({offset.x:.6f}, {offset.y:.6f}, {offset.z:.6f}) "
                f"exceeds 3% height cap {cap:.6f}"
            )
        hips = armature.pose.bones["Hips"]
        matrix = hips.matrix.copy()
        matrix.translation += offset
        hips.matrix = matrix
        hips.keyframe_insert(data_path="location", frame=frame, group="Hips")
        contact_corrections[str(frame)] = {
            "feet": sides,
            "offset_armature": [round(float(value), 9) for value in offset],
            "magnitude": round(float(offset.length), 9),
        }

    armature.animation_data.action = action
    first = _capture(armature, action, 1)["bones"]
    closure = int(sequence["closure_frame"])
    _set_pose(armature, first, closure)
    action["pf_sample_frames_json"] = json.dumps(visible_frames)
    action["pf_loop_closure_frame"] = closure
    action["pf_preview_fps"] = int(sequence["fps"])
    action["pf_transfer_source"] = "approved_elf_motion_profile"
    action["pf_transfer_status"] = "review_candidate"

    closure_values = _capture(armature, action, closure)["bones"]
    for name, value in first.items():
        for key in ("location", "scale"):
            if any(not math.isclose(a, b, abs_tol=1e-5) for a, b in zip(value[key], closure_values[name][key], strict=True)):
                raise RuntimeError(f"{output_name} closure differs at {name} {key}")
        if value["rotation"].rotation_difference(closure_values[name]["rotation"]).angle > 1e-5:
            raise RuntimeError(f"{output_name} closure rotation differs at {name}")
    return action, {
        "action": output_name,
        "visible_frames": visible_frames,
        "closure_frame": closure,
        "fps": int(sequence["fps"]),
        "horizontal_hips_scale": round(horizontal_scale, 9),
        "vertical_hips_scale": round(vertical_scale, 9),
        "contact_cap": round(cap, 9),
        "contact_corrections": contact_corrections,
        "pose_sha256": _pose_digest(armature, action, visible_frames),
    }


def main() -> None:
    args = _args()
    if not args.target_blend.is_file():
        raise FileNotFoundError(args.target_blend)
    if not args.profile.is_file():
        raise FileNotFoundError(args.profile)
    for output in (args.output_blend, args.output_manifest):
        if output.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {output}; pass --force")
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(args.target_blend.resolve()))
    armature = _armature()
    if armature.animation_data is None:
        armature.animation_data_create()
    _validate_hierarchy(armature, profile)
    required = {"PF_BindPose", "PF_Walk", "PF_Run"}
    missing = sorted(name for name in required if bpy.data.actions.get(name) is None)
    if missing:
        raise RuntimeError(f"Target master lacks actions: {missing}")
    original_digests = {
        "PF_BindPose": _pose_digest(armature, bpy.data.actions["PF_BindPose"], [1]),
        "PF_Walk": _pose_digest(armature, bpy.data.actions["PF_Walk"], [1, 5, 9, 13, 17, 21, 25, 29]),
        "PF_Run": _pose_digest(armature, bpy.data.actions["PF_Run"], [1, 3, 6, 8, 10, 13, 15, 18]),
    }
    metrics = _metrics(armature)
    results = {}
    for sequence, baseline in (
        ("idle", bpy.data.actions["PF_BindPose"]),
        ("walk", bpy.data.actions["PF_Walk"]),
        ("run", bpy.data.actions["PF_Run"]),
    ):
        _action, results[sequence] = _build_action(
            armature, profile, sequence, baseline, metrics, args.force
        )
    for name, digest in original_digests.items():
        frames = [1]
        if name == "PF_Walk":
            frames = [1, 5, 9, 13, 17, 21, 25, 29]
        elif name == "PF_Run":
            frames = [1, 3, 6, 8, 10, 13, 15, 18]
        if _pose_digest(armature, bpy.data.actions[name], frames) != digest:
            raise RuntimeError(f"Protected target action {name} changed")

    armature.animation_data.action = bpy.data.actions["PF_Idle_Transfer"]
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 26
    bpy.context.scene.render.fps = 12
    bpy.context.scene.frame_set(1)
    bpy.context.scene["pf_motion_transfer_status"] = "review_candidate"
    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend.resolve()), check_existing=False)
    manifest = {
        "schema_version": 1,
        "status": "motion_transfer_review_candidate",
        "character_id": bpy.context.scene.get("pf_character_id", "unknown"),
        "profile_sha256": _sha256(args.profile),
        "target_master_sha256": _sha256(args.target_blend),
        "output_blend_sha256": _sha256(args.output_blend),
        "target_metrics": {name: round(float(value), 9) for name, value in metrics.items()},
        "protected_action_pose_sha256": original_digests,
        "sequences": results,
    }
    args.output_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output_blend.resolve()}")
    print(f"Wrote {args.output_manifest.resolve()}")


if __name__ == "__main__":
    main()
