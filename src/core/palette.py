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


def palette_from_image(image: Image.Image, max_colors: int = 16) -> list[Color]:
    rgba = image.convert("RGBA")
    color_counts = Counter(rgba.getdata())
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


def quantize_to_palette(
    image: Image.Image,
    palette: list[Color],
    *,
    dither: bool = False,
) -> Image.Image:
    if not palette:
        return image.convert("RGBA")

    source = image.convert("RGBA")
    output = source.convert("RGB").quantize(
        palette=_build_palette_image(palette),
        dither=_dither_mode(dither),
    ).convert("RGBA")
    output.putalpha(source.getchannel("A"))
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


def load_palette_from_source(path_or_text: str | Path, max_colors: int = 256) -> list[Color]:
    path = Path(path_or_text)
    if path.exists():
        if path.suffix.lower() in {".txt", ".hex", ".pal"}:
            return load_palette_from_hex_list(
                path.read_text(encoding="utf-8"),
                max_colors=max_colors,
            )
        return load_palette_from_image(path, max_colors=max_colors)
    return load_palette_from_hex_list(str(path_or_text), max_colors=max_colors)


def load_palette_from_image(path: str | Path, max_colors: int = 16) -> list[Color]:
    image = Image.open(path).convert("RGBA")
    return palette_from_image(image, max_colors=max_colors)


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
