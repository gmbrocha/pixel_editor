from __future__ import annotations

import colorsys

Color = tuple[int, int, int, int]


def rgb_to_hsb(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert RGB (0-255 each) to HSB where H 0-360, S 0-100, B 0-100."""
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return h * 360.0, s * 100.0, v * 100.0


def hsb_to_rgb(h: float, s: float, b: float) -> tuple[int, int, int]:
    """Convert HSB (H 0-360, S 0-100, B 0-100) to RGB (0-255 each)."""
    h_norm = (h % 360.0) / 360.0
    s_norm = max(0.0, min(1.0, s / 100.0))
    b_norm = max(0.0, min(1.0, b / 100.0))
    r, g, bv = colorsys.hsv_to_rgb(h_norm, s_norm, b_norm)
    return int(round(r * 255)), int(round(g * 255)), int(round(bv * 255))


def _apply_offset(h: float, s: float, b: float, dh: float, ds: float, db: float) -> tuple[float, float, float]:
    return (h + dh) % 360.0, max(0.0, min(100.0, s + ds)), max(0.0, min(100.0, b + db))


def shade_ramp(color: Color) -> list[tuple[str, Color]]:
    """Return [(label, rgba), ...] for shadow / base / midlight / highlight."""
    r, g, b = color[0], color[1], color[2]
    a = color[3]
    h, s, bv = rgb_to_hsb(r, g, b)

    offsets = [
        ("Shadow",    +12, +15, -40),
        ("Base",        0,   0,   0),
        ("Midlight",   -6, -12, +22),
        ("Highlight", -12, -30, +45),
    ]
    ramp: list[tuple[str, Color]] = []
    for label, dh, ds, db in offsets:
        nh, ns, nb = _apply_offset(h, s, bv, dh, ds, db)
        nr, ng, nbl = hsb_to_rgb(nh, ns, nb)
        ramp.append((label, (nr, ng, nbl, a)))
    return ramp
