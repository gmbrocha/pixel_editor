from PIL import Image

from src.core.tile_layout import build_grid_tilesheet


RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)
TRANSPARENT = (0, 0, 0, 0)


def _tile(color: tuple[int, int, int, int]) -> Image.Image:
    return Image.new("RGBA", (2, 2), color)


def test_build_grid_tilesheet_preserves_assembly_grid_slots() -> None:
    sheet = build_grid_tilesheet(
        {
            (0, 0): _tile(RED),
            (2, 0): _tile(GREEN),
            (1, 1): _tile(BLUE),
        },
        cols=3,
        rows=2,
        tile_w=2,
        tile_h=2,
    )

    assert sheet.size == (6, 4)
    assert sheet.getpixel((0, 0)) == RED
    assert sheet.getpixel((4, 0)) == GREEN
    assert sheet.getpixel((2, 2)) == BLUE
    assert sheet.getpixel((2, 0)) == TRANSPARENT


def test_build_grid_tilesheet_ignores_cells_outside_dimensions() -> None:
    sheet = build_grid_tilesheet(
        {
            (0, 0): _tile(RED),
            (1, 0): _tile(GREEN),
        },
        cols=1,
        rows=1,
        tile_w=2,
        tile_h=2,
    )

    assert sheet.size == (2, 2)
    assert sheet.getpixel((0, 0)) == RED
