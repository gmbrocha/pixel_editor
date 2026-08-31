"""Install the hand-authored Tiefling Low Run blindfold beneath hair."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "animation_images_models"
    / "component_cleanup_v2"
    / "new_hand_authored"
    / "teifling_blindfold_run.png"
)
DESTINATION = (
    ROOT
    / "assets"
    / "character-forge"
    / "parts"
    / "face"
    / "tiefling-blindfold-run"
)
SIZES = {"idle": (1792, 512), "walk": (1024, 512), "run": (1024, 512)}
DIRECTIONS = ("front", "back", "right", "left")
AUTHORITATIVE_DIRECTIONS = DIRECTIONS[:3]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hex(color: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02X}" for channel in color)


def _with_mirrored_left(source: Image.Image) -> Image.Image:
    result = source.copy()
    for frame_index in range(8):
        right = source.crop(
            (frame_index * 128, 2 * 128, (frame_index + 1) * 128, 3 * 128)
        )
        result.paste(
            right.transpose(Image.Transpose.FLIP_LEFT_RIGHT),
            (frame_index * 128, 3 * 128),
        )
    return result


def _build(destination: Path) -> None:
    with Image.open(SOURCE) as opened:
        source = opened.convert("RGBA")
    if source.size != SIZES["run"]:
        raise ValueError(f"Expected {SIZES['run']} source, got {source.size}")
    if set(source.getchannel("A").get_flattened_data()) - {0, 255}:
        raise ValueError("Blindfold source must use binary transparency")
    for row, direction in enumerate(AUTHORITATIVE_DIRECTIONS):
        alpha = source.crop((0, row * 128, 1024, (row + 1) * 128)).getchannel("A")
        if alpha.getbbox() is None:
            raise ValueError(f"Blindfold source is missing its {direction} row")
    if source.crop((0, 3 * 128, 1024, 4 * 128)).getchannel("A").getbbox():
        raise ValueError("Blindfold source Left row must remain empty and mirror Right")
    run = _with_mirrored_left(source)

    destination.mkdir(parents=True, exist_ok=True)
    for sequence, size in SIZES.items():
        output = destination / f"{sequence}.png"
        image = run if sequence == "run" else Image.new(
            "RGBA", size, (0, 0, 0, 0)
        )
        image.save(output, format="PNG", optimize=False, compress_level=9)

    colors = sorted(
        {
            (red, green, blue)
            for red, green, blue, alpha in source.get_flattened_data()
            if alpha
        },
        key=lambda color: (sum(color), color),
    )
    animations = {sequence: f"{sequence}.png" for sequence in SIZES}
    manifest = {
        "schemaVersion": 1,
        "id": "tiefling-blindfold-run",
        "familyId": "tiefling-blindfold",
        "displayName": "Tiefling Blindfold — Run",
        "slot": "face",
        "occupiesSlots": ["face"],
        "reservedSlots": [],
        "layer": "face_accessory_under_hair",
        "tags": [
            "user_authored",
            "blindfold",
            "under_hair",
            "low_camera_only",
        ],
        "fit": "tiefling-female-01",
        "version": 1,
        "status": "incomplete",
        "animations": animations,
        "directionMirrors": {"run": {"left": "right"}},
        "coverage": {
            "idle": [],
            "walk": [],
            "run": list(DIRECTIONS),
        },
        "colorRamp": {"main": "#ED1C24", "colors": [_hex(c) for c in colors]},
        "suggestedColors": ["#ED1C24", "#222222", "#5A382B", "#334A7D"],
        "provenance": {
            "kind": "hand_authored_component",
            "source": SOURCE.relative_to(ROOT).as_posix(),
            "sourceSha256": _sha256(SOURCE),
            "cameraHeight": "low",
            "authoritativeDirections": list(AUTHORITATIVE_DIRECTIONS),
            "derivedDirections": {
                "left": {
                    "source": "right",
                    "transform": "flip_complete_composite_horizontal",
                }
            },
            "approvedAnimations": ["run"],
            "renderOrderContract": "face_accessory_under_hair",
            "animationSha256": {
                sequence: _sha256(destination / filename)
                for sequence, filename in animations.items()
            },
        },
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="pf-tiefling-blindfold-") as temporary:
            candidate = Path(temporary)
            _build(candidate)
            if not DESTINATION.is_dir() or _tree(candidate) != _tree(DESTINATION):
                raise SystemExit("Installed Tiefling blindfold is stale")
        print("Verified Tiefling blindfold")
        return
    if DESTINATION.exists():
        shutil.rmtree(DESTINATION)
    _build(DESTINATION)
    print(f"Installed {DESTINATION}")


if __name__ == "__main__":
    main()
