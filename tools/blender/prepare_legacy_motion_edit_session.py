"""Prepare authored Idle and original Meshy Walk/Run for safe pose editing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.mannequin_semantics import sha256_path  # noqa: E402
from tools.blender.build_semantic_mannequin import action_hashes  # noqa: E402


MOTIONS = {
    "idle": {
        "source": "PF_Idle",
        "editable": "PF_Idle_Edit",
        "source_frames": [1, 7, 13, 19, 25, 31, 37, 43],
        "phases": [
            "Neutral",
            "Breath 1",
            "Breath 2",
            "Breath 3",
            "Opposite",
            "Breath 5",
            "Breath 6",
            "Settle",
        ],
        "origin": "Pixel Forge authored restrained idle",
    },
    "walk": {
        "source": "PF_Walk",
        "editable": "PF_Walk_Meshy_Edit",
        "source_frames": [1, 5, 9, 13, 17, 21, 25, 29],
        "phases": [
            "Left Contact",
            "Left Down",
            "Left Passing",
            "Left Up",
            "Right Contact",
            "Right Down",
            "Right Passing",
            "Right Up",
        ],
        "origin": "Original Meshy walk",
    },
    "run": {
        "source": "PF_Run",
        "editable": "PF_Run_Meshy_Edit",
        "source_frames": [1, 3, 6, 8, 10, 13, 15, 18],
        "phases": [
            "Run Pose 1",
            "Run Pose 2",
            "Run Pose 3",
            "Run Pose 4",
            "Run Pose 5",
            "Run Pose 6",
            "Run Pose 7",
            "Run Pose 8",
        ],
        "origin": "Original untouched Meshy run",
    },
}


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--output-blend", required=True, type=Path)
    parser.add_argument("--output-manifest", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def _armature() -> bpy.types.Object:
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected one armature, found {[obj.name for obj in armatures]}")
    return armatures[0]


def _snapshot_action(
    armature: bpy.types.Object,
    action: bpy.types.Action,
    frames: list[int],
) -> list[dict[str, Matrix]]:
    armature.animation_data.action = action
    snapshots = []
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        snapshots.append({
            bone.name: bone.matrix_basis.copy()
            for bone in armature.pose.bones
        })
    return snapshots


def _create_editable_action(
    armature: bpy.types.Object,
    role: str,
    specification: dict[str, object],
    snapshots: list[dict[str, Matrix]],
    force: bool,
) -> bpy.types.Action:
    editable_name = str(specification["editable"])
    existing = bpy.data.actions.get(editable_name)
    if existing is not None:
        if not force:
            raise RuntimeError(f"Action already exists: {editable_name}")
        bpy.data.actions.remove(existing, do_unlink=True)

    editable = bpy.data.actions.new(editable_name)
    editable.use_fake_user = True
    editable["pf_status"] = "editable_copy"
    editable["pf_role"] = role
    editable["pf_origin"] = str(specification["origin"])
    editable["pf_source_action"] = str(specification["source"])
    editable["pf_source_frames_json"] = json.dumps(specification["source_frames"])
    editable["pf_sample_frames_json"] = json.dumps(list(range(1, 9)))
    editable["pf_unique_loop_frames"] = 8
    editable["pf_loop_frame_start"] = 1
    editable["pf_loop_frame_end_duplicate"] = 9
    editable["pf_phase_names_json"] = json.dumps(specification["phases"])
    armature.animation_data.action = editable

    for edit_frame, snapshot in enumerate(snapshots, start=1):
        bpy.context.scene.frame_set(edit_frame)
        for name, basis in snapshot.items():
            bone = armature.pose.bones[name]
            bone.matrix_basis = basis
            bone.rotation_mode = "QUATERNION"
            bone.keyframe_insert(data_path="location", frame=edit_frame, group=name)
            bone.keyframe_insert(data_path="rotation_quaternion", frame=edit_frame, group=name)
            bone.keyframe_insert(data_path="scale", frame=edit_frame, group=name)

    bpy.context.scene.frame_set(9)
    for name, basis in snapshots[0].items():
        bone = armature.pose.bones[name]
        bone.matrix_basis = basis
        bone.rotation_mode = "QUATERNION"
        bone.keyframe_insert(data_path="location", frame=9, group=name)
        bone.keyframe_insert(data_path="rotation_quaternion", frame=9, group=name)
        bone.keyframe_insert(data_path="scale", frame=9, group=name)

    for frame, phase in enumerate(specification["phases"], start=1):
        marker = editable.pose_markers.new(str(phase))
        marker.frame = frame
    return editable


def _quickstart() -> str:
    return """PIXEL FORGE ORIGINAL MOTION EDIT SESSION

EDITABLE ACTIONS
- PF_Idle_Edit: our restrained authored Idle
- PF_Walk_Meshy_Edit: the original Meshy Walk
- PF_Run_Meshy_Edit: the original untouched Meshy Run

