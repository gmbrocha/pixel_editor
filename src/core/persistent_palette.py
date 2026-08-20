from __future__ import annotations

from pathlib import Path

from src.core.palette import (
    export_palette_json as _export_palette_json,
    load_palette_from_json,
)

Color = tuple[int, int, int, int]

_CONFIG_DIR = Path.home() / ".pixelforge"
_PALETTE_PATH = _CONFIG_DIR / "palette.json"


def _ensure_dir() -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_persistent_palette() -> list[Color]:
    if not _PALETTE_PATH.exists():
        return []
    return load_palette_from_json(_PALETTE_PATH, max_colors=None)


def save_persistent_palette(palette: list[Color]) -> None:
    _ensure_dir()
    if not palette:
        _PALETTE_PATH.unlink(missing_ok=True)
        return
    _export_palette_json(palette, _PALETTE_PATH, name="Saved colors")


def add_color_persistent(palette: list[Color], color: Color) -> list[Color]:
    """Add *color* to *palette* without duplicates. Returns updated list."""
    updated = list(palette)
    if color not in updated:
        updated.append(color)
    return updated


def merge_palettes(base: list[Color], incoming: list[Color]) -> list[Color]:
    """Merge *incoming* into *base*, skipping duplicates."""
    merged = list(base)
    for c in incoming:
        if c not in merged:
            merged.append(c)
    return merged


def export_palette_json(palette: list[Color], path: str | Path) -> None:
    _export_palette_json(palette, path, name="Saved colors")


def import_palette_json(path: str | Path) -> list[Color]:
    return load_palette_from_json(path, max_colors=None)


def color_hex(color: Color) -> str:
    return "#{:02X}{:02X}{:02X}".format(color[0], color[1], color[2])


def color_tooltip(color: Color) -> str:
    return f"{color_hex(color)}  RGBA({color[0]}, {color[1]}, {color[2]}, {color[3]})"
