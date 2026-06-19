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
