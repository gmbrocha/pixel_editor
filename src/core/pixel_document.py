from __future__ import annotations

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


def push_image_history(document: PixelDocument, max_entries: int = 20) -> None:
    document.image_history.append(document.image.copy())
    if len(document.image_history) > max_entries:
        document.image_history = document.image_history[-max_entries:]


def undo_image_history(document: PixelDocument) -> bool:
    if not document.image_history:
        return False
    document.image = document.image_history.pop()
    return True
