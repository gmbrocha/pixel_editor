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
SIDE_FRAME_ORDER = (0, 1, 2, 5, 4, 3)
LEFT_ALIGNMENT_OFFSET = (-1, -1)


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
    """Correct side-view phase order and rebuild Left from Right per frame."""
    authored = source.convert("RGBA")
    if authored.size != SHEET_SIZE:
        raise ValueError(f"Character Walk source must be {SHEET_SIZE}, got {authored.size}")
    if authored.crop((0, 256, 384, 259)).getbbox() is not None:
        raise ValueError("Character Walk source has pixels outside its 384x256 logical extent")

    output = Image.new("RGBA", SHEET_SIZE, (0, 0, 0, 0))
    output.paste(authored.crop((0, 0, 384, 128)), (0, 0))

    for output_index, source_index in enumerate(SIDE_FRAME_ORDER):
        right = _frame(authored, "right", source_index)
        output.paste(right, (output_index * FRAME_SIZE, DIRECTION_ROWS["right"] * FRAME_SIZE))

        left = right.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        left_aligned = Image.new("RGBA", (FRAME_SIZE, FRAME_SIZE), (0, 0, 0, 0))
        left_aligned.paste(left, LEFT_ALIGNMENT_OFFSET)
        output.paste(
            left_aligned,
            (output_index * FRAME_SIZE, DIRECTION_ROWS["left"] * FRAME_SIZE),
        )

    for frame_index in range(FRAMES_PER_DIRECTION):
        right = _frame(output, "right", frame_index)
        expected = Image.new("RGBA", (FRAME_SIZE, FRAME_SIZE), (0, 0, 0, 0))
        expected.paste(
            right.transpose(Image.Transpose.FLIP_LEFT_RIGHT),
            LEFT_ALIGNMENT_OFFSET,
        )
        if _frame(output, "left", frame_index).tobytes() != expected.tobytes():
            raise RuntimeError(f"Left frame {frame_index + 1} is not the aligned Right mirror")
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
        "frontBackOperation": "preserved-byte-for-byte",
        "sideFrameOrder": [index + 1 for index in SIDE_FRAME_ORDER],
        "leftOperation": {
            "operation": "horizontal-frame-mirror",
            "sourceDirection": "right",
            "alignmentOffset": list(LEFT_ALIGNMENT_OFFSET),
        },
        "rationale": (
            "The authored side strip stores its second half in reverse phase. "
            "Order 1,2,3,6,5,4 gives both planted feet a front-to-rear contact arc. "
            "Left is mirrored per cell so direction changes do not reverse time."
        ),
        "generator": "tools/build_character_forge_walk_sheet.py",
        "generatorVersion": 1,
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
