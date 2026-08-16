"""Assemble the authoritative six-frame directional Character Forge run sheet."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
BASE_ROOT = ROOT / "assets" / "character-forge" / "bases" / "human-01"


def _load_rgba(path: Path, expected_size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGBA")
    if image.size != expected_size:
        raise ValueError(f"{path.name} is {image.size}, expected {expected_size}")
    return image


def main() -> None:
    front = _load_rgba(BASE_ROOT / "run-front.png", (384, 64))
    back = _load_rgba(BASE_ROOT / "run-back.png", (384, 64))
    right = _load_rgba(BASE_ROOT / "run-right.png", (384, 64))
    left = _load_rgba(BASE_ROOT / "run-left.png", (384, 64))

    sheet = Image.new("RGBA", (384, 256), (0, 0, 0, 0))
    # Direct paste preserves the authoritative RGBA pixel data exactly.
    sheet.paste(front, (0, 0))
    sheet.paste(back, (0, 64))
    sheet.paste(right, (0, 128))
    sheet.paste(left, (0, 192))

    sheet.save(BASE_ROOT / "run.png")


if __name__ == "__main__":
    main()
