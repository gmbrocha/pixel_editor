from src.core.persistent_palette import (
    add_color_persistent,
    color_hex,
    color_tooltip,
    merge_palettes,
)


def test_add_color_no_duplicates() -> None:
    pal = [(255, 0, 0, 255)]
    result = add_color_persistent(pal, (255, 0, 0, 255))
    assert result == [(255, 0, 0, 255)]


def test_add_color_appends() -> None:
    pal = [(255, 0, 0, 255)]
    result = add_color_persistent(pal, (0, 255, 0, 255))
    assert result == [(255, 0, 0, 255), (0, 255, 0, 255)]


def test_merge_palettes_deduplicates() -> None:
    a = [(10, 20, 30, 255), (40, 50, 60, 255)]
    b = [(40, 50, 60, 255), (70, 80, 90, 255)]
    merged = merge_palettes(a, b)
    assert merged == [(10, 20, 30, 255), (40, 50, 60, 255), (70, 80, 90, 255)]


def test_color_hex() -> None:
    assert color_hex((255, 128, 0, 255)) == "#FF8000"


def test_color_tooltip_format() -> None:
    tip = color_tooltip((0, 0, 0, 255))
    assert "RGBA" in tip
    assert "#000000" in tip
