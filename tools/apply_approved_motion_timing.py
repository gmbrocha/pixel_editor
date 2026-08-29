"""Apply or deterministically verify canonical motion timing across live assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.motion_timing import runtime_timing
from src.core.semantic_sprite_package import _native_gif
from src.core.sprite_pixelizer import _save_preview_gif


MODEL_ROOT = ROOT / "animation_images_models"
ASSET_ROOT = ROOT / "assets" / "character-forge"
TIMING = MODEL_ROOT / "approved_motion_timing.json"
SPECS = ASSET_ROOT / "sheet_specs.json"
CAMERA_MANIFEST = ASSET_ROOT / "camera_views_manifest.json"
BLENDER_DEFAULT = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")
DIRECTIONS = ("front", "back", "right", "left")
CAMERAS = ("top_down", "three_quarter", "low")
BASES = {
    "elf-01": "elf_bald_female/canonical/elf_bald_female_mannequin.blend",
    "tiefling-female-01": "tiefling_bald_female/canonical/tiefling_bald_female_approved_motions.blend",
    "dwarf-male-01": "dwarf_bald_male/canonical/dwarf_bald_male_approved_motions.blend",
    "human-muscular-male-01": "human_bald_male/canonical/human_bald_male_approved_motions.blend",
}
TARGETS = {
    "tiefling-female-01": "tiefling_bald_female",
    "dwarf-male-01": "dwarf_bald_male",
    "human-muscular-male-01": "human_bald_male",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(data: object) -> bytes:
    return (json.dumps(data, indent=2) + "\n").encode()


def _sync_json(path: Path, data: object, *, check: bool) -> None:
    expected = _json_bytes(data)
    if check:
        if not path.is_file() or path.read_bytes() != expected:
            raise RuntimeError(f"Stale timing metadata: {path}")
    else:
        path.write_bytes(expected)


def _blender() -> Path:
    discovered = shutil.which("blender")
    candidate = Path(discovered) if discovered else BLENDER_DEFAULT
    if not candidate.is_file():
        raise FileNotFoundError("Blender 5.1 executable was not found")
    return candidate


def _sync_blends(*, check: bool) -> None:
    helper = ROOT / "tools" / "blender" / "apply_approved_motion_timing.py"
    for relative in BASES.values():
        blend = MODEL_ROOT / relative
        command = [
            str(_blender()),
            "--background",
            str(blend),
            "--python-exit-code",
            "1",
            "--python",
            str(helper),
            "--",
            "--timing",
            str(TIMING),
        ]
        if check:
            command.append("--check")
        subprocess.run(command, cwd=ROOT, check=True)


def _authored_durations(timing: dict[str, object], sequence: str) -> list[int]:
    spec = timing[sequence]
    values = [int(spec["default_frame_duration_ms"])] * int(spec["frame_count"])
    for raw_frame, raw_duration in spec["frame_duration_overrides_ms"].items():
        values[int(raw_frame) - 1] = int(raw_duration)
    return values


def _gif_destination(base_id: str, camera: str, direction: str) -> tuple[Path, bool]:
    if camera == "low" and base_id == "elf-01":
        return (
            ASSET_ROOT / "semantic" / "elf-01" / "idle" / "gifs" / f"idle_{direction}.gif",
            True,
        )
    root = ASSET_ROOT / "base_sources" / base_id
    if camera != "low":
        root = root / "camera_views" / camera
    return root / "gifs" / f"idle_{direction}.gif", False


def _sheet(base_id: str, camera: str) -> Path:
    if camera == "low" and base_id == "elf-01":
        return ASSET_ROOT / "semantic" / "elf-01" / "idle" / "idle.png"
    root = ASSET_ROOT / "bases" / base_id
    if camera != "low":
        root = root / "camera_views" / camera
    return root / "idle.png"


def _encode_gif(
    sheet_path: Path,
    row: int,
    output: Path,
    durations: list[int],
    *,
    native: bool,
) -> None:
    with Image.open(sheet_path) as opened:
        sheet = opened.convert("RGBA")
    frames = [
        sheet.crop((index * 128, row * 128, (index + 1) * 128, (row + 1) * 128))
        for index in range(len(durations))
    ]
    if native:
        _native_gif(frames, output, 6, durations)
    else:
        _save_preview_gif(frames, output, 6, scale=1, frame_durations_ms=durations)


def _sync_gifs(durations: list[int], *, check: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="pixel-forge-idle-timing-") as raw_temp:
        temp = Path(raw_temp)
        for base_id in BASES:
            for camera in CAMERAS:
                sheet = _sheet(base_id, camera)
                for row, direction in enumerate(DIRECTIONS):
                    destination, native = _gif_destination(base_id, camera, direction)
                    output = temp / f"{base_id}-{camera}-{direction}.gif" if check else destination
                    _encode_gif(sheet, row, output, durations, native=native)
                    if check and destination.read_bytes() != output.read_bytes():
                        raise RuntimeError(f"Stale Idle GIF timing: {destination}")


def _sync_canonical_manifests(timing: dict[str, object], *, check: bool) -> None:
    authored = _authored_durations(timing, "idle")
    for base_id, target_id in TARGETS.items():
        root = MODEL_ROOT / target_id / "canonical"
        manifest_path = root / "approved_motions_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["canonical_blend_sha256"] = _sha256(
            root / f"{target_id}_approved_motions.blend"
        )
        manifest["sequences"]["idle"]["frame_durations_ms"] = authored
        _sync_json(manifest_path, manifest, check=check)

    elf_root = MODEL_ROOT / "elf_bald_female" / "canonical"
    elf_blend = elf_root / "elf_bald_female_mannequin.blend"
    elf_sha = _sha256(elf_blend)
    approved_path = elf_root / "approved_motions_manifest.json"
    approved = json.loads(approved_path.read_text(encoding="utf-8"))
    approved["output_blend_sha256"] = elf_sha
    _sync_json(approved_path, approved, check=check)
    semantics_path = elf_root / "mannequin_semantics.json"
    semantics = json.loads(semantics_path.read_text(encoding="utf-8"))
    semantics["canonical_blend_sha256"] = elf_sha
    _sync_json(semantics_path, semantics, check=check)
    profile_path = elf_root / "approved_motion_transfer_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["source_blend_sha256"] = elf_sha
    _sync_json(profile_path, profile, check=check)


def _sync_semantic_manifests(
    timing: dict[str, object], durations: list[int], *, check: bool
) -> dict[str, str]:
    elf_blend = MODEL_ROOT / BASES["elf-01"]
    result = {}
    for sequence in ("idle", "walk", "run"):
        path = ASSET_ROOT / "semantic" / "elf-01" / sequence / f"{sequence}_manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["source"]["blend_sha256"] = _sha256(elf_blend)
        if sequence == "idle":
            manifest["frame_durations_ms"] = durations
            default = int(timing["idle"]["runtime_default_frame_duration_ms"])
            manifest["settings"]["frame_duration_overrides"] = [
                [index, duration]
                for index, duration in enumerate(durations, start=1)
                if duration != default
            ]
            for direction in DIRECTIONS:
                relative = f"gifs/idle_{direction}.gif"
                manifest["output_sha256"][relative] = _sha256(path.parent / relative)
        _sync_json(path, manifest, check=check)
        result[sequence] = hashlib.sha256(_json_bytes(manifest)).hexdigest()
    return result


def _sync_target_sources(durations: list[int], *, check: bool) -> None:
    timing_sha = _sha256(TIMING)
    for base_id, target_id in TARGETS.items():
        path = ASSET_ROOT / "base_sources" / base_id / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        canonical_root = MODEL_ROOT / target_id / "canonical"
        manifest["canonical_blend_sha256"] = _sha256(
            canonical_root / f"{target_id}_approved_motions.blend"
        )
        manifest["canonical_manifest_sha256"] = _sha256(
            canonical_root / "approved_motions_manifest.json"
        )
        manifest["timing_sha256"] = timing_sha
        manifest["sequences"]["idle"]["frame_durations_ms"] = durations
        _sync_json(path, manifest, check=check)


def _sync_forge_metadata(
    durations: list[int], semantic_hashes: dict[str, str], *, check: bool
) -> None:
    specs = json.loads(SPECS.read_text(encoding="utf-8"))
    for base_id, base in specs["bases"].items():
        base["animations"]["idle"]["frame_durations_ms"] = durations
        if base_id == "elf-01":
            for sequence in ("idle", "walk", "run"):
                base["animations"][sequence]["sources"][0]["sha256"] = semantic_hashes[
                    sequence
                ]
    _sync_json(SPECS, specs, check=check)

    manifest = json.loads(CAMERA_MANIFEST.read_text(encoding="utf-8"))
    manifest["timing_sha256"] = _sha256(TIMING)
    for base_id, base in manifest["bases"].items():
        blend = MODEL_ROOT / BASES[base_id]
        for camera, view in base["camera_views"].items():
            view["canonical_blend_sha256"] = _sha256(blend)
            idle = view["sequences"]["idle"]
            idle["frame_durations_ms"] = durations
            for direction, record in idle["gifs"].items():
                gif, _native = _gif_destination(base_id, camera, direction)
                record["sha256"] = _sha256(gif)
    _sync_json(CAMERA_MANIFEST, manifest, check=check)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    timing = json.loads(TIMING.read_text(encoding="utf-8"))
    durations = list(runtime_timing(timing, "idle").frame_durations_ms)
    _sync_blends(check=args.check)
    _sync_gifs(durations, check=args.check)
    _sync_canonical_manifests(timing, check=args.check)
    semantic_hashes = _sync_semantic_manifests(timing, durations, check=args.check)
    _sync_target_sources(durations, check=args.check)
    _sync_forge_metadata(durations, semantic_hashes, check=args.check)
    verb = "Verified" if args.check else "Applied"
    print(f"{verb} approved motion timing across four canonical Character Forge bases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
