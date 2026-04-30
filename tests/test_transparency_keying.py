from PIL import Image

from src.core.pixel_document import (
    replace_light_background_with_transparent,
    replace_similar_color_with_transparent,
)


def test_replace_similar_color_with_transparent_uses_rgb_distance() -> None:
    image = Image.new("RGBA", (4, 1))
    image.putdata(
        [
            (255, 255, 255, 255),
            (248, 248, 248, 255),
            (220, 220, 220, 255),
            (255, 0, 0, 255),
        ]
    )

    updated, replaced = replace_similar_color_with_transparent(image, (250, 250, 250, 255), 12)

    assert replaced == 2
    assert [updated.getpixel((x, 0)) for x in range(updated.width)] == [
        (0, 0, 0, 0),
        (0, 0, 0, 0),
        (220, 220, 220, 255),
        (255, 0, 0, 255),
    ]


def test_replace_light_background_with_transparent_preserves_colored_lights() -> None:
    image = Image.new("RGBA", (4, 1))
    image.putdata(
        [
            (255, 255, 255, 255),
            (238, 236, 232, 255),
            (240, 180, 180, 255),
            (120, 120, 120, 255),
        ]
    )

    updated, replaced = replace_light_background_with_transparent(
        image,
        min_brightness=230,
        max_saturation=24,
    )

    assert replaced == 2
    assert [updated.getpixel((x, 0)) for x in range(updated.width)] == [
        (0, 0, 0, 0),
        (0, 0, 0, 0),
        (240, 180, 180, 255),
        (120, 120, 120, 255),
    ]
