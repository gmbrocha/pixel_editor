from src.core.palette import add_color_to_palette


def test_add_color_to_palette_appends_unique_color():
    palette = [(255, 0, 0, 255)]

    updated = add_color_to_palette(palette, (0, 255, 0, 255))

    assert updated == [(255, 0, 0, 255), (0, 255, 0, 255)]


def test_add_color_to_palette_moves_existing_color_to_end_without_duplicates():
    palette = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]

    updated = add_color_to_palette(palette, (0, 255, 0, 255))

    assert updated == [(255, 0, 0, 255), (0, 0, 255, 255), (0, 255, 0, 255)]
