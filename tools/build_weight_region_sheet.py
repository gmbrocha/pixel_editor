"""Reduce weight-derived semantic renders into Character Forge region sheets."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.mannequin_semantics import REGIONS
from src.core.semantic_sprite_package import _downsample_regions, _preview


DIRECTIONS = ("front", "back", "right", "left")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _portable_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _portable_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_portable_value(item) for item in value]
    if isinstance(value, str):
        candidate = Path(value)
        if candidate.is_absolute():
            return _display_path(candidate)
    return value


def _portable_manifest_sha256(manifest: dict[str, object]) -> str:
    payload = json.dumps(
        _portable_value(manifest), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _build(
    manifest_path: Path,
    base_sheet_path: Path,
    output_dir: Path,
    sequence_name: str,
) -> dict[str, object]:
    source = json.loads(manifest_path.read_text(encoding="utf-8"))
    if source.get("semantic", {}).get("derived_from_weights") is not True:
        raise ValueError("Semantic source was not derived from rig weights")
    if source.get("direction_order") != list(DIRECTIONS):
        raise ValueError("Semantic source direction order differs")
    sequence = source.get("sequences", {}).get(sequence_name)
    if not isinstance(sequence, dict):
        raise ValueError(f"Semantic source has no {sequence_name} sequence")
    frames = [int(value) for value in sequence.get("source_frames", [])]
    frame_count = len(frames)
    expected_size = (128 * frame_count, 128 * len(DIRECTIONS))
    with Image.open(base_sheet_path) as opened:
        base_sheet = opened.convert("RGBA")
    if base_sheet.size != expected_size:
        raise ValueError(
            f"Base sheet is {base_sheet.size}, expected {expected_size}"
        )

    region_sheet = Image.new("L", expected_size, 0)
    semantic_hashes: dict[str, str] = {}
    rescued: dict[str, list[int]] = {}
    for row, direction in enumerate(DIRECTIONS):
        raw_paths = source["sequences"][sequence_name]["semantic_directions"][
            direction
        ]
        if len(raw_paths) != frame_count:
            raise ValueError(f"{sequence_name}/{direction} frame count differs")
        for column, raw_path in enumerate(raw_paths):
            semantic_path = Path(raw_path)
            if not semantic_path.is_absolute():
                semantic_path = manifest_path.parent / semantic_path
            semantic_path = semantic_path.resolve()
            with Image.open(semantic_path) as opened:
                semantic = opened.convert("RGBA")
            box = (
                column * 128,
                row * 128,
                (column + 1) * 128,
                (row + 1) * 128,
            )
            art = base_sheet.crop(box)
            ids, rescued_ids = _downsample_regions(
                semantic, art, 128, 112, 8
            )
            region_sheet.paste(Image.fromarray(ids, "L"), box[:2])
            relative = f"{direction}/frame_{column:02d}"
            semantic_hashes[relative] = _sha256(semantic_path)
            if rescued_ids:
                rescued[relative] = rescued_ids

    ids = np.asarray(region_sheet, dtype=np.uint8)
    base_alpha = np.asarray(base_sheet, dtype=np.uint8)[..., 3] > 0
    if not np.array_equal(ids > 0, base_alpha):
        raise RuntimeError("Region coverage does not exactly match base alpha")
    present = sorted(int(value) for value in np.unique(ids) if value > 0)
    missing = sorted(region.id for region in REGIONS if region.id not in present)
    if missing:
        raise RuntimeError(f"Region sheet is missing region IDs {missing}")

    output_dir.mkdir(parents=True, exist_ok=True)
    region_path = output_dir / f"{sequence_name}_regions.png"
    preview_path = output_dir / f"{sequence_name}_regions_preview.png"
    region_sheet.save(region_path, format="PNG", optimize=False, compress_level=9)
    _preview(ids).save(
        preview_path, format="PNG", optimize=False, compress_level=9
    )
    manifest = {
        "schema_version": 1,
        "kind": "weight_derived_character_region_sheet",
        "sequence": sequence_name,
        "base_sheet": _display_path(base_sheet_path),
        "base_sheet_sha256": _sha256(base_sheet_path),
        "paired_manifest": _display_path(manifest_path),
        "paired_manifest_sha256": _portable_manifest_sha256(source),
        "source_blend": _display_path(Path(str(source["blend"]))),
        "source_blend_sha256": source["blend_sha256"],
        "source_frames": frames,
        "direction_order": list(DIRECTIONS),
        "sheet_dimensions": list(expected_size),
        "region_ids": present,
        "rescued_regions": rescued,
        "semantic_render_sha256": semantic_hashes,
        "outputs": {
            region_path.name: _sha256(region_path),
            preview_path.name: _sha256(preview_path),
        },
    }
    manifest_path_out = output_dir / f"{sequence_name}_region_manifest.json"
    manifest_path_out.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--base-sheet", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--sequence", required=True, choices=("idle", "walk", "run"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="pf-weight-regions-") as temporary:
            candidate = Path(temporary)
            _build(args.manifest, args.base_sheet, candidate, args.sequence)
            expected = {path.relative_to(candidate): path for path in candidate.rglob("*") if path.is_file()}
            mismatches = [
                relative.as_posix()
                for relative, path in expected.items()
                if not (args.output_dir / relative).is_file()
                or (args.output_dir / relative).read_bytes() != path.read_bytes()
            ]
        if mismatches:
            raise SystemExit("Weight-region outputs differ: " + ", ".join(mismatches))
        print(f"Verified {args.sequence} region sheet in {args.output_dir.resolve()}")
        return 0
    _build(args.manifest, args.base_sheet, args.output_dir, args.sequence)
    print(f"Wrote {args.sequence} region sheet to {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
