from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from PIL import Image

try:
    from tools.finish_component_regions import MARKERS
except ModuleNotFoundError:  # Direct `python tools/...py` execution.
    from finish_component_regions import MARKERS


SHEET_WIDTH = 384
SOURCE_HEIGHT = 256
RUNTIME_HEIGHT = 259
FRAME_SIZE = 64
FRAMES_PER_DIRECTION = 6
DIRECTION_ROWS = {"front": 0, "back": 1, "right": 2, "left": 3}
SIDE_FRAME_ORDER = (0, 1, 2, 3, 4, 5)
LEFT_ALIGNMENT_OFFSET = (-1, -1)


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def _pixels(image: Image.Image):
    if hasattr(image, "get_flattened_data"):
        return image.get_flattened_data()
    return image.getdata()


def _frame(image: Image.Image, direction: str, frame_index: int) -> Image.Image:
    row = DIRECTION_ROWS[direction]
    left = frame_index * FRAME_SIZE
    top = row * FRAME_SIZE
    return image.crop((left, top, left + FRAME_SIZE, top + FRAME_SIZE))


def complete_cloak_walk_regions(source: Image.Image) -> Image.Image:
    """Preserve authored rows and mirror Right per frame into blank Left."""
    rgba = source.convert("RGBA")
    if rgba.size not in {(SHEET_WIDTH, SOURCE_HEIGHT), (SHEET_WIDTH, RUNTIME_HEIGHT)}:
        raise ValueError(
            "Authored cloak Walk regions must be 384x256 or 384x259, "
            f"got {rgba.size}"
        )

    unknown = {
        pixel for pixel in _pixels(rgba) if pixel[3] and pixel not in MARKERS
    }
    if unknown:
        formatted = ", ".join(
            f"#{red:02X}{green:02X}{blue:02X}/{alpha}"
            for red, green, blue, alpha in sorted(unknown)
        )
        raise ValueError(f"Authored sheet contains unknown opaque colors: {formatted}")

    completed = Image.new("RGBA", (SHEET_WIDTH, RUNTIME_HEIGHT), (0, 0, 0, 0))
    completed.paste(rgba.crop((0, 0, SHEET_WIDTH, SOURCE_HEIGHT)), (0, 0))

    if completed.crop((0, 3 * FRAME_SIZE, SHEET_WIDTH, 4 * FRAME_SIZE)).getbbox():
        raise ValueError("Left row must be blank before deterministic completion")

    for direction in ("front", "back", "right"):
        for frame_index in range(FRAMES_PER_DIRECTION):
            if _frame(completed, direction, frame_index).getbbox() is None:
                raise ValueError(
                    f"Authored {direction} frame {frame_index + 1} is empty"
                )

    authored_right = [
        _frame(completed, "right", frame_index)
        for frame_index in range(FRAMES_PER_DIRECTION)
    ]
    completed.paste(
        Image.new("RGBA", (SHEET_WIDTH, FRAME_SIZE), (0, 0, 0, 0)),
        (0, DIRECTION_ROWS["right"] * FRAME_SIZE),
    )
    for output_index, source_index in enumerate(SIDE_FRAME_ORDER):
        right = authored_right[source_index]
        completed.paste(
            right,
            (output_index * FRAME_SIZE, DIRECTION_ROWS["right"] * FRAME_SIZE),
        )
        mirrored = right.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        left_aligned = Image.new("RGBA", (FRAME_SIZE, FRAME_SIZE), (0, 0, 0, 0))
        left_aligned.paste(mirrored, LEFT_ALIGNMENT_OFFSET)
        completed.paste(
            left_aligned,
            (output_index * FRAME_SIZE, DIRECTION_ROWS["left"] * FRAME_SIZE),
        )

    for frame_index in range(FRAMES_PER_DIRECTION):
        expected = Image.new("RGBA", (FRAME_SIZE, FRAME_SIZE), (0, 0, 0, 0))
        expected.paste(
            _frame(completed, "right", frame_index).transpose(
                Image.Transpose.FLIP_LEFT_RIGHT
            ),
            LEFT_ALIGNMENT_OFFSET,
        )
        if _frame(completed, "left", frame_index).tobytes() != expected.tobytes():
            raise RuntimeError(f"Left frame {frame_index + 1} is not an exact mirror")
    return completed


def _write_or_check(path: Path, content: bytes, check: bool, label: str) -> None:
    if check:
        if not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"{label} is stale or missing: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def generate_completed_walk_source(
    source_path: str | Path,
    authored_path: str | Path,
    output_path: str | Path,
    *,
    check: bool = False,
) -> tuple[str, str]:
    source_bytes = Path(source_path).read_bytes()
    with Image.open(BytesIO(source_bytes)) as opened:
        completed = complete_cloak_walk_regions(opened)
    completed_bytes = _png_bytes(completed)
    _write_or_check(Path(authored_path), source_bytes, check, "Authored source copy")
    _write_or_check(Path(output_path), completed_bytes, check, "Completed semantic sheet")
    return sha256(source_bytes).hexdigest(), sha256(completed_bytes).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserve a semantic cloak Walk source and mirror Right "
            "pixel-exactly into the missing Left row."
        )
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--authored-out", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source_hash, completed_hash = generate_completed_walk_source(
        args.source,
        args.authored_out,
        args.output,
        check=args.check,
    )
    action = "Verified" if args.check else "Generated"
    print(f"{action} authored source sha256={source_hash}")
    print(f"{action} completed semantic sheet sha256={completed_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
