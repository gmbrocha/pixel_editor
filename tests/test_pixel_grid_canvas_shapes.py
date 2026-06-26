from PIL import Image

from src.ui.pixel_grid_canvas import PixelGridCanvas


def test_ellipse_outline_uses_drag_bounds() -> None:
    points = set(PixelGridCanvas._ellipse_outline((1, 1), (5, 3)))

    assert points == {
        (1, 2),
        (2, 1),
        (2, 3),
        (3, 1),
        (3, 3),
        (4, 1),
        (4, 3),
        (5, 2),
    }


def test_ellipse_outline_is_independent_of_drag_direction() -> None:
    forward = PixelGridCanvas._ellipse_outline((0, 0), (4, 4))
    reverse = PixelGridCanvas._ellipse_outline((4, 4), (0, 0))

    assert reverse == forward


def test_ellipse_outline_handles_single_pixel_rows_and_columns() -> None:
    assert PixelGridCanvas._ellipse_outline((2, 2), (2, 6)) == [
        (2, 2),
        (2, 3),
        (2, 4),
        (2, 5),
        (2, 6),
    ]
    assert PixelGridCanvas._ellipse_outline((2, 2), (6, 2)) == [
        (2, 2),
        (3, 2),
        (4, 2),
        (5, 2),
        (6, 2),
    ]
    assert PixelGridCanvas._ellipse_outline((2, 2), (2, 2)) == [(2, 2)]


def test_isometric_guide_endpoints_keep_exact_pixel_art_iso_slope() -> None:
    slash_end = PixelGridCanvas._isometric_guide_end((4, 10), -1, 3)
    backslash_end = PixelGridCanvas._isometric_guide_end((4, 10), 1, 3)

    assert slash_end == (10, 7)
    assert backslash_end == (10, 13)


def test_isometric_guide_projection_snaps_resize_to_two_by_one_steps() -> None:
    steps = PixelGridCanvas._isometric_steps_from_projection((0.5, 0.5), (12.6, 6.4), 1)

    assert steps == 6


def test_stamp_flip_image_handles_horizontal_and_vertical_orientation() -> None:
    stamp = Image.new("RGBA", (2, 2))
    stamp.putdata(
        [
            (255, 0, 0, 255),
            (0, 255, 0, 255),
            (0, 0, 255, 255),
            (255, 255, 0, 255),
        ]
    )

    horizontal = PixelGridCanvas._flip_stamp_image(stamp, "horizontal")
    vertical = PixelGridCanvas._flip_stamp_image(stamp, "vertical")

    assert [horizontal.getpixel((x, y)) for y in range(2) for x in range(2)] == [
        (0, 255, 0, 255),
        (255, 0, 0, 255),
        (255, 255, 0, 255),
        (0, 0, 255, 255),
    ]
    assert [vertical.getpixel((x, y)) for y in range(2) for x in range(2)] == [
        (0, 0, 255, 255),
        (255, 255, 0, 255),
        (255, 0, 0, 255),
        (0, 255, 0, 255),
    ]
