from __future__ import annotations

from collections import Counter
import colorsys
import re
from pathlib import Path

from PIL import Image, ImageDraw


Color = tuple[int, int, int, int]
_HEX_COLOR_RE = re.compile(r"#?(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6})")


def add_color_to_palette(
    palette: list[Color],
    color: Color,
    max_colors: int | None = None,
) -> list[Color]:
    updated = list(palette)
    if color in updated:
        updated.remove(color)
    updated.append(color)
    if max_colors is not None and len(updated) > max_colors:
        updated = updated[-max_colors:]
    return updated


def palette_from_image(
    image: Image.Image,
    max_colors: int = 16,
    *,
    selection: str = "frequent",
) -> list[Color]:
    """Extract up to `max_colors` colors from `image`.

    `selection` controls which colors win when the image has more distinct
    colors than `max_colors`:

    - "frequent": the most common colors win (good for sampling photos).
      Tie-break is the raw RGB tuple, which favors darker colors when every
      color appears the same number of times -- so this mode is a poor fit
      for images that are themselves uniform palette strips.
    - "spread": greedy farthest-point sampling over the distinct opaque
      colors. Picks N colors that cover the gamut as evenly as possible,
      regardless of how often each color appears (good for loading a
      palette image with one swatch per color).
    """
    rgba = image.convert("RGBA")
    color_counts = Counter(rgba.getdata())
    if not color_counts:
        return [(0, 0, 0, 0)]

    normalized = (selection or "balanced").strip().lower()
    if normalized == "spread":
        colors = _spread_sample_colors(color_counts, max_colors)
    elif normalized == "balanced":
        colors = _hue_balanced_sample_colors(color_counts, max_colors)
    else:
        colors = [
            color
            for color, _count in sorted(
                color_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:max_colors]
        ]

    if not colors:
        colors.append((0, 0, 0, 0))
    return colors


def _spread_sample_colors(
    color_counts: "Counter[Color]",
    max_colors: int,
) -> list[Color]:
    """Greedy farthest-point sampling over the distinct colors in `color_counts`.

    Transparent pixels are excluded from the candidate pool but a single
    fully-transparent entry is preserved if the source image had any.

    The first seed is chosen as the most-saturated, mid-brightness color so
    the result includes a chromatic anchor instead of starting from whichever
    color happens to be most common; subsequent picks maximize the minimum
    distance to the already-chosen set in RGB space.
    """
    if max_colors <= 0:
        return []

    has_transparent = any(c[3] == 0 for c in color_counts)
    candidates = [c for c in color_counts if c[3] > 0]
    if not candidates:
        return [(0, 0, 0, 0)] if has_transparent else []

    if len(candidates) <= max_colors:
        # Sort deterministically so the result is stable across loads.
        ordered = sorted(candidates, key=lambda c: (-color_counts[c], c))
        if has_transparent and len(ordered) < max_colors:
            ordered.append((0, 0, 0, 0))
        return ordered[:max_colors]

    def _rgb(c: Color) -> tuple[int, int, int]:
        return c[0], c[1], c[2]

    def _dist_sq(a: Color, b: Color) -> int:
        ar, ag, ab = _rgb(a)
        br, bg, bb = _rgb(b)
        return (ar - br) ** 2 + (ag - bg) ** 2 + (ab - bb) ** 2

    def _seed_score(c: Color) -> tuple[float, float, int]:
        # Prefer high saturation, mid-brightness, then frequency as a tie-break.
        h, s, v = _rgb_to_hsv(c)
        mid_bias = -abs(v - 0.5)
        return (s, mid_bias, color_counts[c])

    seed = max(candidates, key=_seed_score)
    chosen: list[Color] = [seed]
    # Track each remaining color's current min-distance to the chosen set.
    remaining = [c for c in candidates if c != seed]
    min_dist = {c: _dist_sq(c, seed) for c in remaining}

    while len(chosen) < max_colors and remaining:
        # Pick the color whose nearest neighbor in `chosen` is farthest away.
        # Tie-break by frequency, then by RGB for determinism.
        next_color = max(
            remaining,
            key=lambda c: (min_dist[c], color_counts[c], c),
        )
        chosen.append(next_color)
        remaining.remove(next_color)
        del min_dist[next_color]
        # Update min-distance for the rest with the newly added color.
        for c in remaining:
            d = _dist_sq(c, next_color)
            if d < min_dist[c]:
                min_dist[c] = d

    if has_transparent and len(chosen) < max_colors:
        chosen.append((0, 0, 0, 0))

    return chosen


