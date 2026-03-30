from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from uuid import uuid4

from PIL import Image


@dataclass(slots=True)
class SavedAsset:
    name: str
    image: Image.Image
    id: str = field(default_factory=lambda: uuid4().hex)


def build_tilesheet(
    assets: list[SavedAsset],
    columns: int = 8,
    padding: int = 2,
) -> Image.Image:
    if not assets:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    max_width = max(asset.image.width for asset in assets)
    max_height = max(asset.image.height for asset in assets)
    rows = ceil(len(assets) / columns)
    width = columns * max_width + max(0, columns - 1) * padding
    height = rows * max_height + max(0, rows - 1) * padding
    tilesheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    for index, asset in enumerate(assets):
        row = index // columns
        column = index % columns
        x = column * (max_width + padding)
        y = row * (max_height + padding)
        tilesheet.alpha_composite(asset.image.convert("RGBA"), (x, y))

    return tilesheet
