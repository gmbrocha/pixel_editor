"""Build, promote, and verify the canonical JRPG Chibi Character Forge style."""

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
MODEL_ROOT = ROOT / "animation_images_models"
ASSET_ROOT = ROOT / "assets" / "character-forge"
STYLE = MODEL_ROOT / "chibi_style.json"
TIMING = MODEL_ROOT / "approved_motion_timing.json"
SPECS = ASSET_ROOT / "sheet_specs.json"
MANIFEST = ASSET_ROOT / "chibi_manifest.json"
BLENDER_DEFAULT = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")

STYLE_ID = "jrpg_chibi"
DIRECTIONS = ("front", "back", "right", "left")
SEQUENCES = ("idle", "walk", "run")
CAMERAS = {
    "top_down": {"name": "Near Top-Down", "pitch_degrees": 70.0},
    "three_quarter": {"name": "Three-Quarter", "pitch_degrees": 45.0},
    "low": {"name": "Low", "pitch_degrees": 28.0},
}
BASES = {
    "elf_bald_female": {
        "base_id": "elf-01",
        "name": "Elf Female Base",
        "blend": "elf_bald_female/canonical/elf_bald_female_mannequin.blend",
    },
    "tiefling_bald_female": {
        "base_id": "tiefling-female-01",
        "name": "Tiefling Female Base",
        "blend": "tiefling_bald_female/canonical/tiefling_bald_female_approved_motions.blend",
    },
    "dwarf_bald_male": {
        "base_id": "dwarf-male-01",
        "name": "Dwarf Male Base",
        "blend": "dwarf_bald_male/canonical/dwarf_bald_male_approved_motions.blend",
    },
    "human_bald_male": {
        "base_id": "human-muscular-male-01",
        "name": "Muscular Human Male Base",
        "blend": "human_bald_male/canonical/human_bald_male_approved_motions.blend",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: list[str]) -> None:
    print("Running:", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def _blender() -> Path:
    discovered = shutil.which("blender")
    candidate = Path(discovered) if discovered else BLENDER_DEFAULT
    if not candidate.is_file():
        raise FileNotFoundError("Blender 5.1 executable was not found")
    return candidate


def _working_root(character_id: str, camera_height: str) -> Path:
    return MODEL_ROOT / character_id / "working" / "chibi" / camera_height


def _working_paths(character_id: str, camera_height: str) -> dict[str, Path]:
    root = _working_root(character_id, camera_height)
    return {
        "root": root,
        "renders": root / "source_renders",
        "normalized": root / "normalized_renders",
        "pixels": root / "pixel_package",
        "regions": root / "regions",
    }


def _safe_clear(path: Path, character_id: str) -> None:
    if not path.exists():
        return
    resolved = path.resolve()
    allowed = (MODEL_ROOT / character_id / "working" / "chibi").resolve()
    if allowed not in resolved.parents:
        raise RuntimeError(f"Refusing to clear path outside {allowed}: {resolved}")
    shutil.rmtree(resolved)


def _style() -> dict[str, object]:
    data = json.loads(STYLE.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("id") != STYLE_ID:
        raise RuntimeError(f"Unsupported chibi style profile: {STYLE}")
    return data


def _build_view(
    character_id: str,
    config: dict[str, object],
    camera_height: str,
    blender: Path,
    style: dict[str, object],
    *,
    force: bool,
) -> None:
    paths = _working_paths(character_id, camera_height)
    final_manifest = paths["pixels"] / "pixel_sprite_manifest.json"
    if final_manifest.exists() and not force:
        raise FileExistsError(
            f"{character_id}/{camera_height} chibi output exists; use --force"
        )
    if force:
        _safe_clear(paths["root"], character_id)
    blend = MODEL_ROOT / str(config["blend"])
    if not blend.is_file():
        raise FileNotFoundError(blend)
    framing = float(style["framing_scales"][character_id])
    _run(
        [
            str(blender),
            "--background",
            str(blend),
            "--python-exit-code",
            "1",
            "--python",
            str(ROOT / "tools" / "blender" / "render_chibi_sprite_sequences.py"),
            "--",
            "--output-dir",
            str(paths["renders"]),
            "--style-config",
            str(STYLE),
            "--character-id",
            character_id,
            "--render-size",
            str(style["render_size"]),
            "--pitch",
            str(CAMERAS[camera_height]["pitch_degrees"]),
            "--framing-scale",
            str(framing),
            "--timing-config",
            str(TIMING),
        ]
    )
    render_manifest = paths["renders"] / "sprite_render_manifest.json"
    _run(
        [
            sys.executable,
            str(ROOT / "tools" / "normalize_chibi_renders.py"),
            "--manifest",
            str(render_manifest),
            "--output-dir",
            str(paths["normalized"]),
        ]
    )
    normalized_manifest = paths["normalized"] / "sprite_render_manifest.json"
    command = [
        sys.executable,
        str(ROOT / "tools" / "blender" / "pixelize_sprite_sheets.py"),
        "--manifest",
        str(normalized_manifest),
        "--output-dir",
        str(paths["pixels"]),
        "--cell-size",
        "128",
        "--palette-size",
        str(style["palette_size"]),
        "--alpha-threshold",
        str(style["alpha_threshold"]),
        "--cleanup-threshold",
        str(style["cleanup_threshold"]),
        "--preview-scale",
        "1",
    ]
    if style.get("silhouette_outline") is True:
        command.append("--silhouette-outline")
    _run(command)
    for sequence in SEQUENCES:
        _run(
            [
                sys.executable,
                str(ROOT / "tools" / "build_weight_region_sheet.py"),
                "--manifest",
                str(normalized_manifest),
                "--base-sheet",
                str(paths["pixels"] / "sheets" / f"{sequence}_four_direction_128px.png"),
                "--output-dir",
                str(paths["regions"] / sequence),
                "--sequence",
                sequence,
            ]
        )


def _verify_view(character_id: str, camera_height: str, style: dict[str, object]) -> dict[str, object]:
    paths = _working_paths(character_id, camera_height)
    normalized_manifest = paths["normalized"] / "sprite_render_manifest.json"
    pixel_manifest = paths["pixels"] / "pixel_sprite_manifest.json"
    if not normalized_manifest.is_file() or not pixel_manifest.is_file():
        raise FileNotFoundError(f"Missing {character_id}/{camera_height} chibi outputs")
    _run(
        [
            sys.executable,
            str(ROOT / "tools" / "normalize_chibi_renders.py"),
            "--manifest",
            str(paths["renders"] / "sprite_render_manifest.json"),
            "--output-dir",
            str(paths["normalized"]),
            "--check",
        ]
    )
    pixel_command = [
        sys.executable,
        str(ROOT / "tools" / "blender" / "pixelize_sprite_sheets.py"),
        "--manifest",
        str(normalized_manifest),
        "--output-dir",
        str(paths["pixels"]),
        "--cell-size",
        "128",
        "--palette-size",
        str(style["palette_size"]),
        "--alpha-threshold",
        str(style["alpha_threshold"]),
        "--cleanup-threshold",
        str(style["cleanup_threshold"]),
        "--preview-scale",
        "1",
        "--check",
    ]
    if style.get("silhouette_outline") is True:
        pixel_command.append("--silhouette-outline")
    _run(pixel_command)
    data = json.loads(pixel_manifest.read_text(encoding="utf-8"))
    if data["direction_order"] != list(DIRECTIONS) or len(data["palette"]) != int(style["palette_size"]):
        raise RuntimeError(f"Invalid pixel manifest for {character_id}/{camera_height}")
    report: dict[str, object] = {"sequences": {}}
    for sequence in SEQUENCES:
        sheet = paths["pixels"] / "sheets" / f"{sequence}_four_direction_128px.png"
        region_dir = paths["regions"] / sequence
        _run(
            [
                sys.executable,
                str(ROOT / "tools" / "build_weight_region_sheet.py"),
                "--manifest",
                str(normalized_manifest),
                "--base-sheet",
                str(sheet),
                "--output-dir",
                str(region_dir),
                "--sequence",
                sequence,
                "--check",
            ]
        )
        sequence_data = data["sequences"][sequence]
        expected = (int(sequence_data["frame_count"]) * 128, 512)
        with Image.open(sheet) as opened:
            image = opened.convert("RGBA")
        if image.size != expected:
            raise RuntimeError(f"{sheet} is {image.size}; expected {expected}")
        margins = []
        for row in range(4):
            for column in range(int(sequence_data["frame_count"])):
                frame = image.crop((column * 128, row * 128, (column + 1) * 128, (row + 1) * 128))
                bbox = frame.getchannel("A").getbbox()
                if bbox is None:
                    raise RuntimeError(f"Empty frame in {sheet}: row {row}, frame {column}")
                margins.append(min(bbox[0], bbox[1], 128 - bbox[2], 128 - bbox[3]))
        if min(margins) < 8:
            raise RuntimeError(f"{sheet} has unsafe canvas margin {min(margins)}")
        report["sequences"][sequence] = {
            "frame_count": int(sequence_data["frame_count"]),
            "fps": int(sequence_data["fps"]),
            "frame_durations_ms": sequence_data["frame_durations_ms"],
            "minimum_alpha_margin": min(margins),
            "sheet_sha256": _sha256(sheet),
            "regions_sha256": _sha256(region_dir / f"{sequence}_regions.png"),
        }
    report["pixel_manifest_sha256"] = _sha256(pixel_manifest)
    report["normalized_manifest_sha256"] = _sha256(normalized_manifest)
    return report


def _copy_file(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return _sha256(destination)


def _promote_view(
    character_id: str,
    config: dict[str, object],
    camera_height: str,
    report: dict[str, object],
) -> dict[str, object]:
    paths = _working_paths(character_id, camera_height)
    base_id = str(config["base_id"])
    promoted: dict[str, object] = {"sequences": {}}
    palette_source = paths["pixels"] / "palette.png"
    palette_target = ASSET_ROOT / "base_sources" / base_id / "styles" / STYLE_ID / camera_height / "palette.png"
    promoted["palette"] = {
        "file": palette_target.relative_to(ASSET_ROOT).as_posix(),
        "sha256": _copy_file(palette_source, palette_target),
    }
    for sequence in SEQUENCES:
        sheet_source = paths["pixels"] / "sheets" / f"{sequence}_four_direction_128px.png"
        sheet_target = ASSET_ROOT / "bases" / base_id / "styles" / STYLE_ID / camera_height / f"{sequence}.png"
        region_source = paths["regions"] / sequence / f"{sequence}_regions.png"
        region_target = ASSET_ROOT / "style_regions" / STYLE_ID / base_id / camera_height / f"{sequence}_regions.png"
        preview_source = paths["regions"] / sequence / f"{sequence}_regions_preview.png"
        preview_target = ASSET_ROOT / "style_regions" / STYLE_ID / base_id / camera_height / f"{sequence}_regions_preview.png"
        review_source = paths["pixels"] / "review" / f"{sequence}_four_direction_128px_4x.png"
        review_target = ASSET_ROOT / "base_sources" / base_id / "styles" / STYLE_ID / camera_height / f"{sequence}_review_4x.png"
        gifs = {}
        for direction in DIRECTIONS:
            gif_source = paths["pixels"] / "review" / f"{sequence}_{direction}_{report['sequences'][sequence]['fps']}fps.gif"
            gif_target = ASSET_ROOT / "base_sources" / base_id / "styles" / STYLE_ID / camera_height / f"{sequence}_{direction}.gif"
            gifs[direction] = {
                "file": gif_target.relative_to(ASSET_ROOT).as_posix(),
                "sha256": _copy_file(gif_source, gif_target),
            }
        promoted["sequences"][sequence] = {
            **report["sequences"][sequence],
            "sheet": sheet_target.relative_to(ASSET_ROOT).as_posix(),
            "sheet_sha256": _copy_file(sheet_source, sheet_target),
            "regions": region_target.relative_to(ASSET_ROOT).as_posix(),
            "regions_sha256": _copy_file(region_source, region_target),
            "region_preview": preview_target.relative_to(ASSET_ROOT).as_posix(),
            "region_preview_sha256": _copy_file(preview_source, preview_target),
            "review": review_target.relative_to(ASSET_ROOT).as_posix(),
            "review_sha256": _copy_file(review_source, review_target),
            "gifs": gifs,
        }
    return promoted


def _update_specs(records: dict[str, object]) -> None:
    specs = json.loads(SPECS.read_text(encoding="utf-8"))
    styles = specs.setdefault("sprite_styles", {})
    styles.setdefault("standard", {"name": "Standard Pixel"})
    styles[STYLE_ID] = {
        "name": "JRPG Chibi",
        "description": "Compact limbs and torso with an enlarged head and crisp interior silhouette outline.",
    }
    for character_id, cameras in records.items():
        base_id = str(BASES[character_id]["base_id"])
        for camera_height, camera_record in cameras.items():
            for sequence, sequence_record in camera_record["sequences"].items():
                variants = specs["bases"][base_id]["animations"][sequence].setdefault("camera_variants", {})
                variants[f"{STYLE_ID}_{camera_height}"] = {
                    "runtime_file": sequence_record["sheet"],
                    "runtime_sha256": sequence_record["sheet_sha256"],
                }
    SPECS.write_text(json.dumps(specs, indent=2) + "\n", encoding="utf-8", newline="\n")


def _verify_promoted(manifest: dict[str, object]) -> None:
    for cameras in manifest["characters"].values():
        for camera in cameras.values():
            palette = ASSET_ROOT / camera["palette"]["file"]
            if not palette.is_file() or _sha256(palette) != camera["palette"]["sha256"]:
                raise RuntimeError(f"Promoted chibi palette differs: {palette}")
            for sequence in camera["sequences"].values():
                for file_key, hash_key in (
                    ("sheet", "sheet_sha256"),
                    ("regions", "regions_sha256"),
                    ("region_preview", "region_preview_sha256"),
                    ("review", "review_sha256"),
                ):
                    path = ASSET_ROOT / sequence[file_key]
                    if not path.is_file() or _sha256(path) != sequence[hash_key]:
                        raise RuntimeError(f"Promoted chibi asset differs: {path}")
                for gif in sequence["gifs"].values():
                    path = ASSET_ROOT / gif["file"]
                    if not path.is_file() or _sha256(path) != gif["sha256"]:
                        raise RuntimeError(f"Promoted chibi GIF differs: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=(*BASES, "all"), default="all")
    parser.add_argument("--camera-height", choices=(*CAMERAS, "all"), default="all")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.force and args.check:
        parser.error("--force and --check are mutually exclusive")
    style = _style()
    targets = list(BASES) if args.target == "all" else [args.target]
    cameras = list(CAMERAS) if args.camera_height == "all" else [args.camera_height]
    blender = _blender()
    if not args.check:
        for character_id in targets:
            for camera_height in cameras:
                _build_view(character_id, BASES[character_id], camera_height, blender, style, force=args.force)
    reports: dict[str, object] = {}
    for character_id in targets:
        reports[character_id] = {}
        for camera_height in cameras:
            reports[character_id][camera_height] = _verify_view(character_id, camera_height, style)
    if args.check:
        if args.target == "all" and args.camera_height == "all":
            if not MANIFEST.is_file():
                raise FileNotFoundError(MANIFEST)
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
            if manifest.get("style_config_sha256") != _sha256(STYLE):
                raise RuntimeError("Chibi manifest style hash differs")
            _verify_promoted(manifest)
        print(f"Verified {len(targets) * len(cameras)} chibi Character Forge views")
        return 0
    promoted: dict[str, object] = {}
    for character_id in targets:
        promoted[character_id] = {}
        for camera_height in cameras:
            promoted[character_id][camera_height] = _promote_view(
                character_id, BASES[character_id], camera_height, reports[character_id][camera_height]
            )
    if MANIFEST.is_file() and (args.target != "all" or args.camera_height != "all"):
        old = json.loads(MANIFEST.read_text(encoding="utf-8"))
        merged = old.get("characters", {})
        for character_id, camera_records in promoted.items():
            merged.setdefault(character_id, {}).update(camera_records)
        promoted = merged
    manifest = {
        "schema_version": 1,
        "kind": "canonical_character_forge_sprite_style",
        "status": "canonical",
        "style_id": STYLE_ID,
        "display_name": style["display_name"],
        "style_config": STYLE.relative_to(ROOT).as_posix(),
        "style_config_sha256": _sha256(STYLE),
        "timing_config": TIMING.relative_to(ROOT).as_posix(),
        "timing_config_sha256": _sha256(TIMING),
        "camera_heights": CAMERAS,
        "characters": promoted,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    _update_specs(promoted)
    _verify_promoted(manifest)
    print(f"Built and promoted {len(targets) * len(cameras)} chibi Character Forge views")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
