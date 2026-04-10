from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.core.image_io import load_image, save_image
from src.core.palette import (
    add_color_to_palette,
    export_palette_strip,
    load_palette_from_image,
    palette_from_image,
)
from src.core.persistent_palette import merge_palettes
from src.core.shade_ramp import shade_ramp
from src.core.pixel_document import (
    PixelDocument,
    darken_image,
    flip_image_horizontal,
    flip_image_vertical,
    lighten_image,
    normalize_to_black_white,
    push_image_history,
    replace_color,
    replace_color_with_transparent,
    rotate_image_clockwise,
    rotate_image_counterclockwise,
    undo_image_history,
)
from src.ui.pixel_grid_canvas import PixelGridCanvas


class ClickableColorButton(QPushButton):
    clicked_color = Signal(tuple)

    def __init__(self, color: tuple[int, int, int, int], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedSize(24, 24)
        self._apply_style()
        self.clicked.connect(self._emit_color)

    def _emit_color(self) -> None:
        self.clicked_color.emit(self._color)

    def _apply_style(self) -> None:
        if self._color[3] == 0:
            self.setText("T")
            self.setStyleSheet("background: #444; color: white; border: 1px solid #888;")
        else:
            self.setText("")
            self.setStyleSheet(
                "background: rgba(%d, %d, %d, %d); border: 1px solid #111;"
                % self._color
            )


class PixelEditorWindow(QMainWindow):
    asset_save_requested = Signal(str, object)

    def __init__(self, document: PixelDocument, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = document
        self.setWindowTitle(f"PixelForge - {document.name}")
        self.resize(1100, 820)

        self.canvas = PixelGridCanvas()
        self.canvas.set_document(self.document)

        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(4, 64)
        self.zoom_spin.setValue(20)

        self.color_preview = QLabel()
        self.color_preview.setFixedSize(40, 40)
        self.color_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 255)
        self.opacity_slider.setValue(self.document.current_color[3])
        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(0, 255)
        self.opacity_spin.setValue(self.document.current_color[3])

        self.selection_summary = QLabel("No selection")
        self.palette_container = QWidget()
        self.palette_layout = QGridLayout(self.palette_container)
        self.palette_layout.setContentsMargins(0, 0, 0, 0)
        self.palette_layout.setSpacing(2)
        self._palette_cols = 8
        self._transparent_replace_target: tuple[int, int, int, int] | None = None
        self._replace_with_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self.transparent_replace_preview = QLabel("No replace target")
        self.transparent_replace_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.transparent_replace_preview.setMinimumHeight(28)
        self.replace_with_preview = QLabel()
        self.replace_with_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.replace_with_preview.setMinimumHeight(28)
        self.pick_replace_target_button = QPushButton("Pick Target Color")
        self.transparent_replace_button = QPushButton("Replace Target -> Transparent")
        self.replace_with_color_button = QPushButton("Replace Target -> Selected Color")
        self.replace_with_button = QPushButton("Pick Replace With Color")
        self.transparent_replace_clear_button = QPushButton("Clear")

        self.paint_radio = QRadioButton("Paint")
        self.select_radio = QRadioButton("Select")
        self.stamp_radio = QRadioButton("Stamp")
        self.paint_radio.setChecked(True)
        self.copy_stamp_button = QPushButton("Copy Selection as Stamp")

        self.transparent_button = QPushButton("Use Transparent")
        self.custom_color_button = QPushButton("Pick Color")
        self.ref_underlay_button = QPushButton("Import Sprite to Grid")
        self.ref_clear_button = QPushButton("Clear Reference")
        self.ref_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.ref_opacity_slider.setRange(10, 100)
        self.ref_opacity_slider.setValue(50)
        self.transparent_display_button = QPushButton("Transparent Color: Checker")
        self.transparent_display_button.setToolTip("Click to pick a solid color for transparent pixels.\nRight-click to reset to checkerboard.")
        self.transparent_display_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.transparent_display_button.customContextMenuRequested.connect(
            lambda _pos: self._reset_transparent_display()
        )
        self.load_image_button = QPushButton("Open Image")
        self.load_palette_button = QPushButton("Load Palette (replace)")
        self.add_palette_from_file_button = QPushButton("Add to Palette from File")
        self.palette_from_current_button = QPushButton("Palette From Current (replace)")
        self.add_palette_from_current_button = QPushButton("Add to Palette from Current")
        self.export_palette_button = QPushButton("Export Palette")
        self.flip_horizontal_button = QPushButton("Flip Horizontal")
        self.flip_vertical_button = QPushButton("Flip Vertical")
        self.rotate_clockwise_button = QPushButton("Rotate 90 CW")
        self.rotate_counterclockwise_button = QPushButton("Rotate 90 CCW")
        self.darken_spin = QSpinBox()
        self.darken_spin.setRange(1, 100)
        self.darken_spin.setValue(30)
        self.darken_spin.setSuffix("%")
        self.darken_button = QPushButton("Darken Image")
        self.lighten_button = QPushButton("Lighten Image")
        self.normalize_threshold_spin = QSpinBox()
        self.normalize_threshold_spin.setRange(0, 255)
        self.normalize_threshold_spin.setValue(48)
        self.normalize_button = QPushButton("Normalize to B/W")
        self.undo_tone_button = QPushButton("Undo Tone")
        self.save_image_button = QPushButton("Save Image")
        self.save_asset_button = QPushButton("Save To Asset Tray")

        self.resize_w_spin = QSpinBox()
        self.resize_w_spin.setRange(1, 1024)
        self.resize_h_spin = QSpinBox()
        self.resize_h_spin.setRange(1, 1024)
        self.resize_anchor_combo = None  # created in _build_layout
        self.resize_canvas_button = QPushButton("Resize Canvas")

        self.shade_ramp_button = QPushButton("Generate Shade Ramp")
        self.shade_ramp_container = QWidget()
        self.shade_ramp_layout = QHBoxLayout(self.shade_ramp_container)
        self.shade_ramp_layout.setContentsMargins(0, 0, 0, 0)
        self.shade_ramp_layout.setSpacing(4)
        self.shade_add_all_button = QPushButton("Add Ramp to Palette")
        self.shade_add_all_button.setEnabled(False)
        self._current_ramp: list[tuple[str, tuple[int, int, int, int]]] = []

        self._build_toolbar()
        self._build_layout()
        self._connect_signals()
        self._refresh_palette_buttons()
        self._update_color_preview()
        self.statusBar().showMessage("Paint pixels or switch to selection mode")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Pixel Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        open_action = QAction("Open Image", self)
        open_action.triggered.connect(self.open_image)
        toolbar.addAction(open_action)

        save_action = QAction("Save Image", self)
        save_action.triggered.connect(self.save_image)
        toolbar.addAction(save_action)

        flip_h_action = QAction("Flip Horizontal", self)
        flip_h_action.triggered.connect(self.flip_horizontal)
        toolbar.addAction(flip_h_action)

        flip_v_action = QAction("Flip Vertical", self)
        flip_v_action.triggered.connect(self.flip_vertical)
        toolbar.addAction(flip_v_action)

        rotate_cw_action = QAction("Rotate 90 CW", self)
        rotate_cw_action.triggered.connect(self.rotate_clockwise)
        toolbar.addAction(rotate_cw_action)

        rotate_ccw_action = QAction("Rotate 90 CCW", self)
        rotate_ccw_action.triggered.connect(self.rotate_counterclockwise)
        toolbar.addAction(rotate_ccw_action)

        darken_action = QAction("Darken Image", self)
        darken_action.triggered.connect(self.darken_current_image)
        toolbar.addAction(darken_action)

        lighten_action = QAction("Lighten Image", self)
        lighten_action.triggered.connect(self.lighten_current_image)
        toolbar.addAction(lighten_action)

        normalize_action = QAction("Normalize to B/W", self)
        normalize_action.triggered.connect(self.normalize_current_image)
        toolbar.addAction(normalize_action)

        undo_tone_action = QAction("Undo Tone", self)
        undo_tone_action.triggered.connect(self.undo_tone_adjustment)
        toolbar.addAction(undo_tone_action)

        toolbar.addSeparator()
        self._mirror_action = QAction("Mirror", self)
        self._mirror_action.setCheckable(True)
        self._mirror_action.toggled.connect(self.canvas.set_mirror)
        toolbar.addAction(self._mirror_action)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Zoom"))
        toolbar.addWidget(self.zoom_spin)

    def _build_layout(self) -> None:
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.paint_radio)
        mode_group.addButton(self.select_radio)
        mode_group.addButton(self.stamp_radio)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self.paint_radio)
        mode_row.addWidget(self.select_radio)
        mode_row.addWidget(self.stamp_radio)
        mode_row.addWidget(self.copy_stamp_button)
        mode_row.addStretch(1)

        controls_layout = QVBoxLayout()
        controls_layout.addLayout(mode_row)
        controls_layout.addWidget(QLabel("Current Color"))
        controls_layout.addWidget(self.color_preview)
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity"))
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_spin)
        controls_layout.addLayout(opacity_row)
        controls_layout.addWidget(self.custom_color_button)
        controls_layout.addWidget(self.transparent_button)
        controls_layout.addWidget(self.transparent_display_button)
        controls_layout.addSpacing(8)
        controls_layout.addWidget(QLabel("Reference Underlay"))
        controls_layout.addWidget(self.ref_underlay_button)
        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("Ref opacity"))
        ref_row.addWidget(self.ref_opacity_slider)
        ref_row.addWidget(self.ref_clear_button)
        controls_layout.addLayout(ref_row)
        controls_layout.addSpacing(12)
        controls_layout.addWidget(QLabel("Palette"))
        controls_layout.addWidget(self.palette_container)
        controls_layout.addWidget(self.load_palette_button)
        controls_layout.addWidget(self.add_palette_from_file_button)
        controls_layout.addWidget(self.palette_from_current_button)
        controls_layout.addWidget(self.add_palette_from_current_button)
        controls_layout.addWidget(self.export_palette_button)
        controls_layout.addSpacing(8)
        controls_layout.addWidget(QLabel("Replace Target"))
        controls_layout.addWidget(self.transparent_replace_preview)
        controls_layout.addWidget(self.pick_replace_target_button)
        controls_layout.addWidget(QLabel("Replace With"))
        controls_layout.addWidget(self.replace_with_preview)
        replace_row = QHBoxLayout()
        replace_row.addWidget(self.transparent_replace_button)
        replace_row.addWidget(self.replace_with_color_button)
        replace_row.addWidget(self.replace_with_button)
        replace_row.addWidget(self.transparent_replace_clear_button)
        controls_layout.addLayout(replace_row)
        controls_layout.addSpacing(8)
        controls_layout.addWidget(QLabel("Shade Ramp"))
        controls_layout.addWidget(self.shade_ramp_button)
        controls_layout.addWidget(self.shade_ramp_container)
        controls_layout.addWidget(self.shade_add_all_button)
        controls_layout.addSpacing(8)
        controls_layout.addWidget(self.flip_horizontal_button)
        controls_layout.addWidget(self.flip_vertical_button)
        controls_layout.addWidget(self.rotate_clockwise_button)
        controls_layout.addWidget(self.rotate_counterclockwise_button)
        darken_row = QHBoxLayout()
        darken_row.addWidget(QLabel("Darken"))
        darken_row.addWidget(self.darken_spin)
        controls_layout.addLayout(darken_row)
        controls_layout.addWidget(self.darken_button)
        controls_layout.addWidget(self.lighten_button)
        normalize_row = QHBoxLayout()
        normalize_row.addWidget(QLabel("Black cutoff"))
        normalize_row.addWidget(self.normalize_threshold_spin)
        controls_layout.addLayout(normalize_row)
        controls_layout.addWidget(self.normalize_button)
        controls_layout.addWidget(self.undo_tone_button)
        controls_layout.addSpacing(12)
        controls_layout.addWidget(self.selection_summary)
        controls_layout.addSpacing(12)
        controls_layout.addWidget(QLabel("Resize Canvas"))
        resize_row = QHBoxLayout()
        resize_row.addWidget(QLabel("W"))
        self.resize_w_spin.setValue(self.document.image.width)
        resize_row.addWidget(self.resize_w_spin)
        resize_row.addWidget(QLabel("H"))
        self.resize_h_spin.setValue(self.document.image.height)
        resize_row.addWidget(self.resize_h_spin)
        controls_layout.addLayout(resize_row)
        anchor_row = QHBoxLayout()
        anchor_row.addWidget(QLabel("Anchor"))
        self.resize_anchor_combo = QComboBox()
        self.resize_anchor_combo.addItems([
            "Top-Left", "Top-Center", "Top-Right",
            "Center-Left", "Center", "Center-Right",
            "Bottom-Left", "Bottom-Center", "Bottom-Right",
        ])
        self.resize_anchor_combo.setCurrentIndex(0)
        anchor_row.addWidget(self.resize_anchor_combo)
        controls_layout.addLayout(anchor_row)
        crop_row = QHBoxLayout()
        crop_row.addWidget(self.resize_canvas_button)
        self.trim_transparent_button = QPushButton("Trim Transparent")
        crop_row.addWidget(self.trim_transparent_button)
        controls_layout.addLayout(crop_row)
        controls_layout.addSpacing(12)
        controls_layout.addWidget(self.load_image_button)
        controls_layout.addWidget(self.save_image_button)
        controls_layout.addWidget(self.save_asset_button)
        controls_layout.addStretch(1)

        controls_panel = QWidget()
        controls_panel.setLayout(controls_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.canvas)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(scroll, 1)
        layout.addWidget(controls_panel)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.zoom_spin.valueChanged.connect(self.canvas.set_zoom)
        self.paint_radio.toggled.connect(self._on_mode_changed)
        self.select_radio.toggled.connect(self._on_mode_changed)
        self.stamp_radio.toggled.connect(self._on_mode_changed)
        self.copy_stamp_button.clicked.connect(self._copy_as_stamp)
        self.ref_underlay_button.clicked.connect(self._import_reference_underlay)
        self.ref_clear_button.clicked.connect(self._clear_reference_underlay)
        self.ref_opacity_slider.valueChanged.connect(
            lambda v: self.canvas.set_reference_opacity(v / 100.0)
        )
        self.opacity_slider.valueChanged.connect(self.opacity_spin.setValue)
        self.opacity_spin.valueChanged.connect(self.opacity_slider.setValue)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.custom_color_button.clicked.connect(self.pick_color)
        self.transparent_button.clicked.connect(self.use_transparent_color)
        self.transparent_display_button.clicked.connect(self._pick_transparent_display_color)
        self.load_image_button.clicked.connect(self.open_image)
        self.load_palette_button.clicked.connect(self.load_palette)
        self.add_palette_from_file_button.clicked.connect(self.add_palette_from_file)
        self.palette_from_current_button.clicked.connect(self.palette_from_current_image)
        self.add_palette_from_current_button.clicked.connect(self.add_palette_from_current_image)
        self.export_palette_button.clicked.connect(self.export_palette)
        self.pick_replace_target_button.clicked.connect(self._pick_replace_target_color)
        self.transparent_replace_button.clicked.connect(self._replace_target_with_transparent)
        self.replace_with_color_button.clicked.connect(self._replace_target_with_color)
        self.replace_with_button.clicked.connect(self._pick_replace_with_color)
        self.transparent_replace_clear_button.clicked.connect(self._clear_transparent_replace_target)
        self.flip_horizontal_button.clicked.connect(self.flip_horizontal)
        self.flip_vertical_button.clicked.connect(self.flip_vertical)
        self.rotate_clockwise_button.clicked.connect(self.rotate_clockwise)
        self.rotate_counterclockwise_button.clicked.connect(self.rotate_counterclockwise)
        self.darken_button.clicked.connect(self.darken_current_image)
        self.lighten_button.clicked.connect(self.lighten_current_image)
        self.normalize_button.clicked.connect(self.normalize_current_image)
        self.undo_tone_button.clicked.connect(self.undo_tone_adjustment)
        self.save_image_button.clicked.connect(self.save_image)
        self.save_asset_button.clicked.connect(self.save_to_asset_tray)
        self.shade_ramp_button.clicked.connect(self._generate_shade_ramp)
        self.shade_add_all_button.clicked.connect(self._add_ramp_to_palette)
        self.resize_canvas_button.clicked.connect(self._resize_canvas)
        self.trim_transparent_button.clicked.connect(self._trim_transparent)
        self.canvas.image_changed.connect(self._on_canvas_image_changed)
        self.canvas.selection_changed.connect(self.selection_summary.setText)
        self.canvas.status_changed.connect(self.statusBar().showMessage)
        self._update_transparent_replace_preview()
        self._update_replace_with_preview()

    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image In PixelForge",
            "",
            "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)",
        )
        if not path:
            return

        try:
            image = load_image(path)
        except Exception as exc:  # pragma: no cover - GUI feedback
            QMessageBox.critical(self, "Open failed", str(exc))
            return

        self.document.image = image
        self.document.name = Path(path).stem
        self.document.selected_pixels.clear()
        self.document.selection_rect = None
        self.document.image_history.clear()
        self.canvas.set_document(self.document)
        self.setWindowTitle(f"PixelForge - {self.document.name}")
        self.statusBar().showMessage(f"Loaded {Path(path).name}")

    def load_palette(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Palette",
            "",
            "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        try:
            self.document.palette = load_palette_from_image(path, max_colors=64)
        except Exception as exc:  # pragma: no cover - GUI feedback
            QMessageBox.critical(self, "Palette load failed", str(exc))
            return
        self._refresh_palette_buttons()
        self.statusBar().showMessage(f"Loaded palette from {Path(path).name}")

    def save_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Pixel Image",
            f"{self.document.name}.png",
            "PNG Image (*.png)",
        )
        if not path:
            return
        save_image(self.document.image, path)
        self.statusBar().showMessage(f"Saved {Path(path).name}")

    def add_palette_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Add Colors from Palette Image",
            "",
            "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        try:
            incoming = load_palette_from_image(path, max_colors=64)
        except Exception as exc:
            QMessageBox.critical(self, "Palette load failed", str(exc))
            return
        self.document.palette = merge_palettes(self.document.palette, incoming)
        self._refresh_palette_buttons()
        added = len(self.document.palette) - len(set(self.document.palette) & set(incoming))
        self.statusBar().showMessage(f"Merged palette from {Path(path).name}")

    def palette_from_current_image(self) -> None:
        self.document.palette = palette_from_image(self.document.image, max_colors=64)
        self._refresh_palette_buttons()
        self.statusBar().showMessage("Loaded palette from current editor image")

    def add_palette_from_current_image(self) -> None:
        incoming = palette_from_image(self.document.image, max_colors=64)
        self.document.palette = merge_palettes(self.document.palette, incoming)
        self._refresh_palette_buttons()
        self.statusBar().showMessage("Added colors from current image to palette")

    def add_external_color(self, color: tuple[int, int, int, int]) -> None:
        """Called by the main window when the eyedropper picks a color."""
        self.document.palette = merge_palettes(self.document.palette, [color])
        self._refresh_palette_buttons()

    def export_palette(self) -> None:
        if not self.document.palette:
            self.statusBar().showMessage("No palette to export")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PixelForge Palette",
            f"{self.document.name}_palette.png",
            "PNG Image (*.png)",
        )
        if not path:
            return
        export_palette_strip(self.document.palette, path)
        self.statusBar().showMessage(f"Exported palette to {Path(path).name}")

    def flip_horizontal(self) -> None:
        self.document.image = flip_image_horizontal(self.document.image)
        self.document.selected_pixels.clear()
        self.document.selection_rect = None
        self.canvas.set_document(self.document)
        self.selection_summary.setText("No selection")
        self.statusBar().showMessage("Flipped image horizontally")

    def flip_vertical(self) -> None:
        self.document.image = flip_image_vertical(self.document.image)
        self.document.selected_pixels.clear()
        self.document.selection_rect = None
        self.canvas.set_document(self.document)
        self.selection_summary.setText("No selection")
        self.statusBar().showMessage("Flipped image vertically")

    def rotate_clockwise(self) -> None:
        self.document.image = rotate_image_clockwise(self.document.image)
        self._reset_selection_after_transform()
        self.statusBar().showMessage("Rotated image 90 degrees clockwise")

    def rotate_counterclockwise(self) -> None:
        self.document.image = rotate_image_counterclockwise(self.document.image)
        self._reset_selection_after_transform()
        self.statusBar().showMessage("Rotated image 90 degrees counterclockwise")

    def darken_current_image(self) -> None:
        percent = self.darken_spin.value()
        push_image_history(self.document)
        self.document.image = darken_image(self.document.image, percent)
        self._reset_selection_after_transform()
        self.statusBar().showMessage(f"Darkened image by {percent}%")

    def lighten_current_image(self) -> None:
        percent = self.darken_spin.value()
        push_image_history(self.document)
        self.document.image = lighten_image(self.document.image, percent)
        self._reset_selection_after_transform()
        self.statusBar().showMessage(f"Lightened image by {percent}%")

    def normalize_current_image(self) -> None:
        threshold = self.normalize_threshold_spin.value()
        push_image_history(self.document)
        self.document.image = normalize_to_black_white(self.document.image, threshold)
        self._reset_selection_after_transform()
        self.statusBar().showMessage(
            f"Normalized image to black/white with black cutoff {threshold}"
        )

    def undo_tone_adjustment(self) -> None:
        if not undo_image_history(self.document):
            self.statusBar().showMessage("No darken, lighten, or normalize step to undo")
            return
        self._reset_selection_after_transform()
        self.statusBar().showMessage("Undid last darken, lighten, or normalize step")

    def save_to_asset_tray(self) -> None:
        self.asset_save_requested.emit(self.document.name, self.document.clone_image())
        self.statusBar().showMessage("Sent pixel map to asset tray")

    def pick_color(self) -> None:
        initial = QColor(*self.document.current_color)
        dialog = QColorDialog(initial, self)
        dialog.setWindowTitle("Pick Pixel Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        if dialog.exec() != QColorDialog.DialogCode.Accepted:
            return
        color = dialog.selectedColor()
        self._set_current_color((color.red(), color.green(), color.blue(), color.alpha()))
        self.document.palette = add_color_to_palette(self.document.palette, self.document.current_color)
        self._refresh_palette_buttons()
        self.statusBar().showMessage("Updated current paint color and saved it to the palette")

    def use_transparent_color(self) -> None:
        red, green, blue, _alpha = self.document.current_color
        self._set_current_color((red, green, blue, 0))
        self.statusBar().showMessage("Painting with transparent pixels")

    def _on_canvas_image_changed(self) -> None:
        self.canvas.update()

    def _on_mode_changed(self) -> None:
        if self.paint_radio.isChecked():
            mode = "paint"
        elif self.stamp_radio.isChecked():
            mode = "stamp"
        else:
            mode = "select"
        self.canvas.set_mode(mode)

    def _reset_selection_after_transform(self) -> None:
        self.document.selected_pixels.clear()
        self.document.selection_rect = None
        self.canvas.set_document(self.document)
        self.selection_summary.setText("No selection")

    def _refresh_palette_buttons(self) -> None:
        while self.palette_layout.count():
            item = self.palette_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self.document.palette:
            self.palette_layout.addWidget(QLabel("No palette"), 0, 0)
            return

        for i, color in enumerate(self.document.palette):
            button = ClickableColorButton(color)
            button.clicked_color.connect(self._select_palette_color)
            row = i // self._palette_cols
            col = i % self._palette_cols
            self.palette_layout.addWidget(button, row, col)

    def _select_palette_color(self, color: tuple[int, int, int, int]) -> None:
        self._set_current_color(color)
        if color[3] == 0:
            self._clear_transparent_replace_target(show_message=False)
            return
        self._transparent_replace_target = color
        self._update_transparent_replace_preview()
        self.statusBar().showMessage("Selected palette color and armed transparent replace target")

    def _set_current_color(self, color: tuple[int, int, int, int]) -> None:
        self.document.current_color = color
        self.document.use_transparent_color = color[3] == 0
        self.opacity_slider.setValue(color[3])
        self._update_color_preview()
        self.statusBar().showMessage("Selected palette color")

    def _on_opacity_changed(self, alpha: int) -> None:
        red, green, blue, _current_alpha = self.document.current_color
        self.document.current_color = (red, green, blue, alpha)
        self.document.use_transparent_color = alpha == 0
        self._update_color_preview()

    def _update_color_preview(self) -> None:
        if self.document.use_transparent_color:
            self.color_preview.setText("T")
            self.color_preview.setStyleSheet("background: #444; color: white; border: 1px solid #888;")
            return

        r, g, b, a = self.document.current_color
        self.color_preview.setText("")
        self.color_preview.setStyleSheet(
            "background: rgba(%d, %d, %d, %d); border: 1px solid #111;" % (r, g, b, a)
        )

    def _generate_shade_ramp(self) -> None:
        color = self.document.current_color
        if color[3] == 0:
            self.statusBar().showMessage("Select a non-transparent color first")
            return
        self._current_ramp = shade_ramp(color)
        while self.shade_ramp_layout.count():
            item = self.shade_ramp_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for label, rgba in self._current_ramp:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.setMinimumWidth(60)
            r, g, b, a = rgba
            luma = 0.299 * r + 0.587 * g + 0.114 * b
            text_color = "#000" if luma > 128 else "#fff"
            btn.setStyleSheet(
                f"background: rgba({r},{g},{b},{a}); color: {text_color}; border: 1px solid #555;"
            )
            btn.setToolTip(f"#{r:02X}{g:02X}{b:02X}  RGBA({r},{g},{b},{a})")
            btn.clicked.connect(lambda _checked=False, c=rgba: self._set_current_color(c))
            self.shade_ramp_layout.addWidget(btn)
        self.shade_add_all_button.setEnabled(True)
        self.statusBar().showMessage("Shade ramp generated from current color")

    def _add_ramp_to_palette(self) -> None:
        if not self._current_ramp:
            return
        incoming = [rgba for _, rgba in self._current_ramp]
        self.document.palette = merge_palettes(self.document.palette, incoming)
        self._refresh_palette_buttons()
        self.statusBar().showMessage(f"Added {len(incoming)} ramp colors to palette")

    def _import_reference_underlay(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import reference image",
            "",
            "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        from PySide6.QtGui import QPixmap
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.critical(self, "Load failed", "Could not load image.")
            return
        from PIL import Image
        self.document.image = Image.new(
            "RGBA",
            (self.document.image.width, self.document.image.height),
            (0, 0, 0, 0),
        )
        self.canvas.set_document(self.document)
        self.canvas.set_reference_image(pixmap)
        self.canvas.set_reference_opacity(self.ref_opacity_slider.value() / 100.0)
        self.statusBar().showMessage(
            f"Reference loaded ({pixmap.width()}x{pixmap.height()}) — "
            f"canvas cleared to transparent. Paint over it!"
        )

    def _clear_reference_underlay(self) -> None:
        self.canvas.clear_reference()
        self.statusBar().showMessage("Reference underlay removed")

    def _copy_as_stamp(self) -> None:
        if self.canvas.copy_stamp():
            stamp = self.canvas.stamp_image()
            w, h = stamp.size if stamp else (0, 0)
            self.stamp_radio.setChecked(True)
            self.statusBar().showMessage(f"Stamp copied ({w}x{h}px) — click to place")
        else:
            self.statusBar().showMessage("Select a region first (use Select mode, drag a rectangle)")

    def _pick_transparent_display_color(self) -> None:
        c = QColorDialog.getColor(QColor("#ff00ff"), self, "Transparent pixel display color")
        if not c.isValid():
            return
        self.canvas.set_transparent_display_color(c)
        self.transparent_display_button.setText(f"Transparent Color: {c.name()}")
        self.transparent_display_button.setStyleSheet(
            f"background: {c.name()}; color: {'#000' if c.lightness() > 128 else '#fff'}; border: 1px solid #888;"
        )
        self.statusBar().showMessage(f"Transparent pixels shown as {c.name()} — right-click to reset")

    def _reset_transparent_display(self) -> None:
        self.canvas.set_transparent_display_color(None)
        self.transparent_display_button.setText("Transparent Color: Checker")
        self.transparent_display_button.setStyleSheet("")
        self.statusBar().showMessage("Transparent pixels shown as checkerboard")

    def _replace_target_with_transparent(self) -> None:
        if self._transparent_replace_target is None:
            self.statusBar().showMessage("Choose a palette color to replace first")
            return
        replaced, count = replace_color_with_transparent(
            self.document.image,
            self._transparent_replace_target,
        )
        if count == 0:
            self.statusBar().showMessage("No pixels matched the armed palette color")
            return
        push_image_history(self.document)
        self.document.image = replaced
        self.canvas.update()
        self.statusBar().showMessage(f"Replaced {count} pixel{'s' if count != 1 else ''} with transparent")

    def _pick_replace_with_color(self) -> None:
        initial = QColor(*self._replace_with_color)
        dialog = QColorDialog(initial, self)
        dialog.setWindowTitle("Pick Replace With Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        if dialog.exec() != QColorDialog.DialogCode.Accepted:
            return
        color = dialog.selectedColor()
        self._replace_with_color = (color.red(), color.green(), color.blue(), color.alpha())
        self._update_replace_with_preview()
        r, g, b, a = self._replace_with_color
        self.statusBar().showMessage(f"Selected replace-with color #{r:02X}{g:02X}{b:02X} / {a}")

    def _pick_replace_target_color(self) -> None:
        initial = QColor(*self._transparent_replace_target) if self._transparent_replace_target else QColor("#ff00ff")
        dialog = QColorDialog(initial, self)
        dialog.setWindowTitle("Pick Replace Target Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        if dialog.exec() != QColorDialog.DialogCode.Accepted:
            return
        color = dialog.selectedColor()
        self._transparent_replace_target = (color.red(), color.green(), color.blue(), color.alpha())
        self._update_transparent_replace_preview()
        r, g, b, a = self._transparent_replace_target
        self.statusBar().showMessage(f"Selected replace target #{r:02X}{g:02X}{b:02X} / {a}")

    def _replace_target_with_color(self) -> None:
        if self._transparent_replace_target is None:
            self.statusBar().showMessage("Choose a palette color to replace first")
            return
        replaced, count = replace_color(
            self.document.image,
            self._transparent_replace_target,
            self._replace_with_color,
        )
        if count == 0:
            self.statusBar().showMessage("No pixels matched the armed palette color")
            return
        push_image_history(self.document)
        self.document.image = replaced
        self.canvas.update()
        r, g, b, a = self._replace_with_color
        self.statusBar().showMessage(
            f"Replaced {count} pixel{'s' if count != 1 else ''} with #{r:02X}{g:02X}{b:02X} / {a}"
        )

    def _clear_transparent_replace_target(self, show_message: bool = True) -> None:
        self._transparent_replace_target = None
        self._update_transparent_replace_preview()
        if show_message:
            self.statusBar().showMessage("Transparent replace target cleared")

    def _update_transparent_replace_preview(self) -> None:
        color = self._transparent_replace_target
        self.transparent_replace_button.setEnabled(color is not None)
        self.replace_with_color_button.setEnabled(color is not None)
        if color is None:
            self.transparent_replace_preview.setText("No replace target")
            self.transparent_replace_preview.setStyleSheet("border: 1px solid #555; color: #bbb;")
            return
        red, green, blue, alpha = color
        luma = 0.299 * red + 0.587 * green + 0.114 * blue
        text_color = "#000" if luma > 128 else "#fff"
        self.transparent_replace_preview.setText(f"Target: #{red:02X}{green:02X}{blue:02X} / {alpha}")
        self.transparent_replace_preview.setStyleSheet(
            f"background: rgba({red}, {green}, {blue}, {alpha});"
            f"color: {text_color}; border: 1px solid #555;"
        )

    def _update_replace_with_preview(self) -> None:
        red, green, blue, alpha = self._replace_with_color
        luma = 0.299 * red + 0.587 * green + 0.114 * blue
        text_color = "#000" if luma > 128 else "#fff"
        self.replace_with_preview.setText(f"Replace With: #{red:02X}{green:02X}{blue:02X} / {alpha}")
        self.replace_with_preview.setStyleSheet(
            f"background: rgba({red}, {green}, {blue}, {alpha});"
            f"color: {text_color}; border: 1px solid #555;"
        )

    def _resize_canvas(self) -> None:
        new_w = self.resize_w_spin.value()
        new_h = self.resize_h_spin.value()
        old_img = self.document.image
        if new_w == old_img.width and new_h == old_img.height:
            self.statusBar().showMessage("Canvas size unchanged")
            return

        from PIL import Image
        new_img = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))

        anchor = self.resize_anchor_combo.currentText() if self.resize_anchor_combo else "Top-Left"
        anchor_map = {
            "Top-Left": (0.0, 0.0),
            "Top-Center": (0.5, 0.0),
            "Top-Right": (1.0, 0.0),
            "Center-Left": (0.0, 0.5),
            "Center": (0.5, 0.5),
            "Center-Right": (1.0, 0.5),
            "Bottom-Left": (0.0, 1.0),
            "Bottom-Center": (0.5, 1.0),
            "Bottom-Right": (1.0, 1.0),
        }
        ax, ay = anchor_map.get(anchor, (0.0, 0.0))
        ox = int((new_w - old_img.width) * ax)
        oy = int((new_h - old_img.height) * ay)
        new_img.paste(old_img, (ox, oy))

        self.document.image = new_img
        self._reset_selection_after_transform()
        self.statusBar().showMessage(f"Canvas resized to {new_w}x{new_h} (anchor: {anchor})")

    def _trim_transparent(self) -> None:
        img = self.document.image
        bbox = img.getbbox()
        if bbox is None:
            self.statusBar().showMessage("Canvas is fully transparent, nothing to trim")
            return
        left, top, right, bottom = bbox
        if left == 0 and top == 0 and right == img.width and bottom == img.height:
            self.statusBar().showMessage("No transparent border to trim")
            return
        trimmed = img.crop(bbox).copy()
        self.document.image = trimmed
        self.resize_w_spin.setValue(trimmed.width)
        self.resize_h_spin.setValue(trimmed.height)
        self._reset_selection_after_transform()
        self.statusBar().showMessage(f"Trimmed to {trimmed.width}x{trimmed.height}")
