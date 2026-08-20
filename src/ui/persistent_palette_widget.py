from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.palette import PALETTE_SOURCE_FILTER, load_palette_from_source
from src.core.persistent_palette import (
    add_color_persistent,
    color_tooltip,
    export_palette_json,
    load_persistent_palette,
    merge_palettes,
    save_persistent_palette,
)

Color = tuple[int, int, int, int]


class _PaletteSwatch(QPushButton):
    """Single persistent-palette swatch. Left-click selects, right-click offers delete."""

    color_selected = Signal(tuple)
    remove_requested = Signal(tuple)

    def __init__(self, color: Color, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedSize(26, 26)
        self._apply_style()
        self.clicked.connect(self._emit_select)

    def _apply_style(self) -> None:
        if self._color[3] == 0:
            self.setText("T")
            self.setStyleSheet("background: #444; color: white; border: 1px solid #888; font-size: 10px;")
        else:
            self.setText("")
            r, g, b, a = self._color
            self.setStyleSheet(
                "background: rgba(%d, %d, %d, %d); border: 1px solid #222;" % (r, g, b, a)
            )

    def _emit_select(self) -> None:
        self.color_selected.emit(self._color)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        remove_action = menu.addAction("Delete color")
        action = menu.exec(event.globalPos())
        if action == remove_action:
            self.remove_requested.emit(self._color)


class PersistentPaletteWidget(QWidget):
    """Displays saved colors that persist across application sessions."""

    color_selected = Signal(tuple)
    palette_changed = Signal()
    use_for_preview_requested = Signal(object)
    status_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._load_error: str | None = None
        try:
            self._palette: list[Color] = load_persistent_palette()
        except (OSError, ValueError) as exc:
            self._palette = []
            self._load_error = str(exc)

        self._swatch_cols = 8
        self._swatch_container = QWidget()
        self._swatch_layout = QGridLayout(self._swatch_container)
        self._swatch_layout.setContentsMargins(0, 0, 0, 0)
        self._swatch_layout.setSpacing(2)

        self._clear_button = QPushButton("Clear All")
        self._import_button = QPushButton("Import Palette")
        self._export_button = QPushButton("Export JSON")
        self._use_button = QPushButton("Use for Preview")
        self._use_button.setToolTip(
            "Replace the active preview/quantization palette with all saved colors"
        )
        self._import_button.setToolTip(
            "Merge a JSON, text, JASC, GIMP, or image palette into saved colors"
        )
        self._export_button.setToolTip("Export saved colors as PixelForge JSON")

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._use_button)
        btn_row.addWidget(self._clear_button)
        btn_row.addWidget(self._import_button)
        btn_row.addWidget(self._export_button)
        btn_row.addStretch(1)

        self._summary = QLabel(self._summary_text())
        if self._load_error:
            self._description = QLabel(
                f"Saved-color file could not be loaded: {self._load_error}"
            )
            self._description.setStyleSheet("color: #C44; font-size: 11px;")
        else:
            self._description = QLabel(
                "Saved across app restarts; eyedropper picks are added here."
            )
            self._description.setStyleSheet("color: #888; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._summary)
        layout.addWidget(self._description)
        layout.addWidget(self._swatch_container)
        layout.addLayout(btn_row)

        self._clear_button.clicked.connect(self._clear_all)
        self._import_button.clicked.connect(self._import_palette)
        self._export_button.clicked.connect(self._export_json)
        self._use_button.clicked.connect(self._use_for_preview)

        self._rebuild_swatches()
        self._update_button_states()

    def palette(self) -> list[Color]:
        return list(self._palette)

    def add_color(self, color: Color) -> bool:
        """Add *color*. Returns True if it was new, False if duplicate."""
        if color in self._palette:
            return False
        self._palette = add_color_persistent(self._palette, color)
        self._save_and_refresh()
        return True

    def _save_and_refresh(self) -> None:
        save_persistent_palette(self._palette)
        self._load_error = None
        self._description.setText(
            "Saved across app restarts; eyedropper picks are added here."
        )
        self._description.setStyleSheet("color: #888; font-size: 11px;")
        self._rebuild_swatches()
        self._summary.setText(self._summary_text())
        self._update_button_states()
        self.palette_changed.emit()

    def _rebuild_swatches(self) -> None:
        while self._swatch_layout.count():
            item = self._swatch_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        if not self._palette:
            self._swatch_layout.addWidget(QLabel("No colors saved"), 0, 0)
            return

        for i, c in enumerate(self._palette):
            sw = _PaletteSwatch(c)
            sw.setToolTip(color_tooltip(c))
            sw.color_selected.connect(self.color_selected.emit)
            sw.remove_requested.connect(self._remove_color)
            row = i // self._swatch_cols
            col = i % self._swatch_cols
            self._swatch_layout.addWidget(sw, row, col)

    def _remove_color(self, color: Color) -> None:
        if color in self._palette:
            self._palette.remove(color)
            self._save_and_refresh()

    def _clear_all(self) -> None:
        self._palette.clear()
        self._save_and_refresh()

    def _import_palette(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Saved Palette",
            "",
            PALETTE_SOURCE_FILTER,
        )
        if not path:
            return
        try:
            incoming = load_palette_from_source(path, max_colors=None)
        except Exception as exc:  # pragma: no cover - GUI feedback
            QMessageBox.critical(self, "Palette import failed", str(exc))
            return
        previous_count = len(self._palette)
        self._palette = merge_palettes(self._palette, incoming)
        self._save_and_refresh()
        added = len(self._palette) - previous_count
        self.status_changed.emit(
            f"Imported {len(incoming)} palette colors; {added} new saved color(s)"
        )

    def _export_json(self) -> None:
        if not self._palette:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Palette JSON",
            "palette.json",
            "JSON Files (*.json)",
        )
        if not path:
            return
        destination = Path(path)
        if not destination.suffix:
            destination = destination.with_suffix(".json")
        try:
            export_palette_json(self._palette, destination)
        except Exception as exc:  # pragma: no cover - GUI feedback
            QMessageBox.critical(self, "Palette export failed", str(exc))
            return
        self.status_changed.emit(f"Exported saved colors to {destination}")

    def _use_for_preview(self) -> None:
        if self._palette:
            self.use_for_preview_requested.emit(list(self._palette))

    def _update_button_states(self) -> None:
        has_palette = bool(self._palette)
        self._use_button.setEnabled(has_palette)
        self._clear_button.setEnabled(has_palette)
        self._export_button.setEnabled(has_palette)

    def _summary_text(self) -> str:
        n = len(self._palette)
        return f"Saved colors: {n} color{'s' if n != 1 else ''} (persistent)"
