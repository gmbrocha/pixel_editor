from __future__ import annotations

from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw


Color = tuple[int, int, int, int]


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


def quantize_to_palette(image: Image.Image, palette: list[Color]) -> Image.Image:
    if not palette:
        return image.convert("RGBA")

    source = image.convert("RGBA")
    output = Image.new("RGBA", source.size)
    source_pixels = source.load()
    output_pixels = output.load()

    for y in range(source.height):
        for x in range(source.width):
            pixel = source_pixels[x, y]
            if pixel[3] == 0:
                output_pixels[x, y] = (0, 0, 0, 0)
                continue

            best = min(
                palette,
                key=lambda color: (
                    (pixel[0] - color[0]) ** 2
                    + (pixel[1] - color[1]) ** 2
                    + (pixel[2] - color[2]) ** 2
                ),
            )
            output_pixels[x, y] = best

    return output


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
