import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from src.core.pixel_document import PixelDocument
from src.ui.pixel_editor_window import PixelEditorWindow
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


def test_pixel_measurement_uses_euclidean_center_distance() -> None:
    assert PixelGridCanvas._pixel_distance((2, 4), (5, 6)) == math.sqrt(13)
    assert PixelGridCanvas._format_pixel_distance(5.0) == "5 px"
    assert PixelGridCanvas._format_pixel_distance(math.sqrt(13)) == "3.606 px"


def test_measurement_click_move_click_and_right_click_clear() -> None:
    application = QApplication.instance() or QApplication([])
    canvas = PixelGridCanvas()
    document = PixelDocument(image=Image.new("RGBA", (10, 10)))
    original_pixels = document.image.tobytes()
    canvas.set_document(document)
    canvas.show()
    application.processEvents()
    statuses: list[str] = []
    canvas.status_changed.connect(statuses.append)
    canvas.set_measurement_enabled(True)

    margin = canvas._view_margin
    zoom = canvas._zoom
    start = QPoint(margin + 2 * zoom + zoom // 2, margin + 3 * zoom + zoom // 2)
    end = QPoint(margin + 5 * zoom + zoom // 2, margin + 5 * zoom + zoom // 2)
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, end)
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=end)

    assert canvas.measurement() == ((2, 3), (5, 5))
    assert canvas.measurement_distance() == math.sqrt(13)
    assert statuses[-1] == "Distance: 3.606 px. Right-click to clear"
    assert document.image.tobytes() == original_pixels

    QTest.mouseClick(canvas, Qt.MouseButton.RightButton, pos=end)
    assert canvas.measurement() is None
    assert statuses[-1] == "Measurement cleared"
    canvas.close()
    application.processEvents()


def test_header_measure_action_toggles_canvas_tool() -> None:
    application = QApplication.instance() or QApplication([])
    window = PixelEditorWindow(
        PixelDocument(image=Image.new("RGBA", (4, 4))),
        headless=True,
    )

    assert window.measure_action.isCheckable()
    assert window.canvas.is_measurement_enabled() is False
    window.measure_action.setChecked(True)
    assert window.canvas.is_measurement_enabled() is True
    window.measure_action.setChecked(False)
    assert window.canvas.is_measurement_enabled() is False

    window.close()
    application.processEvents()


def test_right_click_transparent_toggle_erases_without_changing_left_color() -> None:
    application = QApplication.instance() or QApplication([])
    green = (20, 210, 70, 255)
    document = PixelDocument(image=Image.new("RGBA", (4, 2), (90, 80, 70, 255)))
    document.current_color = green
    document.use_transparent_color = False
    window = PixelEditorWindow(document, headless=True)
    window.canvas.show()
    application.processEvents()

    assert window.right_click_transparent_checkbox.isChecked() is False
    assert window.canvas.right_click_transparent_enabled() is False
    window.right_click_transparent_checkbox.setChecked(True)
    assert window.canvas.right_click_transparent_enabled() is True

    margin = window.canvas._view_margin
    zoom = window.canvas._zoom

    def pixel_center(x: int, y: int) -> QPoint:
        return QPoint(margin + x * zoom + zoom // 2, margin + y * zoom + zoom // 2)

    QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, pos=pixel_center(0, 0))
    QTest.mouseClick(window.canvas, Qt.MouseButton.RightButton, pos=pixel_center(1, 0))
    QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, pos=pixel_center(2, 0))

    assert document.image.getpixel((0, 0)) == green
    assert document.image.getpixel((1, 0)) == (0, 0, 0, 0)
    assert document.image.getpixel((2, 0)) == green
    assert document.current_color == green
    assert document.use_transparent_color is False

    window.canvas.close()
    window.close()
    application.processEvents()


