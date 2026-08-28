"""Promote approved staged pixel Idle and Walk sheets into Character Forge."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


DIRECTION_ROWS = {"front": 0, "back": 1, "right": 2, "left": 3}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pixel-manifest", required=True, type=Path)
    parser.add_argument("--asset-root", required=True, type=Path)
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    args = _args()
    if not args.approved:
        raise RuntimeError("Character Forge promotion requires the explicit --approved flag")
    pixel = json.loads(args.pixel_manifest.read_text(encoding="utf-8"))
    specs_path = args.asset_root / "sheet_specs.json"
    specs = json.loads(specs_path.read_text(encoding="utf-8"))
    sequences = pixel.get("sequences", {})
    if set(("idle", "walk")) - set(sequences):
        raise ValueError("Pixel manifest must contain staged Idle and Walk sequences")
    if pixel.get("direction_order") != list(DIRECTION_ROWS):
        raise ValueError("Staged sheets must use Front, Back, Right, Left row order")
    if pixel.get("settings", {}).get("cell_size") != 64:
        raise ValueError("Character Forge promotion requires 64x64 cells")
    runtime_dir = args.asset_root / "bases" / str(specs["base_id"])
    runtime_dir.mkdir(parents=True, exist_ok=True)
    run_before = json.dumps(specs["animations"]["run"], sort_keys=True)
    manifest_root = args.pixel_manifest.parent
    for role in ("idle", "walk"):
        sequence = sequences[role]
        if sequence.get("frame_count") != 8 or sequence.get("dimensions") != [512, 256]:
            raise ValueError(f"Staged {role} must be an eight-frame 512x256 sheet")
        source = manifest_root / sequence["sheet"]
        destination = runtime_dir / f"{role}.png"
        if destination.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {destination}; pass --force")
        shutil.copy2(source, destination)
        digest = _sha256(destination)
        specs["animations"][role] = {
            "name": role.title(),
            "runtime_file": str(destination.relative_to(args.asset_root)).replace("\\", "/"),
            "runtime_sha256": digest,
            "sheet_size": [512, 256],
            "logical_extent": [512, 256],
            "frames_per_direction": 8,
            "direction_rows": DIRECTION_ROWS,
            "direction_playback": {
                direction: list(range(8)) for direction in DIRECTION_ROWS
            },
            "fps": 10,
            "source_matte": None,
            "pivot": None,
            "generation_size": [2048, 1024],
            "padding": [0, 0, 0, 0],
            "sources": [{
                "file": str(destination.relative_to(args.asset_root)).replace("\\", "/"),
                "sha256": digest,
                "action": sequence["action"],
                "source_frames": sequence["source_frames"],
            }],
        }
    if json.dumps(specs["animations"]["run"], sort_keys=True) != run_before:
        raise RuntimeError("Motion promotion changed Run metadata")
    specs_path.write_text(json.dumps(specs, indent=2) + "\n", encoding="utf-8")
    print(f"Promoted approved Idle and Walk sheets under {runtime_dir.resolve()}")


if __name__ == "__main__":
    main()
