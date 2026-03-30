from PIL import Image

from src.core.pixel_document import (
    PixelDocument,
    darken_image,
    lighten_image,
    push_image_history,
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
