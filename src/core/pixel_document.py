from __future__ import annotations

import colorsys
from dataclasses import dataclass, field

from PIL import Image


Point = tuple[int, int]
Rect = tuple[int, int, int, int]
Color = tuple[int, int, int, int]


@dataclass(slots=True)
class PixelDocument:
    image: Image.Image
    name: str = "pixel_map"
    palette: list[Color] = field(default_factory=list)
    selected_pixels: set[Point] = field(default_factory=set)
    selection_rect: Rect | None = None
    current_color: Color = (0, 0, 0, 255)
    use_transparent_color: bool = False
    image_history: list[Image.Image] = field(default_factory=list)

    def clone_image(self) -> Image.Image:
        return self.image.copy()


@dataclass(slots=True)
class ColorShift:
    hue_degrees: float = 0.0
    saturation_delta: float = 0.0
    value_delta: float = 0.0
    alpha_delta: int = 0


def create_blank_pixel_map(width: int, height: int) -> PixelDocument:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    return PixelDocument(image=image, name=f"blank_{width}x{height}")


def rect_points(rect: Rect) -> set[Point]:
    left, top, right, bottom = normalize_rect(rect)
    return {
        (x, y)
        for y in range(top, bottom + 1)
        for x in range(left, right + 1)
    }


def normalize_rect(rect: Rect) -> Rect:
    left, top, right, bottom = rect
    return (
        min(left, right),
        min(top, bottom),
        max(left, right),
        max(top, bottom),
    )


def move_rect_contents(image: Image.Image, rect: Rect, dx: int, dy: int) -> tuple[Image.Image, Rect]:
    left, top, right, bottom = normalize_rect(rect)
    width = right - left + 1
    height = bottom - top + 1

    moved = image.copy()
    chunk = image.crop((left, top, right + 1, bottom + 1))

    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            moved.putpixel((x, y), (0, 0, 0, 0))

    new_left = max(0, min(image.width - width, left + dx))
    new_top = max(0, min(image.height - height, top + dy))
    moved.alpha_composite(chunk, (new_left, new_top))
    new_rect = (
        new_left,
        new_top,
        new_left + width - 1,
        new_top + height - 1,
    )
    return moved, new_rect


def flip_image_horizontal(image: Image.Image) -> Image.Image:
    return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)


def flip_image_vertical(image: Image.Image) -> Image.Image:
    return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def rotate_image_clockwise(image: Image.Image) -> Image.Image:
    return image.transpose(Image.Transpose.ROTATE_270)


def rotate_image_counterclockwise(image: Image.Image) -> Image.Image:
    return image.transpose(Image.Transpose.ROTATE_90)


def darken_image(image: Image.Image, percent: int) -> Image.Image:
    amount = max(0, min(100, percent)) / 100.0
    factor = 1.0 - amount
    source = image.convert("RGBA")
    darkened = source.copy()

    for y in range(source.height):
        for x in range(source.width):
            red, green, blue, alpha = source.getpixel((x, y))
            if alpha == 0:
                continue
            darkened.putpixel(
                (x, y),
                (
                    int(round(red * factor)),
                    int(round(green * factor)),
                    int(round(blue * factor)),
                    alpha,
                ),
            )

    return darkened


def lighten_image(image: Image.Image, percent: int) -> Image.Image:
    amount = max(0, min(100, percent)) / 100.0
    source = image.convert("RGBA")
    lightened = source.copy()

    for y in range(source.height):
        for x in range(source.width):
            red, green, blue, alpha = source.getpixel((x, y))
            if alpha == 0:
                continue
            lightened.putpixel(
                (x, y),
                (
                    int(round(red + (255 - red) * amount)),
                    int(round(green + (255 - green) * amount)),
                    int(round(blue + (255 - blue) * amount)),
                    alpha,
                ),
            )

    return lightened


def normalize_to_black_white(image: Image.Image, black_threshold: int) -> Image.Image:
    threshold = max(0, min(255, black_threshold))
    source = image.convert("RGBA")
    normalized = source.copy()

    for y in range(source.height):
        for x in range(source.width):
            red, green, blue, alpha = source.getpixel((x, y))
            if alpha == 0:
                continue
            luma = int(round(0.299 * red + 0.587 * green + 0.114 * blue))
            normalized.putpixel(
                (x, y),
                (0, 0, 0, alpha) if luma <= threshold else (255, 255, 255, alpha),
            )

    return normalized


