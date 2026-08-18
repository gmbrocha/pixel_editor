from __future__ import annotations

import argparse
import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = PROJECT_ROOT / "assets" / "character-forge"
SOURCE_ROOT = ASSET_ROOT / "base_sources" / "human-01"
AUTHORED_SOURCE = SOURCE_ROOT / "walk-authored.png"
SOURCE_MANIFEST = SOURCE_ROOT / "walk-source.json"
RUNTIME_OUTPUT = ASSET_ROOT / "bases" / "human-01" / "walk.png"

FRAME_SIZE = 64
FRAMES_PER_DIRECTION = 6
SHEET_SIZE = (384, 259)
DIRECTION_ROWS = {"front": 0, "back": 1, "right": 2, "left": 3}
LEFT_FRAME_ORDER = (5, 4, 3, 2, 1, 0)


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def _frame(image: Image.Image, direction: str, frame_index: int) -> Image.Image:
    row = DIRECTION_ROWS[direction]
    left = frame_index * FRAME_SIZE
    top = row * FRAME_SIZE
    return image.crop((left, top, left + FRAME_SIZE, top + FRAME_SIZE))


def build_walk_sheet(source: Image.Image) -> Image.Image:
    """Preserve rows 1-3 and reverse only the six frames in row 4."""
    authored = source.convert("RGBA")
    if authored.size != SHEET_SIZE:
        raise ValueError(f"Character Walk source must be {SHEET_SIZE}, got {authored.size}")
    if authored.crop((0, 256, 384, 259)).getbbox() is not None:
        raise ValueError("Character Walk source has pixels outside its 384x256 logical extent")

    output = authored.copy()
    for output_index, source_index in enumerate(LEFT_FRAME_ORDER):
        output.paste(
            _frame(authored, "left", source_index),
            (output_index * FRAME_SIZE, DIRECTION_ROWS["left"] * FRAME_SIZE),
        )

    if output.crop((0, 0, 384, 192)).tobytes() != authored.crop(
        (0, 0, 384, 192)
    ).tobytes():
        raise RuntimeError("Walk rows 1-3 changed while reversing row 4")
    for output_index, source_index in enumerate(LEFT_FRAME_ORDER):
        if _frame(output, "left", output_index).tobytes() != _frame(
            authored, "left", source_index
        ).tobytes():
            raise RuntimeError(f"Left frame {output_index + 1} was not reversed exactly")
    return output


def _write_or_check(path: Path, content: bytes, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"Generated Character Walk asset is stale or missing: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _manifest(source_hash: str, runtime_hash: str) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "id": "human-01-walk-source",
        "authoredSource": "walk-authored.png",
        "authoredSourceSha256": source_hash,
        "runtimeOutput": "bases/human-01/walk.png",
        "runtimeSha256": runtime_hash,
        "sheetSize": [384, 259],
        "logicalExtent": [384, 256],
        "frameSize": [64, 64],
        "framesPerDirection": 6,
        "directionRows": DIRECTION_ROWS,
        "preservedRows": ["front", "back", "right"],
        "leftOperation": {
            "operation": "reverse-frame-order",
            "sourceDirection": "left",
            "sourceFrameOrder": [index + 1 for index in LEFT_FRAME_ORDER],
        },
        "rationale": (
            "The supplied final Walk sheet is authoritative for rows 1-3. "
            "Only the Left row is reversed cell-for-cell so frame 6 becomes frame 1."
        ),
        "generator": "tools/build_character_forge_walk_sheet.py",
        "generatorVersion": 2,
    }


def generate(*, check: bool = False) -> tuple[str, str]:
    source_bytes = AUTHORED_SOURCE.read_bytes()
    with Image.open(BytesIO(source_bytes)) as opened:
        output = build_walk_sheet(opened)
    runtime_bytes = _png_bytes(output)
    source_hash = sha256(source_bytes).hexdigest()
    runtime_hash = sha256(runtime_bytes).hexdigest()
    _write_or_check(RUNTIME_OUTPUT, runtime_bytes, check)
    _write_or_check(
        SOURCE_MANIFEST,
        (json.dumps(_manifest(source_hash, runtime_hash), indent=2) + "\n").encode("utf-8"),
        check,
    )
    return source_hash, runtime_hash


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the canonical Character Forge Walk sheet with corrected side cycles."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source_hash, runtime_hash = generate(check=args.check)
    action = "Verified" if args.check else "Generated"
    print(f"{action} authored Walk source sha256={source_hash}")
    print(f"{action} runtime Walk sheet sha256={runtime_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
