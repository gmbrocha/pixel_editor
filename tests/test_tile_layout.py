from PIL import Image

from src.core.tile_layout import PlacedTile, layout_bounds_px, next_free_position


def test_layout_bounds_empty() -> None:
    assert layout_bounds_px([], 16, 16) == (0, 0, 16, 16)


def test_layout_bounds_tiles() -> None:
    a = PlacedTile(id="1", name="a", image=Image.new("RGBA", (8, 8)), grid_x=0, grid_y=0)
    b = PlacedTile(id="2", name="b", image=Image.new("RGBA", (8, 8)), grid_x=2, grid_y=1)
    min_x, min_y, max_x, max_y = layout_bounds_px([a, b], 8, 8)
    assert (min_x, min_y, max_x, max_y) == (0, 0, 24, 16)


def test_next_free_empty() -> None:
    assert next_free_position([]) == (0, 0)


def test_next_free_skips_occupied() -> None:
    tiles = [
        PlacedTile(id="1", name="a", image=Image.new("RGBA", (8, 8)), grid_x=0, grid_y=0),
        PlacedTile(id="2", name="b", image=Image.new("RGBA", (8, 8)), grid_x=1, grid_y=0),
    ]
    assert next_free_position(tiles) == (2, 0)


def test_next_free_wraps_row() -> None:
    tiles = [
        PlacedTile(id=str(i), name="t", image=Image.new("RGBA", (8, 8)), grid_x=i, grid_y=0)
        for i in range(16)
    ]
    assert next_free_position(tiles, max_cols=16) == (0, 1)
