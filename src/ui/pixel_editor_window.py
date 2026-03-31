from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QFileDialog,
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
from src.core.pixel_document import (
    PixelDocument,
    darken_image,
    flip_image_horizontal,
    flip_image_vertical,
    lighten_image,
    push_image_history,
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
        self.setWindowTitle(f"Pixel Editor - {document.name}")
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
        self.palette_layout = QHBoxLayout(self.palette_container)
        self.palette_layout.setContentsMargins(0, 0, 0, 0)

        self.paint_radio = QRadioButton("Paint")
        self.select_radio = QRadioButton("Select")
        self.paint_radio.setChecked(True)

        self.transparent_button = QPushButton("Use Transparent")
        self.custom_color_button = QPushButton("Pick Color")
        self.load_image_button = QPushButton("Open Image")
        self.load_palette_button = QPushButton("Load Palette")
        self.palette_from_current_button = QPushButton("Palette From Current")
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
        self.undo_tone_button = QPushButton("Undo Tone")
        self.save_image_button = QPushButton("Save Image")
        self.save_asset_button = QPushButton("Save To Asset Tray")

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

        undo_tone_action = QAction("Undo Tone", self)
        undo_tone_action.triggered.connect(self.undo_tone_adjustment)
        toolbar.addAction(undo_tone_action)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Zoom"))
        toolbar.addWidget(self.zoom_spin)

    def _build_layout(self) -> None:
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.paint_radio)
        mode_group.addButton(self.select_radio)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self.paint_radio)
        mode_row.addWidget(self.select_radio)
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
        controls_layout.addSpacing(12)
        controls_layout.addWidget(QLabel("Palette"))
        controls_layout.addWidget(self.palette_container)
        controls_layout.addWidget(self.load_palette_button)
        controls_layout.addWidget(self.palette_from_current_button)
        controls_layout.addWidget(self.export_palette_button)
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
        controls_layout.addWidget(self.undo_tone_button)
        controls_layout.addSpacing(12)
        controls_layout.addWidget(self.selection_summary)
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
        self.opacity_slider.valueChanged.connect(self.opacity_spin.setValue)
        self.opacity_spin.valueChanged.connect(self.opacity_slider.setValue)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.custom_color_button.clicked.connect(self.pick_color)
        self.transparent_button.clicked.connect(self.use_transparent_color)
        self.load_image_button.clicked.connect(self.open_image)
        self.load_palette_button.clicked.connect(self.load_palette)
        self.palette_from_current_button.clicked.connect(self.palette_from_current_image)
        self.export_palette_button.clicked.connect(self.export_palette)
        self.flip_horizontal_button.clicked.connect(self.flip_horizontal)
        self.flip_vertical_button.clicked.connect(self.flip_vertical)
        self.rotate_clockwise_button.clicked.connect(self.rotate_clockwise)
        self.rotate_counterclockwise_button.clicked.connect(self.rotate_counterclockwise)
        self.darken_button.clicked.connect(self.darken_current_image)
        self.lighten_button.clicked.connect(self.lighten_current_image)
        self.undo_tone_button.clicked.connect(self.undo_tone_adjustment)
        self.save_image_button.clicked.connect(self.save_image)
        self.save_asset_button.clicked.connect(self.save_to_asset_tray)
        self.canvas.image_changed.connect(self._on_canvas_image_changed)
        self.canvas.selection_changed.connect(self.selection_summary.setText)
        self.canvas.status_changed.connect(self.statusBar().showMessage)

    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image In Pixel Editor",
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
        self.setWindowTitle(f"Pixel Editor - {self.document.name}")
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

    def palette_from_current_image(self) -> None:
        self.document.palette = palette_from_image(self.document.image, max_colors=64)
        self._refresh_palette_buttons()
        self.statusBar().showMessage("Loaded palette from current editor image")

    def export_palette(self) -> None:
        if not self.document.palette:
            self.statusBar().showMessage("No palette to export")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Pixel Editor Palette",
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

    def undo_tone_adjustment(self) -> None:
        if not undo_image_history(self.document):
            self.statusBar().showMessage("No darken or lighten step to undo")
            return
        self._reset_selection_after_transform()
        self.statusBar().showMessage("Undid last darken or lighten step")

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
        mode = "paint" if self.paint_radio.isChecked() else "select"
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
            self.palette_layout.addWidget(QLabel("No palette"))
            return

        for color in self.document.palette:
            button = ClickableColorButton(color)
            button.clicked_color.connect(self._set_current_color)
            self.palette_layout.addWidget(button)
        self.palette_layout.addStretch(1)

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
