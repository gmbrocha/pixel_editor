from PIL import Image

from src.core.pixel_document import PixelDocument, selection_points_from_perimeter


RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)
YELLOW = (255, 255, 0, 255)
TRANSPARENT = (0, 0, 0, 0)


def test_copy_selection_image_compacts_arbitrary_selected_pixels() -> None:
    image = Image.new("RGBA", (4, 3), TRANSPARENT)
    image.putpixel((0, 0), RED)
    image.putpixel((1, 1), GREEN)
    image.putpixel((3, 2), BLUE)
    image.putpixel((2, 0), YELLOW)
    document = PixelDocument(image=image)
    document.selected_pixels = {(0, 0), (1, 1), (3, 2)}

    stamp = document.copy_selection_image(compact=True)

    assert stamp is not None
    assert stamp.size == (4, 3)
    assert stamp.getpixel((0, 0)) == RED
    assert stamp.getpixel((1, 1)) == GREEN
    assert stamp.getpixel((3, 2)) == BLUE
    assert stamp.getpixel((2, 0)) == TRANSPARENT


def test_selected_points_combines_rect_and_pixel_selection() -> None:
    document = PixelDocument(image=Image.new("RGBA", (5, 5), TRANSPARENT))
    document.selection_rect = (1, 1, 2, 2)
    document.selected_pixels = {(4, 4), (9, 9)}

    assert document.selected_points() == {
        (1, 1),
        (2, 1),
        (1, 2),
        (2, 2),
        (4, 4),
    }


def test_copy_selection_to_new_layer_preserves_source_layer() -> None:
    image = Image.new("RGBA", (4, 3), TRANSPARENT)
    image.putpixel((0, 0), RED)
    image.putpixel((1, 1), GREEN)
    image.putpixel((3, 2), BLUE)
    image.putpixel((2, 0), YELLOW)
    document = PixelDocument(image=image)
    document.selected_pixels = {(0, 0), (3, 2)}

    result = document.copy_selection_to_new_layer()

    assert result == (1, 2)
    assert len(document.layers) == 2
    assert document.active_layer_index == 1
    assert document.layers[0].image.getpixel((0, 0)) == RED
    assert document.layers[0].image.getpixel((3, 2)) == BLUE
    assert document.layers[0].image.getpixel((2, 0)) == YELLOW
    assert document.layers[1].image.getpixel((0, 0)) == RED
    assert document.layers[1].image.getpixel((3, 2)) == BLUE
    assert document.layers[1].image.getpixel((2, 0)) == TRANSPARENT


def test_selection_points_from_perimeter_fills_enclosed_cells() -> None:
    selected = selection_points_from_perimeter(
        [(1, 1), (4, 1), (4, 4), (1, 4)],
        width=8,
        height=8,
    )

    assert selected == {
        (x, y)
        for y in range(1, 5)
        for x in range(1, 5)
    }
    assert (2, 2) in selected
    assert (0, 0) not in selected


def test_selection_points_from_perimeter_handles_canvas_edge_shape() -> None:
    selected = selection_points_from_perimeter(
        [(0, 0), (3, 0), (3, 3), (0, 3), (0, 0)],
        width=5,
        height=5,
    )

    assert selected == {
        (x, y)
        for y in range(0, 4)
        for x in range(0, 4)
    }
    assert (4, 4) not in selected