def _hue_balanced_sample_colors(
    color_counts: "Counter[Color]",
    max_colors: int,
    hue_bins: int = 12,
) -> list[Color]:
    """Palette-slot allocation that guarantees every occupied hue band gets
    at least one representative color regardless of pixel count.

    Colors are bucketed into `hue_bins` equal hue bands (plus a neutral
    bucket for low-saturation colors).  Each occupied bucket is given
    an equal share of the available slots.  If a bucket has fewer unique
    colors than its share, unused slots are redistributed to buckets that
    still want more.  Within each bucket, _spread_sample_colors picks the
    most gamut-diverse representatives.

    This prevents a majority hue family (e.g. 100 tan variants) from
    consuming all palette slots and erasing minority families (e.g. 8 greens)
    even when those minorities are a small fraction of total pixels.
    """
    NEUTRAL_SAT = 0.15

    has_transparent = any(c[3] == 0 for c in color_counts)
    candidates = [c for c in color_counts if c[3] > 0]

    if not candidates:
        return [(0, 0, 0, 0)] if has_transparent else []

    if len(candidates) <= max_colors:
        ordered = sorted(candidates, key=lambda c: (-color_counts[c], c))
        if has_transparent and len(ordered) < max_colors:
            ordered.append((0, 0, 0, 0))
        return ordered[:max_colors]

    bins: dict[int, list[Color]] = {}
    for c in candidates:
        h, s, _v = _rgb_to_hsv(c)
        key = hue_bins if s < NEUTRAL_SAT else int(h * hue_bins) % hue_bins
        bins.setdefault(key, []).append(c)

    occupied = sorted(bins.keys())
    n_occupied = len(occupied)

    # Each bin guaranteed 1 slot; distribute the rest equally.
    if max_colors <= n_occupied:
        allocation = {k: 0 for k in occupied}
        for k in occupied[:max_colors]:
            allocation[k] = 1
    else:
        base = max_colors // n_occupied
        extra = max_colors - base * n_occupied
        # Extra slots go to the bins with the most unique colors first.
        by_size = sorted(occupied, key=lambda k: -len(bins[k]))
        allocation = {k: base for k in occupied}
        for k in by_size[:extra]:
            allocation[k] += 1

    # Two-pass redistribution: if a bin has fewer colors than its slot budget,
    # give the unused slots to whichever bins still want more.
    changed = True
    while changed:
        changed = False
        surplus = 0
        for k in occupied:
            cap = len(bins[k])
            if allocation[k] > cap:
                surplus += allocation[k] - cap
                allocation[k] = cap
        if surplus:
            changed = True
            hungry = [k for k in occupied if len(bins[k]) > allocation[k]]
            if not hungry:
                break
            per = surplus // len(hungry)
            leftover = surplus - per * len(hungry)
            for k in hungry:
                allocation[k] += per
            for k in sorted(hungry, key=lambda k: -len(bins[k]))[:leftover]:
                allocation[k] += 1

    result: list[Color] = []
    for k in occupied:
        n = allocation[k]
        if n <= 0:
            continue
        bin_counts: Counter[Color] = Counter({c: color_counts[c] for c in bins[k]})
        result.extend(_spread_sample_colors(bin_counts, n))

    if has_transparent and len(result) < max_colors:
        result.append((0, 0, 0, 0))

    return result[:max_colors]


def _dither_mode(enabled: bool) -> Image.Dither:
    return Image.Dither.FLOYDSTEINBERG if enabled else Image.Dither.NONE


def _build_palette_image(palette: list[Color]) -> Image.Image:
    if not palette:
        raise ValueError("Palette cannot be empty")

    palette_image = Image.new("P", (1, 1))
    raw_palette: list[int] = []
    for color in palette[:256]:
        raw_palette.extend(color[:3])
    raw_palette.extend([0] * (768 - len(raw_palette)))
    palette_image.putpalette(raw_palette)
    return palette_image


