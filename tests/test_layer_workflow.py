from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from src.core.pixel_document import Layer, PixelDocument
from src.ui.layer_panel import LayerPanel
from src.ui.pixel_editor_window import PixelEditorWindow
from src.ui.pixel_grid_canvas import PixelGridCanvas


TRANSPARENT = (0, 0, 0, 0)
RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)
YELLOW = (255, 255, 0, 255)


def layered_document() -> PixelDocument:
    source = Image.new("RGBA", (4, 3), TRANSPARENT)
    source.putpixel((0, 0), RED)
    source.putpixel((1, 0), GREEN)
    source.putpixel((3, 2), YELLOW)
    target = Image.new("RGBA", (4, 3), TRANSPARENT)
    target.putpixel((0, 0), BLUE)
    return PixelDocument(
        layers=[
            Layer(name="Source Art", image=source),
            Layer(name="Destination", image=target),
        ],
        active_layer_index=0,
    )


def test_switching_editing_layer_clears_stale_selection() -> None:
    document = layered_document()
    document.selected_pixels = {(0, 0), (1, 0)}
    document.selection_rect = (0, 0, 2, 1)

    assert document.set_active_layer(1) is True

    assert document.active_layer.name == "Destination"
    assert document.selected_pixels == set()
    assert document.selection_rect is None


def test_move_selection_to_existing_layer_preserves_coordinates_and_clears_source() -> None:
    document = layered_document()
    document.selected_pixels = {(0, 0), (1, 0), (2, 2)}

    result = document.transfer_selection_to_layer(1, move=True)

    assert result == (1, 2)
    assert document.active_layer_index == 1
    assert document.selected_pixels == {(0, 0), (1, 0)}
    assert document.layers[0].image.getpixel((0, 0)) == TRANSPARENT
    assert document.layers[0].image.getpixel((1, 0)) == TRANSPARENT
    assert document.layers[0].image.getpixel((3, 2)) == YELLOW
    assert document.layers[1].image.getpixel((0, 0)) == RED
    assert document.layers[1].image.getpixel((1, 0)) == GREEN

    assert document.undo_layer_transfer() is True
    assert document.active_layer_index == 0
    assert document.layers[0].image.getpixel((0, 0)) == RED
    assert document.layers[0].image.getpixel((1, 0)) == GREEN
    assert document.layers[1].image.getpixel((0, 0)) == BLUE

    assert document.redo_layer_transfer() is True
    assert document.active_layer_index == 1
    assert document.layers[0].image.getpixel((0, 0)) == TRANSPARENT
    assert document.layers[1].image.getpixel((0, 0)) == RED


def test_copy_selection_to_existing_layer_preserves_source() -> None:
    document = layered_document()
    document.selected_pixels = {(1, 0)}

    result = document.transfer_selection_to_layer(1, move=False)

    assert result == (1, 1)
    assert document.layers[0].image.getpixel((1, 0)) == GREEN
    assert document.layers[1].image.getpixel((1, 0)) == GREEN
    assert len(document.layers[0].history) == 0
    assert len(document.layers[1].history) == 0


def test_layer_panel_makes_edit_target_explicit_and_offers_existing_targets() -> None:
    application = QApplication.instance() or QApplication([])
    document = layered_document()
    document.selected_pixels = {(0, 0)}
    panel = LayerPanel()
    panel.set_document(document)
    panel.set_selection_count(1)

    assert "Source Art" in panel.active_layer_label.text()
    assert panel._list.currentItem().font().bold() is True
    assert panel.selection_target_combo.count() == 1
    assert panel.selection_target_combo.currentText() == "Destination"
    assert panel.selection_target_combo.currentData() == 1
    assert panel.move_selection_button.isEnabled() is True

    requests: list[tuple[int, bool]] = []
    panel.selection_transfer_requested.connect(
        lambda target, move: requests.append((target, move))
    )
    panel.move_selection_button.click()
    assert requests == [(1, True)]

    panel.deleteLater()
    application.processEvents()


def test_visibility_checkbox_does_not_change_editing_layer() -> None:
    application = QApplication.instance() or QApplication([])
    document = layered_document()
    panel = LayerPanel()
    panel.set_document(document)
    panel.show()
    application.processEvents()
    top_item = panel._list.item(0)
    rect = panel._list.visualItemRect(top_item)
    checkbox_point = QPoint(rect.left() + 8, rect.center().y())

    QTest.mouseClick(panel._list.viewport(), Qt.MouseButton.LeftButton, pos=checkbox_point)
    application.processEvents()

    assert document.active_layer.name == "Source Art"
    assert document.layers[1].visible is False
    assert panel._list.currentRow() == 1

    panel.close()
    application.processEvents()


def test_layer_panel_switch_clears_selection_and_delete_names_target(monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    document = layered_document()
    document.selected_pixels = {(0, 0)}
    panel = LayerPanel()
    panel.set_document(document)

    panel._list.setCurrentRow(0)  # Top display row is Destination.
    application.processEvents()

    assert document.active_layer.name == "Destination"
    assert document.selected_points() == set()
    assert "Destination" in panel.active_layer_label.text()

    prompts: list[str] = []

    def confirm(_parent, _title, message, *_args):
        prompts.append(message)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", confirm)
    panel._delete_active()

    assert len(document.layers) == 2
    assert prompts and "Destination" in prompts[0]

    panel.deleteLater()
    application.processEvents()


def test_pixel_editor_moves_selection_without_switching_source_first() -> None:
    application = QApplication.instance() or QApplication([])
    document = layered_document()
    document.selected_pixels = {(0, 0), (1, 0)}
    window = PixelEditorWindow(document, headless=True)
    window.layer_panel.set_selection_count(2)

    window.layer_panel.move_selection_button.click()

    assert document.active_layer.name == "Destination"
    assert document.layers[0].image.getpixel((0, 0)) == TRANSPARENT
    assert document.layers[1].image.getpixel((0, 0)) == RED
    assert window.statusBar().currentMessage() == (
        "Moved 2 pixels from 'Source Art' to 'Destination'. "
        "Now editing 'Destination'."
    )
    assert "Destination" in window.layer_panel.active_layer_label.text()

    window.undo_last_edit()
    assert document.active_layer.name == "Source Art"
    assert document.layers[0].image.getpixel((0, 0)) == RED
    assert document.layers[1].image.getpixel((0, 0)) == BLUE
    assert "Source Art" in window.layer_panel.active_layer_label.text()

    window.redo_last_edit()
    assert document.active_layer.name == "Destination"
    assert document.layers[0].image.getpixel((0, 0)) == TRANSPARENT
    assert document.layers[1].image.getpixel((0, 0)) == RED

    window.close()
    application.processEvents()


def test_hidden_active_layer_rejects_canvas_paint() -> None:
    application = QApplication.instance() or QApplication([])
    document = PixelDocument(image=Image.new("RGBA", (3, 3), TRANSPARENT))
    document.active_layer.visible = False
    document.current_color = RED
    canvas = PixelGridCanvas()
    canvas.set_document(document)
    canvas.show()
    application.processEvents()
    statuses: list[str] = []
    canvas.status_changed.connect(statuses.append)
    point = QPoint(
        canvas._view_margin + canvas._zoom // 2,
        canvas._view_margin + canvas._zoom // 2,
    )

    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=point)

    assert document.image.getpixel((0, 0)) == TRANSPARENT
    assert statuses[-1] == (
        "Cannot edit hidden layer 'Layer 1'. Enable its visibility checkbox "
        "or choose another editing layer."
    )
    canvas.close()
    application.processEvents()
