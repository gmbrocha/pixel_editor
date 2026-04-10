import colorsys

from PIL import Image

from src.core.pixel_document import (
    ColorShift,
    PixelDocument,
    apply_ramp_shifts,
    apply_color_shift,
    calculate_ramp_shifts,
    calculate_color_shift,
    darken_image,
    lighten_image,
    normalize_to_black_white,
    push_image_history,
    replace_color,
    replace_colors,
    replace_color_with_transparent,
    undo_image_history,
)


def test_darken_image_reduces_rgb_values_evenly_and_preserves_alpha():
    image = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (200, 100, 50, 255))
    image.putpixel((1, 0), (20, 40, 60, 128))

    darkened = darken_image(image, 25)

    assert darkened.getpixel((0, 0)) == (150, 75, 38, 255)
    assert darkened.getpixel((1, 0)) == (15, 30, 45, 128)


def test_darken_image_leaves_transparent_pixels_unchanged():
    image = Image.new("RGBA", (1, 1), (10, 20, 30, 0))

    darkened = darken_image(image, 80)

    assert darkened.getpixel((0, 0)) == (10, 20, 30, 0)


def test_lighten_image_increases_rgb_values_evenly_and_preserves_alpha():
    image = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (100, 50, 0, 255))
    image.putpixel((1, 0), (10, 20, 30, 128))

    lightened = lighten_image(image, 25)

    assert lightened.getpixel((0, 0)) == (139, 101, 64, 255)
    assert lightened.getpixel((1, 0)) == (71, 79, 86, 128)


def test_normalize_to_black_white_maps_only_near_black_to_black() -> None:
    image = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (20, 20, 20, 255))
    image.putpixel((1, 0), (90, 90, 90, 255))
    image.putpixel((2, 0), (200, 210, 220, 128))

    normalized = normalize_to_black_white(image, 48)

    assert normalized.getpixel((0, 0)) == (0, 0, 0, 255)
    assert normalized.getpixel((1, 0)) == (255, 255, 255, 255)
    assert normalized.getpixel((2, 0)) == (255, 255, 255, 128)


def test_normalize_to_black_white_leaves_transparent_pixels_unchanged() -> None:
    image = Image.new("RGBA", (1, 1), (10, 20, 30, 0))

    normalized = normalize_to_black_white(image, 48)

    assert normalized.getpixel((0, 0)) == (10, 20, 30, 0)


def test_replace_color_with_transparent_only_replaces_exact_rgba_matches():
    image = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (100, 50, 0, 255))
    image.putpixel((1, 0), (100, 50, 0, 128))
    image.putpixel((2, 0), (10, 20, 30, 255))

    replaced, count = replace_color_with_transparent(image, (100, 50, 0, 255))

    assert count == 1
    assert replaced.getpixel((0, 0)) == (0, 0, 0, 0)
    assert replaced.getpixel((1, 0)) == (100, 50, 0, 128)
    assert replaced.getpixel((2, 0)) == (10, 20, 30, 255)


def test_calculate_color_shift_round_trips_back_to_target():
    source = (200, 80, 40, 180)
    target = (120, 220, 90, 220)

    shift = calculate_color_shift(source, target)
    applied = apply_color_shift(source, shift)

    for actual, expected in zip(applied, target):
        assert abs(actual - expected) <= 1


def test_apply_color_shift_reuses_same_hue_relative_delta():
    base = _hsv_to_rgba(350, 0.7, 0.6, 255)
    target = _hsv_to_rgba(10, 0.8, 0.7, 255)
    shift = calculate_color_shift(base, target)

    other_base = _hsv_to_rgba(120, 0.5, 0.4, 200)
    shifted = apply_color_shift(other_base, shift)

    expected = apply_color_shift(
        other_base,
        ColorShift(hue_degrees=20.0, saturation_delta=0.1, value_delta=0.1, alpha_delta=0),
    )

    for actual, expected_channel in zip(shifted, expected):
        assert abs(actual - expected_channel) <= 1


def test_apply_ramp_shifts_projects_same_step_sequence_from_new_base():
    source_ramp = [
        _hsv_to_rgba(30, 0.8, 0.3, 255),
        _hsv_to_rgba(40, 0.7, 0.45, 255),
        _hsv_to_rgba(55, 0.6, 0.65, 255),
    ]
    shifts = calculate_ramp_shifts(source_ramp)

    new_base = _hsv_to_rgba(200, 0.5, 0.25, 200)
    projected = apply_ramp_shifts(new_base, shifts)

    assert len(projected) == 3
    assert projected[0] == new_base

    projected_shifts = calculate_ramp_shifts(projected)
    for actual, expected in zip(projected_shifts, shifts):
        assert abs(actual.hue_degrees - expected.hue_degrees) <= 1.0
        assert abs(actual.saturation_delta - expected.saturation_delta) <= 0.02
        assert abs(actual.value_delta - expected.value_delta) <= 0.02
        assert actual.alpha_delta == expected.alpha_delta


def test_replace_color_with_transparent_ignores_transparent_target_color():
    image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    replaced, count = replace_color_with_transparent(image, (0, 0, 0, 0))

    assert count == 0
    assert replaced.getpixel((0, 0)) == (0, 0, 0, 0)


def test_replace_color_can_replace_exact_matches_with_white():
    image = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (100, 50, 0, 255))
    image.putpixel((1, 0), (100, 50, 0, 128))
    image.putpixel((2, 0), (10, 20, 30, 255))

    replaced, count = replace_color(image, (100, 50, 0, 255), (255, 255, 255, 255))

    assert count == 1
    assert replaced.getpixel((0, 0)) == (255, 255, 255, 255)
    assert replaced.getpixel((1, 0)) == (100, 50, 0, 128)
    assert replaced.getpixel((2, 0)) == (10, 20, 30, 255)


def test_replace_colors_maps_multiple_exact_matches_in_single_pass():
    image = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (10, 20, 30, 255))
    image.putpixel((1, 0), (40, 50, 60, 255))
    image.putpixel((2, 0), (40, 50, 60, 255))

    replaced, count = replace_colors(
        image,
        {
            (10, 20, 30, 255): (100, 110, 120, 255),
            (40, 50, 60, 255): (130, 140, 150, 255),
        },
    )

    assert count == 3
    assert replaced.getpixel((0, 0)) == (100, 110, 120, 255)
    assert replaced.getpixel((1, 0)) == (130, 140, 150, 255)
    assert replaced.getpixel((2, 0)) == (130, 140, 150, 255)


def test_undo_image_history_restores_previous_image():
    original = Image.new("RGBA", (1, 1), (100, 100, 100, 255))
    document = PixelDocument(image=original.copy())
    push_image_history(document)
    document.image = darken_image(document.image, 50)

    restored = undo_image_history(document)

    assert restored is True
    assert document.image.getpixel((0, 0)) == (100, 100, 100, 255)
    assert document.image_history == []


def test_undo_image_history_returns_false_when_empty():
    document = PixelDocument(image=Image.new("RGBA", (1, 1), (0, 0, 0, 0)))

    restored = undo_image_history(document)

    assert restored is False


def _hsv_to_rgba(hue_degrees: float, saturation: float, value: float, alpha: int) -> tuple[int, int, int, int]:
    red, green, blue = colorsys.hsv_to_rgb(hue_degrees / 360.0, saturation, value)
    return (
        int(round(red * 255)),
        int(round(green * 255)),
        int(round(blue * 255)),
        alpha,
    )
