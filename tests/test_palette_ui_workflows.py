from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

from src.core.pixel_document import PixelDocument
from src.ui.main_window import MainWindow
from src.ui.persistent_palette_widget import PersistentPaletteWidget, _PaletteSwatch
from src.ui.pixel_editor_window import PixelEditorWindow


def _write_palette(path, colors: list[str]) -> None:
    path.write_text(json.dumps({"colors": colors}), encoding="utf-8")


def test_main_json_load_becomes_active_preview_palette(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "blacksmith.json"
    _write_palette(path, ["#101010", "#F09030", "#B0B0A0"])
    monkeypatch.setattr(
        "src.ui.main_window.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(path), "JSON Palettes (*.json)"),
    )
    window = MainWindow()

    window.load_palette()

    assert window.document.palette == [
        (16, 16, 16, 255),
        (240, 144, 48, 255),
        (176, 176, 160, 255),
    ]
    assert window.document.palette_name == "blacksmith.json"
    assert window.palette_panel.quantize_preview_button.isEnabled() is True
    assert "active preview palette" in window.statusBar().currentMessage()
    assert "Quantize Preview" in window.statusBar().currentMessage()

    window.close()
    application.processEvents()


def test_saved_palette_can_replace_active_preview_palette(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "src.core.persistent_palette._PALETTE_PATH",
        tmp_path / "saved-colors.json",
    )
    window = MainWindow()
    colors = [(10, 20, 30, 255), (40, 50, 60, 128)]
    for color in colors:
        window.persistent_palette.add_color(color)

    window.persistent_palette._use_for_preview()

    assert window.document.palette == colors
    assert window.document.palette_name == "saved colors"
    assert "active preview palette" in window.statusBar().currentMessage()
    assert window.persistent_palette._use_button.isEnabled() is True
    assert "across app restarts" in window.persistent_palette._description.text()

    window.close()
    application.processEvents()


def test_saved_palette_import_accepts_colors_json_instead_of_silent_no_op(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    saved_path = tmp_path / "saved-colors.json"
    import_path = tmp_path / "blacksmith.json"
    _write_palette(import_path, ["#101010", "#F09030"])
    monkeypatch.setattr("src.core.persistent_palette._PALETTE_PATH", saved_path)
    monkeypatch.setattr(
        "src.ui.persistent_palette_widget.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(import_path), "JSON Palettes (*.json)"),
    )
    widget = PersistentPaletteWidget()
    messages: list[str] = []
    widget.status_changed.connect(messages.append)

    widget._import_palette()

    assert widget.palette() == [(16, 16, 16, 255), (240, 144, 48, 255)]
    assert saved_path.is_file()
    assert messages and "2 new saved color(s)" in messages[-1]

    widget.deleteLater()
    application.processEvents()


def test_corrupt_persistent_palette_is_visible_and_recoverable(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    saved_path = tmp_path / "saved-colors.json"
    saved_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr("src.core.persistent_palette._PALETTE_PATH", saved_path)

    widget = PersistentPaletteWidget()

    assert widget.palette() == []
    assert "could not be loaded" in widget._description.text()
    widget.add_color((1, 2, 3, 255))
    assert widget.palette() == [(1, 2, 3, 255)]
    assert "across app restarts" in widget._description.text()

    widget.deleteLater()
    application.processEvents()


def test_saved_swatch_adds_color_and_invalidates_stale_quantized_preview(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "src.core.persistent_palette._PALETTE_PATH",
        tmp_path / "saved-colors.json",
    )
    window = MainWindow()
    baseline = Image.new("RGBA", (2, 1))
    baseline.putdata([(20, 20, 20, 255), (230, 230, 230, 255)])
    window.document.unquantized_preview_image = baseline.copy()
    window.document.preview_image = baseline.copy()
    window._set_active_palette([(0, 0, 0, 255), (255, 255, 255, 255)], "B/W")
    window.quantize_preview()
    assert window.document.preview_quantized is True

    saved_color = (220, 40, 30, 255)
    window.persistent_palette.add_color(saved_color)
    swatch = window.persistent_palette.findChildren(_PaletteSwatch)[0]
    swatch.click()
    application.processEvents()

    assert saved_color in window.document.palette
    assert window.document.preview_quantized is False
    assert window.document.preview_image.tobytes() == baseline.tobytes()
    assert window._selected_transparency_color == saved_color

    window.close()
    application.processEvents()


def test_eyedropper_add_does_not_silently_truncate_active_palette(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "src.core.persistent_palette._PALETTE_PATH",
        tmp_path / "saved-colors.json",
    )
    window = MainWindow()
    original = [(value, 10, 20, 255) for value in range(20)]
    window._set_active_palette(original, "twenty colors")
    assert window.palette_panel.max_colors() == 16
    assert window.palette_panel.reduce_colors_enabled() is False

    picked = (200, 210, 220, 255)
    window._on_eyedropper_color(picked)

    assert window.document.palette == [*original, picked]

    window.close()
    application.processEvents()


def test_pixel_editor_json_palette_replace_and_merge(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_palette(first, ["#010203", "#040506"])
    _write_palette(second, ["#040506", "#070809"])
    selected_paths = iter((first, second))
    monkeypatch.setattr(
        "src.ui.pixel_editor_window.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (
            str(next(selected_paths)),
            "JSON Palettes (*.json)",
        ),
    )
    window = PixelEditorWindow(
        PixelDocument(image=Image.new("RGBA", (2, 2))),
        headless=True,
    )

    window.load_palette()
    assert window.document.palette == [(1, 2, 3, 255), (4, 5, 6, 255)]
    window.add_palette_from_file()
    assert window.document.palette == [
        (1, 2, 3, 255),
        (4, 5, 6, 255),
        (7, 8, 9, 255),
    ]

    window.close()
    application.processEvents()
