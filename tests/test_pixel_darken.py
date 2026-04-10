from PIL import Image

from src.core.pixel_document import (
    PixelDocument,
    darken_image,
    lighten_image,
    normalize_to_black_white,
    push_image_history,
    replace_color,
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
