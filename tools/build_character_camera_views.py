"""Render, promote, and verify the three canonical Character Forge camera heights."""

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
TIMING = MODEL_ROOT / "approved_motion_timing.json"
SPECS = ASSET_ROOT / "sheet_specs.json"
CAMERA_MANIFEST = ASSET_ROOT / "camera_views_manifest.json"
BLENDER_DEFAULT = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")

DIRECTIONS = ("front", "back", "right", "left")
SEQUENCES = ("idle", "walk", "run")
CAMERAS = {
    "top_down": {"name": "Near Top-Down", "pitch_degrees": 70.0},
    "three_quarter": {"name": "Three-Quarter", "pitch_degrees": 45.0},
    "low": {"name": "Low", "pitch_degrees": 28.0},
}
RENDER_CAMERAS = ("top_down", "three_quarter")
BASES = {
    "elf_bald_female": {
        "base_id": "elf-01",
        "name": "Elf Female Base",
        "blend": "elf_bald_female/canonical/elf_bald_female_mannequin.blend",
        "semantic_low": True,
        "framing_scales": {
            "top_down": 1.0,
            "three_quarter": 1.0,
            "low": 1.2525964394593852,
        },
    },
    "tiefling_bald_female": {
        "base_id": "tiefling-female-01",
        "name": "Tiefling Female Base",
        "blend": "tiefling_bald_female/canonical/tiefling_bald_female_approved_motions.blend",
        "semantic_low": False,
        "framing_scales": {camera: 1.0 for camera in CAMERAS},
    },
    "dwarf_bald_male": {
        "base_id": "dwarf-male-01",
        "name": "Dwarf Male Base",
        "blend": "dwarf_bald_male/canonical/dwarf_bald_male_approved_motions.blend",
        "semantic_low": False,
        "framing_scales": {camera: 1.12 for camera in CAMERAS},
    },
    "human_bald_male": {
        "base_id": "human-muscular-male-01",
        "name": "Muscular Human Male Base",
        "blend": "human_bald_male/canonical/human_bald_male_approved_motions.blend",
        "semantic_low": False,
        "framing_scales": {camera: 1.0 for camera in CAMERAS},
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str]) -> None:
    print("Running:", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def _blender() -> Path:
    discovered = shutil.which("blender")
    candidate = Path(discovered) if discovered else BLENDER_DEFAULT
    if not candidate.is_file():
        raise FileNotFoundError("Blender 5.1 executable was not found")
    return candidate


def _working_paths(character_id: str, camera_height: str) -> tuple[Path, Path]:
    root = MODEL_ROOT / character_id / "working" / "camera_views" / camera_height
    return root / "source_renders", root / "pixel_package"


def _render_view(
    character_id: str,
    config: dict[str, object],
    camera_height: str,
    blender: Path,
    *,
    force: bool,
    check: bool,
) -> dict[str, object]:
    renders, pixels = _working_paths(character_id, camera_height)
    render_manifest = renders / "sprite_render_manifest.json"
    pixel_manifest = pixels / "pixel_sprite_manifest.json"
    if check:
        if not render_manifest.is_file() or not pixel_manifest.is_file():
            raise FileNotFoundError(
                f"Missing {character_id}/{camera_height} camera working outputs"
            )
        _run(
            [
                sys.executable,
                str(ROOT / "tools" / "blender" / "pixelize_sprite_sheets.py"),
                "--manifest",
                str(render_manifest),
                "--output-dir",
                str(pixels),
                "--cell-size",
                "128",
                "--palette-size",
                "16",
                "--preview-scale",
                "1",
                "--check",
            ]
        )
    else:
        blend = MODEL_ROOT / str(config["blend"])
        if not blend.is_file():
            raise FileNotFoundError(blend)
        if force:
            for path in (renders, pixels):
                resolved = path.resolve()
                working_root = (MODEL_ROOT / character_id / "working").resolve()
                if working_root not in resolved.parents:
                    raise RuntimeError(f"Refusing to clear path outside {working_root}: {resolved}")
                if path.exists():
                    shutil.rmtree(path)
        elif render_manifest.exists() or pixel_manifest.exists():
            raise FileExistsError(
                f"{character_id}/{camera_height} already exists; use --force to rebuild"
            )
        _run(
            [
                str(blender),
                "--background",
                str(blend),
                "--python-exit-code",
                "1",
                "--python",
                str(ROOT / "tools" / "blender" / "render_sprite_sequences.py"),
                "--",
                "--output-dir",
                str(renders),
                "--render-size",
                "1024",
                "--auto-frame",
                "--pitch",
                str(CAMERAS[camera_height]["pitch_degrees"]),
                "--framing-scale",
                str(config["framing_scales"][camera_height]),
                "--timing-config",
                str(TIMING),
                "--idle-action",
                "PF_Idle_Approved",
                "--walk-action",
                "PF_Walk_Approved",
                "--run-action",
                "PF_Run_Approved",
            ]
        )
        _run(
            [
                sys.executable,
                str(ROOT / "tools" / "blender" / "pixelize_sprite_sheets.py"),
                "--manifest",
                str(render_manifest),
                "--output-dir",
                str(pixels),
                "--cell-size",
                "128",
                "--palette-size",
                "16",
                "--preview-scale",
                "1",
            ]
        )
    render = json.loads(render_manifest.read_text(encoding="utf-8"))
    pixel = json.loads(pixel_manifest.read_text(encoding="utf-8"))
    _validate_generated(
        character_id, config, camera_height, render, pixel, pixels
    )
    return pixel


def _expected_durations(sequence: str) -> list[int]:
    timing = json.loads(TIMING.read_text(encoding="utf-8"))
    return list(runtime_timing(timing, sequence).frame_durations_ms)


def _validate_generated(
    character_id: str,
    config: dict[str, object],
    camera_height: str,
    render: dict[str, object],
    pixel: dict[str, object],
    pixels: Path,
) -> None:
    if float(render["pitch_degrees"]) != float(
        CAMERAS[camera_height]["pitch_degrees"]
    ):
        raise RuntimeError(f"{character_id}/{camera_height} has the wrong pitch")
    if float(render.get("framing_scale", 1.0)) != float(
        config["framing_scales"][camera_height]
    ):
        raise RuntimeError(
            f"{character_id}/{camera_height} has the wrong framing scale"
        )
    if len(pixel["palette"]) != 16:
        raise RuntimeError(f"{character_id}/{camera_height} must use 16 colors")
    for sequence in SEQUENCES:
        data = pixel["sequences"][sequence]
        durations = _expected_durations(sequence)
        if data["frame_durations_ms"] != durations:
            raise RuntimeError(f"{character_id}/{camera_height}/{sequence} timing differs")
        if data["dimensions"] != [128 * len(durations), 128 * len(DIRECTIONS)]:
            raise RuntimeError(f"{character_id}/{camera_height}/{sequence} dimensions differ")
        for direction in DIRECTIONS:
            gif = pixels / data["previews"][direction]
            with Image.open(gif) as opened:
                if opened.size != (128, 128) or opened.n_frames != len(durations):
                    raise RuntimeError(f"Invalid preview {gif}")
                actual = []
                for index in range(opened.n_frames):
                    opened.seek(index)
                    actual.append(int(opened.info["duration"]))
            if actual != [round(value / 10) * 10 for value in durations]:
                raise RuntimeError(f"Invalid GIF timing {gif}")


def _low_gif(base_id: str, semantic: bool, sequence: str, direction: str) -> Path:
    if semantic:
        return (
            ASSET_ROOT
            / "semantic"
            / base_id
            / sequence
            / "gifs"
            / f"{sequence}_{direction}.gif"
        )
    return ASSET_ROOT / "base_sources" / base_id / "gifs" / f"{sequence}_{direction}.gif"


def _variant_record(
    character_id: str,
    config: dict[str, object],
    camera_height: str,
    pixel: dict[str, object] | None,
    *,
    check: bool,
) -> dict[str, object]:
    base_id = str(config["base_id"])
    canonical = MODEL_ROOT / str(config["blend"])
    sequence_records: dict[str, object] = {}
    for sequence in SEQUENCES:
        if camera_height == "low":
            runtime = ASSET_ROOT / "bases" / base_id / f"{sequence}.png"
            gifs = {
                direction: _low_gif(
                    base_id, bool(config["semantic_low"]), sequence, direction
                )
                for direction in DIRECTIONS
            }
            source_frames = list(runtime_timing(
                json.loads(TIMING.read_text(encoding="utf-8")), sequence
            ).source_frames)
            palette_sha = None
        else:
            if pixel is None:
                raise RuntimeError(f"Missing generated pixel data for {camera_height}")
            _, pixels = _working_paths(character_id, camera_height)
            data = pixel["sequences"][sequence]
            runtime = (
                ASSET_ROOT
                / "bases"
                / base_id
                / "camera_views"
                / camera_height
                / f"{sequence}.png"
            )
            source_root = (
                ASSET_ROOT / "base_sources" / base_id / "camera_views" / camera_height
            )
            source_sheet = pixels / data["sheet"]
            gifs = {
                direction: source_root / "gifs" / f"{sequence}_{direction}.gif"
                for direction in DIRECTIONS
            }
            if check:
                if not runtime.is_file() or runtime.read_bytes() != source_sheet.read_bytes():
                    raise RuntimeError(f"Live {base_id}/{camera_height}/{sequence} is stale")
            else:
                runtime.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_sheet, runtime)
            for direction, destination in gifs.items():
                source = pixels / data["previews"][direction]
                if check:
                    if not destination.is_file() or destination.read_bytes() != source.read_bytes():
                        raise RuntimeError(
                            f"Live {base_id}/{camera_height}/{sequence}/{direction} GIF is stale"
                        )
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
            palette = pixels / "palette.png"
            live_palette = source_root / "palette.png"
            if check:
                if not live_palette.is_file() or live_palette.read_bytes() != palette.read_bytes():
                    raise RuntimeError(f"Live {base_id}/{camera_height} palette is stale")
            else:
                live_palette.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(palette, live_palette)
            source_frames = data["source_frames"]
            palette_sha = _sha256(palette)
        if not runtime.is_file():
            raise FileNotFoundError(runtime)
        for gif in gifs.values():
            if not gif.is_file():
                raise FileNotFoundError(gif)
        sequence_records[sequence] = {
            "runtime_file": runtime.relative_to(ASSET_ROOT).as_posix(),
            "runtime_sha256": _sha256(runtime),
            "source_frames": source_frames,
            "frame_durations_ms": _expected_durations(sequence),
            "gifs": {
                direction: {
                    "file": path.relative_to(ASSET_ROOT).as_posix(),
                    "sha256": _sha256(path),
                }
                for direction, path in gifs.items()
            },
        }
    return {
        "pitch_degrees": CAMERAS[camera_height]["pitch_degrees"],
        "framing_scale": config["framing_scales"][camera_height],
        "orthographic": True,
        "canonical_blend": canonical.relative_to(ROOT).as_posix(),
        "canonical_blend_sha256": _sha256(canonical),
        "palette_sha256": palette_sha,
        "sequences": sequence_records,
    }


