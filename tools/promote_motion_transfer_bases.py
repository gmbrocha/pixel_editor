"""Promote approved target motions into canonical blends and Character Forge bases."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.core.motion_timing import runtime_timing

MODEL_ROOT = ROOT / "animation_images_models"
ASSET_ROOT = ROOT / "assets" / "character-forge"
CONFIG = MODEL_ROOT / "motion_transfer_targets.json"
TIMING = MODEL_ROOT / "approved_motion_timing.json"
BLENDER_DEFAULT = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")
DIRECTIONS = ("front", "back", "right", "left")
SEQUENCES = ("idle", "walk", "run")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str]) -> None:
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def _blender() -> Path:
    discovered = shutil.which("blender")
    candidate = Path(discovered) if discovered else BLENDER_DEFAULT
    if not candidate.is_file():
        raise FileNotFoundError("Blender 5.1 executable was not found")
    return candidate


def _target_paths(target_id: str, target: dict[str, str]) -> dict[str, Path]:
    candidate_root = MODEL_ROOT / target_id / "working" / "motion_transfer"
    input_blend = (
        MODEL_ROOT / target["approved_idle_edit"]
        if target.get("approved_idle_edit")
        else candidate_root / f"{target_id}_motion_transfer_candidate.blend"
    )
    canonical_root = MODEL_ROOT / target_id / "canonical"
    promotion_root = MODEL_ROOT / target_id / "working" / "motion_promotion"
    return {
        "input": input_blend,
        "canonical": canonical_root / f"{target_id}_approved_motions.blend",
        "canonical_manifest": canonical_root / "approved_motions_manifest.json",
        "renders": promotion_root / "source_renders",
        "pixels": promotion_root / "pixel_package",
    }


def _build_target(
    target_id: str,
    target: dict[str, str],
    blender: Path,
    force: bool,
    check: bool,
) -> tuple[dict[str, Path], dict[str, object]]:
    paths = _target_paths(target_id, target)
    if check:
        required = (
            paths["canonical"],
            paths["canonical_manifest"],
            paths["renders"] / "sprite_render_manifest.json",
            paths["pixels"] / "pixel_sprite_manifest.json",
        )
        missing = [path for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Missing promoted outputs for {target_id}: {missing}")
        canonical_manifest = json.loads(
            paths["canonical_manifest"].read_text(encoding="utf-8")
        )
        if canonical_manifest["canonical_blend_sha256"] != _sha256(paths["canonical"]):
            raise RuntimeError(f"{target_id} canonical blend hash is stale")
        _run([
            sys.executable,
            str(ROOT / "tools" / "blender" / "pixelize_sprite_sheets.py"),
            "--manifest", str(paths["renders"] / "sprite_render_manifest.json"),
            "--output-dir", str(paths["pixels"]),
            "--cell-size", "128",
            "--palette-size", "16",
            "--preview-scale", "1",
            "--check",
        ])
    else:
        if not paths["input"].is_file():
            raise FileNotFoundError(paths["input"])
        force_flag = ["--force"] if force else []
        _run([
            str(blender), "--background", str(paths["input"]),
            "--python-exit-code", "1",
            "--python", str(ROOT / "tools" / "blender" / "promote_motion_transfer_actions.py"),
            "--",
            "--input", str(paths["input"]),
            "--output", str(paths["canonical"]),
            "--manifest", str(paths["canonical_manifest"]),
            "--character-id", target_id,
            "--idle-action", target.get("approved_idle_action", "PF_Idle_Transfer"),
            "--timing", str(TIMING),
            *force_flag,
        ])
        if paths["renders"].exists() and force:
            shutil.rmtree(paths["renders"])
        _run([
            str(blender), "--background", str(paths["canonical"]),
            "--python-exit-code", "1",
            "--python", str(ROOT / "tools" / "blender" / "render_sprite_sequences.py"),
            "--",
            "--output-dir", str(paths["renders"]),
            "--render-size", "1024",
            "--auto-frame",
            "--framing-scale", str(target.get("sprite_framing_scale", 1.0)),
            "--idle-action", "PF_Idle_Approved",
            "--walk-action", "PF_Walk_Approved",
            "--run-action", "PF_Run_Approved",
            "--timing-config", str(TIMING),
        ])
        _run([
            sys.executable,
            str(ROOT / "tools" / "blender" / "pixelize_sprite_sheets.py"),
            "--manifest", str(paths["renders"] / "sprite_render_manifest.json"),
            "--output-dir", str(paths["pixels"]),
            "--cell-size", "128",
            "--palette-size", "16",
            "--preview-scale", "1",
        ])
    pixel = json.loads(
        (paths["pixels"] / "pixel_sprite_manifest.json").read_text(encoding="utf-8")
    )
    render = json.loads(
        (paths["renders"] / "sprite_render_manifest.json").read_text(encoding="utf-8")
    )
    expected_framing_scale = float(target.get("sprite_framing_scale", 1.0))
    if float(render.get("framing_scale", 1.0)) != expected_framing_scale:
        raise RuntimeError(
            f"{target_id} framing scale differs from {expected_framing_scale}"
        )
    timing = json.loads(TIMING.read_text(encoding="utf-8"))
    if len(pixel["palette"]) != 16:
        raise RuntimeError(f"{target_id} does not have one 16-color shared palette")
    for sequence in SEQUENCES:
        actual = pixel["sequences"][sequence]
        expected = runtime_timing(timing, sequence)
        count = len(expected.source_frames)
        durations = list(expected.frame_durations_ms)
        if actual["frame_count"] != count or actual["frame_durations_ms"] != durations:
            raise RuntimeError(f"{target_id} {sequence} timing differs from approval")
        for direction in DIRECTIONS:
            gif_path = paths["pixels"] / actual["previews"][direction]
            with Image.open(gif_path) as opened:
                gif_durations = []
                for index in range(opened.n_frames):
                    opened.seek(index)
                    gif_durations.append(int(opened.info["duration"]))
            expected_gif = [round(value / 10) * 10 for value in durations]
            if gif_durations != expected_gif:
                raise RuntimeError(
                    f"{target_id} {sequence}/{direction} GIF timing differs: {gif_durations}"
                )
    return paths, pixel


def _schema_v2(specs: dict[str, object]) -> dict[str, object]:
    if specs.get("schema_version") == 2:
        return specs
    if specs.get("schema_version") != 1:
        raise RuntimeError("Unsupported Character Forge sheet specification")
    base_id = str(specs.pop("base_id"))
    base_name = str(specs.pop("base_name"))
    animations = specs.pop("animations")
    specs["schema_version"] = 2
    specs["default_base_id"] = base_id
    specs["bases"] = {
        base_id: {
            "name": base_name,
            "semantic": True,
            "animations": animations,
        }
    }
    return specs


def _base_entry(
    target_id: str,
    target: dict[str, str],
    paths: dict[str, Path],
    pixel: dict[str, object],
    check: bool,
) -> dict[str, object]:
    base_id = target["base_id"]
    runtime_dir = ASSET_ROOT / "bases" / base_id
    source_dir = ASSET_ROOT / "base_sources" / base_id
    if not check:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "gifs").mkdir(parents=True, exist_ok=True)
        shutil.copy2(paths["pixels"] / "palette.png", source_dir / "palette.png")
    animations = {}
    source_sequences = {}
    for sequence in SEQUENCES:
        data = pixel["sequences"][sequence]
        source_sheet = paths["pixels"] / data["sheet"]
        runtime = runtime_dir / f"{sequence}.png"
        if check:
            if not runtime.is_file() or runtime.read_bytes() != source_sheet.read_bytes():
                raise RuntimeError(f"Live {base_id} {sequence} sheet is stale")
        else:
            shutil.copy2(source_sheet, runtime)
        gif_records = {}
        for direction in DIRECTIONS:
            source_gif = paths["pixels"] / data["previews"][direction]
            destination = source_dir / "gifs" / f"{sequence}_{direction}.gif"
            if check:
                if not destination.is_file() or destination.read_bytes() != source_gif.read_bytes():
                    raise RuntimeError(f"Live {base_id} {sequence}/{direction} GIF is stale")
            else:
                shutil.copy2(source_gif, destination)
            gif_records[direction] = destination.relative_to(ASSET_ROOT).as_posix()
        source_sequences[sequence] = {
            "action": data["action"],
            "source_frames": data["source_frames"],
            "frame_durations_ms": data["frame_durations_ms"],
            "runtime_sha256": _sha256(source_sheet),
            "gifs": gif_records,
        }
        animations[sequence] = {
            "name": sequence.title(),
            "runtime_file": runtime.relative_to(ASSET_ROOT).as_posix(),
            "runtime_sha256": _sha256(source_sheet),
            "sheet_size": data["dimensions"],
            "logical_extent": data["dimensions"],
            "frames_per_direction": data["frame_count"],
            "direction_rows": {direction: index for index, direction in enumerate(DIRECTIONS)},
            "direction_playback": {
                direction: list(range(data["frame_count"])) for direction in DIRECTIONS
            },
            "fps": data["fps"],
            "frame_durations_ms": data["frame_durations_ms"],
            "source_matte": None,
            "pivot": None,
            "sources": [{
                "file": (source_dir / "manifest.json").relative_to(ASSET_ROOT).as_posix(),
                "action": data["action"],
                "source_frames": data["source_frames"],
            }],
        }
    source_manifest = {
        "schema_version": 1,
        "status": "approved_character_base",
        "base_id": base_id,
        "character_id": target_id,
        "canonical_blend": paths["canonical"].relative_to(ROOT).as_posix(),
        "canonical_blend_sha256": _sha256(paths["canonical"]),
        "canonical_manifest_sha256": _sha256(paths["canonical_manifest"]),
        "timing_sha256": _sha256(TIMING),
        "palette_sha256": _sha256(paths["pixels"] / "palette.png"),
        "sequences": source_sequences,
    }
    manifest_path = source_dir / "manifest.json"
    expected = (json.dumps(source_manifest, indent=2) + "\n").encode()
    if check:
        if not manifest_path.is_file() or manifest_path.read_bytes() != expected:
            raise RuntimeError(f"Live {base_id} source manifest is stale")
    else:
        manifest_path.write_bytes(expected)
    return {
        "name": target["display_name"],
        "semantic": False,
        "animations": animations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=("tiefling_bald_female", "dwarf_bald_male", "human_bald_male", "all"),
        default="all",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.force and args.check:
        parser.error("--force and --check are mutually exclusive")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    targets = list(config["targets"]) if args.target == "all" else [args.target]
    blender = _blender()
    built = {
        target_id: _build_target(
            target_id, config["targets"][target_id], blender, args.force, args.check
        )
        for target_id in targets
    }
    specs_path = ASSET_ROOT / "sheet_specs.json"
    specs = _schema_v2(json.loads(specs_path.read_text(encoding="utf-8")))
    for target_id in targets:
        target = config["targets"][target_id]
        paths, pixel = built[target_id]
        entry = _base_entry(target_id, target, paths, pixel, args.check)
        previous = specs["bases"].get(target["base_id"], {})
        previous_animations = previous.get("animations", {})
        for sequence in SEQUENCES:
            old_variants = previous_animations.get(sequence, {}).get(
                "camera_variants", {}
            )
            if old_variants:
                entry["animations"][sequence]["camera_variants"] = {
                    **old_variants,
                    "low": {
                        "runtime_file": entry["animations"][sequence]["runtime_file"],
                        "runtime_sha256": entry["animations"][sequence]["runtime_sha256"],
                    },
                }
        if args.check:
            if specs["bases"].get(target["base_id"]) != entry:
                raise RuntimeError(f"Character Forge metadata for {target['base_id']} is stale")
        else:
            specs["bases"][target["base_id"]] = entry
    if not args.check:
        specs_path.write_text(
            json.dumps(specs, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"Promoted {len(targets)} target base(s) into {ASSET_ROOT.resolve()}")
    else:
        print(f"Verified {len(targets)} promoted target base(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