def _clear_fully_transparent_pixels(image: Image.Image) -> Image.Image:
    output = image.convert("RGBA")
    pixels = output.load()
    for y in range(output.height):
        for x in range(output.width):
            if pixels[x, y][3] == 0:
                pixels[x, y] = (0, 0, 0, 0)
    return output


def _opaque_sample_image(source: Image.Image) -> Image.Image | None:
    rgba = source.convert("RGBA")
    pixels = rgba.load()
    visible_pixels: list[tuple[int, int, int]] = []
    for y in range(rgba.height):
        for x in range(rgba.width):
            pixel = pixels[x, y]
            if pixel[3] > 0:
                visible_pixels.append(pixel[:3])
    if not visible_pixels:
        return None

    sample = Image.new("RGB", (len(visible_pixels), 1))
    sample.putdata(visible_pixels)
    return sample


def quantize_image(
    image: Image.Image,
    max_colors: int = 32,
    *,
    dither: bool = False,
    method: Image.Quantize = Image.Quantize.MEDIANCUT,
    reference_palette: list[Color] | None = None,
) -> Image.Image:
    source = image.convert("RGBA")
    if source.getbbox() is None:
        return Image.new("RGBA", source.size, (0, 0, 0, 0))

    sample = _opaque_sample_image(source)
    if sample is None:
        return Image.new("RGBA", source.size, (0, 0, 0, 0))

    quantized_sample = sample.quantize(
        colors=max(1, min(int(max_colors), 256)),
        method=method,
        dither=_dither_mode(dither),
    )

    output = source.convert("RGB").quantize(
        palette=quantized_sample,
        dither=_dither_mode(dither),
    ).convert("RGBA")
    output.putalpha(source.getchannel("A"))
    output = _clear_fully_transparent_pixels(output)

    if reference_palette:
        output = quantize_to_palette(output, reference_palette, dither=dither)

    return output


