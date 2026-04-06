from __future__ import annotations

import json

from PySide6.QtCore import QMimeData, QPoint, QRect, Qt, Signal, QSize
from PySide6.QtGui import QColor, QDrag, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from src.core.qt_image import pil_image_to_qimage, pil_image_to_qpixmap
from src.core.tile_layout import PlacedTile, layout_bounds_px


class TileLayoutCanvas(QWidget):
    """Paints same-sized tiles on a grid; Ctrl+click multi-select; Alt+drag moves selected group."""

    tiles_changed = Signal()
    selection_changed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tiles: list[PlacedTile] = []
        self._selected: set[str] = set()
        self._tile_w = 16
        self._tile_h = 16
        self._zoom = 16
        self._margin = 8
        self._alt_moving = False
        self._drag_start: QPoint | None = None
        self._positions_at_drag: dict[str, tuple[int, int]] = {}
        self._drag_tile: PlacedTile | None = None
        self._drag_threshold = 8
        self.setMouseTracking(True)
        self.setMinimumSize(400, 400)
        self.setToolTip(
            "Click a tile to select. Ctrl+click toggles in the selection.\n"
            "Alt+drag from a tile moves all selected tiles together (grid snapped).\n"
            "Drag a tile to the Assembly Grid to copy it there."
        )

    def set_tiles(self, tiles: list[PlacedTile], tile_w: int, tile_h: int) -> None:
        self._tiles = tiles
        self._tile_w = max(1, tile_w)
        self._tile_h = max(1, tile_h)
        self._selected = {t.id for t in tiles if t.id in self._selected}
        self.updateGeometry()
        self.update()

    def all_tiles(self) -> list[PlacedTile]:
        return self._tiles

    def selected_ids(self) -> set[str]:
        return set(self._selected)

    def set_selection(self, ids: set[str]) -> None:
        self._selected = {i for i in ids if any(t.id == i for t in self._tiles)}
        self.selection_changed.emit(self._selection_summary())
        self.update()

    def remove_selected(self) -> None:
        # Keep the same list object so the parent window's reference stays in sync.
        self._tiles[:] = [t for t in self._tiles if t.id not in self._selected]
        self._selected.clear()
        self.tiles_changed.emit()
        self.selection_changed.emit(self._selection_summary())
        self.updateGeometry()
        self.update()

    def tile_size(self) -> tuple[int, int]:
        return self._tile_w, self._tile_h

    def set_zoom(self, zoom: int) -> None:
        self._zoom = max(2, zoom)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        m = self._margin
        if not self._tiles:
            return QSize(480, 480)
        min_x, min_y, max_x, max_y = layout_bounds_px(self._tiles, self._tile_w, self._tile_h)
        w = (max_x - min_x + 2 * m) * self._zoom
        h = (max_y - min_y + 2 * m) * self._zoom
        return QSize(max(400, w + 1), max(400, h + 1))

    def _bounds_min(self) -> tuple[int, int]:
        if not self._tiles:
            return 0, 0
        min_x, min_y, _, _ = layout_bounds_px(self._tiles, self._tile_w, self._tile_h)
        return min_x, min_y

    def _layout_to_screen(self, lx: int, ly: int) -> QPoint:
        min_x, min_y = self._bounds_min()
        m = self._margin
        z = self._zoom
        return QPoint(m + (lx - min_x) * z, m + (ly - min_y) * z)

    def _screen_to_layout(self, pt: QPoint) -> tuple[float, float]:
        min_x, min_y = self._bounds_min()
        m = self._margin
        z = self._zoom
        return (min_x + (pt.x() - m) / z, min_y + (pt.y() - m) / z)

    def _hit_tile(self, lx: float, ly: float) -> PlacedTile | None:
        for t in reversed(self._tiles):
            left = t.grid_x * self._tile_w
            top = t.grid_y * self._tile_h
            if left <= lx < left + self._tile_w and top <= ly < top + self._tile_h:
                return t
        return None

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#252525"))
        if not self._tiles:
            painter.setPen(QColor("#999"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Add tiles (same width and height)")
            return

        min_x, min_y, max_x, max_y = layout_bounds_px(self._tiles, self._tile_w, self._tile_h)
        checker_a = QColor("#2a2a2a")
        checker_b = QColor("#333333")
        tw, th = self._tile_w, self._tile_h
        z = self._zoom

        for gy in range(min_y // th, (max_y + th - 1) // th):
            for gx in range(min_x // tw, (max_x + tw - 1) // tw):
                px = gx * tw
                py = gy * th
                p0 = self._layout_to_screen(px, py)
                rect = QRect(p0.x(), p0.y(), tw * z, th * z)
                use_a = (gx + gy) % 2 == 0
                painter.fillRect(rect, checker_a if use_a else checker_b)

        for t in self._tiles:
            left = t.grid_x * tw
            top = t.grid_y * th
            p0 = self._layout_to_screen(left, top)
            rect = QRect(p0.x(), p0.y(), tw * z, th * z)
            qimg = pil_image_to_qimage(t.image)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawImage(rect, qimg)
            painter.setPen(QPen(QColor("#555"), 1))
            painter.drawRect(rect)

        painter.setPen(QPen(QColor("#5ddb7a"), 2))
        for t in self._tiles:
            if t.id not in self._selected:
                continue
            left = t.grid_x * tw
            top = t.grid_y * th
            p0 = self._layout_to_screen(left, top)
            painter.drawRect(QRect(p0.x(), p0.y(), tw * z, th * z))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._tiles or event.button() != Qt.MouseButton.LeftButton:
            return

        lx, ly = self._screen_to_layout(event.position().toPoint())
        hit = self._hit_tile(lx, ly)

        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            if hit is None:
                return
            if hit.id not in self._selected:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self._selected.add(hit.id)
                else:
                    self._selected = {hit.id}
                self.selection_changed.emit(self._selection_summary())
                self.update()
            self._alt_moving = True
            self._drag_start = event.position().toPoint()
            self._positions_at_drag = {t.id: (t.grid_x, t.grid_y) for t in self._tiles if t.id in self._selected}
            self.status_changed.emit("Alt+drag: moving selected tiles")
            self.update()
            return

        self._drag_tile = hit
        self._drag_start = event.position().toPoint()

        if hit is None:
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._selected.clear()
            self.selection_changed.emit(self._selection_summary())
            self.update()
            return

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if hit.id in self._selected:
                self._selected.discard(hit.id)
            else:
                self._selected.add(hit.id)
        else:
            self._selected = {hit.id}
        self.selection_changed.emit(self._selection_summary())
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton) or self._drag_start is None:
            return

        cur = event.position().toPoint()

        if self._alt_moving:
            dx = cur.x() - self._drag_start.x()
            dy = cur.y() - self._drag_start.y()
            dgx = round(dx / (self._zoom * self._tile_w))
            dgy = round(dy / (self._zoom * self._tile_h))
            id_to_tile = {t.id: t for t in self._tiles}
            for tid, (ox, oy) in self._positions_at_drag.items():
                t = id_to_tile.get(tid)
                if t is not None:
                    t.grid_x = ox + dgx
                    t.grid_y = oy + dgy
            self.tiles_changed.emit()
            self.updateGeometry()
            self.update()
            return

        if self._drag_tile is not None:
            dist = (cur - self._drag_start).manhattanLength()
            if dist >= self._drag_threshold:
                self._start_external_drag(self._drag_tile)
                self._drag_tile = None
                self._drag_start = None

    def _start_external_drag(self, tile: PlacedTile) -> None:
        """Initiate a QDrag to copy *tile* into the AssemblyGridWidget."""
        raw = tile.image.tobytes()
        payload = json.dumps({
            "width": tile.image.width,
            "height": tile.image.height,
            "image_hex": raw.hex(),
        })
        mime = QMimeData()
        mime.setData("application/x-tile-id", payload.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        pix = pil_image_to_qpixmap(tile.image)
        if pix.width() > 128 or pix.height() > 128:
            pix = pix.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio)
        drag.setPixmap(pix)
        drag.exec(Qt.DropAction.CopyAction)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._alt_moving:
                self.status_changed.emit("Tiles repositioned")
            self._alt_moving = False
            self._drag_start = None
            self._drag_tile = None
            self._positions_at_drag.clear()

    def _selection_summary(self) -> str:
        n = len(self._selected)
        if n == 0:
            return "No tiles selected"
        if n == 1:
            tid = next(iter(self._selected))
            t = next((x for x in self._tiles if x.id == tid), None)
            if t:
                return f"Selected: {t.name} at grid ({t.grid_x}, {t.grid_y})"
        return f"{n} tiles selected"
