from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core.persistent_palette import (
    add_color_persistent,
    export_palette_json,
    import_palette_json,
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
    """Displays and manages the session-persistent palette stored to disk."""

    color_selected = Signal(tuple)
    palette_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette: list[Color] = load_persistent_palette()

        self._swatch_cols = 8
        self._swatch_container = QWidget()
        self._swatch_layout = QGridLayout(self._swatch_container)
        self._swatch_layout.setContentsMargins(0, 0, 0, 0)
        self._swatch_layout.setSpacing(2)

        self._clear_button = QPushButton("Clear All")
        self._import_button = QPushButton("Import JSON")
        self._export_button = QPushButton("Export JSON")

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._clear_button)
        btn_row.addWidget(self._import_button)
        btn_row.addWidget(self._export_button)
        btn_row.addStretch(1)

        self._summary = QLabel(self._summary_text())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._summary)
        layout.addWidget(self._swatch_container)
        layout.addLayout(btn_row)

        self._clear_button.clicked.connect(self._clear_all)
        self._import_button.clicked.connect(self._import_json)
        self._export_button.clicked.connect(self._export_json)

        self._rebuild_swatches()

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
        self._rebuild_swatches()
        self._summary.setText(self._summary_text())
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

    def _import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Palette JSON",
            "",
            "JSON Files (*.json)",
        )
        if not path:
            return
        try:
            incoming = import_palette_json(path)
        except Exception:
            return
        self._palette = merge_palettes(self._palette, incoming)
        self._save_and_refresh()

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
        export_palette_json(self._palette, path)

    def _summary_text(self) -> str:
        n = len(self._palette)
        return f"Persistent palette: {n} color{'s' if n != 1 else ''}"
