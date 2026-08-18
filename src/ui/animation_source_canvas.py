from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import QScrollArea, QWidget

from src.core.animation_document import FrameRect
from src.core.qt_image import pil_image_to_qpixmap


class AnimationSourceCanvas(QWidget):
    """Pixel-aligned source-sheet selection canvas with frame overlays."""

    selection_changed = Signal(tuple)
    zoom_changed = Signal(int)
    status_changed = Signal(str)

    MARGIN = 16

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image: Image.Image | None = None
        self._pixmap: QPixmap | None = None
        self._zoom = 2
        self._selection: FrameRect | None = None
        self._drag_start: tuple[int, int] | None = None
        self._frame_rects: list[tuple[FrameRect, bool, bool]] = []
        self._active_rect: FrameRect | None = None
        self._scroll: QScrollArea | None = None
        self._pan_origin: QPoint | None = None
        self._pan_scroll_origin: tuple[int, int] | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_scroll_area(self, scroll: QScrollArea) -> None:
        self._scroll = scroll

    def set_image(self, image: Image.Image | None) -> None:
        self._image = image.convert("RGBA") if image is not None else None
        self._pixmap = (
            pil_image_to_qpixmap(self._image) if self._image is not None else None
        )
        self._selection = None
        self._frame_rects = []
        self._active_rect = None
        self.updateGeometry()
        self.resize(self.sizeHint())
        self.update()

    def refresh_image(self, image: Image.Image) -> None:
        self._image = image.convert("RGBA")
        self._pixmap = pil_image_to_qpixmap(self._image)
        self.updateGeometry()
        self.resize(self.sizeHint())
        self.update()

    def set_zoom(self, zoom: int) -> None:
        value = max(1, min(32, int(zoom)))
        if value == self._zoom:
            return
        self._zoom = value
        self.updateGeometry()
        self.resize(self.sizeHint())
        self.zoom_changed.emit(value)
        self.update()

    def zoom(self) -> int:
        return self._zoom

    def set_selection(self, rect: FrameRect | None, *, emit: bool = False) -> None:
        self._selection = rect
        self.update()
        if emit and rect is not None:
            self.selection_changed.emit(rect)

    def selection(self) -> FrameRect | None:
        return self._selection

    def set_frame_rects(self, frames: list[tuple[FrameRect, bool, bool]]) -> None:
        self._frame_rects = list(frames)
        self.update()

    def set_active_rect(self, rect: FrameRect | None) -> None:
        self._active_rect = rect
        self.update()

    def sizeHint(self) -> QSize:
        if self._image is None:
            return QSize(480, 360)
        return QSize(
            self._image.width * self._zoom + self.MARGIN * 2,
            self._image.height * self._zoom + self.MARGIN * 2,
        )

    def minimumSizeHint(self) -> QSize:
        return QSize(240, 180)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#181818"))
        if self._image is None or self._pixmap is None:
            painter.setPen(QColor("#999"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Open a sprite sheet"
            )
            return

        target = QRect(
            self.MARGIN,
            self.MARGIN,
            self._image.width * self._zoom,
            self._image.height * self._zoom,
        )
        self._draw_checker(painter, target)
        scaled = self._pixmap.scaled(
            target.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        painter.drawPixmap(target.topLeft(), scaled)

        if self._zoom >= 8:
            painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
            for x in range(self._image.width + 1):
                sx = self.MARGIN + x * self._zoom
                painter.drawLine(sx, self.MARGIN, sx, target.bottom() + 1)
            for y in range(self._image.height + 1):
                sy = self.MARGIN + y * self._zoom
                painter.drawLine(self.MARGIN, sy, target.right() + 1, sy)

        for index, (rect, valid, overlaps) in enumerate(self._frame_rects):
            if not valid:
                color = QColor("#ff4f5e")
            elif overlaps:
                color = QColor("#ffb347")
            else:
                color = QColor("#35cfff")
            painter.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 24))
            widget_rect = self._widget_rect(rect)
            painter.drawRect(widget_rect)
            painter.drawText(widget_rect.adjusted(3, 2, -2, -2), str(index + 1))

        if self._active_rect is not None:
            painter.setPen(QPen(QColor("#54f28b"), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._widget_rect(self._active_rect))

        if self._selection is not None:
            painter.setPen(QPen(QColor("#ffe066"), 2))
            painter.setBrush(QColor(255, 224, 102, 32))
            painter.drawRect(self._widget_rect(self._selection))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_origin = event.position().toPoint()
            if self._scroll is not None:
                self._pan_scroll_origin = (
                    self._scroll.horizontalScrollBar().value(),
                    self._scroll.verticalScrollBar().value(),
                )
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = self._event_to_pixel(event.position().toPoint())
        if point is None:
            return
        self._drag_start = point
        self._selection = (point[0], point[1], 1, 1)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._pan_origin is not None
            and self._scroll is not None
            and self._pan_scroll_origin
        ):
            delta = event.position().toPoint() - self._pan_origin
            self._scroll.horizontalScrollBar().setValue(
                self._pan_scroll_origin[0] - delta.x()
            )
            self._scroll.verticalScrollBar().setValue(
                self._pan_scroll_origin[1] - delta.y()
            )
            return
        point = self._event_to_pixel(event.position().toPoint())
        if self._drag_start is not None and point is not None:
            self._selection = _selection_rect(self._drag_start, point)
            self.update()
        if point is not None:
            self.status_changed.emit(f"Source pixel ({point[0]}, {point[1]})")

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_origin = None
            self._pan_scroll_origin = None
            self.unsetCursor()
            return
        if event.button() != Qt.MouseButton.LeftButton or self._drag_start is None:
            return
        point = self._event_to_pixel(event.position().toPoint())
        if point is not None:
            self._selection = _selection_rect(self._drag_start, point)
        self._drag_start = None
        if self._selection is not None:
            self.selection_changed.emit(self._selection)
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = 1 if event.angleDelta().y() > 0 else -1
        self.set_zoom(self._zoom + delta)
        event.accept()

    def _event_to_pixel(self, point: QPoint) -> tuple[int, int] | None:
        if self._image is None:
            return None
        x = (point.x() - self.MARGIN) // self._zoom
        y = (point.y() - self.MARGIN) // self._zoom
        if 0 <= x < self._image.width and 0 <= y < self._image.height:
            return x, y
        return None

    def _widget_rect(self, rect: FrameRect) -> QRect:
        x, y, width, height = rect
        return QRect(
            self.MARGIN + x * self._zoom,
            self.MARGIN + y * self._zoom,
            width * self._zoom,
            height * self._zoom,
        )

    @staticmethod
    def _draw_checker(painter: QPainter, rect: QRect) -> None:
        size = 8
        for row, y in enumerate(range(rect.top(), rect.bottom() + 1, size)):
            for column, x in enumerate(range(rect.left(), rect.right() + 1, size)):
                color = (
                    QColor("#343434") if (row + column) % 2 == 0 else QColor("#252525")
                )
                painter.fillRect(
                    x,
                    y,
                    min(size, rect.right() - x + 1),
                    min(size, rect.bottom() - y + 1),
                    color,
                )


def _selection_rect(start: tuple[int, int], end: tuple[int, int]) -> FrameRect:
    left = min(start[0], end[0])
    top = min(start[1], end[1])
    return left, top, abs(end[0] - start[0]) + 1, abs(end[1] - start[1]) + 1
