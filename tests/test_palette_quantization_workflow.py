import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QGroupBox

from src.core.palette import quantize_to_palette
from src.core.selection_models import RegionSelection
from src.ui.main_window import MainWindow
from src.ui.palette_panel import PalettePanel


BLACK_WHITE = [(0, 0, 0, 255), (255, 255, 255, 255)]


def _gradient(width: int = 32, height: int = 4) -> Image.Image:
    image = Image.new("RGBA", (width, height))
    image.putdata(
        [
            (round(x * 255 / (width - 1)),) * 3 + (255,)
            for _y in range(height)
            for x in range(width)
        ]
    )
    return image


def _full_selection(width: int, height: int) -> list[RegionSelection]:
    return [
        RegionSelection(
            kind="polygon",
            points=[(0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)],
        )
    ]


def test_floyd_steinberg_is_deterministic_distinct_and_palette_bounded() -> None:
    image = _gradient()
    plain = quantize_to_palette(image, BLACK_WHITE, dither=False)
    first = quantize_to_palette(image, BLACK_WHITE, dither=True)
    second = quantize_to_palette(image, BLACK_WHITE, dither=True)

    assert first.tobytes() == second.tobytes()
    assert first.tobytes() != plain.tobytes()
    assert {
        pixel[:3] for pixel in first.getdata() if pixel[3] > 0
    } <= {color[:3] for color in BLACK_WHITE}


def test_floyd_steinberg_does_not_wrap_right_edge_error_to_next_scanline() -> None:
    image = Image.new("RGBA", (4, 2), (0, 0, 0, 255))
    image.putpixel((3, 0), (100, 100, 100, 255))
    image.putpixel((0, 1), (120, 120, 120, 255))

    result = quantize_to_palette(image, BLACK_WHITE, dither=True)

    assert result.getpixel((0, 1)) == (0, 0, 0, 255)


def test_floyd_steinberg_preserves_alpha_and_ignores_hidden_rgb() -> None:
    image = Image.new("RGBA", (5, 2), (0, 255, 0, 0))
    image.putpixel((0, 0), (110, 110, 110, 255))
    image.putpixel((4, 0), (145, 145, 145, 128))
    result = quantize_to_palette(image, BLACK_WHITE, dither=True)

    assert result.getpixel((1, 0)) == (0, 0, 0, 0)
    assert result.getpixel((4, 0))[3] == 128
    assert all(
        pixel == (0, 0, 0, 0)
        for pixel in result.getdata()
        if pixel[3] == 0
    )


def test_floyd_steinberg_uses_palette_entries_beyond_pillow_256_limit() -> None:
    image = Image.new("RGBA", (1, 1), (255, 255, 255, 255))
    palette = [(0, 0, value, 255) for value in range(256)]
    palette.append((255, 255, 255, 255))

    result = quantize_to_palette(image, palette, dither=True)

    assert result.getpixel((0, 0)) == (255, 255, 255, 255)


def test_palette_panel_consolidates_status_dither_and_legacy_preferences() -> None:
    application = QApplication.instance() or QApplication([])
    panel = PalettePanel()

    assert panel.quantize_preview_button.isEnabled() is False
    assert panel.dither_quantized_checkbox.isEnabled() is False
    panel.apply_legacy_quantization_settings(
        {"max_colors": 64, "dither": True, "quantize_enabled": True}
    )
    assert panel.max_colors() == 64
    assert panel.dither_enabled() is True
    assert not hasattr(panel, "quantization_status_label")

    panel.set_palette(BLACK_WHITE)
    assert panel.quantize_preview_button.isEnabled() is True
    assert panel.dither_quantized_checkbox.isEnabled() is True
    panel.deleteLater()
    application.processEvents()