def _rgb_to_lab(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert an sRGB triplet (0-255) to CIELAB (D65 illuminant).

    LAB separates lightness from chroma and places the red/green axis on `a`
    and the yellow/blue axis on `b`, so perceptually distinct hues (e.g. tan
    vs green) remain far apart even when their RGB values are close.
    """
    def _linearize(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    rl, gl, bl = _linearize(r), _linearize(g), _linearize(b)
    x = 0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl
    y = 0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl
    z = 0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl

    def _f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0

    fx, fy, fz = _f(x / 0.95047), _f(y / 1.00000), _f(z / 1.08883)
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def _nearest_palette_color_lab(
    rgb: tuple[int, int, int],
    palette_lab: list[tuple[float, float, float]],
    palette: list[Color],
) -> Color:
    plab = _rgb_to_lab(rgb[0], rgb[1], rgb[2])
    best = min(
        range(len(palette_lab)),
        key=lambda i: (
            (plab[0] - palette_lab[i][0]) ** 2
            + (plab[1] - palette_lab[i][1]) ** 2
            + (plab[2] - palette_lab[i][2]) ** 2
        ),
    )
    return palette[best]


def quantize_to_palette(
    image: Image.Image,
    palette: list[Color],
    *,
    dither: bool = False,
) -> Image.Image:
    if not palette:
        return image.convert("RGBA")

    source = image.convert("RGBA")

    if dither:
        # PIL's Floyd-Steinberg dithering works in RGB space; use it for dither mode.
        output = source.convert("RGB").quantize(
            palette=_build_palette_image(palette),
            dither=_dither_mode(dither),
        ).convert("RGBA")
        output.putalpha(source.getchannel("A"))
        return _clear_fully_transparent_pixels(output)

    # Perceptual (CIELAB) nearest-neighbor for non-dithered output.
    # Pre-compute LAB for every palette entry, then build a unique-color
    # lookup table so each distinct pixel color is only converted once.
    palette_lab = [_rgb_to_lab(c[0], c[1], c[2]) for c in palette]

    raw_pixels: list[tuple[int, int, int, int]] = list(source.getdata())  # type: ignore[arg-type]
    unique_rgb: set[tuple[int, int, int]] = {p[:3] for p in raw_pixels if p[3] > 0}

    color_map: dict[tuple[int, int, int], Color] = {
        rgb: _nearest_palette_color_lab(rgb, palette_lab, palette)
        for rgb in unique_rgb
    }

    new_pixels: list[Color] = [
        (0, 0, 0, 0) if px[3] == 0 else (*color_map[px[:3]][:3], px[3])  # type: ignore[misc]
        for px in raw_pixels
    ]

    output = Image.new("RGBA", source.size)
    output.putdata(new_pixels)  # type: ignore[arg-type]
    return _clear_fully_transparent_pixels(output)


def load_palette_from_hex_list(text: str, max_colors: int = 256) -> list[Color]:
    colors: list[Color] = []
    for match in _HEX_COLOR_RE.finditer(text):
        raw = match.group(0).lstrip("#")
        if len(raw) == 6:
            color = (
                int(raw[0:2], 16),
                int(raw[2:4], 16),
                int(raw[4:6], 16),
                255,
            )
        else:
            color = (
                int(raw[0:2], 16),
                int(raw[2:4], 16),
                int(raw[4:6], 16),
                int(raw[6:8], 16),
            )
        if color not in colors:
            colors.append(color)
        if len(colors) >= max_colors:
            break

    if not colors:
        raise ValueError("No palette colors found in hex list")
    return colors


def load_palette_from_source(
    path_or_text: str | Path,
    max_colors: int = 256,
    *,
    selection: str = "frequent",
) -> list[Color]:
    path = Path(path_or_text)
    if path.exists():
        if path.suffix.lower() in {".txt", ".hex", ".pal"}:
            return load_palette_from_hex_list(
                path.read_text(encoding="utf-8"),
                max_colors=max_colors,
            )
        return load_palette_from_image(path, max_colors=max_colors, selection=selection)
    return load_palette_from_hex_list(str(path_or_text), max_colors=max_colors)


def load_palette_from_image(
    path: str | Path,
    max_colors: int = 16,
    *,
    selection: str = "frequent",
) -> list[Color]:
    image = Image.open(path).convert("RGBA")
    return palette_from_image(image, max_colors=max_colors, selection=selection)


def export_palette_strip(
    palette: list[Color],
    path: str | Path,
    swatch_size: int = 24,
) -> None:
    width = max(1, len(palette)) * swatch_size
    image = Image.new("RGBA", (width, swatch_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for index, color in enumerate(palette):
        x0 = index * swatch_size
        x1 = x0 + swatch_size - 1
        draw.rectangle((x0, 0, x1, swatch_size - 1), fill=color)
    image.save(path)


def export_palette_grid(
    cells: list[Color | None],
    columns: int,
    rows: int,
    path: str | Path,
    swatch_size: int = 24,
) -> None:
    columns = max(1, int(columns))
    rows = max(1, int(rows))
    image = Image.new("RGBA", (columns * swatch_size, rows * swatch_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    for index, color in enumerate(cells[: columns * rows]):
        if color is None:
            continue
        col = index % columns
        row = index // columns
        x0 = col * swatch_size
        y0 = row * swatch_size
        x1 = x0 + swatch_size - 1
        y1 = y0 + swatch_size - 1
        draw.rectangle((x0, y0, x1, y1), fill=color)

    image.save(path)


def sort_palette(palette: list[Color], mode: str = "brightness") -> list[Color]:
    normalized_mode = mode.strip().lower()
    if normalized_mode == "brightness":
        return sorted(palette, key=_brightness_sort_key)
    if normalized_mode == "hue":
        return sorted(palette, key=_hue_sort_key)
    raise ValueError(f"Unsupported palette sort mode: {mode}")


def _brightness_sort_key(color: Color) -> tuple[bool, float, float, int]:
    red, green, blue, alpha = color
    luma = 0.299 * red + 0.587 * green + 0.114 * blue
    saturation = _rgb_to_hsv(color)[1]
    return (alpha == 0, luma, saturation, alpha)


def _hue_sort_key(color: Color) -> tuple[bool, float, float, float, int]:
    hue, saturation, value = _rgb_to_hsv(color)
    return (color[3] == 0, hue, saturation, value, color[3])


def _rgb_to_hsv(color: Color) -> tuple[float, float, float]:
    red, green, blue, _alpha = color
    hue, saturation, value = colorsys.rgb_to_hsv(red / 255.0, green / 255.0, blue / 255.0)
    return (hue, saturation, value)
