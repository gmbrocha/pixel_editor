from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class PaletteSwatchStrip(QWidget):
    color_selected = Signal(int)        # index of clicked swatch
    color_remove_requested = Signal(int)
    color_edit_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette: list[tuple[int, int, int, int]] = []
        self._selected_index: int | None = None
        self.setMinimumHeight(48)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def set_palette(self, palette: list[tuple[int, int, int, int]]) -> None:
        self._palette = list(palette)
        if self._selected_index is not None and self._selected_index >= len(self._palette):
            self._selected_index = None
        self.update()

    def selected_index(self) -> int | None:
        return self._selected_index

    def clear_selection(self) -> None:
        self._selected_index = None
        self.update()

    def _swatch_at(self, x: int) -> int | None:
        if not self._palette:
            return None
        sw = max(18, self.width() // max(1, len(self._palette)))
        idx = x // sw
        return idx if 0 <= idx < len(self._palette) else None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._swatch_at(int(event.position().x()))
            if idx is not None:
                self._selected_index = idx
                self.update()
                self.color_selected.emit(idx)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._swatch_at(int(event.position().x()))
            if idx is not None:
                self._selected_index = idx
                self.update()
                self.color_edit_requested.emit(idx)
        super().mouseDoubleClickEvent(event)

    def _show_context_menu(self, pos) -> None:
        idx = self._swatch_at(pos.x())
        if idx is None:
            return
        self._selected_index = idx
        self.update()
        menu = QMenu(self)
        edit_action = menu.addAction("Edit Color…")
        remove_action = menu.addAction("Remove Color")
        action = menu.exec(self.mapToGlobal(pos))
        if action == edit_action:
            self.color_edit_requested.emit(idx)
        elif action == remove_action:
            self.color_remove_requested.emit(idx)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        if not self._palette:
            painter.setPen(QColor("#b5b5b5"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No palette loaded")
            return

        sw = max(18, self.width() // max(1, len(self._palette)))
        for index, color in enumerate(self._palette):
            x = index * sw
            painter.fillRect(x, 0, sw, self.height(), QColor(*color))
            if index == self._selected_index:
                pen = QPen(QColor("#ffffff"), 2)
                painter.setPen(pen)
                painter.drawRect(x + 1, 1, sw - 3, self.height() - 3)
            else:
                painter.setPen(QColor("#111111"))
                painter.drawRect(x, 0, sw, self.height() - 1)


class PalettePanel(QWidget):
    derive_from_preview_requested = Signal()
    load_palette_requested = Signal()
    export_palette_requested = Signal()
    apply_palette_to_preview_requested = Signal()
    apply_palette_to_source_requested = Signal()
    custom_color_requested = Signal()
    color_remove_requested = Signal(int)
    color_edit_requested = Signal(int)
    sort_palette_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.swatches = PaletteSwatchStrip()
        self.max_colors_spin = QSpinBox()
        self.max_colors_spin.setRange(2, 256)
        self.max_colors_spin.setValue(16)
        self.sample_mode_combo = QComboBox()
        self.sample_mode_combo.addItem("Balanced", "balanced")
        self.sample_mode_combo.addItem("Spread", "spread")
        self.sample_mode_combo.addItem("Most Frequent", "frequent")
        self.sample_mode_combo.setCurrentIndex(0)
        self.sample_mode_combo.setToolTip(
            "How to pick colors when the source has more distinct colors than Max Colors:\n"
            "  Balanced - hue-stratified: every hue family gets palette slots regardless of pixel count.\n"
            "  Spread - greedy farthest-point sampling in RGB (can be dominated by large hue families).\n"
            "  Most Frequent - the N most common colors (good for sampling photos)."
        )
        self.sort_mode_combo = QComboBox()
        self.sort_mode_combo.addItems(["Brightness", "Hue"])

        self.summary_label = QLabel("Palette colors: 0")
        self._selected_color_label = QLabel("")
        self._selected_color_label.setStyleSheet("color: #888; font-size: 11px;")

        derive_button = QPushButton("Palette From Preview")
        derive_button.clicked.connect(self.derive_from_preview_requested.emit)

        load_button = QPushButton("Load Palette")
        load_button.clicked.connect(self.load_palette_requested.emit)

        export_button = QPushButton("Export Palette")
        export_button.clicked.connect(self.export_palette_requested.emit)

        self._add_button = QPushButton("Add Color")
        self._add_button.clicked.connect(self.custom_color_requested.emit)

        self._remove_button = QPushButton("Remove")
        self._remove_button.setEnabled(False)
        self._remove_button.clicked.connect(self._emit_remove_selected)

        sort_button = QPushButton("Sort Palette")
        sort_button.clicked.connect(self._emit_sort_requested)

        apply_preview_button = QPushButton("Quantize Preview")
        apply_preview_button.clicked.connect(self.apply_palette_to_preview_requested.emit)

        apply_source_button = QPushButton("Apply To Source")
        apply_source_button.clicked.connect(self.apply_palette_to_source_requested.emit)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Max Colors"))
        top_row.addWidget(self.max_colors_spin)
        top_row.addSpacing(8)
        top_row.addWidget(QLabel("Sampling"))
        top_row.addWidget(self.sample_mode_combo)
        top_row.addStretch(1)

        info_row = QHBoxLayout()
        info_row.addWidget(self.summary_label)
        info_row.addStretch(1)
        info_row.addWidget(self._selected_color_label)

        button_grid = QGridLayout()
        button_grid.setContentsMargins(0, 0, 0, 0)
        button_grid.addWidget(derive_button, 0, 0)
        button_grid.addWidget(load_button, 0, 1)
        button_grid.addWidget(export_button, 1, 0)
        button_grid.addWidget(self._add_button, 1, 1)
        button_grid.addWidget(self._remove_button, 1, 2)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("Sort"))
        sort_row.addWidget(self.sort_mode_combo)
        sort_row.addWidget(sort_button)
        sort_row.addStretch(1)

        apply_row = QHBoxLayout()
        apply_row.addWidget(apply_preview_button)
        apply_row.addWidget(apply_source_button)
        apply_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.swatches)
        layout.addLayout(info_row)
        layout.addLayout(button_grid)
        layout.addLayout(sort_row)
        layout.addLayout(apply_row)

        self.swatches.color_selected.connect(self._on_swatch_selected)
        self.swatches.color_remove_requested.connect(self.color_remove_requested.emit)
        self.swatches.color_edit_requested.connect(self.color_edit_requested.emit)

    def max_colors(self) -> int:
        return self.max_colors_spin.value()

    def sample_mode(self) -> str:
        data = self.sample_mode_combo.currentData()
        return data if isinstance(data, str) else "balanced"

    def set_palette(self, palette: list[tuple[int, int, int, int]]) -> None:
        self.swatches.set_palette(palette)
        self.summary_label.setText(f"Palette colors: {len(palette)}")
        # Revalidate selection state after palette change
        self._on_swatch_selected(self.swatches.selected_index())

    def _on_swatch_selected(self, index: int | None) -> None:
        has_selection = index is not None
        self._remove_button.setEnabled(has_selection)
        if has_selection and index < len(self.swatches._palette):
            r, g, b, a = self.swatches._palette[index]
            self._selected_color_label.setText(f"#{r:02X}{g:02X}{b:02X}  α{a}")
        else:
            self._selected_color_label.setText("")

    def _emit_remove_selected(self) -> None:
        idx = self.swatches.selected_index()
        if idx is not None:
            self.color_remove_requested.emit(idx)

    def _emit_sort_requested(self) -> None:
        mode = "brightness" if self.sort_mode_combo.currentText() == "Brightness" else "hue"
        self.sort_palette_requested.emit(mode)