def _promote(
    generated: dict[tuple[str, str], dict[str, object]], *, check: bool
) -> None:
    bases_manifest: dict[str, object] = {}
    for character_id, config in BASES.items():
        views = {
            camera_height: _variant_record(
                character_id,
                config,
                camera_height,
                generated.get((character_id, camera_height)),
                check=check,
            )
            for camera_height in CAMERAS
        }
        bases_manifest[str(config["base_id"])] = {
            "character_id": character_id,
            "name": config["name"],
            "camera_views": views,
        }
    manifest = {
        "schema_version": 1,
        "status": "canonical",
        "camera_heights": CAMERAS,
        "direction_order": list(DIRECTIONS),
        "sequence_order": list(SEQUENCES),
        "excluded_models": ["human_bald_male_less_muscular"],
        "timing_file": TIMING.relative_to(ROOT).as_posix(),
        "timing_sha256": _sha256(TIMING),
        "bases": bases_manifest,
    }
    expected_manifest = (json.dumps(manifest, indent=2) + "\n").encode()
    specs = json.loads(SPECS.read_text(encoding="utf-8"))
    specs["camera_heights"] = CAMERAS
    for base_id, base_record in bases_manifest.items():
        try:
            base_spec = specs["bases"][base_id]
        except KeyError as exc:
            raise RuntimeError(f"Character Forge specs are missing {base_id}") from exc
        for sequence in SEQUENCES:
            variants = {}
            for camera_height in CAMERAS:
                record = base_record["camera_views"][camera_height]["sequences"][sequence]
                variants[camera_height] = {
                    "runtime_file": record["runtime_file"],
                    "runtime_sha256": record["runtime_sha256"],
                }
            base_spec["animations"][sequence]["camera_variants"] = variants
    expected_specs = (json.dumps(specs, indent=2) + "\n").encode()
    if check:
        if not CAMERA_MANIFEST.is_file() or CAMERA_MANIFEST.read_bytes() != expected_manifest:
            raise RuntimeError("Canonical camera view manifest is stale")
        if SPECS.read_bytes() != expected_specs:
            raise RuntimeError("Character Forge camera metadata is stale")
    else:
        CAMERA_MANIFEST.write_bytes(expected_manifest)
        SPECS.write_bytes(expected_specs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=(*BASES, "all"), default="all")
    parser.add_argument(
        "--camera-height", choices=(*RENDER_CAMERAS, "all"), default="all"
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--promote-only",
        action="store_true",
        help="Refresh live metadata from existing deterministic camera packages",
    )
    args = parser.parse_args()
    if sum(bool(value) for value in (args.force, args.check, args.promote_only)) > 1:
        parser.error("--force, --check, and --promote-only are mutually exclusive")
    selected_bases = list(BASES) if args.target == "all" else [args.target]
    selected_cameras = (
        list(RENDER_CAMERAS)
        if args.camera_height == "all"
        else [args.camera_height]
    )
    blender = _blender()
    generated: dict[tuple[str, str], dict[str, object]] = {}
    for character_id in BASES:
        for camera_height in RENDER_CAMERAS:
            _, pixels = _working_paths(character_id, camera_height)
            pixel_manifest = pixels / "pixel_sprite_manifest.json"
            if (
                not args.promote_only
                and character_id in selected_bases
                and camera_height in selected_cameras
            ):
                generated[(character_id, camera_height)] = _render_view(
                    character_id,
                    BASES[character_id],
                    camera_height,
                    blender,
                    force=args.force,
                    check=args.check,
                )
            elif pixel_manifest.is_file():
                generated[(character_id, camera_height)] = json.loads(
                    pixel_manifest.read_text(encoding="utf-8")
                )
    missing = [
        f"{character_id}/{camera_height}"
        for character_id in BASES
        for camera_height in RENDER_CAMERAS
        if (character_id, camera_height) not in generated
    ]
    if missing:
        raise RuntimeError(
            "All camera views must exist before canonical promotion; missing "
            + ", ".join(missing)
        )
    _promote(generated, check=args.check)
    verb = "Verified" if args.check else "Promoted"
    print(f"{verb} three canonical camera heights for {len(BASES)} Character Forge bases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
