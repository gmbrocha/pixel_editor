"""Install the approved Tiefling Front/Low Run hair as a two-layer part."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "animation_images_models" / "component_cleanup_v2"
    / "new_hand_authored" / "teifling_long_hair_run_front_only_third_edit.png"
)
DESTINATION = (
    ROOT / "assets" / "character-forge" / "parts" / "hair"
    / "tiefling-long-hair-run-front-prototype"
)
SIZES = {"idle": (1792, 512), "walk": (1024, 512), "run": (1024, 512)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build(destination: Path) -> None:
    with Image.open(SOURCE) as opened:
        source = opened.convert("RGBA")
    if source.size != SIZES["run"]:
        raise ValueError(f"Expected {SIZES['run']} source, got {source.size}")
    pixels = np.asarray(source, dtype=np.uint8)
    if np.count_nonzero(pixels[128:, :, 3]):
        raise ValueError("Prototype source must contain artwork only in the Front row")

    destination.mkdir(parents=True, exist_ok=True)
    for sequence, size in SIZES.items():
        front_output = destination / f"{sequence}_front.png"
        back_output = destination / f"{sequence}_back.png"
        front = source if sequence == "run" else Image.new("RGBA", size, (0, 0, 0, 0))
        back = Image.new("RGBA", size, (0, 0, 0, 0))
        front.save(front_output, format="PNG", optimize=False, compress_level=9)
        back.save(back_output, format="PNG", optimize=False, compress_level=9)

        # Preserve the primary-layer filenames for legacy single-layer readers.
        shutil.copy2(front_output, destination / f"{sequence}.png")

    colors = ["#946575", "#FFAEC9", "#FFCEE1"]
    animations = {sequence: f"{sequence}.png" for sequence in SIZES}
    front_animations = {sequence: f"{sequence}_front.png" for sequence in SIZES}
    back_animations = {sequence: f"{sequence}_back.png" for sequence in SIZES}
    manifest = {
        "schemaVersion": 1,
        "id": "tiefling-long-hair-run-front-prototype",
        "familyId": "tiefling-long-hair",
        "displayName": "Tiefling Long Hair — Run Front",
        "slot": "hair",
        "occupiesSlots": ["hair"],
        "reservedSlots": [],
        "layer": "hair_front",
        "tags": ["user_authored", "prototype", "low_camera_only"],
        "fit": "tiefling-female-01",
        "version": 1,
        "status": "incomplete",
        "animations": animations,
        "renderLayers": {
            "hair_back": {"animations": back_animations},
            "hair_front": {"animations": front_animations},
        },
        "coverage": {"idle": [], "walk": [], "run": ["front"]},
        "colorRamp": {"main": "#FFAEC9", "colors": colors},
        "suggestedColors": ["#FFAEC9", "#A96B4F", "#5A382B", "#E6D1A3"],
        "provenance": {
            "kind": "hand_authored_component_prototype",
            "source": SOURCE.relative_to(ROOT).as_posix(),
            "sourceSha256": _sha256(SOURCE),
            "cameraHeight": "low",
            "direction": "front",
            "animationSha256": {
                sequence: _sha256(destination / filename)
                for sequence, filename in animations.items()
            },
            "renderLayerSha256": {
                "hair_back": {
                    sequence: _sha256(destination / filename)
                    for sequence, filename in back_animations.items()
                },
                "hair_front": {
                    sequence: _sha256(destination / filename)
                    for sequence, filename in front_animations.items()
                },
            },
        },
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="pf-hair-prototype-") as temporary:
            candidate = Path(temporary)
            _build(candidate)
            if not DESTINATION.is_dir() or _tree(candidate) != _tree(DESTINATION):
                raise SystemExit("Installed Tiefling hair prototype is stale")
        print("Verified Tiefling long-hair prototype")
        return
    if DESTINATION.exists():
        shutil.rmtree(DESTINATION)
    _build(DESTINATION)
    print(f"Installed {DESTINATION}")


if __name__ == "__main__":
    main()
