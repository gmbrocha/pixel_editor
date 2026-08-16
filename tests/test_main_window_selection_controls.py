import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def test_select_all_detects_resolution_and_replaces_regions() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    image = Image.new("RGBA", (5001, 7), (20, 40, 60, 255))
    window.document.source_image = image
    window.source_canvas.set_image(image)
    window.source_canvas.drop_rect_selection(2, 2)

    window.select_all_button.click()

    assert window.rect_w_spin.value() == 5001
    assert window.rect_h_spin.value() == 7
    assert window.rect_w_spin.maximum() >= 5001
    assert len(window.document.selections) == 1
    assert window.document.selections[0].kind == "rect"
    assert window.document.selections[0].points == [
        (0.0, 0.0),
        (5001.0, 0.0),
        (5001.0, 7.0),
        (0.0, 7.0),
    ]
    assert window.preview_panel.downscale_combo.isEnabled() is True
    window.preview_panel.downscale_combo.setCurrentIndex(
        window.preview_panel.downscale_combo.findData(2)
    )
    assert window.preview_panel.width_spin.value() == 2500
    assert window.preview_panel.height_spin.value() == 3
    assert window.statusBar().currentMessage() == "Selected full image: 5001x7 pixels"

    window.close()
    application.processEvents()


def test_select_all_requires_an_imported_image() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()

    window.select_all_button.click()

    assert window.document.selections == []
    assert window.statusBar().currentMessage() == "Load an image first"

    window.close()
    application.processEvents()
