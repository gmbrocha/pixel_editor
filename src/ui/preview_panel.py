from __future__ import annotations

import statistics

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
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
        self._eyedropper_sample_size = 1
        self._eyedropper_sample_method = "median"
        self.setMinimumSize(220, 220)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)

    def set_pil_image(self, image: Image.Image | None) -> None:
        self._pil_image = image

    def set_eyedropper(self, enabled: bool) -> None:
        self._eyedropper = enabled
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)

    def set_eyedropper_sampling(self, sample_size: int, method: str) -> None:
        self._eyedropper_sample_size = max(1, int(sample_size))
        self._eyedropper_sample_method = method if method in {"average", "median"} else "median"

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
        rgba = self._sample_eyedropper_color(ix, iy)
        self.color_picked.emit(tuple(rgba))

    def _sample_eyedropper_color(self, px: int, py: int) -> tuple[int, int, int, int]:
        if self._pil_image is None:
            return (0, 0, 0, 0)
        image = self._pil_image.convert("RGBA")
        half = self._eyedropper_sample_size // 2
        left = max(0, px - half)
        top = max(0, py - half)
        right = min(image.width, px + half + 1)
        bottom = min(image.height, py + half + 1)
        pixels = list(image.crop((left, top, right, bottom)).getdata())
        if not pixels:
            return tuple(image.getpixel((px, py)))
        if self._eyedropper_sample_method == "average":
            return tuple(int(round(sum(pixel[i] for pixel in pixels) / len(pixels))) for i in range(4))
        return tuple(int(statistics.median(pixel[i] for pixel in pixels)) for i in range(4))

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
    load_reference_palette_requested = Signal()
    clear_reference_palette_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preview_image: Image.Image | None = None
        self._reference_palette: tuple[tuple[int, int, int, int], ...] = ()
        self._reference_palette_name: str | None = None

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

        self.post_process_combo = QComboBox()
        self.post_process_combo.addItems(
            ["None", "Median Filter", "Posterize", "Small Gaussian Blur"]
        )

        self.max_colors_slider = QSlider(Qt.Orientation.Horizontal)
        self.max_colors_slider.setRange(0, 3)
        self.max_colors_slider.setValue(2)
        self.max_colors_value_label = QLabel(str(self.max_colors()))

        self.quantize_checkbox = QCheckBox("Enable palette reduction")
        self.quantize_checkbox.setChecked(False)

        self.dither_checkbox = QCheckBox("Dither output")
        self.dither_checkbox.setChecked(False)

        self.reference_palette_label = QLabel("Reference palette: none")
        self.reference_palette_label.setWordWrap(True)

        self.load_reference_palette_button = QPushButton("Load Ref Palette")
        self.clear_reference_palette_button = QPushButton("Clear Ref")

        self.save_button = QPushButton("Save Output To Tray")
        self.save_button.clicked.connect(self.save_requested.emit)

        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)
        output_layout.addWidget(self.preview_canvas, 1)
        output_layout.addWidget(self.size_label)
        output_layout.addWidget(self.save_button)
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("W"))
        size_row.addWidget(self.width_spin)
        size_row.addWidget(QLabel("H"))
        size_row.addWidget(self.height_spin)
        size_row.addWidget(self.fit_combo)
        size_row.addWidget(self.resample_combo)
        output_layout.addLayout(size_row)
        process_row = QHBoxLayout()
        process_row.addWidget(QLabel("Process"))
        process_row.addWidget(self.post_process_combo, 1)
        output_layout.addLayout(process_row)

        quant_group = QGroupBox("Palette Reduction")
        quant_layout = QVBoxLayout(quant_group)
        quant_layout.addWidget(self.quantize_checkbox)
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Max colors"))
        color_row.addWidget(self.max_colors_slider, 1)
        color_row.addWidget(self.max_colors_value_label)
        quant_layout.addLayout(color_row)
        quant_layout.addWidget(self.dither_checkbox)
        quant_layout.addWidget(self.reference_palette_label)
        ref_button_row = QHBoxLayout()
        ref_button_row.addWidget(self.load_reference_palette_button)
        ref_button_row.addWidget(self.clear_reference_palette_button)
        quant_layout.addLayout(ref_button_row)
        quant_layout.addWidget(QLabel("Dithering/reduction only apply when sampling is Nearest"))
        output_layout.addWidget(quant_group)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(output_group, 1)

        self.preview_canvas.color_picked.connect(self.color_picked.emit)
        self.width_spin.valueChanged.connect(self._emit_settings)
        self.height_spin.valueChanged.connect(self._emit_settings)
        self.fit_combo.currentIndexChanged.connect(self._emit_settings)
        self.resample_combo.currentIndexChanged.connect(self._emit_settings)
        self.post_process_combo.currentIndexChanged.connect(self._emit_settings)
        self.max_colors_slider.valueChanged.connect(self._on_max_colors_changed)
        self.dither_checkbox.toggled.connect(self._emit_settings)
        self.quantize_checkbox.toggled.connect(self._emit_settings)
        self.load_reference_palette_button.clicked.connect(self.load_reference_palette_requested.emit)
        self.clear_reference_palette_button.clicked.connect(self.clear_reference_palette_requested.emit)

    def set_eyedropper(self, enabled: bool) -> None:
        self.preview_canvas.set_eyedropper(enabled)

    def set_eyedropper_sampling(self, sample_size: int, method: str) -> None:
        self.preview_canvas.set_eyedropper_sampling(sample_size, method)

    def set_reference_palette(
        self,
        palette: list[tuple[int, int, int, int]] | tuple[tuple[int, int, int, int], ...],
        name: str | None = None,
    ) -> None:
        self._reference_palette = tuple(palette)
        self._reference_palette_name = name
        if self._reference_palette:
            label = name or "custom"
            self.reference_palette_label.setText(
                f"Reference palette: {label} ({len(self._reference_palette)} colors)"
            )
        else:
            self.reference_palette_label.setText("Reference palette: none")
        self._emit_settings()

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
            post_process_mode=self.post_process_combo.currentText(),
            max_colors=self.max_colors(),
            dither=self.dither_checkbox.isChecked(),
            quantize_enabled=self.quantize_checkbox.isChecked(),
            reference_palette=self._reference_palette,
        )

    def _emit_settings(self) -> None:
        self.settings_changed.emit(self.settings())

    def max_colors(self) -> int:
        return [8, 16, 32, 64][self.max_colors_slider.value()]

    def _on_max_colors_changed(self) -> None:
        self.max_colors_value_label.setText(str(self.max_colors()))
        self._emit_settings()
