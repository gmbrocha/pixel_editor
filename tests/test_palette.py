from PIL import Image

from src.core.palette import (
    export_palette_grid,
    load_palette_from_hex_list,
    palette_from_image,
    quantize_image,
    quantize_to_palette,
    sort_palette,
)


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


def test_quantize_image_limits_opaque_color_count():
    image = Image.new("RGBA", (4, 1))
    colors = [
        (255, 0, 0, 255),
        (250, 10, 10, 255),
        (0, 0, 255, 255),
        (10, 10, 250, 255),
    ]
    for index, color in enumerate(colors):
        image.putpixel((index, 0), color)

    output = quantize_image(image, max_colors=2)
    used = {output.getpixel((x, 0)) for x in range(output.width) if output.getpixel((x, 0))[3] > 0}

    assert len(used) == 2


def test_quantize_image_can_remap_to_reference_palette():
    image = Image.new("RGBA", (2, 1))
    image.putpixel((0, 0), (250, 20, 20, 255))
    image.putpixel((1, 0), (20, 20, 250, 255))
    reference_palette = [(255, 0, 0, 255), (0, 0, 255, 255)]

    output = quantize_image(image, max_colors=2, reference_palette=reference_palette)

    assert output.getpixel((0, 0)) == (255, 0, 0, 255)
    assert output.getpixel((1, 0)) == (0, 0, 255, 255)


def test_load_palette_from_hex_list_supports_rgb_and_rgba():
    palette = load_palette_from_hex_list("#ff0000 00ff0080", max_colors=4)

    assert palette == [
        (255, 0, 0, 255),
        (0, 255, 0, 128),
    ]


def test_export_palette_grid_writes_expected_cells(tmp_path):
    path = tmp_path / "palette_grid.png"

    export_palette_grid(
        [
            (255, 0, 0, 255),
            None,
            (0, 255, 0, 255),
            (0, 0, 255, 255),
        ],
        columns=2,
        rows=2,
        path=path,
        swatch_size=4,
    )

    image = Image.open(path).convert("RGBA")

    assert image.size == (8, 8)
    assert image.getpixel((1, 1)) == (255, 0, 0, 255)
    assert image.getpixel((5, 1)) == (0, 0, 0, 0)
    assert image.getpixel((1, 5)) == (0, 255, 0, 255)
    assert image.getpixel((5, 5)) == (0, 0, 255, 255)


def test_sort_palette_by_brightness_orders_dark_to_light_and_keeps_transparent_last():
    palette = [
        (255, 255, 255, 255),
        (0, 0, 0, 0),
        (40, 40, 40, 255),
        (180, 180, 180, 255),
    ]

    sorted_palette = sort_palette(palette, "brightness")

    assert sorted_palette == [
        (40, 40, 40, 255),
        (180, 180, 180, 255),
        (255, 255, 255, 255),
        (0, 0, 0, 0),
    ]


def test_sort_palette_by_hue_groups_colors_by_hsv_hue():
    palette = [
        (0, 0, 255, 255),
        (255, 0, 0, 255),
        (0, 255, 0, 255),
    ]

    sorted_palette = sort_palette(palette, "hue")

    assert sorted_palette == [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
    ]
