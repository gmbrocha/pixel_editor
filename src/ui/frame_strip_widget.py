from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize, QMimeData
from PySide6.QtGui import QColor, QDrag, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from src.core.animation_document import AnimationFrame
from src.core.qt_image import pil_image_to_qpixmap


class FrameStripWidget(QWidget):
    """Horizontal strip of frame thumbnails. Click selects, Shift+click range-selects, drag reorders."""

    frame_selected = Signal(int)
    frame_reordered = Signal(int, int)  # from_index, to_index
    range_selected = Signal(int, int)   # start, end (inclusive)

    THUMB = 64
    PAD = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frames: list[AnimationFrame] = []
        self._current: int = 0
        self._selected_range: tuple[int, int] | None = None
        self._drag_from: int | None = None
        self._drop_target: int | None = None
        self.setMinimumHeight(self.THUMB + self.PAD * 4 + 18)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

    def set_frames(self, frames: list[AnimationFrame], current: int = 0) -> None:
        self._frames = frames
        self._current = max(0, min(current, len(frames) - 1))
        self._selected_range = None
        self.updateGeometry()
        self.update()

    def set_current(self, index: int) -> None:
        self._current = max(0, min(index, len(self._frames) - 1))
        self.update()

    def selected_range(self) -> tuple[int, int] | None:
        return self._selected_range

    def sizeHint(self) -> QSize:
        w = max(320, len(self._frames) * (self.THUMB + self.PAD) + self.PAD)
        return QSize(w, self.THUMB + self.PAD * 4 + 18)

    def _index_at(self, x: int) -> int | None:
        if not self._frames:
            return None
        i = (x - self.PAD) // (self.THUMB + self.PAD)
        if 0 <= i < len(self._frames):
            return i
        return None

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1a1a1a"))
        if not self._frames:
            painter.setPen(QColor("#888"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No frames")
            return

        for i, frame in enumerate(self._frames):
            x = self.PAD + i * (self.THUMB + self.PAD)
            y = self.PAD
            pm = pil_image_to_qpixmap(frame.image).scaled(
                self.THUMB, self.THUMB,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            painter.drawPixmap(x + (self.THUMB - pm.width()) // 2, y + (self.THUMB - pm.height()) // 2, pm)

            if i == self._current:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 180, 255, 40))
                painter.drawRect(x - 1, y - 1, self.THUMB + 2, self.THUMB + 2)
                painter.setPen(QColor("#00b4ff"))
            elif self._selected_range and self._selected_range[0] <= i <= self._selected_range[1]:
                painter.setPen(QColor("#ffa500"))
            else:
                painter.setPen(QColor("#555"))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(x - 1, y - 1, self.THUMB + 2, self.THUMB + 2)

            label = f"{i}"
            if frame.duration_ticks > 1:
                label += f" ({frame.duration_ticks}x)"
            if frame.label:
                label = frame.label
            painter.setPen(QColor("#ccc"))
            painter.drawText(x, y + self.THUMB + 14, label)

        if self._drop_target is not None:
            dx = self.PAD + self._drop_target * (self.THUMB + self.PAD) - 2
            painter.setPen(QColor("#00ff88"))
            painter.drawLine(dx, 0, dx, self.height())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        idx = self._index_at(int(event.position().x()))
        if idx is None:
            return

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            lo = min(self._current, idx)
            hi = max(self._current, idx)
            self._selected_range = (lo, hi)
            self.range_selected.emit(lo, hi)
            self.update()
            return

        self._selected_range = None
        self._current = idx
        self._drag_from = idx
        self.frame_selected.emit(idx)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_from is not None and event.buttons() & Qt.MouseButton.LeftButton:
            target = self._index_at(int(event.position().x()))
            if target is not None and target != self._drag_from:
                self._drop_target = target
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_from is not None and self._drop_target is not None and self._drag_from != self._drop_target:
            self.frame_reordered.emit(self._drag_from, self._drop_target)
        self._drag_from = None
        self._drop_target = None
        self.update()
