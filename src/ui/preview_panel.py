from __future__ import annotations

import statistics

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
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
        self.resample_combo.addItem("Nearest Neighbor", "Nearest")
        self.resample_combo.addItem("Bilinear", "Bilinear")
        self.resample_combo.addItem("Bicubic", "Bicubic")
        self.resample_combo.addItem("Area (Box Average)", "Area (Box Average)")
        self.resample_combo.addItem("Lanczos 3", "Lanczos 3")
        self.resample_combo.setItemData(
            3,
            "Smooth, noise-reducing area-weighted sampling intended for downscaling.",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.resample_combo.setItemData(
            4,
            "Sharper high-quality resizing; extreme contrast transitions may show slight ringing.",
            Qt.ItemDataRole.ToolTipRole,
        )

        self.post_process_combo = QComboBox()
        self.post_process_combo.addItems(
            [
                "None",
                "Median Filter",
                "Posterize",
                "Small Gaussian Blur",
                "Edge-Preserving Denoise",
                "Despeckle",
            ]
        )
        self.post_process_combo.setItemData(
            self.post_process_combo.findText("Edge-Preserving Denoise"),
            "Mildly reduces low-contrast variation while retaining strong pixel boundaries.",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.post_process_combo.setItemData(
            self.post_process_combo.findText("Despeckle"),
            "Conservatively replaces small isolated color clusters with coherent surroundings.",
            Qt.ItemDataRole.ToolTipRole,
        )

        self.denoise_radius_spin = QSpinBox()
        self.denoise_radius_spin.setRange(1, 3)
        self.denoise_radius_spin.setValue(1)
        self.denoise_radius_spin.setSuffix(" px")
        self.denoise_strength_spin = QSpinBox()
        self.denoise_strength_spin.setRange(0, 100)
        self.denoise_strength_spin.setValue(35)
        self.denoise_strength_spin.setSuffix("%")

        self.despeckle_max_size_spin = QSpinBox()
        self.despeckle_max_size_spin.setRange(1, 8)
        self.despeckle_max_size_spin.setValue(1)
        self.despeckle_max_size_spin.setSuffix(" px")
        self.despeckle_tolerance_spin = QSpinBox()
        self.despeckle_tolerance_spin.setRange(0, 128)
        self.despeckle_tolerance_spin.setValue(24)
        self.despeckle_tolerance_spin.setToolTip(
            "Maximum RGBA distance used to group a speck or coherent surroundings"
        )
        self.reset_processing_button = QPushButton("Reset Processing")
        self.reset_processing_button.setToolTip(
            "Disable cleanup and restore its controls to their mild defaults"
        )

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
        self.process_controls_widget = QWidget()
        process_controls_layout = QGridLayout(self.process_controls_widget)
        process_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.denoise_radius_label = QLabel("Radius")
        self.denoise_strength_label = QLabel("Strength")
        self.despeckle_size_label = QLabel("Maximum speck size")
        self.despeckle_tolerance_label = QLabel("Color tolerance")
        process_controls_layout.addWidget(self.denoise_radius_label, 0, 0)
        process_controls_layout.addWidget(self.denoise_radius_spin, 0, 1)
        process_controls_layout.addWidget(self.denoise_strength_label, 0, 2)
        process_controls_layout.addWidget(self.denoise_strength_spin, 0, 3)
        process_controls_layout.addWidget(self.despeckle_size_label, 1, 0)
        process_controls_layout.addWidget(self.despeckle_max_size_spin, 1, 1)
        process_controls_layout.addWidget(self.despeckle_tolerance_label, 1, 2)
        process_controls_layout.addWidget(self.despeckle_tolerance_spin, 1, 3)
        process_controls_layout.addWidget(self.reset_processing_button, 2, 0, 1, 4)
        output_layout.addWidget(self.process_controls_widget)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(output_group, 1)

        self.preview_canvas.color_picked.connect(self.color_picked.emit)
        self.width_spin.valueChanged.connect(self._emit_settings)
        self.height_spin.valueChanged.connect(self._emit_settings)
        self.fit_combo.currentIndexChanged.connect(self._emit_settings)
        self.resample_combo.currentIndexChanged.connect(self._emit_settings)
        self.resample_combo.currentIndexChanged.connect(self._update_resample_tooltip)
        self.post_process_combo.currentIndexChanged.connect(self._on_process_changed)
        self.denoise_radius_spin.valueChanged.connect(self._emit_settings)
        self.denoise_strength_spin.valueChanged.connect(self._emit_settings)
        self.despeckle_max_size_spin.valueChanged.connect(self._emit_settings)
        self.despeckle_tolerance_spin.valueChanged.connect(self._emit_settings)
        self.reset_processing_button.clicked.connect(self._reset_processing)
        self._update_resample_tooltip()
        self._update_process_controls()

    def set_eyedropper(self, enabled: bool) -> None:
        self.preview_canvas.set_eyedropper(enabled)

    def set_eyedropper_sampling(self, sample_size: int, method: str) -> None:
        self.preview_canvas.set_eyedropper_sampling(sample_size, method)

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
        resample_mode = self.resample_combo.currentData()
        return ExtractSettings(
            width=self.width_spin.value(),
            height=self.height_spin.value(),
            fit_mode=self.fit_combo.currentText(),
            resample_mode=(
                resample_mode if isinstance(resample_mode, str) else "Nearest"
            ),
            post_process_mode=self.post_process_combo.currentText(),
            denoise_radius=self.denoise_radius_spin.value(),
            denoise_strength=self.denoise_strength_spin.value(),
            despeckle_max_size=self.despeckle_max_size_spin.value(),
            despeckle_tolerance=self.despeckle_tolerance_spin.value(),
        )

    def _emit_settings(self) -> None:
        self.settings_changed.emit(self.settings())

    def _on_process_changed(self) -> None:
        self._update_process_controls()
        self._emit_settings()

    def _update_process_controls(self) -> None:
        mode = self.post_process_combo.currentText()
        denoise = mode == "Edge-Preserving Denoise"
        despeckle_mode = mode == "Despeckle"
        for widget in (
            self.denoise_radius_label,
            self.denoise_radius_spin,
            self.denoise_strength_label,
            self.denoise_strength_spin,
        ):
            widget.setVisible(denoise)
        for widget in (
            self.despeckle_size_label,
            self.despeckle_max_size_spin,
            self.despeckle_tolerance_label,
            self.despeckle_tolerance_spin,
        ):
            widget.setVisible(despeckle_mode)
        self.reset_processing_button.setVisible(denoise or despeckle_mode)

    def _reset_processing(self) -> None:
        self.denoise_radius_spin.setValue(1)
        self.denoise_strength_spin.setValue(35)
        self.despeckle_max_size_spin.setValue(1)
        self.despeckle_tolerance_spin.setValue(24)
        self.post_process_combo.setCurrentText("None")
        self._update_process_controls()
        self._emit_settings()

    def _update_resample_tooltip(self) -> None:
        descriptions = {
            "Area (Box Average)": (
                "Smooth, noise-reducing area-weighted sampling intended for downscaling."
            ),
            "Lanczos 3": (
                "Sharper high-quality resizing; extreme contrast transitions may show slight ringing."
            ),
        }
        self.resample_combo.setToolTip(
            descriptions.get(self.resample_combo.currentText(), "Resize sampling method")
        )
