from PIL import Image

from src.core.pixel_document import move_rect_contents


def test_move_rect_contents_leaves_transparent_gap_and_moves_pixels():
    image = Image.new("RGBA", (5, 5), (0, 0, 0, 0))
    image.putpixel((1, 1), (255, 0, 0, 255))
    image.putpixel((2, 1), (0, 255, 0, 255))

    moved, rect = move_rect_contents(image, (1, 1, 2, 1), 1, 2)

    assert rect == (2, 3, 3, 3)
    assert moved.getpixel((1, 1))[3] == 0
    assert moved.getpixel((2, 3)) == (255, 0, 0, 255)
    assert moved.getpixel((3, 3)) == (0, 255, 0, 255)
