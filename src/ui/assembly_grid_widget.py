from __future__ import annotations

import json

from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt, Signal, QSize, QMimeData
from PySide6.QtGui import QColor, QDrag, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QWidget

from src.core.qt_image import pil_image_to_qimage


class AssemblyGridWidget(QWidget):
    """Fixed-size 2D grid of cells. Tiles are dropped from the sheet. Rubber-band to select."""

    selection_changed = Signal(object)  # list[tuple[int,int]]
    grid_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid: dict[tuple[int, int], Image.Image] = {}
        self._cols = 4
        self._rows = 4
        self._tile_w = 16
        self._tile_h = 16
        self._zoom = 16
        self._selected: set[tuple[int, int]] = set()

        self._rubber_origin: QPoint | None = None
        self._rubber_current: QPoint | None = None

        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setMinimumSize(200, 200)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def set_tile_size(self, tw: int, th: int) -> None:
        self._tile_w = max(1, tw)
        self._tile_h = max(1, th)
        self.updateGeometry()
        self.update()

    def set_dimensions(self, cols: int, rows: int) -> None:
        self._cols = max(1, cols)
        self._rows = max(1, rows)
        stale = [k for k in self._grid if k[0] >= self._cols or k[1] >= self._rows]
        for k in stale:
            del self._grid[k]
        self._selected = {s for s in self._selected if s[0] < self._cols and s[1] < self._rows}
        self.updateGeometry()
        self.update()
        self.grid_changed.emit()
        self.selection_changed.emit(sorted(self._selected))

    def dimensions(self) -> tuple[int, int]:
        return self._cols, self._rows

    def set_zoom(self, zoom: int) -> None:
        self._zoom = max(2, zoom)
        self.updateGeometry()
        self.update()

    def grid_data(self) -> dict[tuple[int, int], Image.Image]:
        return dict(self._grid)

    def selected_cells(self) -> list[tuple[int, int]]:
        return sorted(self._selected)

    def place_tile(self, col: int, row: int, image: Image.Image) -> None:
        if col < 0 or row < 0:
            return
        if col >= self._cols:
            self._cols = col + 1
        if row >= self._rows:
            self._rows = row + 1
        self._grid[(col, row)] = image.copy()
        self.updateGeometry()
        self.update()
        self.grid_changed.emit()

    def remove_cell(self, col: int, row: int) -> None:
        self._grid.pop((col, row), None)
        self._selected.discard((col, row))
        self.update()
        self.grid_changed.emit()
        self.selection_changed.emit(sorted(self._selected))

    def clear_grid(self) -> None:
        self._grid.clear()
        self._selected.clear()
        self.update()
        self.grid_changed.emit()
        self.selection_changed.emit([])

    def sizeHint(self) -> QSize:
        margin = 4
        w = self._cols * self._tile_w * self._zoom + margin * 2
        h = self._rows * self._tile_h * self._zoom + margin * 2
        return QSize(max(200, w), max(200, h))

    def _cell_rect(self, col: int, row: int) -> QRect:
        z = self._zoom
        tw, th = self._tile_w, self._tile_h
        return QRect(col * tw * z, row * th * z, tw * z, th * z)

    def _pos_to_cell(self, pos: QPoint) -> tuple[int, int] | None:
        z = self._zoom
        tw, th = self._tile_w, self._tile_h
        col = pos.x() // (tw * z)
        row = pos.y() // (th * z)
        if 0 <= col < self._cols and 0 <= row < self._rows:
            return col, row
        return None

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e1e1e"))
        z = self._zoom
        tw, th = self._tile_w, self._tile_h
        checker_a = QColor("#252525")
        checker_b = QColor("#2e2e2e")

        for row in range(self._rows):
            for col in range(self._cols):
                rect = self._cell_rect(col, row)
                use_a = (col + row) % 2 == 0
                painter.fillRect(rect, checker_a if use_a else checker_b)

                img = self._grid.get((col, row))
                if img is not None:
                    qimg = pil_image_to_qimage(img)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
                    painter.drawImage(rect, qimg)

                painter.setPen(QPen(QColor("#444"), 1))
                painter.drawRect(rect)

        for cell in self._selected:
            if cell[0] < self._cols and cell[1] < self._rows:
                rect = self._cell_rect(cell[0], cell[1])
                painter.setPen(QPen(QColor("#5ddb7a"), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)

        if self._rubber_origin is not None and self._rubber_current is not None:
            r = QRect(self._rubber_origin, self._rubber_current).normalized()
            painter.setPen(QPen(QColor("#00b4ff"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(0, 180, 255, 30))
            painter.drawRect(r)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        cell = self._pos_to_cell(event.position().toPoint())
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and cell is not None:
            if cell in self._selected:
                self._selected.discard(cell)
            else:
                self._selected.add(cell)
            self.selection_changed.emit(sorted(self._selected))
            self.update()
            return

        self._rubber_origin = event.position().toPoint()
        self._rubber_current = self._rubber_origin
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._selected.clear()
        if cell is not None:
            self._selected.add(cell)
            self.selection_changed.emit(sorted(self._selected))
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._rubber_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._rubber_current = event.position().toPoint()
            r = QRect(self._rubber_origin, self._rubber_current).normalized()
            sel: set[tuple[int, int]] = set()
            for row in range(self._rows):
                for col in range(self._cols):
                    cr = self._cell_rect(col, row)
                    if r.intersects(cr):
                        sel.add((col, row))
            self._selected = sel
            self.selection_changed.emit(sorted(self._selected))
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._rubber_origin = None
            self._rubber_current = None
            self.update()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-tile-id"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-tile-id"):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        if not mime.hasFormat("application/x-tile-id"):
            return
        cell = self._pos_to_cell(event.position().toPoint())
        if cell is None:
            edge_col = int(event.position().x() // (self._tile_w * self._zoom))
            edge_row = int(event.position().y() // (self._tile_h * self._zoom))
            if edge_col >= 0 and edge_row >= 0:
                if edge_col >= self._cols:
                    self._cols = edge_col + 1
                if edge_row >= self._rows:
                    self._rows = edge_row + 1
                cell = (edge_col, edge_row)
                self.updateGeometry()
        if cell is None:
            return

        payload = bytes(mime.data("application/x-tile-id")).decode("utf-8")
        data = json.loads(payload)
        img_bytes = bytes.fromhex(data["image_hex"])
        w, h = data["width"], data["height"]
        img = Image.frombytes("RGBA", (w, h), img_bytes)
        self.place_tile(cell[0], cell[1], img)
        event.acceptProposedAction()

    def _context_menu(self, pos: QPoint) -> None:
        cell = self._pos_to_cell(pos)
        if cell is None or cell not in self._grid:
            return
        menu = QMenu(self)
        remove = menu.addAction("Remove tile")
        action = menu.exec(self.mapToGlobal(pos))
        if action == remove:
            self.remove_cell(cell[0], cell[1])
