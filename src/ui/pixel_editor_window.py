from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor, QDrag, QKeySequence, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.core.image_io import load_image, save_image
from src.core.palette import (
    add_color_to_palette,
    all_colors_from_image,
    export_palette_grid,
    export_palette_strip,
    load_palette_from_image,
    palette_from_image,
    sort_palette,
)
from src.core.persistent_palette import merge_palettes
from src.ui.layer_panel import LayerPanel
from src.core.shade_ramp import (
    DIRECTIONAL_SHADING_DEFAULT_ANGLE_DEG,
    apply_directional_shading,
    apply_radial_shading,
    shade_ramp,
)
from src.core.pixel_document import (
    ColorShift,
    PixelDocument,
    apply_color_shift,
    apply_ramp_shifts,
    calculate_color_shift,
    calculate_ramp_shifts,
    darken_image,
    dilate_color,
    erode_color,
    flip_image_horizontal,
    flip_image_vertical,
    flood_erase_outside_color,
    lighten_image,
    normalize_to_black_white,
    push_image_history,
    redo_image_history,
    replace_color,
    replace_colors,
    replace_color_with_transparent,
    replace_similar_color_with_transparent,
    rotate_image_clockwise,
    rotate_image_counterclockwise,
    rgb_distance_tolerance_from_percent,
    undo_image_history,
)
from src.ui.pixel_grid_canvas import PixelGridCanvas


_COLOR_MIME_TYPE = "application/x-pixelforge-color"


def _encode_color_payload(color: tuple[int, int, int, int]) -> bytes:
    return ",".join(str(channel) for channel in color).encode("utf-8")


def _decode_color_payload(mime) -> tuple[int, int, int, int] | None:
    if not mime.hasFormat(_COLOR_MIME_TYPE):
        return None
    try:
        payload = bytes(mime.data(_COLOR_MIME_TYPE)).decode("utf-8")
        red, green, blue, alpha = (int(part) for part in payload.split(","))
    except Exception:
        return None
    return (red, green, blue, alpha)


def _color_drag_pixmap(size, color: tuple[int, int, int, int]) -> QPixmap:
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    if color[3] == 0:
        painter.fillRect(0, 0, pixmap.width(), pixmap.height(), QColor("#444"))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "T")
    else:
        painter.fillRect(pixmap.rect(), QColor(*color))
    painter.setPen(QColor("#111111"))
    painter.drawRect(pixmap.rect().adjusted(0, 0, -1, -1))
    painter.end()
    return pixmap


class ClickableColorButton(QPushButton):
    clicked_color = Signal(tuple)

    def __init__(self, color: tuple[int, int, int, int], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self._drag_start_pos: QPoint | None = None
        self.setFixedSize(24, 24)
        self._apply_style()
        self.clicked.connect(self._emit_color)
        self.setToolTip("Click to select or drag onto a replace color bar")

    def _emit_color(self) -> None:
        self.clicked_color.emit(self._color)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_start_pos is None
            or not (event.buttons() & Qt.MouseButton.LeftButton)
            or (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            < QApplication.startDragDistance()
        ):
            super().mouseMoveEvent(event)
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_COLOR_MIME_TYPE, _encode_color_payload(self._color))
        drag.setMimeData(mime)
        drag.setPixmap(self._drag_pixmap())
        drag.exec(Qt.DropAction.CopyAction)
        self._drag_start_pos = None
        self.setDown(False)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _drag_pixmap(self) -> QPixmap:
        return _color_drag_pixmap(self.size(), self._color)

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


