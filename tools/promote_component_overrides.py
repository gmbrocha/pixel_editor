"""Promote approved editable component sheets into canonical family overrides."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "animation_images_models"
CONFIG = MODEL_ROOT / "component_override_sources.json"
OUTPUT_ROOT = MODEL_ROOT / "component_overrides"
DIRECTIONS = ("front", "back", "right", "left")
FRAME_SIZE = 128


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _build(output_root: Path) -> dict[str, object]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported component override source configuration")
    records: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for raw in config["overrides"]:
        component_id = str(raw["component_id"])
        sequence = str(raw["sequence"])
        key = (component_id, sequence)
        if key in seen:
            raise ValueError(f"Duplicate component override {component_id}/{sequence}")
        seen.add(key)
        source_path = MODEL_ROOT / str(raw["source"])
        with Image.open(source_path) as opened:
            source = opened.convert("RGBA")
        if source.height != FRAME_SIZE * len(DIRECTIONS):
            raise ValueError(f"Unexpected direction rows in {source_path}")
        if source.width % FRAME_SIZE:
            raise ValueError(f"Unexpected frame columns in {source_path}")
        frame_count = source.width // FRAME_SIZE
        authoritative = [str(value) for value in raw["authoritative_directions"]]
        derived = {
            str(target): str(origin)
            for target, origin in raw["derived_directions"].items()
        }
        if set(authoritative) | set(derived) != set(DIRECTIONS):
            raise ValueError(f"{component_id}/{sequence} must account for every direction")
        if set(authoritative) & set(derived):
            raise ValueError(f"{component_id}/{sequence} directions overlap")
        output = Image.new("RGBA", source.size, (0, 0, 0, 0))
        for direction in authoritative:
            row = DIRECTIONS.index(direction)
            band = source.crop(
                (0, row * FRAME_SIZE, source.width, (row + 1) * FRAME_SIZE)
            )
            if band.getchannel("A").getbbox() is None:
                raise ValueError(f"{source_path} has an empty {direction} row")
            output.paste(band, (0, row * FRAME_SIZE))
        for target, origin in derived.items():
            target_row = DIRECTIONS.index(target)
            origin_row = DIRECTIONS.index(origin)
            for frame_index in range(frame_count):
                frame = output.crop(
                    (
                        frame_index * FRAME_SIZE,
                        origin_row * FRAME_SIZE,
                        (frame_index + 1) * FRAME_SIZE,
                        (origin_row + 1) * FRAME_SIZE,
                    )
                ).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                output.paste(
                    frame,
                    (frame_index * FRAME_SIZE, target_row * FRAME_SIZE),
                )
        destination = (
            output_root
            / str(raw["base_id"])
            / str(raw["family_id"])
            / f"{sequence}.png"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        output.save(destination, format="PNG", optimize=False, compress_level=9)
        records.append(
            {
                "component_id": component_id,
                "family_id": str(raw["family_id"]),
                "base_id": str(raw["base_id"]),
                "slot": str(raw["slot"]),
                "sequence": sequence,
                "file": destination.relative_to(output_root).as_posix(),
                "source": source_path.relative_to(ROOT).as_posix(),
                "source_sha256": _sha256(source_path),
                "output_sha256": _sha256(destination),
                "dimensions": list(output.size),
                "frame_size": [FRAME_SIZE, FRAME_SIZE],
                "frame_count": frame_count,
                "direction_rows": list(DIRECTIONS),
                "authoritative_directions": authoritative,
                "derived_directions": derived,
                "transform": "flip_complete_composite_horizontal",
                "status": "approved",
            }
        )
    manifest = {
        "schema_version": 1,
        "kind": "approved_component_overrides",
        "status": "canonical",
        "source_config": CONFIG.relative_to(ROOT).as_posix(),
        "source_config_sha256": _sha256(CONFIG),
        "override_count": len(records),
        "overrides": records,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="pf-component-overrides-") as temporary:
            candidate = Path(temporary)
            _build(candidate)
            if not OUTPUT_ROOT.is_dir() or _tree(candidate) != _tree(OUTPUT_ROOT):
                raise SystemExit("Approved component overrides are stale")
        print("Verified approved component overrides")
        return 0
    if OUTPUT_ROOT.exists():
        manifest_path = OUTPUT_ROOT / "manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError(f"Refusing to replace unrecognized directory {OUTPUT_ROOT}")
        shutil.rmtree(OUTPUT_ROOT)
    manifest = _build(OUTPUT_ROOT)
    print(f"Promoted {manifest['override_count']} approved component overrides")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