def test_right_click_transparent_uses_fill_line_ellipse_and_mirror_paint_paths() -> None:
    application = QApplication.instance() or QApplication([])
    document = PixelDocument(image=Image.new("RGBA", (8, 8), (30, 40, 50, 255)))
    canvas = PixelGridCanvas()
    canvas.set_document(document)
    canvas.set_right_click_transparent_enabled(True)
    canvas.show()
    application.processEvents()

    margin = canvas._view_margin
    zoom = canvas._zoom

    def pixel_center(x: int, y: int) -> QPoint:
        return QPoint(margin + x * zoom + zoom // 2, margin + y * zoom + zoom // 2)

    QTest.mousePress(
        canvas,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.ShiftModifier,
        pixel_center(1, 1),
    )
    QTest.mouseMove(canvas, pixel_center(2, 2))
    QTest.mouseRelease(
        canvas,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.ShiftModifier,
        pixel_center(2, 2),
    )

    QTest.keyPress(canvas, Qt.Key.Key_L)
    QTest.mousePress(canvas, Qt.MouseButton.RightButton, pos=pixel_center(0, 4))
    QTest.mouseMove(canvas, pixel_center(3, 4))
    QTest.mouseRelease(canvas, Qt.MouseButton.RightButton, pos=pixel_center(3, 4))
    QTest.keyRelease(canvas, Qt.Key.Key_L)

    QTest.keyPress(canvas, Qt.Key.Key_C)
    QTest.mousePress(canvas, Qt.MouseButton.RightButton, pos=pixel_center(3, 0))
    QTest.mouseMove(canvas, pixel_center(6, 3))
    QTest.mouseRelease(canvas, Qt.MouseButton.RightButton, pos=pixel_center(6, 3))
    QTest.keyRelease(canvas, Qt.Key.Key_C)

    canvas.set_mirror(True)
    QTest.mouseClick(canvas, Qt.MouseButton.RightButton, pos=pixel_center(0, 7))

    assert document.image.getpixel((1, 1)) == (0, 0, 0, 0)
    assert document.image.getpixel((2, 2)) == (0, 0, 0, 0)
    assert document.image.getpixel((2, 4)) == (0, 0, 0, 0)
    assert document.image.getpixel((3, 1)) == (0, 0, 0, 0)
    assert document.image.getpixel((7, 7)) == (0, 0, 0, 0)

    canvas.close()
    application.processEvents()


def test_right_click_transparent_does_not_override_select_mode_right_click() -> None:
    application = QApplication.instance() or QApplication([])
    original = (100, 110, 120, 255)
    document = PixelDocument(image=Image.new("RGBA", (3, 3), original))
    canvas = PixelGridCanvas()
    canvas.set_document(document)
    canvas.set_right_click_transparent_enabled(True)
    canvas.set_mode("select")
    canvas.show()
    application.processEvents()

    margin = canvas._view_margin
    zoom = canvas._zoom
    point = QPoint(margin + zoom // 2, margin + zoom // 2)
    QTest.mouseClick(canvas, Qt.MouseButton.RightButton, pos=point)

    assert document.image.getpixel((0, 0)) == original
    canvas.close()
    application.processEvents()


def test_import_sprite_stays_native_and_floating_until_canvas_click(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    base = Image.new("RGBA", (8, 8), (80, 20, 10, 255))
    sprite = Image.new("RGBA", (3, 2), (0, 0, 0, 0))
    sprite.putpixel((0, 0), (0, 255, 0, 255))
    sprite.putpixel((2, 1), (0, 0, 255, 255))
    sprite_path = tmp_path / "native-sprite.png"
    sprite.save(sprite_path)
    document = PixelDocument(image=base)
    original_pixels = document.image.tobytes()
    window = PixelEditorWindow(document, headless=True)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(sprite_path), ""),
    )

    window.import_sprite_button.click()

    assert document.image.tobytes() == original_pixels
    assert window.canvas.stamp_image() is not None
    assert window.canvas.stamp_image().size == (3, 2)
    assert window.stamp_radio.isChecked() is True
    assert window.flip_stamp_h_button.isEnabled() is True
    assert "native size (3x2px)" in window.statusBar().currentMessage()

    window.canvas.show()
    application.processEvents()
    zoom = window.canvas._zoom
    margin = window.canvas._view_margin
    placement = QPoint(margin + 4 * zoom + zoom // 2, margin + 4 * zoom + zoom // 2)
    QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, pos=placement)

    assert document.image.getpixel((3, 3)) == (0, 255, 0, 255)
    assert document.image.getpixel((5, 4)) == (0, 0, 255, 255)
    assert document.image.getpixel((4, 3)) == (80, 20, 10, 255)

    window.canvas.close()
    window.close()
    application.processEvents()
