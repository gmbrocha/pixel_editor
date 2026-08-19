import hashlib
import json
from pathlib import Path

from PIL import Image

from tools.build_character_forge_walk_sheet import (
    AUTHORED_SOURCE,
    FRAMES_PER_DIRECTION,
    RUNTIME_OUTPUT,
    SOURCE_MANIFEST,
    generate,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_character_walk_cycle_is_reproducible_and_source_grounded() -> None:
    assert generate(check=True) == (_digest(AUTHORED_SOURCE), _digest(RUNTIME_OUTPUT))
    metadata = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))

    assert metadata["authoredSourceSha256"] == _digest(AUTHORED_SOURCE)
    assert metadata["runtimeSha256"] == _digest(RUNTIME_OUTPUT)
    assert metadata["preservedRows"] == ["front", "back", "right", "left"]
    assert metadata["playback"] == "normal-loop"


def test_character_walk_preserves_all_four_supplied_rows_exactly() -> None:
    with Image.open(AUTHORED_SOURCE) as opened:
        authored = opened.convert("RGBA")
    with Image.open(RUNTIME_OUTPUT) as opened:
        runtime = opened.convert("RGBA")

    assert runtime.tobytes() == authored.tobytes()
    assert runtime.crop((0, 256, 384, 259)).getbbox() is None
    assert FRAMES_PER_DIRECTION == 6
