from PIL import Image

from src.core.pixel_document import (
    rotate_image_clockwise,
    rotate_image_counterclockwise,
)


def test_rotate_image_clockwise_rotates_pixels_right():
    image = Image.new("RGBA", (2, 3), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.putpixel((1, 0), (0, 255, 0, 255))
    image.putpixel((0, 1), (0, 0, 255, 255))

    rotated = rotate_image_clockwise(image)

    assert rotated.size == (3, 2)
    assert rotated.getpixel((2, 0)) == (255, 0, 0, 255)
    assert rotated.getpixel((2, 1)) == (0, 255, 0, 255)
    assert rotated.getpixel((1, 0)) == (0, 0, 255, 255)


def test_rotate_image_counterclockwise_rotates_pixels_left():
    image = Image.new("RGBA", (2, 3), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.putpixel((1, 0), (0, 255, 0, 255))
    image.putpixel((0, 1), (0, 0, 255, 255))

    rotated = rotate_image_counterclockwise(image)

    assert rotated.size == (3, 2)
    assert rotated.getpixel((0, 1)) == (255, 0, 0, 255)
    assert rotated.getpixel((0, 0)) == (0, 255, 0, 255)
    assert rotated.getpixel((1, 1)) == (0, 0, 255, 255)
