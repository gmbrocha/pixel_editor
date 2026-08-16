import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

from src.core.palette import all_colors_from_image, load_palette_from_image
from src.core.pixel_document import PixelDocument
from src.ui.main_window import MainWindow
from src.ui.pixel_editor_window import PixelEditorWindow


def _many_color_image(count: int = 80) -> Image.Image:
    image = Image.new("RGBA", (count, 1))
    image.putdata([(index, 20, 40, 255) for index in range(count)])
    return image


def test_all_colors_preserves_visible_rgba_order_and_ignores_hidden_rgb() -> None:
    image = Image.new("RGBA", (6, 1))
    image.putdata(
        [
            (10, 20, 30, 255),
            (50, 60, 70, 128),
            (10, 20, 30, 255),
            (200, 0, 0, 0),
            (0, 200, 0, 0),
            (50, 60, 70, 64),
        ]
    )

    assert all_colors_from_image(image) == [
        (10, 20, 30, 255),
        (50, 60, 70, 128),
        (50, 60, 70, 64),
    ]


def test_palette_image_loader_has_an_unlimited_exact_mode(tmp_path) -> None:
    image = _many_color_image()
    path = tmp_path / "many-colors.png"
    image.save(path)

    assert load_palette_from_image(path, max_colors=None) == all_colors_from_image(image)


def test_main_preview_palette_defaults_to_all_colors_and_reduction_is_opt_in() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    image = _many_color_image()
    window.document.unquantized_preview_image = image

    assert window.palette_panel.reduce_colors_enabled() is False
    window.derive_palette_from_preview()
    assert window.document.palette == all_colors_from_image(image)
    assert "all distinct colors, 80 colors" in window.statusBar().currentMessage()

    window.palette_panel.reduce_colors_checkbox.setChecked(True)
    window.palette_panel.max_colors_spin.setValue(16)
    window.derive_palette_from_preview()
    assert len(window.document.palette) <= 16

    window.close()
    application.processEvents()


def test_pixel_editor_palette_defaults_to_all_colors_and_reduction_is_opt_in() -> None:
    application = QApplication.instance() or QApplication([])
    image = _many_color_image()
    window = PixelEditorWindow(PixelDocument(image=image), headless=True)

    assert window.reduce_palette_import_checkbox.isChecked() is False
    window.palette_from_current_image()
    assert window.document.palette == all_colors_from_image(image)

    window.reduce_palette_import_checkbox.setChecked(True)
    window.palette_from_current_image()
    assert len(window.document.palette) <= 64
    assert len(window.document.palette) < 80

    window.close()
    application.processEvents()
