"""Validate the three-action original-motion Blender editing session."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.blender.build_semantic_mannequin import action_hashes  # noqa: E402


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    return parser.parse_args(argv)


def _matrix_close(first, second, tolerance: float = 1e-5) -> bool:
    return all(
        math.isclose(float(a), float(b), abs_tol=tolerance)
        for first_row, second_row in zip(first, second, strict=True)
        for a, b in zip(first_row, second_row, strict=True)
    )


def _pose(armature: bpy.types.Object) -> dict[str, object]:
    return {bone.name: bone.matrix_basis.copy() for bone in armature.pose.bones}


def main() -> None:
    args = _args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("status") != "editable_session":
        raise ValueError("Manifest is not an editable original-motion session")
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError("Edit session must contain exactly one armature")
    armature = armatures[0]
    if armature.animation_data is None:
        armature.animation_data_create()

    scene = bpy.context.scene
    if scene.render.fps != 10 or scene.frame_start != 1 or scene.frame_end != 8:
        raise RuntimeError("Edit session must preview frames 1-8 at 10 FPS")
    if scene.tool_settings.use_keyframe_insert_auto:
        raise RuntimeError("Auto Key must start disabled")
    if sorted(marker.frame for marker in scene.timeline_markers) != list(range(1, 9)):
        raise RuntimeError("Expected one generic pose marker on frames 1-8")
    if bpy.data.texts.get("PIXEL_FORGE_ORIGINAL_MOTION_QUICKSTART") is None:
        raise RuntimeError("Embedded original-motion quickstart is missing")
    if not armature.show_in_front:
        raise RuntimeError("Armature must be visible in front")

    source_hashes = action_hashes(armature)
    for role in ("idle", "walk", "run"):
        specification = manifest["motions"][role]
        source = bpy.data.actions.get(specification["source_action"])
        editable = bpy.data.actions.get(specification["editable_action"])
        if source is None or editable is None or source == editable:
            raise RuntimeError(f"{role} source/edit action pair is invalid")
        if source_hashes[source.name] != specification["source_action_sha256"]:
            raise RuntimeError(f"Protected source action changed: {source.name}")
        if editable.get("pf_status") != "editable_copy":
            raise RuntimeError(f"{editable.name} is not marked editable")
        if editable.get("pf_source_action") != source.name:
            raise RuntimeError(f"{editable.name} points to the wrong source")
        if json.loads(editable.get("pf_sample_frames_json", "[]")) != list(range(1, 9)):
            raise RuntimeError(f"{editable.name} does not expose poses 1-8")
        if len(editable.pose_markers) != 8:
            raise RuntimeError(f"{editable.name} does not have eight action markers")

        armature.animation_data.action = source
        source_poses = []
        for frame in specification["source_frames"]:
            scene.frame_set(frame)
            source_poses.append(_pose(armature))
        armature.animation_data.action = editable
        for edit_frame, expected in enumerate(source_poses, start=1):
            scene.frame_set(edit_frame)
            actual = _pose(armature)
            mismatches = [
                name for name in expected
                if not _matrix_close(expected[name], actual[name])
            ]
            if mismatches:
                raise RuntimeError(
                    f"{editable.name} frame {edit_frame} differs from {source.name}: "
                    f"{mismatches}"
                )
        scene.frame_set(1)
        first = _pose(armature)
        scene.frame_set(9)
        closure = _pose(armature)
        if any(not _matrix_close(first[name], closure[name]) for name in first):
            raise RuntimeError(f"{editable.name} frame 9 is not an exact closure")

    if manifest["active_action"] != "PF_Walk_Meshy_Edit":
        raise RuntimeError("Walk should be the default teaching action")
    print(
        "Validated three editable eight-pose motions with exact closures and "
        "protected PF_Idle, PF_Walk, and PF_Run sources"
    )


if __name__ == "__main__":
    main()
