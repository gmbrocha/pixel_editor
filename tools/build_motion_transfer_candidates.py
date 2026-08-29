"""Build and verify review-only motion-transfer candidates for Meshy characters."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "animation_images_models"
DEFAULT_CONFIG = MODEL_ROOT / "motion_transfer_targets.json"
BLENDER_DEFAULT = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")
TEXTURE_SUFFIXES = (".png", "_metallic.png", "_normal.png", "_roughness.png")


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


def _safe_extract(archive: Path, entry: str, destination: Path, force: bool) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / Path(entry).name
    if output.is_file() and not force:
        return output
    with zipfile.ZipFile(archive) as opened:
        names = set(opened.namelist())
        if entry not in names:
            raise RuntimeError(f"{archive} does not contain {entry}")
        with opened.open(entry) as source, output.open("wb") as target:
            shutil.copyfileobj(source, target)
    return output


def _extract_target_sources(target_id: str, data: dict[str, str], force: bool) -> dict[str, Path]:
    extracted = MODEL_ROOT / target_id / "extracted" / "motion_transfer"
    walk_archive = MODEL_ROOT / data["walk_archive"]
    run_archive = MODEL_ROOT / data["run_archive"]
    texture_archive = MODEL_ROOT / data["texture_archive"]
    for path in (walk_archive, run_archive, texture_archive, MODEL_ROOT / data["bind_fbx"]):
        if not path.is_file():
            raise FileNotFoundError(path)
    walk = _safe_extract(walk_archive, data["walk_entry"], extracted / "walk", force)
    run = _safe_extract(run_archive, data["run_entry"], extracted / "run", force)
    texture_dir = extracted / "textures"
    prefix = data["texture_prefix"]
    for suffix in TEXTURE_SUFFIXES:
        _safe_extract(texture_archive, f"{prefix}{suffix}", texture_dir, force)
    return {
        "bind": MODEL_ROOT / data["bind_fbx"],
        "walk": walk,
        "run": run,
        "textures": texture_dir,
    }


def _profile(config: dict[str, object], blender: Path, force: bool, check: bool) -> Path:
    source = config["source"]
    canonical = MODEL_ROOT / source["canonical_blend"]
    profile = MODEL_ROOT / source["profile"]
    if not canonical.is_file():
        raise FileNotFoundError(canonical)
    script = ROOT / "tools" / "blender" / "build_approved_motion_profile.py"
    if check:
        with tempfile.TemporaryDirectory(prefix="pixel-forge-motion-profile-") as temporary:
            candidate = Path(temporary) / "profile.json"
            _run([
                str(blender), "--background", str(canonical), "--python-exit-code", "1", "--python", str(script), "--",
                "--blend", str(canonical), "--output", str(candidate), "--force",
            ])
            if not profile.is_file() or profile.read_bytes() != candidate.read_bytes():
                raise RuntimeError("Tracked approved motion profile is not current")
        return profile
    if force or not profile.is_file():
        _run([
            str(blender), "--background", str(canonical), "--python-exit-code", "1", "--python", str(script), "--",
            "--blend", str(canonical), "--output", str(profile), "--force",
        ])
    return profile


def _qa(pixel_dir: Path, target_id: str) -> dict[str, object]:
    manifest_path = pixel_dir / "pixel_sprite_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report: dict[str, object] = {"target": target_id, "sequences": {}}
    expected = {"idle": (26, 12), "walk": (8, 10), "run": (8, 10)}
    for sequence_name, (frame_count, fps) in expected.items():
        sequence = manifest["sequences"][sequence_name]
        if sequence["frame_count"] != frame_count or sequence["fps"] != fps:
            raise RuntimeError(f"Unexpected {sequence_name} timing: {sequence}")
        sheet_path = pixel_dir / sequence["sheet"]
        with Image.open(sheet_path) as opened:
            sheet = opened.convert("RGBA")
        margins = []
        for row in range(4):
            for column in range(frame_count):
                cell = sheet.crop((column * 128, row * 128, (column + 1) * 128, (row + 1) * 128))
                box = cell.getchannel("A").getbbox()
                if box is None:
                    raise RuntimeError(f"{target_id} {sequence_name} contains an empty frame")
                margins.append((box[0], box[1], 128 - box[2], 128 - box[3]))
        minimum_margins = [min(values[index] for values in margins) for index in range(4)]
        if min(minimum_margins) < 2:
            raise RuntimeError(
                f"{target_id} {sequence_name} clips or lacks safe margin: {minimum_margins}"
            )
        gifs = {}
        for direction, relative in sequence["previews"].items():
            gif_path = pixel_dir / relative
            with Image.open(gif_path) as opened:
                durations = []
                for index in range(opened.n_frames):
                    opened.seek(index)
                    durations.append(opened.info.get("duration"))
                if opened.size != (128, 128) or opened.n_frames != frame_count:
                    raise RuntimeError(f"Invalid GIF geometry/count: {gif_path}")
                expected_duration = round(round(1000 / fps) / 10) * 10
                if durations != [expected_duration] * frame_count or opened.info.get("loop") != 0:
                    raise RuntimeError(f"Invalid GIF timing/loop: {gif_path}")
            gifs[direction] = relative
        report["sequences"][sequence_name] = {
            "frame_count": frame_count,
            "fps": fps,
            "minimum_margins_left_top_right_bottom": minimum_margins,
            "gifs": gifs,
        }
    report["shared_palette_size"] = len(manifest["palette"])
    qa_path = pixel_dir / "motion_transfer_qa.json"
    qa_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _build_target(
    target_id: str,
    target: dict[str, str],
    profile: Path,
    blender: Path,
    force: bool,
    check: bool,
) -> None:
    work = MODEL_ROOT / target_id / "working" / "motion_transfer"
    master = work / f"{target_id}_master.blend"
    master_manifest = work / f"{target_id}_master.json"
    candidate = work / f"{target_id}_motion_transfer_candidate.blend"
    candidate_manifest = work / f"{target_id}_motion_transfer_candidate.json"
    render_dir = work / "source_renders"
    pixel_dir = work / "pixel_review"
    if check:
        required = [master, master_manifest, candidate, candidate_manifest, render_dir / "sprite_render_manifest.json", pixel_dir / "pixel_sprite_manifest.json"]
        missing = [path for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Missing candidate outputs for {target_id}: {missing}")
        transfer = json.loads(candidate_manifest.read_text(encoding="utf-8"))
        if transfer["profile_sha256"] != _sha256(profile) or transfer["output_blend_sha256"] != _sha256(candidate):
            raise RuntimeError(f"{target_id} transfer manifest hashes are stale")
        _run([
            sys.executable, str(ROOT / "tools" / "blender" / "pixelize_sprite_sheets.py"),
            "--manifest", str(render_dir / "sprite_render_manifest.json"),
            "--output-dir", str(pixel_dir), "--cell-size", "128", "--palette-size", "16",
            "--preview-scale", "1", "--check",
        ])
        _qa(pixel_dir, target_id)
        print(f"Verified {target_id}")
        return

    sources = _extract_target_sources(target_id, target, force)
    common_force = ["--force"] if force else []
    _run([
        str(blender), "--background", "--factory-startup", "--python-exit-code", "1",
        "--python", str(ROOT / "tools" / "blender" / "build_character_master.py"), "--",
        "--master", str(sources["bind"]), "--walk", str(sources["walk"]),
        "--run", str(sources["run"]), "--texture-dir", str(sources["textures"]),
        "--character-id", target_id, "--output", str(master), "--manifest", str(master_manifest),
        *common_force,
    ])
    _run([
        str(blender), "--background", str(master), "--python-exit-code", "1",
        "--python", str(ROOT / "tools" / "blender" / "transfer_approved_motions.py"), "--",
        "--target-blend", str(master), "--profile", str(profile),
        "--output-blend", str(candidate), "--output-manifest", str(candidate_manifest),
        *common_force,
    ])
    _run([
        str(blender), "--background", str(candidate), "--python-exit-code", "1",
        "--python", str(ROOT / "tools" / "blender" / "render_sprite_sequences.py"), "--",
        "--output-dir", str(render_dir), "--render-size", "1024", "--auto-frame",
        "--idle-action", "PF_Idle_Transfer", "--walk-action", "PF_Walk_Transfer",
        "--run-action", "PF_Run_Transfer",
    ])
    _run([
        sys.executable, str(ROOT / "tools" / "blender" / "pixelize_sprite_sheets.py"),
        "--manifest", str(render_dir / "sprite_render_manifest.json"),
        "--output-dir", str(pixel_dir), "--cell-size", "128", "--palette-size", "16",
        "--preview-scale", "1",
    ])
    _run([
        sys.executable, str(ROOT / "tools" / "blender" / "pixelize_sprite_sheets.py"),
        "--manifest", str(render_dir / "sprite_render_manifest.json"),
        "--output-dir", str(pixel_dir), "--cell-size", "128", "--palette-size", "16",
        "--preview-scale", "1", "--check",
    ])
    _qa(pixel_dir, target_id)
    print(f"Built {target_id} review candidate in {work.resolve()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
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
    config = json.loads(args.config.read_text(encoding="utf-8"))
    blender = _blender()
    profile = _profile(config, blender, args.force, args.check)
    targets = list(config["targets"]) if args.target == "all" else [args.target]
    for target_id in targets:
        _build_target(
            target_id, config["targets"][target_id], profile,
            blender, args.force, args.check,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
