from PIL import Image

from src.core.pixel_document import flip_image_horizontal, flip_image_vertical


def test_flip_image_horizontal_mirrors_pixels_left_to_right():
    image = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.putpixel((1, 0), (0, 255, 0, 255))
    image.putpixel((2, 0), (0, 0, 255, 255))

    flipped = flip_image_horizontal(image)

    assert flipped.getpixel((0, 0)) == (0, 0, 255, 255)
    assert flipped.getpixel((1, 0)) == (0, 255, 0, 255)
    assert flipped.getpixel((2, 0)) == (255, 0, 0, 255)


def test_flip_image_vertical_mirrors_pixels_top_to_bottom():
    image = Image.new("RGBA", (1, 3), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.putpixel((0, 1), (0, 255, 0, 255))
    image.putpixel((0, 2), (0, 0, 255, 255))

    flipped = flip_image_vertical(image)

    assert flipped.getpixel((0, 0)) == (0, 0, 255, 255)
    assert flipped.getpixel((0, 1)) == (0, 255, 0, 255)
    assert flipped.getpixel((0, 2)) == (255, 0, 0, 255)
