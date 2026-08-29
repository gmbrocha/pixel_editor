"""Consolidate approved artist actions into a canonical elf mannequin copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", required=True, type=Path)
    parser.add_argument("--idle", required=True, type=Path)
    parser.add_argument("--walk", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
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


def _append_action(path: Path, source_name: str) -> bpy.types.Action:
    before = set(bpy.data.actions)
    with bpy.data.libraries.load(str(path.resolve()), link=False) as (source, target):
        if source_name not in source.actions:
            raise RuntimeError(f"{path} does not contain action {source_name}")
        target.actions = [source_name]
    added = [action for action in bpy.data.actions if action not in before]
    if len(added) != 1:
        raise RuntimeError(f"Expected one appended action from {path}, found {[a.name for a in added]}")
    return added[0]


def _pose_digest(armature: bpy.types.Object, action: bpy.types.Action, frames: list[int]) -> str:
    armature.animation_data.action = action
    digest = hashlib.sha256()
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        digest.update(struct.pack("<i", frame))
        for bone in sorted(armature.pose.bones, key=lambda item: item.name):
            digest.update(bone.name.encode("utf-8") + b"\0")
            digest.update(struct.pack("<16f", *(value for row in bone.matrix_basis for value in row)))
    return digest.hexdigest()


def _validate_closure(armature: bpy.types.Object, action: bpy.types.Action, closure: int) -> None:
    armature.animation_data.action = action
    bpy.context.scene.frame_set(1)
    first = {bone.name: tuple(value for row in bone.matrix_basis for value in row) for bone in armature.pose.bones}
    bpy.context.scene.frame_set(closure)
    for bone in armature.pose.bones:
        current = tuple(value for row in bone.matrix_basis for value in row)
        if any(not math.isclose(a, b, abs_tol=1e-5) for a, b in zip(first[bone.name], current, strict=True)):
            raise RuntimeError(f"{action.name} closure frame {closure} differs at {bone.name}")


def main() -> None:
    args = _args()
    sources = {
        "idle": (args.idle, "PF_Idle_Edit", "PF_Idle_Approved", list(range(1, 27)), 27, 12),
        "walk": (args.walk, "PF_Walk_Meshy_Edit", "PF_Walk_Approved", list(range(1, 9)), 9, 10),
        "run": (args.run, "PF_Run_Redo_Edit", "PF_Run_Approved", list(range(1, 9)), 9, 10),
    }
    for path in [args.canonical, *(item[0] for item in sources.values())]:
        if not path.is_file():
            raise FileNotFoundError(path)
    for output in (args.output_blend, args.output_manifest):
        if output.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {output}; pass --force")

    bpy.ops.wm.open_mainfile(filepath=str(args.canonical.resolve()))
    armature = _armature()
    if armature.animation_data is None:
        armature.animation_data_create()
    protected = {"PF_BindPose", "PF_Idle", "PF_Walk", "PF_Run"}
    protected_hashes = {
        name: _pose_digest(armature, bpy.data.actions[name], [int(bpy.data.actions[name].frame_range[0])])
        for name in protected
    }
    approved_manifest: dict[str, object] = {}
    for role, (path, source_name, approved_name, frames, closure, fps) in sources.items():
        existing = bpy.data.actions.get(approved_name)
        if existing is not None:
            bpy.data.actions.remove(existing)
        action = _append_action(path, source_name)
        action.name = approved_name
        action.use_fake_user = True
        action["pf_sample_frames_json"] = json.dumps(frames)
        action["pf_loop_closure_frame"] = closure
        action["pf_preview_fps"] = fps
        action["pf_approval_status"] = "approved"
        action["pf_artist_source_sha256"] = _sha256(path)
        _validate_closure(armature, action, closure)
        approved_manifest[role] = {
            "action": approved_name,
            "frames": frames,
            "closure": closure,
            "fps": fps,
            "artist_source": str(path.resolve()),
            "artist_source_sha256": _sha256(path),
            "pose_sha256": _pose_digest(armature, action, frames),
        }

    for name, digest in protected_hashes.items():
        if _pose_digest(armature, bpy.data.actions[name], [int(bpy.data.actions[name].frame_range[0])]) != digest:
            raise RuntimeError(f"Protected action {name} changed during consolidation")
    armature.animation_data.action = bpy.data.actions["PF_Idle_Approved"]
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 26
    bpy.context.scene.render.fps = 12
    bpy.context.scene.frame_set(1)
    bpy.context.scene["pf_approved_motion_actions_json"] = json.dumps(
        {role: data["action"] for role, data in approved_manifest.items()}, sort_keys=True
    )
    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend.resolve()), check_existing=False)
    manifest = {
        "schema_version": 1,
        "status": "approved_elf_motions_consolidated",
        "canonical_input_sha256": _sha256(args.canonical),
        "output_blend_sha256": _sha256(args.output_blend),
        "protected_actions": sorted(protected),
        "approved": approved_manifest,
    }
    args.output_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output_blend.resolve()}")
    print(f"Wrote {args.output_manifest.resolve()}")


if __name__ == "__main__":
    main()
