"""Consolidate approved target motions into a tracked canonical Blender file."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy


SEQUENCES = {
    "idle": ("PF_Idle_Approved", list(range(1, 27)), 27),
    "walk": ("PF_Walk_Approved", list(range(1, 9)), 9),
    "run": ("PF_Run_Approved", list(range(1, 9)), 9),
}


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--idle-action", default="PF_Idle_Transfer")
    parser.add_argument("--walk-action", default="PF_Walk_Transfer")
    parser.add_argument("--run-action", default="PF_Run_Transfer")
    parser.add_argument("--timing", required=True, type=Path)
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
    armature = armatures[0]
    if armature.animation_data is None:
        armature.animation_data_create()
    return armature


def _capture(
    armature: bpy.types.Object,
    action: bpy.types.Action,
    frame: int,
) -> dict[str, dict[str, object]]:
    armature.animation_data.action = action
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    return {
        bone.name: {
            "location": bone.location.copy(),
            "rotation": bone.matrix_basis.to_quaternion().normalized(),
            "scale": bone.scale.copy(),
        }
        for bone in armature.pose.bones
    }


def _key_pose(
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
        bone.keyframe_insert(
            data_path="rotation_quaternion", frame=frame, group=bone.name
        )
        bone.keyframe_insert(data_path="scale", frame=frame, group=bone.name)


def _pose_digest(
    armature: bpy.types.Object,
    action: bpy.types.Action,
    frames: list[int],
) -> str:
    digest = hashlib.sha256()
    armature.animation_data.action = action
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        for bone in sorted(armature.pose.bones, key=lambda item: item.name):
            digest.update(bone.name.encode("utf-8") + b"\0")
            digest.update(
                struct.pack(
                    "<16f", *(value for row in bone.matrix_basis for value in row)
                )
            )
    return digest.hexdigest()


def _durations(timing: dict[str, object], sequence: str) -> list[int]:
    specification = timing[sequence]
    count = int(specification["frame_count"])
    values = [int(specification["default_frame_duration_ms"])] * count
    for raw_frame, raw_duration in specification["frame_duration_overrides_ms"].items():
        frame = int(raw_frame)
        if not 1 <= frame <= count:
            raise ValueError(f"Invalid {sequence} duration frame {frame}")
        values[frame - 1] = int(raw_duration)
    if any(value < 1 for value in values):
        raise ValueError(f"Invalid {sequence} frame durations")
    return values


def _copy_action(
    armature: bpy.types.Object,
    source: bpy.types.Action,
    sequence: str,
    timing: dict[str, object],
    force: bool,
) -> tuple[bpy.types.Action, dict[str, object]]:
    output_name, frames, closure = SEQUENCES[sequence]
    existing = bpy.data.actions.get(output_name)
    if existing is not None:
        if not force:
            raise RuntimeError(f"Action {output_name} already exists; pass --force")
        bpy.data.actions.remove(existing)
    poses = {frame: _capture(armature, source, frame) for frame in frames}
    action = bpy.data.actions.new(output_name)
    action.use_fake_user = True
    armature.animation_data.action = action
    for frame in frames:
        _key_pose(armature, poses[frame], frame)
    _key_pose(armature, poses[1], closure)
    fps = int(timing[sequence]["fps"])
    durations = _durations(timing, sequence)
    action["pf_status"] = "approved"
    action["pf_source_action"] = source.name
    action["pf_sample_frames_json"] = json.dumps(frames)
    action["pf_loop_closure_frame"] = closure
    action["pf_preview_fps"] = fps
    action["pf_frame_durations_ms_json"] = json.dumps(durations)

    first = _capture(armature, action, 1)
    last = _capture(armature, action, closure)
    error = max(
        abs(first[name]["rotation"][index] - last[name]["rotation"][index])
        for name in first
        for index in range(4)
    )
    if error > 1e-5:
        raise RuntimeError(f"{output_name} closure rotation error {error}")
    return action, {
        "action": output_name,
        "source_action": source.name,
        "visible_frames": frames,
        "closure_frame": closure,
        "fps": fps,
        "frame_durations_ms": durations,
        "pose_sha256": _pose_digest(armature, action, frames),
    }


def main() -> None:
    args = _args()
    for path in (args.input, args.timing):
        if not path.is_file():
            raise FileNotFoundError(path)
    for path in (args.output, args.manifest):
        if path.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {path}; pass --force")
    input_sha256 = _sha256(args.input)
    timing = json.loads(args.timing.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(args.input.resolve()))
    armature = _armature()
    source_names = {
        "idle": args.idle_action,
        "walk": args.walk_action,
        "run": args.run_action,
    }
    missing = [name for name in source_names.values() if bpy.data.actions.get(name) is None]
    if missing:
        raise RuntimeError(f"Missing approved source actions: {missing}")
    protected = {
        name: _pose_digest(
            armature,
            bpy.data.actions[name],
            SEQUENCES[sequence][1],
        )
        for sequence, name in source_names.items()
    }
    results = {}
    approved = {}
    for sequence, source_name in source_names.items():
        approved[sequence], results[sequence] = _copy_action(
            armature, bpy.data.actions[source_name], sequence, timing, args.force
        )
    for sequence, source_name in source_names.items():
        if _pose_digest(
            armature, bpy.data.actions[source_name], SEQUENCES[sequence][1]
        ) != protected[source_name]:
            raise RuntimeError(f"Protected action {source_name} changed")

    scene = bpy.context.scene
    armature.animation_data.action = approved["idle"]
    scene.frame_start = 1
    scene.frame_end = 26
    scene.render.fps = 12
    scene.render.fps_base = 1.0
    scene.frame_set(1)
    scene["pf_character_id"] = args.character_id
    scene["pf_motion_status"] = "approved"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(
        filepath=str(args.output.resolve()), check_existing=False
    )
    manifest = {
        "schema_version": 1,
        "status": "approved_motion_canonical",
        "character_id": args.character_id,
        "artist_input": str(args.input.resolve()),
        "artist_input_sha256": input_sha256,
        "canonical_blend": args.output.name,
        "canonical_blend_sha256": _sha256(args.output),
        "timing_sha256": _sha256(args.timing),
        "protected_source_pose_sha256": protected,
        "sequences": results,
    }
    args.manifest.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Wrote {args.output.resolve()}")
    print(f"Wrote {args.manifest.resolve()}")


if __name__ == "__main__":
    main()