def replace_color(image: Image.Image, color: Color, replacement: Color) -> tuple[Image.Image, int]:
    if color[3] == 0:
        return image.convert("RGBA").copy(), 0

    source = image.convert("RGBA")
    replaced = source.copy()
    replacements = 0

    for y in range(source.height):
        for x in range(source.width):
            if source.getpixel((x, y)) != color:
                continue
            replaced.putpixel((x, y), replacement)
            replacements += 1

    return replaced, replacements


def replace_color_with_transparent(image: Image.Image, color: Color) -> tuple[Image.Image, int]:
    return replace_color(image, color, (0, 0, 0, 0))


def replace_colors(image: Image.Image, replacements: dict[Color, Color]) -> tuple[Image.Image, int]:
    source = image.convert("RGBA")
    replaced = source.copy()
    replacements_applied = 0
    normalized_map = {key: value for key, value in replacements.items() if key[3] != 0}
    if not normalized_map:
        return replaced, 0

    for y in range(source.height):
        for x in range(source.width):
            pixel = source.getpixel((x, y))
            replacement = normalized_map.get(pixel)
            if replacement is None:
                continue
            replaced.putpixel((x, y), replacement)
            replacements_applied += 1

    return replaced, replacements_applied


def calculate_color_shift(source: Color, target: Color) -> ColorShift:
    source_h, source_s, source_v, source_a = _rgba_to_hsva(source)
    target_h, target_s, target_v, target_a = _rgba_to_hsva(target)
    return ColorShift(
        hue_degrees=_shortest_hue_delta(source_h, target_h),
        saturation_delta=target_s - source_s,
        value_delta=target_v - source_v,
        alpha_delta=target_a - source_a,
    )


def apply_color_shift(source: Color, shift: ColorShift) -> Color:
    hue, saturation, value, alpha = _rgba_to_hsva(source)
    shifted_hue = (hue + shift.hue_degrees) % 360.0
    shifted_saturation = max(0.0, min(1.0, saturation + shift.saturation_delta))
    shifted_value = max(0.0, min(1.0, value + shift.value_delta))
    shifted_alpha = max(0, min(255, alpha + shift.alpha_delta))
    return _hsva_to_rgba(shifted_hue, shifted_saturation, shifted_value, shifted_alpha)


def calculate_ramp_shifts(ramp: list[Color]) -> list[ColorShift]:
    if len(ramp) < 2:
        return []
    return [
        calculate_color_shift(ramp[index], ramp[index + 1])
        for index in range(len(ramp) - 1)
    ]


def apply_ramp_shifts(base: Color, shifts: list[ColorShift]) -> list[Color]:
    ramp = [base]
    current = base
    for shift in shifts:
        current = apply_color_shift(current, shift)
        ramp.append(current)
    return ramp


def _rgba_to_hsva(color: Color) -> tuple[float, float, float, int]:
    red, green, blue, alpha = color
    hue, saturation, value = colorsys.rgb_to_hsv(red / 255.0, green / 255.0, blue / 255.0)
    return (hue * 360.0, saturation, value, alpha)


def _hsva_to_rgba(hue_degrees: float, saturation: float, value: float, alpha: int) -> Color:
    red, green, blue = colorsys.hsv_to_rgb(
        (hue_degrees % 360.0) / 360.0,
        max(0.0, min(1.0, saturation)),
        max(0.0, min(1.0, value)),
    )
    return (
        int(round(red * 255)),
        int(round(green * 255)),
        int(round(blue * 255)),
        max(0, min(255, int(alpha))),
    )


def _shortest_hue_delta(start_hue: float, end_hue: float) -> float:
    return ((end_hue - start_hue + 180.0) % 360.0) - 180.0


def push_image_history(document: PixelDocument, max_entries: int = 20) -> None:
    document.image_history.append(document.image.copy())
    if len(document.image_history) > max_entries:
        document.image_history = document.image_history[-max_entries:]


def undo_image_history(document: PixelDocument) -> bool:
    if not document.image_history:
        return False
    document.image = document.image_history.pop()
    return True
