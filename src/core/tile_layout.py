from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(slots=True)
class PlacedTile:
    """One tile bitmap placed on an integer grid (each cell is tile_w × tile_h pixels)."""

    id: str
    name: str
    image: Image.Image
    grid_x: int = 0
    grid_y: int = 0

    @classmethod
    def from_file(cls, path: str, image: Image.Image) -> PlacedTile:
        return cls(
            id=str(uuid.uuid4()),
            name=Path(path).stem,
            image=image,
        )


def layout_bounds_px(tiles: list[PlacedTile], tile_w: int, tile_h: int) -> tuple[int, int, int, int]:
    """Returns (min_x, min_y, max_x, max_y) in layout pixel space (exclusive max)."""
    if not tiles:
        return 0, 0, tile_w, tile_h
    min_x = min(t.grid_x * tile_w for t in tiles)
    min_y = min(t.grid_y * tile_h for t in tiles)
    max_x = max(t.grid_x * tile_w + tile_w for t in tiles)
    max_y = max(t.grid_y * tile_h + tile_h for t in tiles)
    return min_x, min_y, max_x, max_y


def next_free_position(tiles: list[PlacedTile], max_cols: int = 4) -> tuple[int, int]:
    """Return the first unoccupied (grid_x, grid_y) in row-major order."""
    occupied = {(t.grid_x, t.grid_y) for t in tiles}
    row = 0
    while True:
        for col in range(max_cols):
            if (col, row) not in occupied:
                return col, row
        row += 1
