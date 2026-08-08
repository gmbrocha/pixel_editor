from PIL import Image

from src.core.pixel_document import (
    RGB_DISTANCE_MAX,
    replace_light_background_with_transparent,
    replace_similar_color_with_transparent,
    rgb_distance_tolerance_from_percent,
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


def test_rgb_distance_tolerance_from_percent_scales_and_clamps() -> None:
    assert rgb_distance_tolerance_from_percent(0) == 0
    assert rgb_distance_tolerance_from_percent(50) == round(RGB_DISTANCE_MAX * 0.5)
    assert rgb_distance_tolerance_from_percent(-20) == 0
    assert rgb_distance_tolerance_from_percent(120) == RGB_DISTANCE_MAX


def test_percent_key_can_clear_near_white_from_pure_white() -> None:
    image = Image.new("RGBA", (4, 1))
    image.putdata(
        [
            (255, 255, 255, 255),
            (240, 240, 240, 255),
            (230, 230, 230, 255),
            (255, 0, 0, 255),
        ]
    )

    updated, replaced = replace_similar_color_with_transparent(
        image,
        (255, 255, 255, 255),
        rgb_distance_tolerance_from_percent(6),
    )

    assert replaced == 2
    assert [updated.getpixel((x, 0)) for x in range(updated.width)] == [
        (0, 0, 0, 0),
        (0, 0, 0, 0),
        (230, 230, 230, 255),
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
