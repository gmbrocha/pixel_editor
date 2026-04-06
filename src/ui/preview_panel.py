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
    color_picked = Signal(tuple)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pil_image: Image.Image | None = None
        self._eyedropper = False
        self.setMinimumSize(220, 220)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)

    def set_pil_image(self, image: Image.Image | None) -> None:
        self._pil_image = image

    def set_eyedropper(self, enabled: bool) -> None:
        self._eyedropper = enabled
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event) -> None:
        from PySide6.QtCore import Qt as _Qt
        if not self._eyedropper or self._pil_image is None or event.button() != _Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        pm = self.pixmap()
        if pm is None or pm.isNull():
            return
        label_w, label_h = self.width(), self.height()
        pm_w, pm_h = pm.width(), pm.height()
        ox = (label_w - pm_w) / 2
        oy = (label_h - pm_h) / 2
        mx = event.position().x() - ox
        my = event.position().y() - oy
        if mx < 0 or my < 0 or mx >= pm_w or my >= pm_h:
            return
        ix = int(mx / pm_w * self._pil_image.width)
        iy = int(my / pm_h * self._pil_image.height)
        ix = max(0, min(ix, self._pil_image.width - 1))
        iy = max(0, min(iy, self._pil_image.height - 1))
        rgba = self._pil_image.convert("RGBA").getpixel((ix, iy))
        self.color_picked.emit(tuple(rgba))

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
    color_picked = Signal(tuple)

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

        self.resample_combo = QComboBox()
        self.resample_combo.addItems(["Nearest", "Bilinear", "Bicubic"])

        self.save_button = QPushButton("Save Preview To Tray")
        self.save_button.clicked.connect(self.save_requested.emit)

        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)
        output_layout.addWidget(self.preview_canvas, 1)
        output_layout.addWidget(self.size_label)
        output_layout.addWidget(self.save_button)
        form = QFormLayout()
        form.addRow("Width", self.width_spin)
        form.addRow("Height", self.height_spin)
        form.addRow("Fit Mode", self.fit_combo)
        form.addRow("Sampling", self.resample_combo)
        output_layout.addLayout(form)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(output_group, 1)

        self.preview_canvas.color_picked.connect(self.color_picked.emit)
        self.width_spin.valueChanged.connect(self._emit_settings)
        self.height_spin.valueChanged.connect(self._emit_settings)
        self.fit_combo.currentIndexChanged.connect(self._emit_settings)
        self.resample_combo.currentIndexChanged.connect(self._emit_settings)

    def set_eyedropper(self, enabled: bool) -> None:
        self.preview_canvas.set_eyedropper(enabled)

    def set_preview_image(self, image: Image.Image | None) -> None:
        self._preview_image = image
        self.preview_canvas.set_pil_image(image)
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
