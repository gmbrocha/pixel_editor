from __future__ import annotations

import json

import pytest
from PIL import Image

from src.core.palette import (
    add_color_to_palette,
    export_palette_file,
    export_palette_grid,
    load_palette_from_source,
    parse_palette_json,
    sort_palette,
)
from src.core.persistent_palette import import_palette_json, merge_palettes


def test_json_loader_accepts_colors_hex_schema_and_preserves_order() -> None:
    data = {
        "name": "Blacksmith",
        "colors": ["#101010", "#F09030", "#101010", "#20304080"],
    }

    assert parse_palette_json(data, max_colors=None) == [
        (16, 16, 16, 255),
        (240, 144, 48, 255),
        (32, 48, 64, 128),
    ]


def test_json_loader_accepts_legacy_bare_and_common_color_entries() -> None:
    legacy = {
        "palette": [
            {"hex": "#010203FF", "rgba": [1, 2, 3, 255]},
            {"rgb": [4, 5, 6]},
            {"r": 7, "g": 8, "b": 9, "a": 10},
            {"color": "#0B0C0D"},
        ]
    }
    bare = ["#010203", [4, 5, 6, 7]]

    assert parse_palette_json(legacy, max_colors=None) == [
        (1, 2, 3, 255),
        (4, 5, 6, 255),
        (7, 8, 9, 10),
        (11, 12, 13, 255),
    ]
    assert parse_palette_json(bare, max_colors=None) == [
        (1, 2, 3, 255),
        (4, 5, 6, 7),
    ]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"name": "missing colors"}, "'colors' or 'palette'"),
        ({"colors": []}, "contains no colors"),
        ({"colors": ["#GG0000"]}, "expected #RRGGBB"),
        ({"colors": [[0, 1, 256]]}, "0 to 255"),
        (
            {"palette": [{"hex": "#010203", "rgba": [9, 9, 9, 255]}]},
            "fields disagree",
        ),
    ],
)
def test_json_loader_reports_actionable_validation_errors(
    data: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_palette_json(data, max_colors=None)


def test_json_file_dispatch_and_persistent_import_share_one_parser(tmp_path) -> None:
    path = tmp_path / "palette.json"
    path.write_text(
        json.dumps({"colors": ["#101010", "#F09030"]}),
        encoding="utf-8",
    )

    expected = [(16, 16, 16, 255), (240, 144, 48, 255)]
    assert load_palette_from_source(path, max_colors=None) == expected
    assert import_palette_json(path) == expected


def test_text_loader_accepts_hex_jasc_gimp_and_rgba_rows(tmp_path) -> None:
    hex_path = tmp_path / "colors.hex"
    hex_path.write_text("#010203\n#04050680\n", encoding="utf-8")
    jasc_path = tmp_path / "colors.pal"
    jasc_path.write_text(
        "JASC-PAL\n0100\n2\n10 20 30\n40 50 60\n",
        encoding="utf-8",
    )
    gpl_path = tmp_path / "colors.gpl"
    gpl_path.write_text(
        "GIMP Palette\nName: Test\nColumns: 2\n#\n70 80 90 First\n100 110 120 Second\n",
        encoding="utf-8",
    )
    rgba_path = tmp_path / "colors.txt"
    rgba_path.write_text("1, 2, 3, 4\n5 6 7\n", encoding="utf-8")

    assert load_palette_from_source(hex_path, max_colors=None) == [
        (1, 2, 3, 255),
        (4, 5, 6, 128),
    ]
    assert load_palette_from_source(jasc_path, max_colors=None) == [
        (10, 20, 30, 255),
        (40, 50, 60, 255),
    ]
    assert load_palette_from_source(gpl_path, max_colors=None) == [
        (70, 80, 90, 255),
        (100, 110, 120, 255),
    ]
    assert load_palette_from_source(rgba_path, max_colors=None) == [
        (1, 2, 3, 4),
        (5, 6, 7, 255),
    ]


def test_palette_file_export_round_trips_supported_formats(tmp_path) -> None:
    palette = [(1, 2, 3, 255), (4, 5, 6, 128)]

    json_path = export_palette_file(palette, tmp_path / "colors.json", name="Test")
    hex_path = export_palette_file(palette, tmp_path / "colors.hex")
    pal_path = export_palette_file(palette, tmp_path / "colors.pal")
    gpl_path = export_palette_file(palette, tmp_path / "colors.gpl", name="Test")

    assert load_palette_from_source(json_path, max_colors=None) == palette
    assert load_palette_from_source(hex_path, max_colors=None) == palette
    assert load_palette_from_source(pal_path, max_colors=None) == [
        (1, 2, 3, 255),
        (4, 5, 6, 255),
    ]
    assert load_palette_from_source(gpl_path, max_colors=None) == [
        (1, 2, 3, 255),
        (4, 5, 6, 255),
    ]


def test_png_strip_export_round_trips_visible_rgba_colors(tmp_path) -> None:
    palette = [(1, 2, 3, 255), (4, 5, 6, 128)]

    destination = export_palette_file(palette, tmp_path / "colors.png")

    assert load_palette_from_source(destination, max_colors=None) == palette


def test_palette_grid_export_preserves_cell_positions_and_empty_cells(tmp_path) -> None:
    path = tmp_path / "grid.png"
    red = (200, 10, 20, 255)
    blue = (20, 30, 200, 128)

    export_palette_grid([red, None, blue, None], 2, 2, path, swatch_size=2)

    image = Image.open(path).convert("RGBA")
    assert image.size == (4, 4)
    assert image.getpixel((0, 0)) == red
    assert image.getpixel((2, 0)) == (0, 0, 0, 0)
    assert image.getpixel((0, 2)) == blue
    assert image.getpixel((2, 2)) == (0, 0, 0, 0)


def test_palette_export_uses_selected_filter_when_name_has_no_suffix(tmp_path) -> None:
    destination = export_palette_file(
        [(1, 2, 3, 255)],
        tmp_path / "colors",
        selected_filter="PixelForge JSON (*.json)",
    )

    assert destination.suffix == ".json"
    assert destination.is_file()


def test_palette_loader_applies_limit_after_deduplication() -> None:
    data = {"colors": ["#010203", "#010203", "#040506", "#070809"]}

    assert parse_palette_json(data, max_colors=2) == [
        (1, 2, 3, 255),
        (4, 5, 6, 255),
    ]


def test_palette_loader_rejects_unsupported_existing_file(tmp_path) -> None:
    path = tmp_path / "colors.ase"
    path.write_bytes(b"not an ASE palette")

    with pytest.raises(ValueError, match="Unsupported palette file type"):
        load_palette_from_source(path, max_colors=None)


def test_palette_edit_helpers_have_deterministic_duplicate_and_sort_behavior() -> None:
    red = (255, 0, 0, 255)
    green = (0, 255, 0, 255)
    transparent = (0, 0, 0, 0)

    assert add_color_to_palette([red, green], red) == [green, red]
    assert add_color_to_palette([red, green], (0, 0, 255, 255), max_colors=2) == [
        green,
        (0, 0, 255, 255),
    ]
    assert merge_palettes([red, green], [green, transparent]) == [
        red,
        green,
        transparent,
    ]
    assert sort_palette([transparent, green, red], "brightness") == [
        red,
        green,
        transparent,
    ]


def test_persistent_palette_storage_round_trips_and_clears(tmp_path, monkeypatch) -> None:
    import src.core.persistent_palette as persistent_palette

    path = tmp_path / "saved-colors.json"
    monkeypatch.setattr(persistent_palette, "_PALETTE_PATH", path)
    colors = [(1, 2, 3, 255), (4, 5, 6, 128)]

    persistent_palette.save_persistent_palette(colors)
    assert persistent_palette.load_persistent_palette() == colors
    persistent_palette.save_persistent_palette([])
    assert persistent_palette.load_persistent_palette() == []
