from __future__ import annotations

from pathlib import Path

from PIL import Image


def load_image(path: str | Path) -> Image.Image:
    image = Image.open(path)
    return image.convert("RGBA")


def save_image(image: Image.Image, path: str | Path) -> None:
    image.save(path)
