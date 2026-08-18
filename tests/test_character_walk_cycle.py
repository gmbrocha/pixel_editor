import hashlib
import json
from pathlib import Path

from PIL import Image

from tools.build_character_forge_walk_sheet import (
    AUTHORED_SOURCE,
    DIRECTION_ROWS,
    FRAMES_PER_DIRECTION,
    LEFT_FRAME_ORDER,
    RUNTIME_OUTPUT,
    SOURCE_MANIFEST,
    generate,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frame(image: Image.Image, direction: str, frame_index: int) -> Image.Image:
    row = DIRECTION_ROWS[direction]
    return image.crop(
        (frame_index * 64, row * 64, (frame_index + 1) * 64, row * 64 + 64)
    )


def test_character_walk_side_cycle_is_reproducible_and_source_grounded() -> None:
    assert generate(check=True) == (_digest(AUTHORED_SOURCE), _digest(RUNTIME_OUTPUT))
    metadata = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))

    assert metadata["authoredSourceSha256"] == _digest(AUTHORED_SOURCE)
    assert metadata["runtimeSha256"] == _digest(RUNTIME_OUTPUT)
    assert metadata["preservedRows"] == ["front", "back", "right"]
    assert metadata["leftOperation"] == {
        "operation": "reverse-frame-order",
        "sourceDirection": "left",
        "sourceFrameOrder": [6, 5, 4, 3, 2, 1],
    }


def test_character_walk_preserves_rows_one_to_three_and_reverses_only_row_four() -> (
    None
):
    with Image.open(AUTHORED_SOURCE) as opened:
        authored = opened.convert("RGBA")
    with Image.open(RUNTIME_OUTPUT) as opened:
        runtime = opened.convert("RGBA")

    assert runtime.crop((0, 0, 384, 192)).tobytes() == authored.crop(
        (0, 0, 384, 192)
    ).tobytes()
    for output_index, source_index in enumerate(LEFT_FRAME_ORDER):
        assert _frame(runtime, "left", output_index).tobytes() == _frame(
            authored, "left", source_index
        ).tobytes()
        expected_left = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        expected_left.paste(
            _frame(runtime, "right", output_index).transpose(
                Image.Transpose.FLIP_LEFT_RIGHT
            ),
            (-1, -1),
        )
        assert _frame(runtime, "left", output_index).tobytes() == expected_left.tobytes()

    assert runtime.crop((0, 256, 384, 259)).getbbox() is None
    assert FRAMES_PER_DIRECTION == 6