PROTECTED FULL ACTIONS
- PF_Idle (48 unique frames plus closure)
- PF_Walk (32 frames)
- PF_Run (20 frames)

START HERE
1. Click the Animation workspace tab at the top.
2. Keep the armature in Pose Mode. Never animate in Edit Mode.
3. In the Dope Sheet, change the mode to Action Editor.
4. Use the action dropdown to choose one of the three actions ending in _Edit.
5. Edit frames 1 through 8. Frame 9 is the loop-closure copy of frame 1.
6. Select a bone and rotate with R. To key it visibly, right-click the bone,
   choose Insert Keyframe with Keying Set, then Location, Rotation & Scale.
   In Blender 5.1, pressing I is the faster silent shortcut.
7. Move only Hips with G unless you intentionally want a detached joint.
8. Auto Key starts disabled. Use Ctrl+Z and save experiments under new names.

GOOD EDIT ORDER
- First fix contacts and feet.
- Then knees and hip height.
- Then torso balance.
- Adjust arms, neck, and head last.

The original full actions remain in this file for comparison. Switching actions
does not overwrite them. Nothing updates Character Forge until a later explicit
approval and promotion step.
"""


def main() -> None:
    args = _args()
    if not args.blend.is_file():
        raise FileNotFoundError(args.blend)
    for output in (args.output_blend, args.output_manifest):
        if output.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {output}; pass --force")

    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    armature = _armature()
    if armature.animation_data is None:
        armature.animation_data_create()

    missing = [
        str(specification["source"])
        for specification in MOTIONS.values()
        if bpy.data.actions.get(str(specification["source"])) is None
    ]
    if missing:
        raise RuntimeError(f"Missing protected source actions: {missing}")

    hashes_before = action_hashes(armature)
    motion_manifest = {}
    edit_actions = {}
    for role, specification in MOTIONS.items():
        source_name = str(specification["source"])
        source = bpy.data.actions[source_name]
        source_frames = [int(frame) for frame in specification["source_frames"]]
        start, end = (int(round(value)) for value in source.frame_range)
        invalid = [frame for frame in source_frames if frame < start or frame > end]
        if invalid:
            raise ValueError(f"{source_name} samples outside {start}-{end}: {invalid}")
        snapshots = _snapshot_action(armature, source, source_frames)
        editable = _create_editable_action(
            armature, role, specification, snapshots, args.force
        )
        edit_actions[role] = editable
        motion_manifest[role] = {
            "origin": specification["origin"],
            "source_action": source_name,
            "source_action_sha256": hashes_before[source_name],
            "source_frame_range": [start, end],
            "source_frames": source_frames,
            "editable_action": editable.name,
            "editable_frames": list(range(1, 9)),
            "loop_closure_frame": 9,
            "phases": specification["phases"],
        }

    hashes_after = action_hashes(armature)
    changed = [
        str(specification["source"])
        for specification in MOTIONS.values()
        if hashes_before[str(specification["source"])]
        != hashes_after[str(specification["source"])]
    ]
    if changed:
        raise RuntimeError(f"Preparing edit copies changed protected actions: {changed}")

    scene = bpy.context.scene
    scene.render.fps = 10
    scene.render.fps_base = 1.0
    scene.frame_start = 1
    scene.frame_end = 8
    scene.tool_settings.use_keyframe_insert_auto = False
    scene.timeline_markers.clear()
    for frame in range(1, 9):
        scene.timeline_markers.new(f"PF Pose {frame}", frame=frame)

    text = bpy.data.texts.get("PIXEL_FORGE_ORIGINAL_MOTION_QUICKSTART")
    if text is None:
        text = bpy.data.texts.new("PIXEL_FORGE_ORIGINAL_MOTION_QUICKSTART")
    text.clear()
    text.write(_quickstart())

    armature.show_in_front = True
    armature.data.display_type = "BBONE"
    armature["pf_edit_actions_json"] = json.dumps(
        {role: action.name for role, action in edit_actions.items()}
    )
    armature["pf_edit_instructions"] = "Open PIXEL_FORGE_ORIGINAL_MOTION_QUICKSTART"
    armature.animation_data.action = edit_actions["walk"]
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    scene.frame_set(1)
    try:
        bpy.ops.object.mode_set(mode="POSE")
    except RuntimeError:
        pass

    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend.resolve()), check_existing=False)
    output = {
        "schema_version": 1,
        "status": "editable_session",
        "source_blend_sha256": sha256_path(args.blend),
        "output_blend": args.output_blend.name,
        "output_blend_sha256": sha256_path(args.output_blend),
        "fps": 10,
        "active_action": edit_actions["walk"].name,
        "motions": motion_manifest,
    }
    args.output_manifest.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        "Prepared editable Idle, original Meshy Walk, and original Meshy Run; "
        "preserved all full source actions"
    )


if __name__ == "__main__":
    main()
