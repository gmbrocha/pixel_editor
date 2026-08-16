from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from src.core.palette import PaletteExtractionSettings


class PaletteSwatchStrip(QWidget):
    color_selected = Signal(int)        # index of clicked swatch
    color_remove_requested = Signal(int)
    color_edit_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active_palette_name: str | None = None
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
        if not self._palette or self.width() <= 0 or x < 0 or x >= self.width():
            return None
        return min(
            len(self._palette) - 1,
            ((x + 1) * len(self._palette) - 1) // self.width(),
        )

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

        count = len(self._palette)
        for index, color in enumerate(self._palette):
            left = index * self.width() // count
            right = (index + 1) * self.width() // count
            if right <= left:
                continue
            swatch_width = right - left
            painter.fillRect(left, 0, swatch_width, self.height(), QColor(*color))
            if index == self._selected_index:
                pen = QPen(QColor("#ffffff"), 2)
                painter.setPen(pen)
                painter.drawRect(
                    left + 1,
                    1,
                    max(0, swatch_width - 3),
                    self.height() - 3,
                )
            else:
                painter.setPen(QColor("#111111"))
                painter.drawRect(left, 0, max(0, swatch_width - 1), self.height() - 1)


class PalettePanel(QWidget):
    derive_from_preview_requested = Signal()
    load_palette_requested = Signal()
    export_palette_requested = Signal()
    apply_palette_to_preview_requested = Signal()
    apply_palette_to_source_requested = Signal()
    clear_palette_requested = Signal()
    clear_quantized_preview_requested = Signal()
    dither_changed = Signal(bool)
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

        self.min_cluster_percent_spin = QDoubleSpinBox()
        self.min_cluster_percent_spin.setRange(0.0, 10.0)
        self.min_cluster_percent_spin.setDecimals(3)
        self.min_cluster_percent_spin.setSingleStep(0.05)
        self.min_cluster_percent_spin.setValue(0.1)
        self.min_cluster_percent_spin.setSuffix("%")

        self.min_distance_spin = QDoubleSpinBox()
        self.min_distance_spin.setRange(0.0, 100.0)
        self.min_distance_spin.setDecimals(1)
        self.min_distance_spin.setSingleStep(1.0)
        self.min_distance_spin.setValue(10.0)

        self.neutral_saturation_spin = QDoubleSpinBox()
        self.neutral_saturation_spin.setRange(0.0, 1.0)
        self.neutral_saturation_spin.setDecimals(2)
        self.neutral_saturation_spin.setSingleStep(0.01)
        self.neutral_saturation_spin.setValue(0.15)

        self.max_family_spin = QSpinBox()
        self.max_family_spin.setRange(1, 256)
        self.max_family_spin.setValue(4)

        self.preserve_accents_checkbox = QCheckBox("Preserve accents")
        self.preserve_accents_checkbox.setChecked(True)
        self.cap_spread_checkbox = QCheckBox("Cap Spread")
        self.cap_spread_checkbox.setChecked(False)
        self.cap_frequent_checkbox = QCheckBox("Cap Frequent")
        self.cap_frequent_checkbox.setChecked(False)
        self.cap_balanced_checkbox = QCheckBox("Cap Balanced")
        self.cap_balanced_checkbox.setChecked(True)

        self.reduce_colors_checkbox = QCheckBox("Reduce colors")
        self.reduce_colors_checkbox.setChecked(False)
        self.reduce_colors_checkbox.setToolTip(
            "Off loads every distinct visible color. Enable to use palette-size and sampling options."
        )

        self.advanced_details_toggle = QToolButton()
        self.advanced_details_toggle.setText("Advanced extraction")
        self.advanced_details_toggle.setCheckable(True)
        self.advanced_details_toggle.setChecked(False)
        self.advanced_details_toggle.setAutoRaise(True)
        self.advanced_details_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.advanced_details_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_details_toggle.setToolTip(
            "Show cluster thresholds, family controls, and palette-sampling posterize"
        )

        self.posterize_enabled_checkbox = QCheckBox("Posterize palette sampling")
        self.posterize_enabled_checkbox.setChecked(False)
        self.posterize_enabled_checkbox.setToolTip(
            "Simplify colors only while generating a palette; this does not posterize the preview"
        )
        self.posterize_details_toggle = QToolButton()
        self.posterize_details_toggle.setText("Settings")
        self.posterize_details_toggle.setCheckable(True)
        self.posterize_details_toggle.setChecked(False)
        self.posterize_details_toggle.setEnabled(False)
        self.posterize_details_toggle.setAutoRaise(True)
        self.posterize_details_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.posterize_details_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.posterize_details_toggle.setToolTip(
            "Expand or collapse palette-sampling posterize settings"
        )

        self.posterize_preset_combo = QComboBox()
        self.posterize_preset_combo.addItem("Custom", "custom")
        self.posterize_preset_combo.addItem("Light Cleanup", "light")
        self.posterize_preset_combo.addItem("Medium Cleanup", "medium")
        self.posterize_preset_combo.addItem("Strong Cleanup", "strong")

        self.posterize_strength_spin = QDoubleSpinBox()
        self.posterize_strength_spin.setRange(0.0, 1.0)
        self.posterize_strength_spin.setDecimals(2)
        self.posterize_strength_spin.setSingleStep(0.05)
        self.posterize_strength_spin.setValue(0.35)

        self.posterize_rgb_levels_spin = QSpinBox()
        self.posterize_rgb_levels_spin.setRange(2, 256)
        self.posterize_rgb_levels_spin.setValue(12)

        self.posterize_lab_lightness_spin = QSpinBox()
        self.posterize_lab_lightness_spin.setRange(2, 100)
        self.posterize_lab_lightness_spin.setValue(10)

        self.posterize_chroma_spin = QSpinBox()
        self.posterize_chroma_spin.setRange(2, 128)
        self.posterize_chroma_spin.setValue(8)

        self.posterize_mode_combo = QComboBox()
        self.posterize_mode_combo.addItem("Perceptual", "perceptual")
        self.posterize_mode_combo.addItem("RGB Levels", "rgb_levels")
        self.posterize_mode_combo.addItem("LAB Lightness", "lab_lightness")

        self.sample_mode_combo = QComboBox()
        self.sample_mode_combo.addItem("Balanced", "balanced")
        self.sample_mode_combo.addItem("Most Frequent", "frequent")
        self.sample_mode_combo.addItem("Spread", "spread")
        self.sample_mode_combo.setCurrentIndex(0)
        self.sample_mode_combo.setToolTip(
            "How to pick colors when the source has more distinct colors than Max Colors:\n"
            "  Balanced - material-family quotas over perceptual clusters.\n"
            "  Spread - weighted farthest-point sampling in LAB.\n"
            "  Most Frequent - largest perceptual clusters with distance filtering."
        )
        self.sort_mode_combo = QComboBox()
        self.sort_mode_combo.addItems(["Brightness", "Hue"])

        self.summary_label = QLabel("Active palette: none")
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

        self.clear_palette_button = QPushButton("Clear Palette")
        self.clear_palette_button.setEnabled(False)
        self.clear_palette_button.clicked.connect(self.clear_palette_requested.emit)

        sort_button = QPushButton("Sort Palette")
        sort_button.clicked.connect(self._emit_sort_requested)

        self.dither_quantized_checkbox = QCheckBox("Dither Quantized Result")
        self.dither_quantized_checkbox.setChecked(False)
        self.dither_quantized_checkbox.setEnabled(False)
        self.dither_quantized_checkbox.setToolTip(
            "Use deterministic Floyd-Steinberg error diffusion when explicitly quantizing"
        )

        self.quantize_preview_button = QPushButton("Quantize Preview")
        self.quantize_preview_button.setEnabled(False)
        self.quantize_preview_button.setToolTip(
            "Generate or load an active palette before quantizing the preview"
        )
        self.quantize_preview_button.clicked.connect(
            self.apply_palette_to_preview_requested.emit
        )

        self.clear_quantized_preview_button = QPushButton("Clear Quantized Preview")
        self.clear_quantized_preview_button.setEnabled(False)
        self.clear_quantized_preview_button.clicked.connect(
            self.clear_quantized_preview_requested.emit
        )

        self.apply_source_button = QPushButton("Apply To Source")
        self.apply_source_button.setEnabled(False)
        self.apply_source_button.setToolTip(
            "Quantize Preview first, then commit the active palette to the source with undo history"
        )
        self.apply_source_button.clicked.connect(
            self.apply_palette_to_source_requested.emit
        )

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Palette Size"))
        top_row.addWidget(self.max_colors_spin)
        top_row.addSpacing(8)
        top_row.addWidget(QLabel("Sampling"))
        top_row.addWidget(self.sample_mode_combo)
        top_row.addStretch(1)

        cluster_row = QHBoxLayout()
        cluster_row.addWidget(QLabel("Min Cluster"))
        cluster_row.addWidget(self.min_cluster_percent_spin)
        cluster_row.addWidget(QLabel("Min LAB Distance"))
        cluster_row.addWidget(self.min_distance_spin)
        cluster_row.addStretch(1)

        family_row = QHBoxLayout()
        family_row.addWidget(QLabel("Neutral Sat"))
        family_row.addWidget(self.neutral_saturation_spin)
        family_row.addWidget(QLabel("Max / Family"))
        family_row.addWidget(self.max_family_spin)
        family_row.addWidget(self.preserve_accents_checkbox)
        family_row.addStretch(1)

        cap_row = QHBoxLayout()
        cap_row.addWidget(self.cap_spread_checkbox)
        cap_row.addWidget(self.cap_frequent_checkbox)
        cap_row.addWidget(self.cap_balanced_checkbox)
        cap_row.addStretch(1)

        self.posterize_section = QWidget()
        posterize_section_layout = QVBoxLayout(self.posterize_section)
        posterize_section_layout.setContentsMargins(0, 0, 0, 0)
        posterize_section_layout.setSpacing(2)

        posterize_header = QHBoxLayout()
        posterize_header.setContentsMargins(0, 0, 0, 0)
        posterize_header.addWidget(self.posterize_enabled_checkbox)
        posterize_header.addStretch(1)
        posterize_header.addWidget(self.posterize_details_toggle)
        posterize_section_layout.addLayout(posterize_header)

        self.posterize_details = QWidget()
        posterize_layout = QGridLayout(self.posterize_details)
        posterize_layout.setContentsMargins(18, 0, 0, 0)
        posterize_layout.setVerticalSpacing(3)
        posterize_layout.addWidget(QLabel("Preset"), 0, 0)
        posterize_layout.addWidget(self.posterize_preset_combo, 0, 1)
        posterize_layout.addWidget(QLabel("Mode"), 0, 2)
        posterize_layout.addWidget(self.posterize_mode_combo, 0, 3)
        posterize_layout.addWidget(QLabel("Strength"), 1, 0)
        posterize_layout.addWidget(self.posterize_strength_spin, 1, 1)
        posterize_layout.addWidget(QLabel("RGB"), 1, 2)
        posterize_layout.addWidget(self.posterize_rgb_levels_spin, 1, 3)
        posterize_layout.addWidget(QLabel("LAB L"), 2, 0)
        posterize_layout.addWidget(self.posterize_lab_lightness_spin, 2, 1)
        posterize_layout.addWidget(QLabel("Chroma"), 2, 2)
        posterize_layout.addWidget(self.posterize_chroma_spin, 2, 3)
        posterize_section_layout.addWidget(self.posterize_details)

        advanced_header = QHBoxLayout()
        advanced_header.setContentsMargins(0, 0, 0, 0)
        advanced_header.addWidget(self.advanced_details_toggle)
        advanced_header.addStretch(1)

        self.advanced_details = QWidget()
        advanced_layout = QVBoxLayout(self.advanced_details)
        advanced_layout.setContentsMargins(12, 0, 0, 0)
        advanced_layout.setSpacing(3)
        advanced_layout.addLayout(cluster_row)
        advanced_layout.addLayout(family_row)
        advanced_layout.addLayout(cap_row)
        advanced_layout.addWidget(self.posterize_section)

        self.reduction_controls = QWidget()
        reduction_layout = QVBoxLayout(self.reduction_controls)
        reduction_layout.setContentsMargins(12, 0, 0, 0)
        reduction_layout.setSpacing(3)
        reduction_layout.addLayout(top_row)
        reduction_layout.addLayout(advanced_header)
        reduction_layout.addWidget(self.advanced_details)

        info_row = QHBoxLayout()
        info_row.addWidget(self.summary_label)
        info_row.addStretch(1)
        info_row.addWidget(self._selected_color_label)

        self.button_grid = QGridLayout()
        self.button_grid.setContentsMargins(0, 0, 0, 0)
        self.button_grid.addWidget(derive_button, 0, 0)
        self.button_grid.addWidget(load_button, 0, 1)
        self.button_grid.addWidget(self.clear_palette_button, 0, 2)
        self.button_grid.addWidget(export_button, 1, 0)
        self.button_grid.addWidget(self._add_button, 1, 1)
        self.button_grid.addWidget(self._remove_button, 1, 2)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("Sort"))
        sort_row.addWidget(self.sort_mode_combo)
        sort_row.addWidget(sort_button)
        sort_row.addStretch(1)

        apply_row = QHBoxLayout()
        apply_row.addWidget(self.dither_quantized_checkbox)
        apply_row.addWidget(self.quantize_preview_button)
        apply_row.addWidget(self.clear_quantized_preview_button)
        apply_row.addWidget(self.apply_source_button)
        apply_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.reduce_colors_checkbox)
        layout.addWidget(self.reduction_controls)
        layout.addWidget(self.swatches)
        layout.addLayout(info_row)
        layout.addLayout(self.button_grid)
        layout.addLayout(sort_row)
        layout.addLayout(apply_row)

        self.swatches.color_selected.connect(self._on_swatch_selected)
        self.swatches.color_remove_requested.connect(self.color_remove_requested.emit)
        self.swatches.color_edit_requested.connect(self.color_edit_requested.emit)
        self.posterize_preset_combo.currentIndexChanged.connect(
            self._apply_posterize_preset
        )
        self.posterize_enabled_checkbox.toggled.connect(
            self._on_posterize_enabled_changed
        )
        self.posterize_details_toggle.toggled.connect(
            self._update_posterize_details_visibility
        )
        self.advanced_details_toggle.toggled.connect(
            self._update_advanced_details_visibility
        )
        self.reduce_colors_checkbox.toggled.connect(
            self._update_reduction_controls_visibility
        )
        self.dither_quantized_checkbox.toggled.connect(self.dither_changed.emit)
        self._update_posterize_details_visibility()
        self._update_advanced_details_visibility()
        self._update_reduction_controls_visibility()

    def max_colors(self) -> int:
        return self.max_colors_spin.value()

    def reduce_colors_enabled(self) -> bool:
        return self.reduce_colors_checkbox.isChecked()

    def sample_mode(self) -> str:
        data = self.sample_mode_combo.currentData()
        return data if isinstance(data, str) else "balanced"

    def extraction_settings(self) -> PaletteExtractionSettings:
        return PaletteExtractionSettings(
            palette_size=self.max_colors(),
            min_cluster_percent=self.min_cluster_percent_spin.value() / 100.0,
            min_perceptual_distance=self.min_distance_spin.value(),
            neutral_saturation_threshold=self.neutral_saturation_spin.value(),
            max_colors_per_family=self.max_family_spin.value(),
            preserve_accent_colors=self.preserve_accents_checkbox.isChecked(),
            apply_family_cap_to_spread=self.cap_spread_checkbox.isChecked(),
            apply_family_cap_to_most_frequent=self.cap_frequent_checkbox.isChecked(),
            apply_family_cap_to_balanced=self.cap_balanced_checkbox.isChecked(),
            posterize_enabled=self.posterize_enabled_checkbox.isChecked(),
            posterize_strength=self.posterize_strength_spin.value(),
            posterize_rgb_levels=self.posterize_rgb_levels_spin.value(),
            posterize_lab_lightness_levels=self.posterize_lab_lightness_spin.value(),
            posterize_chroma_levels=self.posterize_chroma_spin.value(),
            posterize_mode=self._combo_data(self.posterize_mode_combo, "perceptual"),
            posterize_source="sampling_source",
        )

    def _combo_data(self, combo: QComboBox, fallback: str) -> str:
        data = combo.currentData()
        return data if isinstance(data, str) else fallback

    def _set_combo_data(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _apply_posterize_preset(self, _index: int | None = None) -> None:
        preset = self.posterize_preset_combo.currentData()
        if preset == "light":
            self._set_posterize_controls(
                strength=0.20,
                rgb_levels=16,
                lightness_levels=14,
                chroma_levels=12,
            )
        elif preset == "medium":
            self._set_posterize_controls(
                strength=0.35,
                rgb_levels=12,
                lightness_levels=10,
                chroma_levels=8,
            )
        elif preset == "strong":
            self._set_posterize_controls(
                strength=0.85,
                rgb_levels=6,
                lightness_levels=6,
                chroma_levels=4,
            )

    def _on_posterize_enabled_changed(self, enabled: bool) -> None:
        self.posterize_details_toggle.setEnabled(enabled)
        self.posterize_details_toggle.setChecked(enabled)
        self._update_posterize_details_visibility()

    def _update_advanced_details_visibility(self, _expanded: bool | None = None) -> None:
        visible = self.advanced_details_toggle.isChecked()
        self.advanced_details.setVisible(visible)
        self.advanced_details_toggle.setArrowType(
            Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow
        )

    def _update_reduction_controls_visibility(self, _enabled: bool | None = None) -> None:
        self.reduction_controls.setVisible(self.reduce_colors_enabled())

    def _update_posterize_details_visibility(self, _expanded: bool | None = None) -> None:
        visible = (
            self.posterize_enabled_checkbox.isChecked()
            and self.posterize_details_toggle.isChecked()
        )
        self.posterize_details.setVisible(visible)
        self.posterize_details_toggle.setArrowType(
            Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow
        )

    def _set_posterize_controls(
        self,
        *,
        strength: float,
        rgb_levels: int,
        lightness_levels: int,
        chroma_levels: int,
    ) -> None:
        self.posterize_enabled_checkbox.setChecked(True)
        self.posterize_strength_spin.setValue(strength)
        self.posterize_rgb_levels_spin.setValue(rgb_levels)
        self.posterize_lab_lightness_spin.setValue(lightness_levels)
        self.posterize_chroma_spin.setValue(chroma_levels)
        self._set_combo_data(self.posterize_mode_combo, "perceptual")

    def set_palette(
        self,
        palette: list[tuple[int, int, int, int]],
        name: str | None = None,
    ) -> None:
        self.swatches.set_palette(palette)
        self._active_palette_name = name if palette else None
        has_palette = bool(palette)
        if has_palette:
            label = name or "custom"
            self.summary_label.setText(f"Active palette: {label} ({len(palette)} colors)")
        else:
            self.summary_label.setText("Active palette: none")
        self.clear_palette_button.setEnabled(has_palette)
        self.dither_quantized_checkbox.setEnabled(has_palette)
        self.quantize_preview_button.setEnabled(has_palette)
        self.quantize_preview_button.setToolTip(
            "Map the unquantized preview to the active palette exactly once"
            if has_palette
            else "Generate or load an active palette before quantizing the preview"
        )
        # Revalidate selection state after palette change
        self._on_swatch_selected(self.swatches.selected_index())

    def dither_enabled(self) -> bool:
        return self.dither_quantized_checkbox.isChecked()

    def set_quantization_state(self, quantized: bool) -> None:
        self.clear_quantized_preview_button.setEnabled(quantized)
        self.apply_source_button.setEnabled(quantized and bool(self.swatches._palette))

    def apply_legacy_quantization_settings(self, settings: dict[str, object]) -> None:
        """Migrate preferences without re-enabling legacy automatic quantization."""
        legacy_max = settings.get("max_colors")
        if isinstance(legacy_max, (int, float)):
            self.max_colors_spin.setValue(int(legacy_max))
        legacy_dither = settings.get("dither")
        if isinstance(legacy_dither, bool):
            self.dither_quantized_checkbox.setChecked(legacy_dither)

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
