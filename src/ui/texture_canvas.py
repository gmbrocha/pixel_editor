"""Lightweight pixel canvas dedicated to the Texture Generator window.

Deliberately separate from `PixelGridCanvas` (which carries layer,
selection, stamp, frame, anchor, mirror, reference, and onion-skin state
the texture generator doesn't need). This canvas keeps the same
familiar feel - one pixel per pixel, integer zoom, shift-drag rectangle
fill identical to the main editor - while staying small and easy to
audit.
"""

from __future__ import annotations

from typing import Callable

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget


Color = tuple[int, int, int, int]

# Minimum undo stack length per spec (in practice we keep more, capped to
# avoid unbounded memory if the user spams a tool).
UNDO_LIMIT = 64
ZOOM_LEVELS: tuple[int, ...] = (1, 2, 4, 8, 16, 24)
MODE_PENCIL = "pencil"
MODE_ERASER = "eraser"
MODE_EYEDROPPER = "eyedropper"
ALL_MODES = (MODE_PENCIL, MODE_ERASER, MODE_EYEDROPPER)


def _pil_to_qpixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    qim = QImage(
        rgba.tobytes("raw", "RGBA"),
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()
    return QPixmap.fromImage(qim)


class TextureCanvas(QWidget):
    """Single-image pixel canvas with pencil / eraser / eyedropper, plus
    shift-drag rectangle fill. Tracks its own undo / redo stack."""

    image_changed = Signal()                   # any pixels touched
    color_picked = Signal(int, int, int, int)  # eyedropper -> r, g, b, a
    status_changed = Signal(str)
    zoom_changed = Signal(int)
    mode_changed = Signal(str)
    cursor_pixel_changed = Signal(int, int)    # -1, -1 when off-canvas

    def __init__(self, width: int = 16, height: int = 16, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        self._zoom = 16
        self._mode = MODE_PENCIL
        self._active_color: Color = (255, 255, 255, 255)

        self._undo: list[Image.Image] = []
        self._redo: list[Image.Image] = []

        self._dragging = False
        self._rect_drag = False  # Shift-drag rect preview
        self._rect_start: tuple[int, int] | None = None
        self._rect_end: tuple[int, int] | None = None
        self._last_paint_pixel: tuple[int, int] | None = None
        self._snapshot_pending = False  # True while a stroke owns the most recent snapshot

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._sync_size()

    # -- Public API -----------------------------------------------------

    def image(self) -> Image.Image:
        return self._image

    def image_copy(self) -> Image.Image:
        return self._image.copy()

    def set_image(self, image: Image.Image, *, snapshot: bool = True) -> None:
        if snapshot:
            self._snapshot()
        self._image = image.convert("RGBA")
        self._sync_size()
        self.update()
        self.image_changed.emit()

    def resize_canvas(self, width: int, height: int) -> None:
        """Resize by replacing with a new transparent image. The caller is
        responsible for warning the user if the previous content mattered;
        this method always snapshots so resize is undoable."""
        if width <= 0 or height <= 0:
            return
        self._snapshot()
        self._image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        self._sync_size()
        self.update()
        self.image_changed.emit()

    def has_content(self) -> bool:
        bbox = self._image.getbbox()
        return bbox is not None

    def set_active_color(self, r: int, g: int, b: int, a: int = 255) -> None:
        self._active_color = (int(r), int(g), int(b), int(a))

    def active_color(self) -> Color:
        return self._active_color

    def set_mode(self, mode: str) -> None:
        if mode not in ALL_MODES:
            raise ValueError(f"unknown mode {mode!r}")
        if self._mode == mode:
            return
        self._mode = mode
        self.mode_changed.emit(mode)
        if mode == MODE_EYEDROPPER:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif mode == MODE_ERASER:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mode(self) -> str:
        return self._mode

    def zoom(self) -> int:
        return self._zoom

    def set_zoom(self, zoom: int) -> None:
        # Snap to the nearest supported level so external code passing
        # arbitrary integers still gets a sensible canvas.
        if zoom not in ZOOM_LEVELS:
            zoom = min(ZOOM_LEVELS, key=lambda z: abs(z - zoom))
        if zoom == self._zoom:
            return
        self._zoom = zoom
        self._sync_size()
        self.update()
        self.zoom_changed.emit(zoom)

    # -- Undo / Redo ---------------------------------------------------

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> None:
        if not self._undo:
            return
        # Save current onto redo so user can redo back.
        self._redo.append(self._image.copy())
        self._image = self._undo.pop()
        self._sync_size()
        self.update()
        self.image_changed.emit()
        self.status_changed.emit("Undo")

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(self._image.copy())
        if len(self._undo) > UNDO_LIMIT:
            self._undo = self._undo[-UNDO_LIMIT:]
        self._image = self._redo.pop()
        self._sync_size()
        self.update()
        self.image_changed.emit()
        self.status_changed.emit("Redo")

    def push_external_snapshot(self, before: Image.Image) -> None:
        """Push an externally-supplied 'before' image as one undo step.

        Used when callers (e.g. Generate Texture) replace the entire
        canvas in one shot - they capture the canvas state, do their
        thing, then push the captured state here so a single Ctrl+Z
        rolls back to it.
        """
        self._undo.append(before.convert("RGBA").copy())
        if len(self._undo) > UNDO_LIMIT:
            self._undo = self._undo[-UNDO_LIMIT:]
        self._redo.clear()

    def _snapshot(self) -> None:
        """Push current canvas onto the undo stack and clear redo."""
        self._undo.append(self._image.copy())
        if len(self._undo) > UNDO_LIMIT:
            self._undo = self._undo[-UNDO_LIMIT:]
        self._redo.clear()

    # -- Sizing --------------------------------------------------------

    def _sync_size(self) -> None:
        w, h = self._image.size
        new_size = QSize(max(1, w * self._zoom + 1), max(1, h * self._zoom + 1))
        self.setMinimumSize(new_size)
        self.resize(new_size)
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        w, h = self._image.size
        return QSize(max(1, w * self._zoom + 1), max(1, h * self._zoom + 1))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    # -- Coord transforms ---------------------------------------------

    def _pixel_at(self, pos: QPoint) -> tuple[int, int] | None:
        x = pos.x() // self._zoom
        y = pos.y() // self._zoom
        if 0 <= x < self._image.width and 0 <= y < self._image.height:
            return int(x), int(y)
        return None

    # -- Mouse / Key events --------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus()
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pix = self._pixel_at(event.position().toPoint())
        if pix is None:
            return
        # Eyedropper is one-shot - no drag, no shift-rect.
        if self._mode == MODE_EYEDROPPER:
            r, g, b, a = self._image.getpixel(pix)
            self.color_picked.emit(int(r), int(g), int(b), int(a))
            self.status_changed.emit(f"Picked #{r:02x}{g:02x}{b:02x} alpha {a}")
            return
        # Shift-drag begins a rectangle-fill regardless of pencil/eraser.
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._rect_drag = True
            self._rect_start = pix
            self._rect_end = pix
            self.update()
            return
        # Otherwise free-draw stroke.
        self._snapshot()
        self._dragging = True
        self._last_paint_pixel = None
        self._paint_at(pix)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pix = self._pixel_at(event.position().toPoint())
        if pix is None:
            self.cursor_pixel_changed.emit(-1, -1)
        else:
            self.cursor_pixel_changed.emit(pix[0], pix[1])

        if self._rect_drag and pix is not None:
            self._rect_end = pix
            self.update()
            return
        if not self._dragging or pix is None:
            return
        self._paint_at(pix)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._rect_drag:
            self._commit_rect_fill()
            self._rect_drag = False
            self._rect_start = None
            self._rect_end = None
            self.update()
            return
        if self._dragging:
            self._dragging = False
            self._last_paint_pixel = None
            self.image_changed.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Tool shortcuts mirror the spec.
        key = event.key()
        if key == Qt.Key.Key_P:
            self.set_mode(MODE_PENCIL); return
        if key == Qt.Key.Key_E:
            self.set_mode(MODE_ERASER); return
        if key == Qt.Key.Key_I:
            self.set_mode(MODE_EYEDROPPER); return
        if key == Qt.Key.Key_Z and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.redo()
            else:
                self.undo()
            return
        if key == Qt.Key.Key_Y and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.redo(); return
        super().keyPressEvent(event)

    # -- Painting primitives -------------------------------------------

    def _paint_at(self, pix: tuple[int, int]) -> None:
        """Paint a single pixel; if the cursor jumped from the previous
        sample, fill the gap with a Bresenham line so fast strokes don't
        leave dotted trails."""
        x, y = pix
        if self._last_paint_pixel == pix:
            return
        target_color = (0, 0, 0, 0) if self._mode == MODE_ERASER else self._active_color
        if self._last_paint_pixel is None:
            self._image.putpixel((x, y), target_color)
        else:
            for px, py in _bresenham_line(*self._last_paint_pixel, x, y):
                if 0 <= px < self._image.width and 0 <= py < self._image.height:
                    self._image.putpixel((px, py), target_color)
        self._last_paint_pixel = pix
        self.update()

    def _commit_rect_fill(self) -> None:
        if self._rect_start is None or self._rect_end is None:
            return
        x0, y0 = self._rect_start
        x1, y1 = self._rect_end
        x_min, x_max = sorted((x0, x1))
        y_min, y_max = sorted((y0, y1))
        target_color = (0, 0, 0, 0) if self._mode == MODE_ERASER else self._active_color
        self._snapshot()
        # Vectorised fill via a paste of a same-size solid block - faster
        # and clearer than a per-pixel loop on big rects.
        rect_w = x_max - x_min + 1
        rect_h = y_max - y_min + 1
        block = Image.new("RGBA", (rect_w, rect_h), target_color)
        self._image.paste(block, (x_min, y_min))
        self.image_changed.emit()
        self.status_changed.emit(
            f"Filled rect {rect_w}x{rect_h} at ({x_min},{y_min})"
        )

    # -- Painting -------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Checker background so transparent pixels are visible.
        cell = max(4, self._zoom)
        light = QColor(60, 60, 60)
        dark = QColor(40, 40, 40)
        w = self._image.width * self._zoom
        h = self._image.height * self._zoom
        painter.fillRect(0, 0, w, h, dark)
        for y in range(0, h, cell):
            for x in range(0, w, cell):
                if ((x // cell) + (y // cell)) & 1:
                    painter.fillRect(x, y, cell, cell, light)

        # Pixmap, scaled by integer zoom (no smoothing - each pixel must be sharp).
        pix = _pil_to_qpixmap(self._image)
        target = QRect(0, 0, w, h)
        painter.drawPixmap(target, pix, pix.rect())

        # Shift-rect preview overlay: outline + faint fill.
        if self._rect_drag and self._rect_start and self._rect_end:
            x0, y0 = self._rect_start
            x1, y1 = self._rect_end
            x_min, x_max = sorted((x0, x1))
            y_min, y_max = sorted((y0, y1))
            rect = QRect(
                x_min * self._zoom,
                y_min * self._zoom,
                (x_max - x_min + 1) * self._zoom - 1,
                (y_max - y_min + 1) * self._zoom - 1,
            )
            preview_color = QColor(*self._active_color) if self._mode != MODE_ERASER else QColor(255, 255, 255, 96)
            preview_color.setAlpha(96)
            painter.fillRect(rect, preview_color)
            pen = QPen(QColor(255, 255, 255), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)

        # 1px grid at high zoom so individual pixels are easy to count.
        if self._zoom >= 8:
            grid_pen = QPen(QColor(0, 0, 0, 60), 0)
            painter.setPen(grid_pen)
            for gx in range(0, w + 1, self._zoom):
                painter.drawLine(gx, 0, gx, h)
            for gy in range(0, h + 1, self._zoom):
                painter.drawLine(0, gy, w, gy)

        painter.end()


def _bresenham_line(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Integer-only Bresenham line points from (x0,y0) to (x1,y1) inclusive."""
    points: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return points
