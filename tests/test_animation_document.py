from PIL import Image

from src.core.animation_document import (
    AnimationFrame,
    create_blank_animation,
    create_animation_from_base,
    frames_to_sheet,
    rotate_pixels_around_pivot,
)


def test_create_blank_animation() -> None:
    doc = create_blank_animation(16, 16, 4)
    assert doc.frame_count == 4
    assert doc.frame_size == (16, 16)


def test_create_from_base() -> None:
    base = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    doc = create_animation_from_base(base, 3)
    assert doc.frame_count == 3
    assert doc.frames[0].image.getpixel((0, 0)) == (255, 0, 0, 255)
    doc.frames[0].image.putpixel((0, 0), (0, 255, 0, 255))
    assert doc.frames[1].image.getpixel((0, 0)) == (255, 0, 0, 255)


def test_frames_to_sheet() -> None:
    frames = [AnimationFrame(image=Image.new("RGBA", (8, 8))) for _ in range(6)]
    sheet = frames_to_sheet(frames, 3)
    assert sheet.size == (24, 16)


def test_rotate_pixels_around_pivot_identity() -> None:
    img = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    img.putpixel((2, 0), (255, 0, 0, 255))
    selected = {(2, 0)}
    result = rotate_pixels_around_pivot(img, selected, (2, 2), 0)
    assert result.getpixel((2, 0)) == (255, 0, 0, 255)


def test_rotate_pixels_90() -> None:
    img = Image.new("RGBA", (5, 5), (0, 0, 0, 0))
    img.putpixel((3, 1), (255, 0, 0, 255))
    selected = {(3, 1)}
    result = rotate_pixels_around_pivot(img, selected, (2, 2), 90)
    assert result.getpixel((3, 1))[3] == 0
    assert result.getpixel((3, 3)) == (255, 0, 0, 255)
