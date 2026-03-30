from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PIL import Image

from src.core.extract_region import ExtractSettings
from src.core.qt_image import pil_image_to_qpixmap


class PreviewCanvas(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        tile = 16
        color_a = QColor("#252525")
        color_b = QColor("#313131")
        for y in range(0, self.height(), tile):
            for x in range(0, self.width(), tile):
                painter.fillRect(
                    x,
                    y,
                    tile,
                    tile,
                    color_a if (x // tile + y // tile) % 2 == 0 else color_b,
                )
        super().paintEvent(event)


class PreviewPanel(QWidget):
    settings_changed = Signal(object)
    save_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preview_image: Image.Image | None = None

        self.preview_canvas = PreviewCanvas()
        self.size_label = QLabel("Preview: no output")

        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 1024)
        self.width_spin.setValue(16)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 1024)
        self.height_spin.setValue(16)

        self.fit_combo = QComboBox()
        self.fit_combo.addItems(["Preserve", "Fit", "Actual"])
        self.fit_combo.setToolTip(
            "Preserve keeps the selected content inside the target tile.\n"
            "Fit scales the extracted content to fill the target tile.\n"
            "Actual keeps the source crop at its original pixel size with no resizing."
        )

        self.resample_combo = QComboBox()
        self.resample_combo.addItems(["Nearest", "Bilinear", "Bicubic"])

        self.save_button = QPushButton("Save Preview To Tray")
        self.save_button.clicked.connect(self.save_requested.emit)

        controls = QGroupBox("Output")
        controls_layout = QFormLayout(controls)
        controls_layout.addRow("Width", self.width_spin)
        controls_layout.addRow("Height", self.height_spin)
        controls_layout.addRow("Fit Mode", self.fit_combo)
        controls_layout.addRow("Sampling", self.resample_combo)

        button_row = QHBoxLayout()
        button_row.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview_canvas, 1)
        layout.addWidget(self.size_label)
        layout.addWidget(controls)
        layout.addLayout(button_row)
        layout.addStretch(1)

        self.width_spin.valueChanged.connect(self._emit_settings)
        self.height_spin.valueChanged.connect(self._emit_settings)
        self.fit_combo.currentIndexChanged.connect(self._emit_settings)
        self.resample_combo.currentIndexChanged.connect(self._emit_settings)

    def set_preview_image(self, image: Image.Image | None) -> None:
        self._preview_image = image
        if image is None:
            self.preview_canvas.clear()
            self.size_label.setText("Preview: no output")
            return

        pixmap = pil_image_to_qpixmap(image)
        scaled = pixmap.scaled(
            self.preview_canvas.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.preview_canvas.setPixmap(scaled)
        self.size_label.setText(f"Preview: {image.width} x {image.height}")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._preview_image is not None:
            self.set_preview_image(self._preview_image)

    def settings(self) -> ExtractSettings:
        return ExtractSettings(
            width=self.width_spin.value(),
            height=self.height_spin.value(),
            fit_mode=self.fit_combo.currentText(),
            resample_mode=self.resample_combo.currentText(),
        )

    def _emit_settings(self) -> None:
        self.settings_changed.emit(self.settings())
