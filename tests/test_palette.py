from PIL import Image

from src.core.palette import palette_from_image, quantize_to_palette


def test_palette_from_image_limits_color_count():
    image = Image.new("RGBA", (4, 1))
    colors = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 0, 255),
    ]
    for index, color in enumerate(colors):
        image.putpixel((index, 0), color)

    palette = palette_from_image(image, max_colors=2)

    assert len(palette) == 2


def test_palette_from_image_returns_exact_source_colors() -> None:
    image = Image.new("RGBA", (3, 1))
    colors = [
        (10, 20, 30, 255),
        (10, 20, 30, 255),
        (10, 20, 30, 128),
    ]
    for index, color in enumerate(colors):
        image.putpixel((index, 0), color)

    palette = palette_from_image(image, max_colors=2)

    assert palette == [(10, 20, 30, 255), (10, 20, 30, 128)]


def test_quantize_to_palette_maps_to_nearest_color():
    image = Image.new("RGBA", (1, 1), (250, 10, 10, 255))
    palette = [(255, 0, 0, 255), (0, 0, 255, 255)]

    output = quantize_to_palette(image, palette)

    assert output.getpixel((0, 0)) == (255, 0, 0, 255)
