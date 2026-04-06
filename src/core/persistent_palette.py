from __future__ import annotations

import json
from pathlib import Path

Color = tuple[int, int, int, int]

_CONFIG_DIR = Path.home() / ".pixelforge"
_PALETTE_PATH = _CONFIG_DIR / "palette.json"


def _ensure_dir() -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_persistent_palette() -> list[Color]:
    if not _PALETTE_PATH.exists():
        return []
    try:
        data = json.loads(_PALETTE_PATH.read_text(encoding="utf-8"))
        colors: list[Color] = []
        for entry in data.get("palette", []):
            rgba = entry.get("rgba", [0, 0, 0, 255])
            c = (int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3]))
            if c not in colors:
                colors.append(c)
        return colors
    except Exception:
        return []


def save_persistent_palette(palette: list[Color]) -> None:
    _ensure_dir()
    entries = []
    for c in palette:
        entries.append({
            "hex": "#{:02X}{:02X}{:02X}{:02X}".format(*c),
            "rgba": list(c),
        })
    data = {"palette": entries}
    _PALETTE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


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
    entries = []
    for c in palette:
        entries.append({
            "hex": "#{:02X}{:02X}{:02X}{:02X}".format(*c),
            "rgba": list(c),
        })
    Path(path).write_text(json.dumps({"palette": entries}, indent=2), encoding="utf-8")


def import_palette_json(path: str | Path) -> list[Color]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    colors: list[Color] = []
    for entry in data.get("palette", []):
        rgba = entry.get("rgba", [0, 0, 0, 255])
        c = (int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3]))
        if c not in colors:
            colors.append(c)
    return colors


def color_hex(color: Color) -> str:
    return "#{:02X}{:02X}{:02X}".format(color[0], color[1], color[2])


def color_tooltip(color: Color) -> str:
    return f"{color_hex(color)}  RGBA({color[0]}, {color[1]}, {color[2]}, {color[3]})"
