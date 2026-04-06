from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, Signal, QSize
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from PIL import Image

from src.core.image_io import load_image, save_image
from src.core.pixel_document import PixelDocument, create_blank_pixel_map
from src.core.qt_image import pil_image_to_qimage
from src.ui.pixel_editor_window import ClickableColorButton
from src.ui.pixel_grid_canvas import PixelGridCanvas


def _cell_average_from_rect(image, left: int, top: int, right: int, bottom: int) -> tuple[int, int, int, int]:
    left = max(0, min(left, image.width - 1))
    top = max(0, min(top, image.height - 1))
    right = max(left + 1, min(right, image.width))
    bottom = max(top + 1, min(bottom, image.height))
    chunk = image.crop((left, top, right, bottom)).convert("RGBA")
    r = g = b = a = 0
    n = 0
    for y in range(chunk.height):
        for x in range(chunk.width):
            px = chunk.getpixel((x, y))
            r += px[0]
            g += px[1]
            b += px[2]
            a += px[3]
            n += 1
    if n == 0:
        return 0, 0, 0, 0
    return (r // n, g // n, b // n, a // n)


class ReferenceImageWidget(QWidget):
    """Shows a reference bitmap scaled to fit with a configurable cell grid; click samples a cell."""

    cell_clicked = Signal(int, int, tuple)  # col, row, rgba

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image = None
        self._cell_w = 16
        self._cell_h = 16
        self._offset_x = 0
        self._offset_y = 0
        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)

    def set_reference(self, image) -> None:
        self._image = image
        self.update()

    def set_cell_size(self, cw: int, ch: int) -> None:
        self._cell_w = max(1, cw)
        self._cell_h = max(1, ch)
        self.update()

    def set_grid_offset(self, ox: int, oy: int) -> None:
        self._offset_x = max(0, ox)
        self._offset_y = max(0, oy)
        self.update()

    def has_reference(self) -> bool:
        return self._image is not None

    @property
    def reference_image(self):
        return self._image

    def grid_dimensions(self) -> tuple[int, int]:
        if self._image is None:
            return 0, 0
        usable_w = max(0, self._image.width - self._offset_x)
        usable_h = max(0, self._image.height - self._offset_y)
        cols = usable_w // self._cell_w
        rows = usable_h // self._cell_h
        return cols, rows

    def sizeHint(self) -> QSize:
        return QSize(480, 480)

    def _scale_and_origin(self) -> tuple[float, float, float]:
        if self._image is None:
            return 1.0, 0.0, 0.0
        margin = 8
        aw = max(1, self.width() - 2 * margin)
        ah = max(1, self.height() - 2 * margin)
        scale = min(aw / self._image.width, ah / self._image.height, 1.0)
        disp_w = self._image.width * scale
        disp_h = self._image.height * scale
        ox = margin + (aw - disp_w) / 2
        oy = margin + (ah - disp_h) / 2
        return scale, ox, oy

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1a1a1a"))
        if self._image is None:
            painter.setPen(QColor("#888"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Open a reference image")
            return

        qimg = pil_image_to_qimage(self._image)
        scale, ox, oy = self._scale_and_origin()
        target = QRect(int(ox), int(oy), int(math.ceil(self._image.width * scale)), int(math.ceil(self._image.height * scale)))
        painter.drawImage(target, qimg)

        painter.setPen(QPen(QColor("#4af"), 1))
        cw, ch = self._cell_w * scale, self._cell_h * scale
        if cw < 1 or ch < 1:
            return
        gx0 = ox + self._offset_x * scale
        gy0 = oy + self._offset_y * scale
        cols, rows = self.grid_dimensions()
        for c in range(cols + 1):
            x = gx0 + c * cw
            painter.drawLine(int(x), int(gy0), int(x), int(gy0 + rows * ch))
        for r in range(rows + 1):
            y = gy0 + r * ch
            painter.drawLine(int(gx0), int(y), int(gx0 + cols * cw), int(y))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._image is None or event.button() != Qt.MouseButton.LeftButton:
            return
        scale, ox, oy = self._scale_and_origin()
        mx = event.position().x()
        my = event.position().y()
        ix = (mx - ox) / scale
        iy = (my - oy) / scale
        if ix < 0 or iy < 0 or ix >= self._image.width or iy >= self._image.height:
            return
        ix -= self._offset_x
        iy -= self._offset_y
        if ix < 0 or iy < 0:
            return
        col = int(ix // self._cell_w)
        row = int(iy // self._cell_h)
        cols, rows = self.grid_dimensions()
        if col < 0 or row < 0 or col >= cols or row >= rows:
            return
        left = self._offset_x + col * self._cell_w
        top = self._offset_y + row * self._cell_h
        rgba = _cell_average_from_rect(
            self._image,
            left,
            top,
            min(left + self._cell_w, self._image.width),
            min(top + self._cell_h, self._image.height),
        )
        self.cell_clicked.emit(col, row, rgba)


class ReferenceMapperWindow(QMainWindow):
    """Map a pixel grid onto a reference photo and paint a small sprite by tracing."""

    def __init__(self, parent: QWidget | None = None, initial_palette: list | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reference Grid Mapper")
        self.resize(1280, 860)

        self._ref_widget = ReferenceImageWidget()
        self._output_doc: PixelDocument | None = None
        self._canvas = PixelGridCanvas()
        self._zoom_spin = QSpinBox()
        self._zoom_spin.setRange(8, 64)
        self._zoom_spin.setValue(24)

        self._cell_w_spin = QSpinBox()
        self._cell_w_spin.setRange(1, 512)
        self._cell_w_spin.setValue(16)
        self._cell_h_spin = QSpinBox()
        self._cell_h_spin.setRange(1, 512)
        self._cell_h_spin.setValue(16)
        self._off_x_spin = QSpinBox()
        self._off_x_spin.setRange(0, 4096)
        self._off_y_spin = QSpinBox()
        self._off_y_spin.setRange(0, 4096)

        self._paint_radio = QRadioButton("Paint output only")
        self._pick_radio = QRadioButton("Click reference → paint output cell")
        self._paint_radio.setChecked(True)

        self._color_preview = QLabel()
        self._color_preview.setFixedSize(36, 36)
        self._palette_container = QWidget()
        self._palette_layout = QHBoxLayout(self._palette_container)
        self._palette_layout.setContentsMargins(0, 0, 0, 0)

        self._status = QLabel("Open a reference, set cell size, then apply grid to create the output map.")

        self._build_toolbar()
        self._build_layout()
        self._connect_signals()

        pal = list(initial_palette or [])
        self._ensure_output(pal)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Reference")
        tb.setMovable(False)
        self.addToolBar(tb)
        open_ref = tb.addAction("Open Reference…")
        open_ref.triggered.connect(self._open_reference)
        save_sprite = tb.addAction("Save Sprite…")
        save_sprite.triggered.connect(self._save_sprite)

    def _build_layout(self) -> None:
        ref_group = QGroupBox("Reference image and grid")
        ref_layout = QVBoxLayout(ref_group)
        ref_layout.addWidget(self._ref_widget)

        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel("Cell W"))
        grid_row.addWidget(self._cell_w_spin)
        grid_row.addWidget(QLabel("Cell H"))
        grid_row.addWidget(self._cell_h_spin)
        grid_row.addWidget(QLabel("Offset X"))
        grid_row.addWidget(self._off_x_spin)
        grid_row.addWidget(QLabel("Offset Y"))
        grid_row.addWidget(self._off_y_spin)
        apply_btn = QPushButton("Apply grid → output size")
        apply_btn.clicked.connect(self._apply_grid)
        grid_row.addWidget(apply_btn)
        ref_layout.addLayout(grid_row)

        fill_btn = QPushButton("Fill output from reference (average per cell)")
        fill_btn.clicked.connect(self._fill_from_reference)
        ref_layout.addWidget(fill_btn)
        ref_layout.addWidget(self._status)

        mode_group = QButtonGroup(self)
        mode_group.addButton(self._paint_radio)
        mode_group.addButton(self._pick_radio)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self._paint_radio)
        mode_row.addWidget(self._pick_radio)

        out_group = QGroupBox("Output sprite (one pixel per grid cell)")
        out_layout = QVBoxLayout(out_group)
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom"))
        zoom_row.addWidget(self._zoom_spin)
        zoom_row.addStretch(1)
        out_layout.addLayout(zoom_row)
        out_layout.addLayout(mode_row)
        out_layout.addWidget(QLabel("Color"))
        out_layout.addWidget(self._color_preview)
        out_layout.addWidget(QLabel("Palette"))
        out_layout.addWidget(self._palette_container)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._canvas)

        out_layout.addWidget(scroll, 1)

        splitter = QSplitter()
        splitter.addWidget(ref_group)
        splitter.addWidget(out_group)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addWidget(splitter)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self._zoom_spin.valueChanged.connect(self._canvas.set_zoom)
        self._cell_w_spin.valueChanged.connect(self._on_cell_changed)
        self._cell_h_spin.valueChanged.connect(self._on_cell_changed)
        self._off_x_spin.valueChanged.connect(self._on_offset_changed)
        self._off_y_spin.valueChanged.connect(self._on_offset_changed)
        self._ref_widget.cell_clicked.connect(self._on_ref_cell)
        self._canvas.image_changed.connect(self._canvas.update)

    def _on_cell_changed(self) -> None:
        self._ref_widget.set_cell_size(self._cell_w_spin.value(), self._cell_h_spin.value())
        self._update_status_dims()

    def _on_offset_changed(self) -> None:
        self._ref_widget.set_grid_offset(self._off_x_spin.value(), self._off_y_spin.value())
        self._update_status_dims()

    def _update_status_dims(self) -> None:
        cols, rows = self._ref_widget.grid_dimensions()
        self._status.setText(f"Grid: {cols} × {rows} cells (apply to create or resize output).")

    def _on_ref_cell(self, col: int, row: int, rgba: tuple[int, int, int, int]) -> None:
        if self._paint_radio.isChecked() or self._output_doc is None:
            return
        self._output_doc.current_color = rgba
        self._output_doc.use_transparent_color = rgba[3] == 0
        self._refresh_color_preview()
        if 0 <= col < self._output_doc.image.width and 0 <= row < self._output_doc.image.height:
            self._output_doc.image.putpixel((col, row), rgba)
            self._canvas.update()

    def _ensure_output(self, palette: list) -> None:
        if self._output_doc is None:
            self._output_doc = create_blank_pixel_map(16, 16)
            self._output_doc.palette = palette
        self._canvas.set_document(self._output_doc)
        self._canvas.set_mode("paint")
        self._refresh_palette_buttons()
        self._refresh_color_preview()

    def _open_reference(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Reference Image",
            "",
            "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        try:
            img = load_image(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self._ref_widget.set_reference(img)
        self._off_x_spin.setMaximum(max(0, img.width - 1))
        self._off_y_spin.setMaximum(max(0, img.height - 1))
        self._update_status_dims()
        self.statusBar().showMessage(f"Loaded {Path(path).name}")

    def _apply_grid(self) -> None:
        if not self._ref_widget.has_reference():
            QMessageBox.information(self, "Reference", "Open a reference image first.")
            return
        cols, rows = self._ref_widget.grid_dimensions()
        if cols < 1 or rows < 1:
            QMessageBox.information(self, "Grid", "No cells fit the image with this cell size and offset.")
            return
        pal = list(self._output_doc.palette) if self._output_doc else []
        self._output_doc = PixelDocument(
            image=Image.new("RGBA", (cols, rows), (0, 0, 0, 0)),
            name="traced_sprite",
            palette=pal,
        )
        self._canvas.set_document(self._output_doc)
        self._canvas.set_mode("paint")
        self._refresh_palette_buttons()
        self._refresh_color_preview()
        self._status.setText(f"Output: {cols} × {rows} — paint or pick colors from the reference.")
        self.statusBar().showMessage(f"Output set to {cols}×{rows}")

    def _fill_from_reference(self) -> None:
        if not self._ref_widget.has_reference() or self._output_doc is None:
            return
        ref = self._ref_widget.reference_image
        cols, rows = self._ref_widget.grid_dimensions()
        if self._output_doc.image.width != cols or self._output_doc.image.height != rows:
            QMessageBox.information(self, "Grid", "Apply the grid first so output size matches.")
            return
        cw, ch = self._cell_w_spin.value(), self._cell_h_spin.value()
        ox, oy = self._off_x_spin.value(), self._off_y_spin.value()
        for row in range(rows):
            for col in range(cols):
                left = ox + col * cw
                top = oy + row * ch
                rgba = _cell_average_from_rect(
                    ref,
                    left,
                    top,
                    min(left + cw, ref.width),
                    min(top + ch, ref.height),
                )
                self._output_doc.image.putpixel((col, row), rgba)
        self._canvas.update()
        self.statusBar().showMessage("Filled output from reference cell averages")

    def _save_sprite(self) -> None:
        if self._output_doc is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Sprite",
            "traced_sprite.png",
            "PNG Image (*.png)",
        )
        if not path:
            return
        save_image(self._output_doc.image, path)
        self.statusBar().showMessage(f"Saved {Path(path).name}")

    def _refresh_color_preview(self) -> None:
        if self._output_doc is None:
            return
        if self._output_doc.use_transparent_color:
            self._color_preview.setText("T")
            self._color_preview.setStyleSheet("background: #444; color: white; border: 1px solid #888;")
            return
        r, g, b, a = self._output_doc.current_color
        self._color_preview.setText("")
        self._color_preview.setStyleSheet(
            "background: rgba(%d, %d, %d, %d); border: 1px solid #111;" % (r, g, b, a)
        )

    def _refresh_palette_buttons(self) -> None:
        while self._palette_layout.count():
            item = self._palette_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if self._output_doc is None or not self._output_doc.palette:
            self._palette_layout.addWidget(QLabel("No palette"))
            return
        for color in self._output_doc.palette:
            btn = ClickableColorButton(color)
            btn.clicked_color.connect(self._set_color)
            self._palette_layout.addWidget(btn)
        self._palette_layout.addStretch(1)

    def _set_color(self, color: tuple[int, int, int, int]) -> None:
        if self._output_doc is None:
            return
        self._output_doc.current_color = color
        self._output_doc.use_transparent_color = color[3] == 0
        self._refresh_color_preview()