def test_palette_sampling_posterize_details_collapse_when_inactive() -> None:
    application = QApplication.instance() or QApplication([])
    panel = PalettePanel()

    assert panel.posterize_enabled_checkbox.text() == "Posterize palette sampling"
    assert panel.posterize_details.isHidden() is True
    assert panel.posterize_details_toggle.isEnabled() is False
    assert panel.extraction_settings().posterize_enabled is False

    panel.posterize_enabled_checkbox.setChecked(True)
    assert panel.posterize_details.isHidden() is False
    assert panel.posterize_details_toggle.isEnabled() is True
    assert panel.posterize_details_toggle.arrowType() == Qt.ArrowType.DownArrow
    assert panel.extraction_settings().posterize_enabled is True

    panel.posterize_details_toggle.setChecked(False)
    assert panel.posterize_details.isHidden() is True
    assert panel.extraction_settings().posterize_enabled is True

    panel.posterize_enabled_checkbox.setChecked(False)
    assert panel.posterize_details.isHidden() is True
    assert panel.posterize_details_toggle.isEnabled() is False

    panel.deleteLater()
    application.processEvents()


def test_palette_panel_compacts_advanced_options_and_actions() -> None:
    application = QApplication.instance() or QApplication([])
    panel = PalettePanel()

    assert panel.reduce_colors_enabled() is False
    assert panel.reduction_controls.isHidden() is True
    panel.reduce_colors_checkbox.setChecked(True)
    assert panel.reduction_controls.isHidden() is False
    assert panel.advanced_details.isHidden() is True
    assert panel.advanced_details_toggle.arrowType() == Qt.ArrowType.RightArrow
    panel.advanced_details_toggle.setChecked(True)
    assert panel.advanced_details.isHidden() is False
    assert panel.advanced_details_toggle.arrowType() == Qt.ArrowType.DownArrow

    assert panel.button_grid.count() == 6
    clear_index = panel.button_grid.indexOf(panel.clear_palette_button)
    clear_row, clear_column, _row_span, _column_span = panel.button_grid.getItemPosition(
        clear_index
    )
    assert (clear_row, clear_column) == (0, 2)

    panel.deleteLater()
    application.processEvents()


def test_explicit_preview_workflow_uses_one_active_palette_and_one_baseline() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    source = _gradient(16, 4)
    window.document.source_image = source.copy()
    window.document.selections = _full_selection(*source.size)
    window._refresh_preview()
    baseline = window.document.preview_image.tobytes()

    group_titles = [group.title() for group in window.findChildren(QGroupBox)]
    assert "Limit Colors" not in group_titles
    assert "Palette & Quantization" in group_titles

    window.palette_panel.reduce_colors_checkbox.setChecked(True)
    window.palette_panel.max_colors_spin.setValue(8)
    window.derive_palette_from_preview()
    assert window.document.palette
    assert window.document.preview_quantized is False
    assert window.document.preview_image.tobytes() == baseline

    # A loaded palette and a generated palette both become the same active list.
    window._set_active_palette(BLACK_WHITE)
    assert window.document.palette == BLACK_WHITE
    window.quantize_preview()
    first = window.document.preview_image.tobytes()
    assert window.document.preview_quantized is True
    window.quantize_preview()
    assert window.document.preview_image.tobytes() == first

    window.save_preview_to_tray()
    assert window.document.assets[-1].image.tobytes() == first

    window.clear_active_palette()
    assert window.document.palette == []
    assert window.document.preview_quantized is False
    assert window.document.preview_image.tobytes() == baseline
    window.quantize_preview()
    assert window.document.preview_quantized is False

    window.close()
    application.processEvents()


def test_apply_to_source_round_trips_through_main_undo_and_redo() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    original = _gradient(12, 3)
    window.document.source_image = original.copy()
    window.document.selections = _full_selection(*original.size)
    window._refresh_preview()
    window._set_active_palette(BLACK_WHITE)
    window.quantize_preview()
    expected = quantize_to_palette(original, BLACK_WHITE, dither=False)

    window.apply_palette_to_source()
    assert window.document.source_image.tobytes() == expected.tobytes()
    window.undo_source_change()
    assert window.document.source_image.tobytes() == original.tobytes()
    window.redo_source_change()
    assert window.document.source_image.tobytes() == expected.tobytes()

    window.close()
    application.processEvents()