class ColorDropLabel(QLabel):
    color_dropped = Signal(tuple)

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._color: tuple[int, int, int, int] | None = None
        self._drag_start_pos: QPoint | None = None
        self.setAcceptDrops(True)

    def set_color(self, color: tuple[int, int, int, int] | None) -> None:
        self._color = color

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._color is not None:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._color is None
            or self._drag_start_pos is None
            or not (event.buttons() & Qt.MouseButton.LeftButton)
            or (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            < QApplication.startDragDistance()
        ):
            super().mouseMoveEvent(event)
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_COLOR_MIME_TYPE, _encode_color_payload(self._color))
        drag.setMimeData(mime)
        drag.setPixmap(_color_drag_pixmap(self.size(), self._color))
        drag.exec(Qt.DropAction.CopyAction)
        self._drag_start_pos = None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event) -> None:
        if _decode_color_payload(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if _decode_color_payload(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        color = _decode_color_payload(event.mimeData())
        if color is None:
            return
        self.color_dropped.emit(color)
        event.acceptProposedAction()


class PaletteGridCell(QLabel):
    color_dropped = Signal(int, object)
    clear_requested = Signal(int)
    clicked_color = Signal(object)

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = index
        self._color: tuple[int, int, int, int] | None = None
        self._drag_start_pos: QPoint | None = None
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(28, 28)
        self.setToolTip("Drag colors in or out. Click to select. Right-click to clear.")
        self._apply_style()

    def set_index(self, index: int) -> None:
        self._index = index

    def color(self) -> tuple[int, int, int, int] | None:
        return self._color

    def set_color(self, color: tuple[int, int, int, int] | None) -> None:
        self._color = color
        self._apply_style()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.clear_requested.emit(self._index)
            return
        if event.button() == Qt.MouseButton.LeftButton and self._color is not None:
            self._drag_start_pos = event.position().toPoint()
            self.clicked_color.emit(self._color)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._color is None
            or self._drag_start_pos is None
            or not (event.buttons() & Qt.MouseButton.LeftButton)
            or (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            < QApplication.startDragDistance()
        ):
            super().mouseMoveEvent(event)
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_COLOR_MIME_TYPE, _encode_color_payload(self._color))
        drag.setMimeData(mime)
        drag.setPixmap(self._drag_pixmap())
        drag.exec(Qt.DropAction.CopyAction)
        self._drag_start_pos = None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event) -> None:
        if _decode_color_payload(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if _decode_color_payload(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        color = _decode_color_payload(event.mimeData())
        if color is None:
            return
        self.color_dropped.emit(self._index, color)
        event.acceptProposedAction()

    def _apply_style(self) -> None:
        if self._color is None:
            self.setText("")
            self.setStyleSheet("background: #232323; border: 1px dashed #666;")
            return
        if self._color[3] == 0:
            self.setText("T")
            self.setStyleSheet("background: #444; color: white; border: 1px solid #888;")
            return
        self.setText("")
        self.setStyleSheet(
            "background: rgba(%d, %d, %d, %d); border: 1px solid #111;"
            % self._color
        )

    def _drag_pixmap(self) -> QPixmap:
        return _color_drag_pixmap(self.size(), self._color or (0, 0, 0, 0))


class PaletteGridWidget(QWidget):
    cell_color_dropped = Signal(int, object)
    cell_cleared = Signal(int)
    cell_clicked = Signal(object)

    def __init__(self, columns: int = 4, rows: int = 4, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._columns = max(1, columns)
        self._rows = max(1, rows)
        self._colors: list[tuple[int, int, int, int] | None] = [None] * (self._columns * self._rows)
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._rebuild_cells()

    def dimensions(self) -> tuple[int, int]:
        return self._columns, self._rows

    def colors(self) -> list[tuple[int, int, int, int] | None]:
        return list(self._colors)

    def set_dimensions(self, columns: int, rows: int) -> None:
        columns = max(1, columns)
        rows = max(1, rows)
        if (columns, rows) == (self._columns, self._rows):
            return
        resized: list[tuple[int, int, int, int] | None] = [None] * (columns * rows)
        for index, color in enumerate(self._colors[: len(resized)]):
            resized[index] = color
        self._columns = columns
        self._rows = rows
        self._colors = resized
        self._rebuild_cells()

    def set_cell_color(self, index: int, color: tuple[int, int, int, int]) -> None:
        if 0 <= index < len(self._colors):
            self._colors[index] = color
            cell = self._layout.itemAt(index).widget()
            if isinstance(cell, PaletteGridCell):
                cell.set_color(color)

    def clear_cell(self, index: int) -> None:
        if 0 <= index < len(self._colors):
            self._colors[index] = None
            cell = self._layout.itemAt(index).widget()
            if isinstance(cell, PaletteGridCell):
                cell.set_color(None)

    def clear_all(self) -> None:
        for index in range(len(self._colors)):
            self.clear_cell(index)

    def ordered_indices(self) -> list[int]:
        return [
            row * self._columns + col
            for row in range(self._rows)
            for col in range(self._columns)
        ]

    def ordered_colors(self, *, filled_only: bool = False) -> list[tuple[int, int, int, int] | None]:
        colors = [self._colors[index] for index in self.ordered_indices()]
        if filled_only:
            return [color for color in colors if color is not None]
        return colors

    def append_colors(self, colors: list[tuple[int, int, int, int]]) -> int:
        ordered_indices = self.ordered_indices()
        start = len(self.ordered_colors(filled_only=True))
        placed = 0
        for color, index in zip(colors, ordered_indices[start:]):
            self.set_cell_color(index, color)
            placed += 1
        return placed

    def _rebuild_cells(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for index, color in enumerate(self._colors):
            cell = PaletteGridCell(index)
            cell.set_color(color)
            cell.color_dropped.connect(self.cell_color_dropped.emit)
            cell.clear_requested.connect(self.cell_cleared.emit)
            cell.clicked_color.connect(self.cell_clicked.emit)
            row = index // self._columns
            col = index % self._columns
            self._layout.addWidget(cell, row, col)


class PixelEditorWindow(QMainWindow):
    asset_save_requested = Signal(str, object)

    @staticmethod
    def _initial_zoom_for(document: PixelDocument) -> int:
        longest = max(document.image.width, document.image.height)
        if longest >= 1600:
            return 1
        if longest >= 900:
            return 2
        if longest >= 512:
            return 4
        return 20

    def __init__(
        self,
        document: PixelDocument,
        parent: QWidget | None = None,
        *,
        headless: bool = False,
        restore_reference=None,
    ) -> None:
        super().__init__(parent)
        self.document = document
        self._headless = headless
        self._restore_reference = (
            restore_reference.convert("RGBA").copy()
            if restore_reference is not None
            else None
        )
        if self._restore_reference is not None and self._restore_reference.size != document.image.size:
            raise ValueError("Cleanup restore reference must match the document geometry")
        self.setWindowTitle(f"PixelForge - {document.name}")
        self.resize(1100, 820)

        initial_zoom = self._initial_zoom_for(document)
        self.canvas = PixelGridCanvas()
        self.canvas.set_zoom(initial_zoom)
        self.canvas.set_document(self.document)

        self.layer_panel = LayerPanel()
        self.layer_panel.set_document(self.document)

        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(1, 64)
        self.zoom_spin.setValue(initial_zoom)

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
        self.palette_grid_cols_spin = QSpinBox()
        self.palette_grid_cols_spin.setRange(1, 16)
        self.palette_grid_cols_spin.setValue(4)
        self.palette_grid_rows_spin = QSpinBox()
        self.palette_grid_rows_spin.setRange(1, 16)
        self.palette_grid_rows_spin.setValue(4)
        self.palette_grid_widget = PaletteGridWidget(4, 4)
        self.add_palette_to_grid_button = QPushButton("Add to Grid")
        self.calculate_ramp_button = QPushButton("Calc Ramp")
        self.apply_ramp_replace_button = QPushButton("Ramp 1->2")
        self.export_palette_grid_button = QPushButton("Export")
        self.clear_palette_grid_button = QPushButton("Clear")
        self._transparent_replace_target: tuple[int, int, int, int] | None = None
        self._replace_with_color: tuple[int, int, int, int] = (255, 255, 255, 255)
        self.transparent_replace_preview = ColorDropLabel("No replace target")
        self.transparent_replace_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.transparent_replace_preview.setMinimumHeight(28)
        self.transparent_replace_preview.setToolTip("Drag a palette color here to set the replace target")
        self.replace_with_preview = ColorDropLabel()
        self.replace_with_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.replace_with_preview.setMinimumHeight(28)
        self.replace_with_preview.setToolTip("Drag a palette color here to set the replacement color")
        self.pick_replace_target_button = QPushButton("Pick")
        self.transparent_replace_button = QPushButton("-> Transparent")
        self.replace_with_color_button = QPushButton("-> Color")
        self.replace_with_button = QPushButton("Pick")
        self.add_replace_with_to_palette_button = QPushButton("+ Palette")
        self.transparent_replace_clear_button = QPushButton("Clear")
        self.white_transparency_percent_spin = QSpinBox()
        self.white_transparency_percent_spin.setRange(0, 100)
        self.white_transparency_percent_spin.setValue(7)
        self.white_transparency_percent_spin.setSuffix("%")
        self.white_transparency_percent_spin.setToolTip(
            "RGB-distance percentage from pure white. 0% only clears #FFFFFF."
        )
        self.white_to_transparency_button = QPushButton("white -> trans")
        self.white_to_transparency_button.setToolTip(
            "Clear active-layer pixels near pure white to transparent"
        )
        self.calculate_change_button = QPushButton("Calculate Change")
        self.change_target_button = QPushButton("Change Target")
        self.color_shift_summary = QLabel("Delta: none")
        self.color_shift_summary.setWordWrap(True)
        self.color_shift_summary.setMinimumWidth(150)
        self._stored_color_shift: ColorShift | None = None

        self._morph_color: tuple[int, int, int, int] | None = None
        self.morph_color_preview = ColorDropLabel("No source color")
        self.morph_color_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.morph_color_preview.setMinimumHeight(28)
        self.morph_color_preview.setToolTip(
            "Drag a palette color here, or click Pick, to set the source color "
            "that Dilate/Erode will operate on."
        )
        self.morph_pick_button = QPushButton("Pick")
        self.morph_thickness_spin = QSpinBox()
        self.morph_thickness_spin.setRange(1, 32)
        self.morph_thickness_spin.setValue(1)
        self.morph_thickness_spin.setSuffix(" px")
        self.morph_thickness_spin.setToolTip("How many pixels to thicken or thin in every direction")
        self.dilate_button = QPushButton("Dilate (+)")
        self.dilate_button.setToolTip("Thicken: fill transparent pixels next to the source color")
        self.erode_button = QPushButton("Erode (-)")
        self.erode_button.setToolTip("Thin: clear source-color pixels touching transparent or other colors")

        self.paint_radio = QRadioButton("Paint")
        self.select_radio = QRadioButton("Select")
        self.draw_selection_checkbox = QCheckBox("Draw Selection")
        self.draw_selection_checkbox.setToolTip(
            "In Select mode, click perimeter cells, then click the first cell "
            "or an adjacent closing cell to fill the enclosed selection."
        )
        self.stamp_radio = QRadioButton("Stamp")
        self.flood_erase_radio = QRadioButton("Flood Erase")
        self.flood_erase_radio.setToolTip(
            "Click anywhere outside the boundary color to erase that connected\n"
            "region to transparent. The boundary acts as a wall, so anything\n"
            "inside the boundary is preserved."
        )
        self.iso_guide_radio = QRadioButton("Guide")
        self.iso_guide_radio.setToolTip(
            "Move and resize the non-pixel isometric guide overlay"
        )
        self.paint_radio.setChecked(True)

        self._flood_boundary_color: tuple[int, int, int, int] | None = None
        self.flood_boundary_preview = ColorDropLabel("No boundary color")
        self.flood_boundary_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.flood_boundary_preview.setMinimumHeight(28)
        self.flood_boundary_preview.setToolTip(
            "Drag a palette color here, or click Pick, to set the boundary color\n"
            "that walls off the flood fill (e.g. the gold ring of a logo)."
        )
        self.flood_boundary_pick_button = QPushButton("Pick")
        self.flood_hue_tolerance_spin = QSpinBox()
        self.flood_hue_tolerance_spin.setRange(0, 180)
        self.flood_hue_tolerance_spin.setValue(20)
        self.flood_hue_tolerance_spin.setSuffix(" deg")
        self.flood_hue_tolerance_spin.setToolTip(
            "How far a pixel's hue can be from the boundary hue and still count as boundary.\n"
            "Higher = catches more shades along anti-aliased edges."
        )
        self.flood_min_saturation_spin = QSpinBox()
        self.flood_min_saturation_spin.setRange(0, 100)
        self.flood_min_saturation_spin.setValue(25)
        self.flood_min_saturation_spin.setSuffix("% sat")
        self.flood_min_saturation_spin.setToolTip(
            "Minimum saturation for a pixel to count as boundary.\n"
            "Keeps neutral grays/blacks in the background from being treated as the gold/yellow ring."
        )
        self.copy_stamp_button = QPushButton("Copy Selection as Stamp")
        self.flip_stamp_h_button = QPushButton("Flip Stamp H")
        self.flip_stamp_h_button.setToolTip("Flip the copied stamp horizontally before placing it")
        self.flip_stamp_h_button.setEnabled(False)
        self.flip_stamp_v_button = QPushButton("Flip Stamp V")
        self.flip_stamp_v_button.setToolTip("Flip the copied stamp vertically before placing it")
        self.flip_stamp_v_button.setEnabled(False)
        self.copy_selection_layer_button = QPushButton("Copy Selection to New Layer")
        self.copy_selection_layer_button.setToolTip(
            "Create a layer above the active layer containing the selected pixels"
        )
        self.restore_source_button = QPushButton("Restore Source Selection")
        self.restore_source_button.setEnabled(self._restore_reference is not None)

        self.transparent_button = QPushButton("Use Transparent")
        self.custom_color_button = QPushButton("Pick Color")
        self.import_sprite_button = QPushButton("Import Sprite")
        self.import_sprite_button.setToolTip(
            "Load a sprite at native resolution as a movable stamp; click the canvas to commit it"
        )
        self.iso_slash_button = QPushButton("Guide /")
        self.iso_slash_button.setToolTip("Show a non-pixel / guide at classic 1/2 iso slope")
        self.iso_backslash_button = QPushButton("Guide \\")
        self.iso_backslash_button.setToolTip("Show a non-pixel \\ guide at classic -1/2 iso slope")
        self.iso_clear_button = QPushButton("Clear")
        self.iso_clear_button.setEnabled(False)
        self.iso_guide_steps_spin = QSpinBox()
        self.iso_guide_steps_spin.setRange(1, 512)
        self.iso_guide_steps_spin.setValue(6)
        self.iso_guide_steps_spin.setSuffix(" steps")
        self.iso_guide_steps_spin.setToolTip(
            "One guide step is 2 pixels across by 1 pixel up or down"
        )
        self.transparent_display_button = QPushButton("Transparent Color: Checker")
        self.transparent_display_button.setToolTip("Click to pick a solid color for transparent pixels.\nRight-click to reset to checkerboard.")
        self.transparent_display_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.transparent_display_button.customContextMenuRequested.connect(
            lambda _pos: self._reset_transparent_display()
        )
        self.load_palette_button = QPushButton("Load (replace)")
        self.add_palette_from_file_button = QPushButton("Add from File")
        self.palette_from_current_button = QPushButton("From Current (replace)")
        self.add_palette_from_current_button = QPushButton("Add from Current")
        self.reduce_palette_import_checkbox = QCheckBox("Reduce to 64")
        self.reduce_palette_import_checkbox.setChecked(False)
        self.reduce_palette_import_checkbox.setToolTip(
            "Off loads every distinct visible color; enable for the previous 64-color reduction"
        )
        self.export_palette_button = QPushButton("Export")
        self.sort_palette_combo = QComboBox()
        self.sort_palette_combo.addItems(["Brightness", "Hue"])
        self.sort_palette_button = QPushButton("Sort")
        self.darken_spin = QSpinBox()
        self.darken_spin.setRange(1, 100)
        self.darken_spin.setValue(30)
        self.darken_spin.setSuffix("%")
        self.normalize_threshold_spin = QSpinBox()
        self.normalize_threshold_spin.setRange(0, 255)
        self.normalize_threshold_spin.setValue(48)

        self.resize_w_spin = QSpinBox()
        self.resize_w_spin.setRange(1, 1024)
        self.resize_h_spin = QSpinBox()
        self.resize_h_spin.setRange(1, 1024)
        self.resize_anchor_combo = None  # created in _build_layout
        self.resize_canvas_button = QPushButton("Resize")

        self.shade_ramp_button = QPushButton("Shade Ramp")
        self.shade_ramp_container = QWidget()
        self.shade_ramp_layout = QHBoxLayout(self.shade_ramp_container)
        self.shade_ramp_layout.setContentsMargins(0, 0, 0, 0)
        self.shade_ramp_layout.setSpacing(4)
        self.shade_add_all_button = QPushButton("+ Palette")
        self.shade_add_all_button.setEnabled(False)
        self.shading_mode_combo = QComboBox()
        self.shading_mode_combo.addItem("Radial", "radial")
        self.shading_mode_combo.addItem("Directional", "directional")
        self.shading_mode_combo.setToolTip(
            "Radial: shade by distance to the nearest transparent pixel "
            "(edges = shadow, centers = highlight).\n"
            "Directional: shade by which side of the shape's centerline a "
            "pixel sits on, relative to a configurable light angle."
        )

        self.shading_angle_spin = QSpinBox()
        self.shading_angle_spin.setRange(0, 359)
        self.shading_angle_spin.setSuffix(" deg")
        self.shading_angle_spin.setValue(int(round(DIRECTIONAL_SHADING_DEFAULT_ANGLE_DEG)))
        self.shading_angle_spin.setToolTip(
            "Light angle for Directional shading.\n"
            "0 = light from the right, 90 = from above, 135 = from the top-left "
            "(default), 180 = from the left, 270 = from below.\n"
            "Counter-clockwise positive."
        )
        self.shading_angle_label = QLabel("Angle:")

        self.apply_shading_button = QPushButton("Apply Shading")
        self.apply_shading_button.setEnabled(False)
        self.apply_shading_button.setToolTip(
            "Radial: recolor along the shade ramp by distance to the nearest "
            "transparent pixel (edges -> shadow, centers -> highlight).\n"
            "Directional: recolor along the shade ramp by offset from the "
            "shape's medial axis projected onto the light direction.\n"
            "Generate a Shade Ramp first to enable this."
        )
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

        open_action = QAction("Open", self)
        open_action.triggered.connect(self.open_image)
        toolbar.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_image)
        toolbar.addAction(save_action)

        self.save_asset_button = QPushButton("To Tray")
        self.save_asset_button.setToolTip("Save to asset tray")
        toolbar.addWidget(self.save_asset_button)

        toolbar.addSeparator()

        flip_h_action = QAction("Flip H", self)
        flip_h_action.triggered.connect(self.flip_horizontal)
        toolbar.addAction(flip_h_action)

        flip_v_action = QAction("Flip V", self)
        flip_v_action.triggered.connect(self.flip_vertical)
        toolbar.addAction(flip_v_action)

        rotate_cw_action = QAction("Rot CW", self)
        rotate_cw_action.triggered.connect(self.rotate_clockwise)
        toolbar.addAction(rotate_cw_action)

        rotate_ccw_action = QAction("Rot CCW", self)
        rotate_ccw_action.triggered.connect(self.rotate_counterclockwise)
        toolbar.addAction(rotate_ccw_action)

        toolbar.addSeparator()

        toolbar.addWidget(self.darken_spin)
        darken_action = QAction("Darken", self)
        darken_action.triggered.connect(self.darken_current_image)
        toolbar.addAction(darken_action)

        lighten_action = QAction("Lighten", self)
        lighten_action.triggered.connect(self.lighten_current_image)
        toolbar.addAction(lighten_action)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("BW"))
        toolbar.addWidget(self.normalize_threshold_spin)
        normalize_action = QAction("Normalize", self)
        normalize_action.triggered.connect(self.normalize_current_image)
        toolbar.addAction(normalize_action)

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.undo_action.setToolTip(
            "Undo the last reversible edit (darken, lighten, normalize, dilate, "
            "erode, flood erase, or replace). Shortcut: Ctrl+Z"
        )
        self.undo_action.triggered.connect(self.undo_last_edit)
        toolbar.addAction(self.undo_action)
        self.addAction(self.undo_action)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.redo_action.setToolTip("Redo the last undone reversible edit. Shortcut: Ctrl+Y")
        self.redo_action.triggered.connect(self.redo_last_edit)
        toolbar.addAction(self.redo_action)
        self.addAction(self.redo_action)

        toolbar.addSeparator()
        self._mirror_action = QAction("Mirror", self)
        self._mirror_action.setCheckable(True)
        self._mirror_action.toggled.connect(self.canvas.set_mirror)
        toolbar.addAction(self._mirror_action)

        self.measure_action = QAction("Measure", self)
        self.measure_action.setCheckable(True)
        self.measure_action.setToolTip(
            "Measure center-to-center pixel distance: click a start pixel, "
            "move and click the endpoint, then right-click to clear"
        )
        self.measure_action.toggled.connect(self.canvas.set_measurement_enabled)
        toolbar.addAction(self.measure_action)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Zoom"))
        toolbar.addWidget(self.zoom_spin)

    def _build_layout(self) -> None:
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.paint_radio)
        mode_group.addButton(self.select_radio)
        mode_group.addButton(self.stamp_radio)
        mode_group.addButton(self.flood_erase_radio)
        mode_group.addButton(self.iso_guide_radio)

        # --- Right panel: painting tools, palette, replace ---
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(4)

        # Layers panel sits at the top so it's always reachable.
        controls_layout.addWidget(self.layer_panel)

        # Mode + color
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.paint_radio)
        mode_row.addWidget(self.select_radio)
        mode_row.addWidget(self.draw_selection_checkbox)
        mode_row.addWidget(self.stamp_radio)
        mode_row.addWidget(self.flood_erase_radio)
        mode_row.addWidget(self.iso_guide_radio)
        mode_row.addStretch(1)
        controls_layout.addLayout(mode_row)

        selection_action_row = QHBoxLayout()
        selection_action_row.addWidget(self.copy_stamp_button)
        selection_action_row.addWidget(self.flip_stamp_h_button)
        selection_action_row.addWidget(self.flip_stamp_v_button)
        selection_action_row.addWidget(self.copy_selection_layer_button)
        selection_action_row.addWidget(self.restore_source_button)
        selection_action_row.addStretch(1)
        controls_layout.addLayout(selection_action_row)

        color_row = QHBoxLayout()
        color_row.addWidget(self.color_preview)
        color_row.addWidget(self.custom_color_button)
        color_row.addWidget(self.transparent_button)
        color_row.addStretch(1)
        controls_layout.addLayout(color_row)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity"))
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_spin)
        controls_layout.addLayout(opacity_row)

        controls_layout.addWidget(self.transparent_display_button)

        import_sprite_row = QHBoxLayout()
        import_sprite_row.addWidget(self.import_sprite_button)
        import_sprite_row.addStretch(1)
        controls_layout.addLayout(import_sprite_row)

        iso_group = QGroupBox("Iso Guide")
        iso_layout = QGridLayout(iso_group)
        iso_layout.setContentsMargins(4, 4, 4, 4)
        iso_layout.setSpacing(4)
        iso_layout.addWidget(QLabel("Length"), 0, 0)
        iso_layout.addWidget(self.iso_guide_steps_spin, 0, 1)
        iso_layout.addWidget(self.iso_clear_button, 0, 2)
        iso_layout.addWidget(self.iso_slash_button, 1, 0)
        iso_layout.addWidget(self.iso_backslash_button, 1, 1)
        controls_layout.addWidget(iso_group)

        # Palette
        palette_header = QHBoxLayout()
        palette_header.addWidget(QLabel("Palette"))
        palette_header.addStretch(1)
        palette_header.addWidget(self.reduce_palette_import_checkbox)
        controls_layout.addLayout(palette_header)
        controls_layout.addWidget(self.palette_container)

        pal_grid = QGridLayout()
        pal_grid.setContentsMargins(0, 0, 0, 0)
        pal_grid.setSpacing(2)
        pal_grid.addWidget(self.load_palette_button, 0, 0)
        pal_grid.addWidget(self.add_palette_from_file_button, 0, 1)
        pal_grid.addWidget(self.palette_from_current_button, 1, 0)
        pal_grid.addWidget(self.add_palette_from_current_button, 1, 1)
        pal_grid.addWidget(self.export_palette_button, 2, 0)
        sort_row = QHBoxLayout()
        sort_row.setSpacing(2)
        sort_row.addWidget(self.sort_palette_combo)
        sort_row.addWidget(self.sort_palette_button)
        pal_grid.addLayout(sort_row, 2, 1)
        controls_layout.addLayout(pal_grid)

        # Palette Grid
        palette_grid_panel = QGroupBox("Palette Grid")
        palette_grid_panel_layout = QVBoxLayout(palette_grid_panel)
        palette_grid_panel_layout.setContentsMargins(4, 4, 4, 4)
        palette_grid_panel_layout.setSpacing(4)
        palette_grid_size_row = QHBoxLayout()
        palette_grid_size_row.addWidget(QLabel("X"))
        palette_grid_size_row.addWidget(self.palette_grid_cols_spin)
        palette_grid_size_row.addWidget(QLabel("Y"))
        palette_grid_size_row.addWidget(self.palette_grid_rows_spin)
        palette_grid_size_row.addStretch(1)
        palette_grid_panel_layout.addLayout(palette_grid_size_row)
        palette_grid_panel_layout.addWidget(self.palette_grid_widget)
        pg_btn_grid = QGridLayout()
        pg_btn_grid.setContentsMargins(0, 0, 0, 0)
        pg_btn_grid.setSpacing(2)
        pg_btn_grid.addWidget(self.add_palette_to_grid_button, 0, 0)
        pg_btn_grid.addWidget(self.calculate_ramp_button, 0, 1)
        pg_btn_grid.addWidget(self.apply_ramp_replace_button, 1, 0)
        pg_btn_grid.addWidget(self.export_palette_grid_button, 1, 1)
        pg_btn_grid.addWidget(self.clear_palette_grid_button, 2, 0)
        palette_grid_panel_layout.addLayout(pg_btn_grid)
        controls_layout.addWidget(palette_grid_panel)

        # Replace section
        replace_group = QGroupBox("Replace")
        replace_group_layout = QVBoxLayout(replace_group)
        replace_group_layout.setContentsMargins(4, 4, 4, 4)
        replace_group_layout.setSpacing(4)

        white_key_row = QHBoxLayout()
        white_key_row.addWidget(QLabel("White range"))
        white_key_row.addWidget(self.white_transparency_percent_spin)
        white_key_row.addWidget(self.white_to_transparency_button)
        white_key_row.addStretch(1)
        replace_group_layout.addLayout(white_key_row)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Target"))
        target_row.addWidget(self.transparent_replace_preview, 1)
        target_row.addWidget(self.pick_replace_target_button)
        replace_group_layout.addLayout(target_row)

        with_row = QHBoxLayout()
        with_row.addWidget(QLabel("With"))
        with_row.addWidget(self.replace_with_preview, 1)
        with_row.addWidget(self.replace_with_button)
        replace_group_layout.addLayout(with_row)

        replace_btn_grid = QGridLayout()
        replace_btn_grid.setContentsMargins(0, 0, 0, 0)
        replace_btn_grid.setSpacing(2)
        replace_btn_grid.addWidget(self.transparent_replace_button, 0, 0)
        replace_btn_grid.addWidget(self.replace_with_color_button, 0, 1)
        replace_btn_grid.addWidget(self.add_replace_with_to_palette_button, 1, 0)
        replace_btn_grid.addWidget(self.transparent_replace_clear_button, 1, 1)
        replace_group_layout.addLayout(replace_btn_grid)

        # Color change
        change_row = QHBoxLayout()
        change_row.addWidget(self.color_shift_summary, 1)
        change_btn_col = QVBoxLayout()
        change_btn_col.addWidget(self.calculate_change_button)
        change_btn_col.addWidget(self.change_target_button)
        change_row.addLayout(change_btn_col)
        replace_group_layout.addLayout(change_row)

        controls_layout.addWidget(replace_group)

        # Thickness (morphological dilate / erode of a chosen source color)
        morph_group = QGroupBox("Thickness")
        morph_group_layout = QVBoxLayout(morph_group)
        morph_group_layout.setContentsMargins(4, 4, 4, 4)
        morph_group_layout.setSpacing(4)

        morph_color_row = QHBoxLayout()
        morph_color_row.addWidget(QLabel("Source"))
        morph_color_row.addWidget(self.morph_color_preview, 1)
        morph_color_row.addWidget(self.morph_pick_button)
        morph_group_layout.addLayout(morph_color_row)

        morph_action_row = QHBoxLayout()
        morph_action_row.addWidget(QLabel("Thickness"))
        morph_action_row.addWidget(self.morph_thickness_spin)
        morph_action_row.addWidget(self.dilate_button)
        morph_action_row.addWidget(self.erode_button)
        morph_group_layout.addLayout(morph_action_row)

        controls_layout.addWidget(morph_group)

        # Flood Erase: clear the connected non-boundary region a click lands in.
        flood_group = QGroupBox("Flood Erase")
        flood_layout = QVBoxLayout(flood_group)
        flood_layout.setContentsMargins(4, 4, 4, 4)
        flood_layout.setSpacing(4)

        flood_color_row = QHBoxLayout()
        flood_color_row.addWidget(QLabel("Boundary"))
        flood_color_row.addWidget(self.flood_boundary_preview, 1)
        flood_color_row.addWidget(self.flood_boundary_pick_button)
        flood_layout.addLayout(flood_color_row)

        flood_tol_row = QHBoxLayout()
        flood_tol_row.addWidget(QLabel("Hue \u00b1"))
        flood_tol_row.addWidget(self.flood_hue_tolerance_spin)
        flood_tol_row.addWidget(QLabel("Min"))
        flood_tol_row.addWidget(self.flood_min_saturation_spin)
        flood_layout.addLayout(flood_tol_row)

        flood_hint = QLabel(
            "Pick the boundary color (e.g. the gold ring), select <b>Flood Erase</b> "
            "mode, then click outside the boundary to clear that connected region. "
            "Anything inside the boundary is preserved."
        )
        flood_hint.setWordWrap(True)
        flood_hint.setStyleSheet("color: #aaa; padding: 2px;")
        flood_layout.addWidget(flood_hint)

        controls_layout.addWidget(flood_group)

        # Shade ramp
        ramp_row = QHBoxLayout()
        ramp_row.addWidget(self.shade_ramp_button)
        ramp_row.addWidget(self.shade_add_all_button)
        controls_layout.addLayout(ramp_row)

        shading_row = QHBoxLayout()
        shading_row.addWidget(QLabel("Mode:"))
        shading_row.addWidget(self.shading_mode_combo)
        shading_row.addWidget(self.shading_angle_label)
        shading_row.addWidget(self.shading_angle_spin)
        shading_row.addWidget(self.apply_shading_button)
        controls_layout.addLayout(shading_row)
        controls_layout.addWidget(self.shade_ramp_container)

        controls_layout.addWidget(self.selection_summary)

        # Resize canvas
        resize_group = QGroupBox("Canvas")
        resize_layout = QHBoxLayout(resize_group)
        resize_layout.setContentsMargins(4, 4, 4, 4)
        resize_layout.addWidget(QLabel("W"))
        self.resize_w_spin.setValue(self.document.image.width)
        resize_layout.addWidget(self.resize_w_spin)
        resize_layout.addWidget(QLabel("H"))
        self.resize_h_spin.setValue(self.document.image.height)
        resize_layout.addWidget(self.resize_h_spin)
        self.resize_anchor_combo = QComboBox()
        self.resize_anchor_combo.addItems([
            "Top-Left", "Top-Center", "Top-Right",
            "Center-Left", "Center", "Center-Right",
            "Bottom-Left", "Bottom-Center", "Bottom-Right",
        ])
        self.resize_anchor_combo.setCurrentIndex(0)
        resize_layout.addWidget(self.resize_anchor_combo)
        resize_layout.addWidget(self.resize_canvas_button)
        self.trim_transparent_button = QPushButton("Trim")
        resize_layout.addWidget(self.trim_transparent_button)
        controls_layout.addWidget(resize_group)

        controls_layout.addStretch(1)

        controls_panel = QWidget()
        controls_panel.setLayout(controls_layout)

        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setWidget(controls_panel)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls_scroll.setMinimumWidth(220)

        if self._headless:
            canvas_host = QLabel(
                "Headless mode\n\n"
                "Canvas rendering is disabled for this document.\n"
                "Palette, ramp, replace, and save workflows remain available."
            )
            canvas_host.setAlignment(Qt.AlignmentFlag.AlignCenter)
            canvas_host.setMinimumSize(360, 360)
            canvas_host.setStyleSheet("border: 1px solid #444; color: #bbb; padding: 24px;")
        else:
            scroll = QScrollArea()
            # Keep widgetResizable off so the canvas's sizeHint (image + pan margin)
            # is always honored. With widgetResizable=True, Qt would clamp the
            # canvas to the viewport size and there would be no scrollable area.
            scroll.setWidgetResizable(False)
            scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
            scroll.setWidget(self.canvas)
            self.canvas.set_scroll_area(scroll)
            canvas_host = scroll

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(canvas_host)
        splitter.addWidget(controls_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([700, 380])
        self.setCentralWidget(splitter)

    def _connect_signals(self) -> None:
        self.zoom_spin.valueChanged.connect(self.canvas.set_zoom)
        self.canvas.zoom_changed.connect(self.zoom_spin.setValue)
        self.paint_radio.toggled.connect(self._on_mode_changed)
        self.select_radio.toggled.connect(self._on_mode_changed)
        self.stamp_radio.toggled.connect(self._on_mode_changed)
        self.flood_erase_radio.toggled.connect(self._on_mode_changed)
        self.iso_guide_radio.toggled.connect(self._on_mode_changed)
        self.draw_selection_checkbox.toggled.connect(self._on_draw_selection_toggled)
        self.copy_stamp_button.clicked.connect(self._copy_as_stamp)
        self.flip_stamp_h_button.clicked.connect(self._flip_stamp_horizontal)
        self.flip_stamp_v_button.clicked.connect(self._flip_stamp_vertical)
        self.copy_selection_layer_button.clicked.connect(self._copy_selection_to_new_layer)
        self.restore_source_button.clicked.connect(self._restore_source_selection)
        self.import_sprite_button.clicked.connect(self._import_sprite_as_stamp)
        self.iso_slash_button.clicked.connect(lambda: self._show_isometric_guide("/"))
        self.iso_backslash_button.clicked.connect(lambda: self._show_isometric_guide("\\"))
        self.iso_clear_button.clicked.connect(self.canvas.clear_isometric_guide)
        self.iso_guide_steps_spin.valueChanged.connect(self.canvas.set_isometric_guide_steps)
        self.canvas.isometric_guide_changed.connect(self._on_isometric_guide_changed)
        self.opacity_slider.valueChanged.connect(self.opacity_spin.setValue)
        self.opacity_spin.valueChanged.connect(self.opacity_slider.setValue)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.custom_color_button.clicked.connect(self.pick_color)
        self.transparent_button.clicked.connect(self.use_transparent_color)
        self.transparent_display_button.clicked.connect(self._pick_transparent_display_color)
        self.load_palette_button.clicked.connect(self.load_palette)
        self.add_palette_from_file_button.clicked.connect(self.add_palette_from_file)
        self.palette_from_current_button.clicked.connect(self.palette_from_current_image)
        self.add_palette_from_current_button.clicked.connect(self.add_palette_from_current_image)
        self.export_palette_button.clicked.connect(self.export_palette)
        self.sort_palette_button.clicked.connect(self.organize_palette)
        self.palette_grid_cols_spin.valueChanged.connect(self._resize_palette_grid)
        self.palette_grid_rows_spin.valueChanged.connect(self._resize_palette_grid)
        self.add_palette_to_grid_button.clicked.connect(self._add_palette_to_grid)
        self.calculate_ramp_button.clicked.connect(self._calculate_ramp_from_grid)
        self.apply_ramp_replace_button.clicked.connect(self._apply_grid_ramp_replacement)
        self.export_palette_grid_button.clicked.connect(self.export_palette_grid)
        self.clear_palette_grid_button.clicked.connect(self._clear_palette_grid)
        self.palette_grid_widget.cell_color_dropped.connect(self._on_palette_grid_color_dropped)
        self.palette_grid_widget.cell_cleared.connect(self._on_palette_grid_cell_cleared)
        self.palette_grid_widget.cell_clicked.connect(self._set_current_color)
        self.pick_replace_target_button.clicked.connect(self._pick_replace_target_color)
        self.transparent_replace_button.clicked.connect(self._replace_target_with_transparent)
        self.replace_with_color_button.clicked.connect(self._replace_target_with_color)
        self.replace_with_button.clicked.connect(self._pick_replace_with_color)
        self.add_replace_with_to_palette_button.clicked.connect(self._add_replace_with_to_palette)
        self.transparent_replace_clear_button.clicked.connect(self._clear_transparent_replace_target)
        self.white_to_transparency_button.clicked.connect(self._replace_near_white_with_transparent)
        self.calculate_change_button.clicked.connect(self._calculate_color_shift)
        self.change_target_button.clicked.connect(self._apply_color_shift_to_target)
        self.transparent_replace_preview.color_dropped.connect(self._drop_replace_target_color)
        self.replace_with_preview.color_dropped.connect(self._drop_replace_with_color)
        self.save_asset_button.clicked.connect(self.save_to_asset_tray)
        self.shade_ramp_button.clicked.connect(self._generate_shade_ramp)
        self.shade_add_all_button.clicked.connect(self._add_ramp_to_palette)
        self.apply_shading_button.clicked.connect(self._apply_shading_from_ramp)
        self.shading_mode_combo.currentIndexChanged.connect(self._update_shading_mode_controls)
        self._update_shading_mode_controls()
        self.resize_canvas_button.clicked.connect(self._resize_canvas)
        self.trim_transparent_button.clicked.connect(self._trim_transparent)
        self.morph_pick_button.clicked.connect(self._pick_morph_color)
        self.morph_color_preview.color_dropped.connect(self._drop_morph_color)
        self.dilate_button.clicked.connect(self._dilate_morph_color)
        self.erode_button.clicked.connect(self._erode_morph_color)
        self.flood_boundary_pick_button.clicked.connect(self._pick_flood_boundary_color)
        self.flood_boundary_preview.color_dropped.connect(self._drop_flood_boundary_color)
        self.canvas.flood_erase_requested.connect(self._flood_erase_at)
        self.canvas.image_changed.connect(self._on_canvas_image_changed)
        self.canvas.selection_changed.connect(self.selection_summary.setText)
        self.canvas.status_changed.connect(self.statusBar().showMessage)
        self.layer_panel.layers_changed.connect(self._on_layers_changed)
        self._update_transparent_replace_preview()
        self._update_replace_with_preview()
        self._update_color_shift_summary()
        self._update_morph_color_preview()
        self._update_flood_boundary_preview()

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

        # Opening a new image replaces the entire layer stack with a single
        # fresh layer so the document's canvas dimensions match the loaded
        # image and the user starts with a clean slate.
        from src.core.pixel_document import Layer
        self.document.layers = [Layer(name="Layer 1", image=image)]
        self.document.active_layer_index = 0
        self.document.name = Path(path).stem
        self.document.selected_pixels.clear()
        self.document.selection_rect = None
        initial_zoom = self._initial_zoom_for(self.document)
        self.zoom_spin.setValue(initial_zoom)
        self.canvas.set_zoom(initial_zoom)
        self.canvas.set_document(self.document)
        self.layer_panel.refresh()
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
            self.document.palette = load_palette_from_image(
                path,
                max_colors=64 if self.reduce_palette_import_checkbox.isChecked() else None,
            )
        except Exception as exc:  # pragma: no cover - GUI feedback
            QMessageBox.critical(self, "Palette load failed", str(exc))
            return
        self._refresh_palette_buttons()
        self.statusBar().showMessage(
            f"Loaded {len(self.document.palette)} colors from {Path(path).name}"
        )

    def save_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Pixel Image",
            f"{self.document.name}.png",
            "PNG Image (*.png)",
        )
        if not path:
            return
        # Flatten all visible layers in stack order so the saved PNG is a
        # single merged image regardless of how many layers the document has.
        save_image(self.document.composite_visible(), path)
        layer_count = sum(1 for layer in self.document.layers if layer.visible)
        self.statusBar().showMessage(
            f"Saved {Path(path).name} (flattened {layer_count} visible "
            f"layer{'s' if layer_count != 1 else ''})"
        )

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
            incoming = load_palette_from_image(
                path,
                max_colors=64 if self.reduce_palette_import_checkbox.isChecked() else None,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Palette load failed", str(exc))
            return
        self.document.palette = merge_palettes(self.document.palette, incoming)
        self._refresh_palette_buttons()
        self.statusBar().showMessage(
            f"Merged colors from {Path(path).name} ({len(self.document.palette)} total)"
        )

    def palette_from_current_image(self) -> None:
        self.document.palette = self._palette_colors_from_current_image()
        self._refresh_palette_buttons()
        self.statusBar().showMessage(
            f"Loaded {len(self.document.palette)} colors from current editor image"
        )

    def add_palette_from_current_image(self) -> None:
        incoming = self._palette_colors_from_current_image()
        self.document.palette = merge_palettes(self.document.palette, incoming)
        self._refresh_palette_buttons()
        self.statusBar().showMessage("Added colors from current image to palette")

    def _palette_colors_from_current_image(self) -> list[tuple[int, int, int, int]]:
        if self.reduce_palette_import_checkbox.isChecked():
            return palette_from_image(self.document.image, max_colors=64)
        return all_colors_from_image(self.document.image)

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

    def organize_palette(self) -> None:
        if not self.document.palette:
            self.statusBar().showMessage("No palette to organize")
            return
        mode = "brightness" if self.sort_palette_combo.currentText() == "Brightness" else "hue"
        self.document.palette = sort_palette(self.document.palette, mode)
        self._refresh_palette_buttons()
        self.statusBar().showMessage(f"Palette organized by {mode}")

    def export_palette_grid(self) -> None:
        columns, rows = self.palette_grid_widget.dimensions()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PixelForge Palette Grid",
            f"{self.document.name}_palette_grid.png",
            "PNG Image (*.png)",
        )
        if not path:
            return
        export_palette_grid(
            self.palette_grid_widget.colors(),
            columns,
            rows,
            path,
        )
        filled = sum(color is not None for color in self.palette_grid_widget.colors())
        self.statusBar().showMessage(
            f"Exported palette grid to {Path(path).name} ({filled}/{columns * rows} filled)"
        )

    def flip_horizontal(self) -> None:
        # Canvas-orientation operation: apply uniformly to every layer so they
        # all stay aligned in the same coordinate system.
        self.document.apply_to_all_layers(flip_image_horizontal)
        self._reset_selection_after_transform()
        self.statusBar().showMessage("Flipped image horizontally")

    def flip_vertical(self) -> None:
        self.document.apply_to_all_layers(flip_image_vertical)
        self._reset_selection_after_transform()
        self.statusBar().showMessage("Flipped image vertically")

    def rotate_clockwise(self) -> None:
        self.document.apply_to_all_layers(rotate_image_clockwise)
        self._reset_selection_after_transform()
        self.statusBar().showMessage("Rotated image 90 degrees clockwise")

    def rotate_counterclockwise(self) -> None:
        self.document.apply_to_all_layers(rotate_image_counterclockwise)
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

    def undo_last_edit(self) -> None:
        if not undo_image_history(self.document):
            self.statusBar().showMessage("Nothing to undo")
            return
        self._reset_selection_after_transform()
        self.statusBar().showMessage("Undid last edit")

    def _restore_source_selection(self) -> None:
        if self._restore_reference is None:
            return
        points = self.document.selected_points()
        if not points:
            self.statusBar().showMessage("Select one or more pixels to restore")
            return
        push_image_history(self.document)
        target = self.document.image.convert("RGBA").copy()
        target_pixels = target.load()
        source_pixels = self._restore_reference.load()
        for x, y in points:
            target_pixels[x, y] = source_pixels[x, y]
        self.document.image = target
        self.canvas.update()
        self.statusBar().showMessage(
            f"Restored {len(points)} pixel{'s' if len(points) != 1 else ''} from extraction"
        )

    def redo_last_edit(self) -> None:
        if not redo_image_history(self.document):
            self.statusBar().showMessage("Nothing to redo")
            return
        self._reset_selection_after_transform()
        self.statusBar().showMessage("Redid last edit")

    # Backwards-compatible alias for the previous, tone-specific name.
    undo_tone_adjustment = undo_last_edit

    def save_to_asset_tray(self) -> None:
        # Asset tray receives the flattened composite of all visible layers,
        # mirroring the save-to-PNG flow.
        self.asset_save_requested.emit(self.document.name, self.document.composite_visible())
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
        pass

    def _on_layers_changed(self) -> None:
        """Active layer or layer stack changed in the panel: redraw the
        composite and reflect the new active layer in dependent widgets."""
        self.canvas.invalidate_render_cache()

    def _on_mode_changed(self) -> None:
        if self.paint_radio.isChecked():
            mode = "paint"
        elif self.stamp_radio.isChecked():
            mode = "stamp"
        elif self.flood_erase_radio.isChecked():
            mode = "flood_erase"
            if self._flood_boundary_color is None:
                self.statusBar().showMessage(
                    "Flood Erase: pick a boundary color (gold/yellow ring) below first"
                )
        elif self.iso_guide_radio.isChecked():
            mode = "iso_guide"
        else:
            mode = "select"
        self.canvas.set_mode(mode)

    def _on_draw_selection_toggled(self, checked: bool) -> None:
        if checked and not self.select_radio.isChecked():
            self.select_radio.setChecked(True)
        self.canvas.set_draw_selection_enabled(checked)

    def _show_isometric_guide(self, direction: str) -> None:
        if not self.iso_guide_radio.isChecked():
            self.iso_guide_radio.setChecked(True)
        self.canvas.show_isometric_guide(direction, self.iso_guide_steps_spin.value())

    def _on_isometric_guide_changed(self, _direction: str, steps: int) -> None:
        self.iso_clear_button.setEnabled(steps > 0)
        if steps <= 0:
            return
        was_blocked = self.iso_guide_steps_spin.blockSignals(True)
        self.iso_guide_steps_spin.setValue(steps)
        self.iso_guide_steps_spin.blockSignals(was_blocked)

    def _reset_selection_after_transform(self) -> None:
        self.document.selected_pixels.clear()
        self.document.selection_rect = None
        self.canvas.set_document(self.document)
        self.selection_summary.setText("No selection")

    def _resize_palette_grid(self) -> None:
        columns = self.palette_grid_cols_spin.value()
        rows = self.palette_grid_rows_spin.value()
        self.palette_grid_widget.set_dimensions(columns, rows)

    def _on_palette_grid_color_dropped(
        self,
        index: int,
        color: tuple[int, int, int, int],
    ) -> None:
        self.palette_grid_widget.set_cell_color(index, color)
        slot = index + 1
        self.statusBar().showMessage(f"Placed color into palette grid slot {slot}")

    def _on_palette_grid_cell_cleared(self, index: int) -> None:
        if self.palette_grid_widget.colors()[index] is None:
            return
        self.palette_grid_widget.clear_cell(index)
        slot = index + 1
        self.statusBar().showMessage(f"Cleared palette grid slot {slot}")

    def _clear_palette_grid(self) -> None:
        self.palette_grid_widget.clear_all()
        self.statusBar().showMessage("Cleared palette grid")

    def _add_palette_to_grid(self) -> None:
        if not self.document.palette:
            self.statusBar().showMessage("No palette to add to grid")
            return
        placed = self.palette_grid_widget.append_colors(self.document.palette)
        if placed == 0:
            self.statusBar().showMessage("Palette grid is full")
            return
        self.statusBar().showMessage(f"Added {placed} palette color{'s' if placed != 1 else ''} to grid")

    def _calculate_ramp_from_grid(self) -> None:
        source_ramp = self.palette_grid_widget.ordered_colors(filled_only=True)
        if not source_ramp:
            self.statusBar().showMessage("Add a ramp to the grid first")
            return
        if self._transparent_replace_target is None:
            self.statusBar().showMessage("Choose a replace target color first")
            return

        if len(source_ramp) == 1:
            projected_ramp = [self._transparent_replace_target]
        else:
            projected_ramp = apply_ramp_shifts(
                self._transparent_replace_target,
                calculate_ramp_shifts(source_ramp),
            )

        placed = self.palette_grid_widget.append_colors(projected_ramp)
        if placed == 0:
            self.statusBar().showMessage("Palette grid is full")
            return
        self.statusBar().showMessage(
            f"Calculated ramp from target and appended {placed} color{'s' if placed != 1 else ''} to grid"
        )

    def _apply_grid_ramp_replacement(self) -> None:
        ramp_colors = self.palette_grid_widget.ordered_colors(filled_only=True)
        if len(ramp_colors) < 2 or len(ramp_colors) % 2 != 0:
            self.statusBar().showMessage("Grid needs two equal-sized ramps")
            return

        midpoint = len(ramp_colors) // 2
        first_ramp = ramp_colors[:midpoint]
        second_ramp = ramp_colors[midpoint:]
        replacements = {
            source: target
            for source, target in zip(first_ramp, second_ramp)
            if source != target
        }
        if not replacements:
            self.statusBar().showMessage("No ramp replacements to apply")
            return

        replaced, count = replace_colors(self.document.image, replacements)
        if count == 0:
            self.statusBar().showMessage("No pixels matched the first ramp colors")
            return

        push_image_history(self.document)
        self.document.image = replaced
        self.canvas.invalidate_render_cache()
        self.statusBar().showMessage(
            f"Replaced {count} pixel{'s' if count != 1 else ''} using ramp 1 -> ramp 2"
        )

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
            btn.setMinimumWidth(52)
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
        self.apply_shading_button.setEnabled(True)
        self.statusBar().showMessage(
            "Generated 6-stop ramp: three cool shadows, exact base, and two warm lights"
        )

    def _add_ramp_to_palette(self) -> None:
        if not self._current_ramp:
            return
        incoming = [rgba for _, rgba in self._current_ramp]
        self.document.palette = merge_palettes(self.document.palette, incoming)
        self._refresh_palette_buttons()
        self.statusBar().showMessage(f"Added {len(incoming)} ramp colors to palette")

    def _update_shading_mode_controls(self) -> None:
        """Show the angle spinbox only when Directional mode is selected."""
        is_directional = self.shading_mode_combo.currentData() == "directional"
        self.shading_angle_label.setVisible(is_directional)
        self.shading_angle_spin.setVisible(is_directional)

    def _apply_shading_from_ramp(self) -> None:
        if not self._current_ramp:
            self.statusBar().showMessage("Generate a Shade Ramp first")
            return
        ramp_colors = [rgba for _, rgba in self._current_ramp]
        mode = self.shading_mode_combo.currentData()
        if mode == "directional":
            angle = float(self.shading_angle_spin.value())
            result, recolored = apply_directional_shading(
                self.document.image, ramp_colors, light_angle_degrees=angle
            )
            mode_label = f"Directional Shading ({int(angle)} deg)"
        else:
            result, recolored = apply_radial_shading(self.document.image, ramp_colors)
            mode_label = "Radial Shading"
        if recolored == 0:
            self.statusBar().showMessage(f"{mode_label}: no filled pixels to recolor")
            return
        push_image_history(self.document)
        self.document.image = result
        self.canvas.invalidate_render_cache()
        self.statusBar().showMessage(
            f"{mode_label}: recolored {recolored} pixel{'s' if recolored != 1 else ''} "
            f"along {len(ramp_colors)}-stop ramp"
        )

    def _import_sprite_as_stamp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Sprite",
            "",
            "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        try:
            sprite = load_image(path)
        except Exception as exc:  # pragma: no cover - GUI feedback
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        self.canvas.set_stamp_image(sprite)
        self._update_stamp_controls()
        self.stamp_radio.setChecked(True)
        self.statusBar().showMessage(
            f"Sprite ready at native size ({sprite.width}x{sprite.height}px) — "
            "move it over the canvas and click to place"
        )

    def _copy_as_stamp(self) -> None:
        if self.canvas.copy_stamp():
            stamp = self.canvas.stamp_image()
            w, h = stamp.size if stamp else (0, 0)
            self._update_stamp_controls()
            self.stamp_radio.setChecked(True)
            self.statusBar().showMessage(f"Stamp copied ({w}x{h}px) — click to place")
        else:
            self.statusBar().showMessage("Select pixels first (use Select mode to drag or Ctrl+click)")

    def _flip_stamp_horizontal(self) -> None:
        if not self.canvas.flip_stamp_horizontal():
            self.statusBar().showMessage("Copy a selection as a stamp first")
            self._update_stamp_controls()
            return
        self._show_stamp_transform_status("horizontally")

    def _flip_stamp_vertical(self) -> None:
        if not self.canvas.flip_stamp_vertical():
            self.statusBar().showMessage("Copy a selection as a stamp first")
            self._update_stamp_controls()
            return
        self._show_stamp_transform_status("vertically")

    def _show_stamp_transform_status(self, direction: str) -> None:
        stamp = self.canvas.stamp_image()
        w, h = stamp.size if stamp else (0, 0)
        self._update_stamp_controls()
        self.stamp_radio.setChecked(True)
        self.statusBar().showMessage(f"Stamp flipped {direction} ({w}x{h}px)")

    def _update_stamp_controls(self) -> None:
        has_stamp = self.canvas.has_stamp()
        self.flip_stamp_h_button.setEnabled(has_stamp)
        self.flip_stamp_v_button.setEnabled(has_stamp)

    def _copy_selection_to_new_layer(self) -> None:
        result = self.document.copy_selection_to_new_layer()
        if result is None:
            self.statusBar().showMessage("Select pixels first (use Select mode to drag or Ctrl+click)")
            return
        new_index, count = result
        self.layer_panel.refresh()
        self.canvas.invalidate_render_cache()
        layer_name = self.document.layers[new_index].name
        pixel_word = "pixel" if count == 1 else "pixels"
        self.statusBar().showMessage(
            f"Copied {count} selected {pixel_word} to new layer '{layer_name}'"
        )

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
        self.canvas.invalidate_render_cache()
        self.statusBar().showMessage(f"Replaced {count} pixel{'s' if count != 1 else ''} with transparent")

    def _replace_near_white_with_transparent(self) -> None:
        percent = self.white_transparency_percent_spin.value()
        tolerance = rgb_distance_tolerance_from_percent(percent)
        replaced, count = replace_similar_color_with_transparent(
            self.document.image,
            (255, 255, 255, 255),
            tolerance,
        )
        if count == 0:
            self.statusBar().showMessage(
                f"No pixels found within {percent}% of pure white"
            )
            return

        push_image_history(self.document)
        self.document.image = replaced
        self.canvas.invalidate_render_cache()
        self.statusBar().showMessage(
            f"Cleared {count} near-white pixel{'s' if count != 1 else ''} "
            f"within {percent}% of pure white"
        )

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

    def _drop_replace_target_color(self, color: tuple[int, int, int, int]) -> None:
        if color[3] == 0:
            self._clear_transparent_replace_target(show_message=False)
            self.statusBar().showMessage("Transparent palette color cannot be used as a replace target")
            return
        self._transparent_replace_target = color
        self._update_transparent_replace_preview()
        r, g, b, a = color
        self.statusBar().showMessage(f"Dropped replace target #{r:02X}{g:02X}{b:02X} / {a}")

    def _drop_replace_with_color(self, color: tuple[int, int, int, int]) -> None:
        self._replace_with_color = color
        self._update_replace_with_preview()
        r, g, b, a = color
        self.statusBar().showMessage(f"Dropped replace-with color #{r:02X}{g:02X}{b:02X} / {a}")

    def _add_replace_with_to_palette(self) -> None:
        self.document.palette = add_color_to_palette(self.document.palette, self._replace_with_color)
        self._refresh_palette_buttons()
        r, g, b, a = self._replace_with_color
        self.statusBar().showMessage(
            f"Added replace-with color #{r:02X}{g:02X}{b:02X} / {a} to palette"
        )

    def _calculate_color_shift(self) -> None:
        if self._transparent_replace_target is None:
            self.statusBar().showMessage("Choose a replace target color first")
            return
        self._stored_color_shift = calculate_color_shift(
            self._transparent_replace_target,
            self._replace_with_color,
        )
        self._update_color_shift_summary()
        self.statusBar().showMessage("Stored HSVA color change from target to replace-with color")

    def _apply_color_shift_to_target(self) -> None:
        if self._stored_color_shift is None:
            self.statusBar().showMessage("Calculate a color change first")
            return
        if self._transparent_replace_target is None:
            self.statusBar().showMessage("Choose a replace target color first")
            return
        self._replace_with_color = apply_color_shift(
            self._transparent_replace_target,
            self._stored_color_shift,
        )
        self._update_replace_with_preview()
        r, g, b, a = self._replace_with_color
        self.statusBar().showMessage(
            f"Applied stored change to target -> #{r:02X}{g:02X}{b:02X} / {a}"
        )

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
        self.canvas.invalidate_render_cache()
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
        self._update_color_shift_summary()
        if color is None:
            self.transparent_replace_preview.set_color(None)
            self.transparent_replace_preview.setText("No replace target")
            self.transparent_replace_preview.setStyleSheet("border: 1px solid #555; color: #bbb;")
            return
        self.transparent_replace_preview.set_color(color)
        red, green, blue, alpha = color
        luma = 0.299 * red + 0.587 * green + 0.114 * blue
        text_color = "#000" if luma > 128 else "#fff"
        self.transparent_replace_preview.setText(f"Target: #{red:02X}{green:02X}{blue:02X} / {alpha}")
        self.transparent_replace_preview.setStyleSheet(
            f"background: rgba({red}, {green}, {blue}, {alpha});"
            f"color: {text_color}; border: 1px solid #555;"
        )

    def _update_replace_with_preview(self) -> None:
        self.replace_with_preview.set_color(self._replace_with_color)
        red, green, blue, alpha = self._replace_with_color
        luma = 0.299 * red + 0.587 * green + 0.114 * blue
        text_color = "#000" if luma > 128 else "#fff"
        self.replace_with_preview.setText(f"Replace With: #{red:02X}{green:02X}{blue:02X} / {alpha}")
        self.replace_with_preview.setStyleSheet(
            f"background: rgba({red}, {green}, {blue}, {alpha});"
            f"color: {text_color}; border: 1px solid #555;"
        )

    def _pick_morph_color(self) -> None:
        initial = QColor(*self._morph_color) if self._morph_color else QColor(*self.document.current_color)
        dialog = QColorDialog(initial, self)
        dialog.setWindowTitle("Pick Source Color for Dilate/Erode")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        if dialog.exec() != QColorDialog.DialogCode.Accepted:
            return
        color = dialog.selectedColor()
        self._morph_color = (color.red(), color.green(), color.blue(), color.alpha())
        self._update_morph_color_preview()
        r, g, b, a = self._morph_color
        self.statusBar().showMessage(f"Dilate/Erode source #{r:02X}{g:02X}{b:02X} / {a}")

    def _drop_morph_color(self, color: tuple[int, int, int, int]) -> None:
        if color[3] < 50:
            self.statusBar().showMessage("Transparent palette color cannot be the dilate/erode source")
            return
        self._morph_color = color
        self._update_morph_color_preview()
        r, g, b, a = color
        self.statusBar().showMessage(f"Dropped dilate/erode source #{r:02X}{g:02X}{b:02X} / {a}")

    def _update_morph_color_preview(self) -> None:
        color = self._morph_color
        has_color = color is not None
        self.dilate_button.setEnabled(has_color)
        self.erode_button.setEnabled(has_color)
        if not has_color:
            self.morph_color_preview.set_color(None)
            self.morph_color_preview.setText("No source color")
            self.morph_color_preview.setStyleSheet("border: 1px solid #555; color: #bbb;")
            return
        self.morph_color_preview.set_color(color)
        red, green, blue, alpha = color
        luma = 0.299 * red + 0.587 * green + 0.114 * blue
        text_color = "#000" if luma > 128 else "#fff"
        self.morph_color_preview.setText(f"Source: #{red:02X}{green:02X}{blue:02X} / {alpha}")
        self.morph_color_preview.setStyleSheet(
            f"background: rgba({red}, {green}, {blue}, {alpha});"
            f"color: {text_color}; border: 1px solid #555;"
        )

    def _dilate_morph_color(self) -> None:
        if self._morph_color is None:
            self.statusBar().showMessage("Pick a source color to dilate first")
            return
        thickness = self.morph_thickness_spin.value()
        result, filled = dilate_color(self.document.image, self._morph_color, thickness)
        if filled == 0:
            self.statusBar().showMessage("Dilate: no transparent pixels were adjacent to the source color")
            return
        push_image_history(self.document)
        self.document.image = result
        self.canvas.invalidate_render_cache()
        r, g, b, a = self._morph_color
        self.statusBar().showMessage(
            f"Dilated #{r:02X}{g:02X}{b:02X} by {thickness}px ({filled} pixel{'s' if filled != 1 else ''} filled)"
        )

    def _erode_morph_color(self) -> None:
        if self._morph_color is None:
            self.statusBar().showMessage("Pick a source color to erode first")
            return
        thickness = self.morph_thickness_spin.value()
        result, cleared = erode_color(self.document.image, self._morph_color, thickness)
        if cleared == 0:
            self.statusBar().showMessage("Erode: no source pixels were adjacent to non-source neighbors")
            return
        push_image_history(self.document)
        self.document.image = result
        self.canvas.invalidate_render_cache()
        r, g, b, a = self._morph_color
        self.statusBar().showMessage(
            f"Eroded #{r:02X}{g:02X}{b:02X} by {thickness}px ({cleared} pixel{'s' if cleared != 1 else ''} cleared)"
        )

    def _pick_flood_boundary_color(self) -> None:
        initial = (
            QColor(*self._flood_boundary_color)
            if self._flood_boundary_color
            else QColor("#e8a317")
        )
        dialog = QColorDialog(initial, self)
        dialog.setWindowTitle("Pick Flood-Erase Boundary Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        if dialog.exec() != QColorDialog.DialogCode.Accepted:
            return
        color = dialog.selectedColor()
        self._flood_boundary_color = (color.red(), color.green(), color.blue(), color.alpha())
        self._update_flood_boundary_preview()
        r, g, b, a = self._flood_boundary_color
        self.statusBar().showMessage(f"Flood-erase boundary #{r:02X}{g:02X}{b:02X} / {a}")

    def _drop_flood_boundary_color(self, color: tuple[int, int, int, int]) -> None:
        if color[3] < 50:
            self.statusBar().showMessage("Transparent palette color cannot be a flood-erase boundary")
            return
        self._flood_boundary_color = color
        self._update_flood_boundary_preview()
        r, g, b, a = color
        self.statusBar().showMessage(f"Dropped flood-erase boundary #{r:02X}{g:02X}{b:02X} / {a}")

    def _update_flood_boundary_preview(self) -> None:
        color = self._flood_boundary_color
        if color is None:
            self.flood_boundary_preview.set_color(None)
            self.flood_boundary_preview.setText("No boundary color")
            self.flood_boundary_preview.setStyleSheet("border: 1px solid #555; color: #bbb;")
            return
        self.flood_boundary_preview.set_color(color)
        red, green, blue, alpha = color
        luma = 0.299 * red + 0.587 * green + 0.114 * blue
        text_color = "#000" if luma > 128 else "#fff"
        self.flood_boundary_preview.setText(
            f"Boundary: #{red:02X}{green:02X}{blue:02X} / {alpha}"
        )
        self.flood_boundary_preview.setStyleSheet(
            f"background: rgba({red}, {green}, {blue}, {alpha});"
            f"color: {text_color}; border: 1px solid #555;"
        )

    def _flood_erase_at(self, x: int, y: int) -> None:
        if self._flood_boundary_color is None:
            self.statusBar().showMessage("Flood Erase: pick a boundary color first")
            return
        hue_tol = float(self.flood_hue_tolerance_spin.value())
        min_sat = self.flood_min_saturation_spin.value() / 100.0
        result, cleared = flood_erase_outside_color(
            self.document.image,
            (x, y),
            self._flood_boundary_color,
            hue_tolerance_degrees=hue_tol,
            min_saturation=min_sat,
            eight_connected=True,
        )
        if cleared == 0:
            self.statusBar().showMessage(
                f"Flood Erase: nothing to clear from ({x}, {y}) "
                "(click landed inside the boundary, or the region was already transparent)"
            )
            return
        push_image_history(self.document)
        self.document.image = result
        self.canvas.invalidate_render_cache()
        self.statusBar().showMessage(
            f"Flood Erase from ({x}, {y}): cleared {cleared} pixel{'s' if cleared != 1 else ''}"
        )

    def _update_color_shift_summary(self) -> None:
        self.calculate_change_button.setEnabled(self._transparent_replace_target is not None)
        self.change_target_button.setEnabled(
            self._transparent_replace_target is not None and self._stored_color_shift is not None
        )
        if self._stored_color_shift is None:
            self.color_shift_summary.setText("Delta: none")
            self.color_shift_summary.setStyleSheet("border: 1px solid #555; color: #bbb; padding: 4px;")
            return
        shift = self._stored_color_shift
        self.color_shift_summary.setText(
            "Delta:\n"
            f"H {shift.hue_degrees:+.1f} deg\n"
            f"S {shift.saturation_delta * 100:+.1f}%\n"
            f"V {shift.value_delta * 100:+.1f}%\n"
            f"A {shift.alpha_delta:+d}"
        )
        self.color_shift_summary.setStyleSheet("border: 1px solid #555; padding: 4px;")

    def _resize_canvas(self) -> None:
        new_w = self.resize_w_spin.value()
        new_h = self.resize_h_spin.value()
        old_w = self.document.width
        old_h = self.document.height
        if new_w == old_w and new_h == old_h:
            self.statusBar().showMessage("Canvas size unchanged")
            return

        from PIL import Image
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
        ox = int((new_w - old_w) * ax)
        oy = int((new_h - old_h) * ay)

        def resize_one(img: Image.Image) -> Image.Image:
            out = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
            out.paste(img, (ox, oy))
            return out

        self.document.apply_to_all_layers(resize_one)
        self._reset_selection_after_transform()
        self.statusBar().showMessage(
            f"Canvas resized to {new_w}x{new_h} (anchor: {anchor}); "
            f"applied to {len(self.document.layers)} layer"
            f"{'s' if len(self.document.layers) != 1 else ''}"
        )

    def _trim_transparent(self) -> None:
        # Trim based on the bbox of the *composite* so all visible layers
        # together drive the crop. Then crop every layer to the same bbox so
        # they remain aligned.
        composite = self.document.composite_visible()
        bbox = composite.getbbox()
        if bbox is None:
            self.statusBar().showMessage("Canvas is fully transparent, nothing to trim")
            return
        left, top, right, bottom = bbox
        if left == 0 and top == 0 and right == self.document.width and bottom == self.document.height:
            self.statusBar().showMessage("No transparent border to trim")
            return
        self.document.apply_to_all_layers(lambda img: img.crop(bbox).copy())
        self.resize_w_spin.setValue(self.document.width)
        self.resize_h_spin.setValue(self.document.height)
        self._reset_selection_after_transform()
        self.statusBar().showMessage(
            f"Trimmed to {self.document.width}x{self.document.height} "
            f"(applied to {len(self.document.layers)} layers)"
        )
