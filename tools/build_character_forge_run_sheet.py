"""Assemble the authoritative mixed-length directional Character Forge Run sheet."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "assets" / "character-forge"
BASE_ROOT = ASSET_ROOT / "bases" / "human-01"
SOURCE_ROOT = ASSET_ROOT / "base_sources" / "human-01"
SOURCE_MANIFEST = SOURCE_ROOT / "run-source.json"
RUNTIME_OUTPUT = BASE_ROOT / "run.png"
ROWS = {"front": 0, "back": 1, "right": 2, "left": 3}
SOURCE_FILES = {
    "front": "run-front.png",
    "back": "run-back.png",
    "right": "run-right.png",
    "left": "run-left.png",
}
FRAME_COUNTS = {"front": 6, "back": 8, "right": 6, "left": 6}
PLAYBACK_FRAMES = {
    "front": (0, 1, 2, 3, 4, 5),
    "back": (0, 1, 2, 3, 4, 5, 6, 7),
    "right": (5, 4, 3, 2, 1, 0, 1, 2, 3, 4),
    "left": (0, 1, 2, 3, 4, 5, 4, 3, 2, 1),
}


def _load_rgba(path: Path, expected_size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGBA")
    if image.size != expected_size:
        raise ValueError(f"{path.name} is {image.size}, expected {expected_size}")
    return image


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def build_run_sheet(sources: dict[str, Image.Image]) -> Image.Image:
    sheet = Image.new("RGBA", (512, 256), (0, 0, 0, 0))
    for direction, row in ROWS.items():
        source = sources[direction]
        expected_size = (FRAME_COUNTS[direction] * 64, 64)
        if source.size != expected_size:
            raise ValueError(
                f"Run {direction} source is {source.size}, expected {expected_size}"
            )
        sheet.paste(source, (0, row * 64))
    return sheet


def _manifest(source_hashes: dict[str, str], runtime_hash: str) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "id": "human-01-run-source",
        "runtimeOutput": "bases/human-01/run.png",
        "runtimeSha256": runtime_hash,
        "sheetSize": [512, 256],
        "frameSize": [64, 64],
        "directionRows": ROWS,
        "directionFrameCounts": FRAME_COUNTS,
        "directionPlaybackFrames": {
            direction: [index + 1 for index in sequence]
            for direction, sequence in PLAYBACK_FRAMES.items()
        },
        "sources": [
            {
                "direction": direction,
                "file": SOURCE_FILES[direction],
                "sha256": source_hashes[direction],
            }
            for direction in ROWS
        ],
        "generator": "tools/build_character_forge_run_sheet.py",
        "generatorVersion": 2,
    }


def generate(*, check: bool = False) -> tuple[dict[str, str], str]:
    source_bytes = {
        direction: (SOURCE_ROOT / filename).read_bytes()
        for direction, filename in SOURCE_FILES.items()
    }
    sources = {
        direction: _load_rgba(
            SOURCE_ROOT / filename, (FRAME_COUNTS[direction] * 64, 64)
        )
        for direction, filename in SOURCE_FILES.items()
    }
    runtime_bytes = _png_bytes(build_run_sheet(sources))
    source_hashes = {
        direction: sha256(content).hexdigest()
        for direction, content in source_bytes.items()
    }
    runtime_hash = sha256(runtime_bytes).hexdigest()
    expected_files = {
        RUNTIME_OUTPUT: runtime_bytes,
        SOURCE_MANIFEST: (
            json.dumps(_manifest(source_hashes, runtime_hash), indent=2) + "\n"
        ).encode("utf-8"),
        **{
            BASE_ROOT / filename: source_bytes[direction]
            for direction, filename in SOURCE_FILES.items()
        },
    }
    for path, content in expected_files.items():
        if check:
            if not path.is_file() or path.read_bytes() != content:
                raise ValueError(f"Generated Character Run asset is stale: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    return source_hashes, runtime_hash


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source_hashes, runtime_hash = generate(check=args.check)
    action = "Verified" if args.check else "Generated"
    print(f"{action} Character Run sheet sha256={runtime_hash}")
    for direction, digest in source_hashes.items():
        print(f"  {direction}: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
