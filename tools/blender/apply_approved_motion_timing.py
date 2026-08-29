"""Apply or verify approved timing metadata in an open canonical Blender file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy


SEQUENCES = {
    "idle": "PF_Idle_Approved",
    "walk": "PF_Walk_Approved",
    "run": "PF_Run_Approved",
}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timing", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    argv = []
    if "--" in __import__("sys").argv:
        argv = __import__("sys").argv[__import__("sys").argv.index("--") + 1 :]
    return parser.parse_args(argv)


def _durations(specification: dict[str, object]) -> list[int]:
    count = int(specification["frame_count"])
    values = [int(specification["default_frame_duration_ms"])] * count
    for raw_frame, raw_duration in specification[
        "frame_duration_overrides_ms"
    ].items():
        frame = int(raw_frame)
        if not 1 <= frame <= count:
            raise ValueError(f"Duration override frame {frame} is out of range")
        values[frame - 1] = int(raw_duration)
    return values


def main() -> None:
    args = _args()
    timing = json.loads(args.timing.read_text(encoding="utf-8"))
    changed = False
    for sequence, action_name in SEQUENCES.items():
        action = bpy.data.actions.get(action_name)
        if action is None:
            raise RuntimeError(f"Missing canonical action {action_name}")
        expected_fps = int(timing[sequence]["fps"])
        expected_durations = json.dumps(_durations(timing[sequence]))
        actual_fps = int(action.get("pf_preview_fps", 0))
        actual_durations = action.get("pf_frame_durations_ms_json")
        if args.check:
            if actual_fps != expected_fps or actual_durations != expected_durations:
                raise RuntimeError(f"{action_name} timing metadata is stale")
            continue
        if actual_fps != expected_fps:
            action["pf_preview_fps"] = expected_fps
            changed = True
        if actual_durations != expected_durations:
            action["pf_frame_durations_ms_json"] = expected_durations
            changed = True
    if changed:
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
        print(f"Updated approved motion timing in {bpy.data.filepath}")
    else:
        print(f"Approved motion timing already current in {bpy.data.filepath}")


if __name__ == "__main__":
    main()
