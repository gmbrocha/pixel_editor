from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class PaletteSwatchStrip(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette: list[tuple[int, int, int, int]] = []
        self.setMinimumHeight(48)

    def set_palette(self, palette: list[tuple[int, int, int, int]]) -> None:
        self._palette = list(palette)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        if not self._palette:
            painter.setPen(QColor("#b5b5b5"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No palette loaded")
            return

        swatch_width = max(18, self.width() // max(1, len(self._palette)))
        for index, color in enumerate(self._palette):
            x = index * swatch_width
            painter.fillRect(x, 0, swatch_width, self.height(), QColor(*color))
            painter.setPen(QColor("#111111"))
            painter.drawRect(x, 0, swatch_width, self.height() - 1)


class PalettePanel(QWidget):
    derive_from_preview_requested = Signal()
    load_palette_requested = Signal()
    export_palette_requested = Signal()
    apply_palette_to_preview_requested = Signal()
    apply_palette_to_source_requested = Signal()
    custom_color_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.swatches = PaletteSwatchStrip()
        self.max_colors_spin = QSpinBox()
        self.max_colors_spin.setRange(2, 256)
        self.max_colors_spin.setValue(16)

        self.summary_label = QLabel("Palette colors: 0")

        derive_button = QPushButton("Palette From Preview")
        derive_button.clicked.connect(self.derive_from_preview_requested.emit)

        load_button = QPushButton("Load Palette")
        load_button.clicked.connect(self.load_palette_requested.emit)

        export_button = QPushButton("Export Palette")
        export_button.clicked.connect(self.export_palette_requested.emit)

        custom_color_button = QPushButton("Add Custom Color")
        custom_color_button.clicked.connect(self.custom_color_requested.emit)

        apply_preview_button = QPushButton("Quantize Preview")
        apply_preview_button.clicked.connect(self.apply_palette_to_preview_requested.emit)

        apply_source_button = QPushButton("Apply To Source")
        apply_source_button.clicked.connect(self.apply_palette_to_source_requested.emit)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Max Colors"))
        top_row.addWidget(self.max_colors_spin)
        top_row.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addWidget(derive_button)
        button_row.addWidget(load_button)
        button_row.addWidget(export_button)
        button_row.addWidget(custom_color_button)

        apply_row = QHBoxLayout()
        apply_row.addWidget(apply_preview_button)
        apply_row.addWidget(apply_source_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.swatches)
        layout.addWidget(self.summary_label)
        layout.addLayout(button_row)
        layout.addLayout(apply_row)

    def max_colors(self) -> int:
        return self.max_colors_spin.value()

    def set_palette(self, palette: list[tuple[int, int, int, int]]) -> None:
        self.swatches.set_palette(palette)
        self.summary_label.setText(f"Palette colors: {len(palette)}")
