from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal, QSize
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from src.core.pixel_document import PixelDocument, move_rect_contents, normalize_rect, rect_points


class PixelGridCanvas(QWidget):
    image_changed = Signal()
    selection_changed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._document: PixelDocument | None = None
        self._zoom = 20
        self._mode = "paint"
        self._drag_rect_start: tuple[int, int] | None = None
        self._drag_rect_current: tuple[int, int] | None = None
        self._moving_selection = False
        self._move_origin: tuple[int, int] | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(360, 360)
        self.setToolTip(
            "Paint mode: click or drag to paint.\n"
            "Select mode: drag to create a rectangle, Ctrl + click toggles selected pixels.\n"
            "Alt + drag inside a rectangle moves it and leaves transparency behind."
        )

    def sizeHint(self) -> QSize:
        if self._document is None:
            return QSize(480, 480)
        return QSize(
            max(320, self._document.image.width * self._zoom + 1),
            max(320, self._document.image.height * self._zoom + 1),
        )

    def set_document(self, document: PixelDocument) -> None:
        self._document = document
        self.updateGeometry()
        self.update()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.status_changed.emit(f"Pixel editor mode: {mode}")

    def set_zoom(self, zoom: int) -> None:
        self._zoom = zoom
        self.updateGeometry()
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#202020"))
        if self._document is None:
            painter.setPen(QColor("#bdbdbd"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No pixel document loaded")
            return

        image = self._document.image
        for y in range(image.height):
            for x in range(image.width):
                pixel = image.getpixel((x, y))
                rect = self._pixel_rect(x, y)
                if pixel[3] == 0:
                    self._draw_checker(painter, rect)
                else:
                    painter.fillRect(rect, QColor(*pixel))
                painter.setPen(QPen(QColor(40, 40, 40), 1))
                painter.drawRect(rect)

        self._draw_pixel_selection(painter)
        self._draw_rect_selection(painter)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._document is None:
            return

        point = self._event_to_pixel(event.position().toPoint())
        if point is None:
            return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.AltModifier
            and self._document.selection_rect is not None
            and self._point_in_rect(point, self._document.selection_rect)
        ):
            self._moving_selection = True
            self._move_origin = point
            self.status_changed.emit("Moving selection rectangle")
            return

        if self._mode == "paint":
            if event.button() == Qt.MouseButton.LeftButton:
                self._paint_point(point)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._document.selection_rect = None
            if point in self._document.selected_pixels:
                self._document.selected_pixels.remove(point)
            else:
                self._document.selected_pixels.add(point)
            self.selection_changed.emit(self._selection_summary())
            self.update()
            return

        self._drag_rect_start = point
        self._drag_rect_current = point
        self._document.selection_rect = (point[0], point[1], point[0], point[1])
        self._document.selected_pixels = set()
        self.selection_changed.emit(self._selection_summary())
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._document is None:
            return

        point = self._event_to_pixel(event.position().toPoint())
        if point is None:
            return

        if self._moving_selection and self._move_origin and event.buttons() & Qt.MouseButton.LeftButton:
            origin_x, origin_y = self._move_origin
            dx = point[0] - origin_x
            dy = point[1] - origin_y
            if dx or dy:
                image, rect = move_rect_contents(self._document.image, self._document.selection_rect, dx, dy)
                self._document.image = image
                self._document.selection_rect = rect
                self._document.selected_pixels = rect_points(rect)
                self._move_origin = point
                self.image_changed.emit()
                self.selection_changed.emit(self._selection_summary())
                self.update()
            return

        if self._mode == "paint" and event.buttons() & Qt.MouseButton.LeftButton:
            self._paint_point(point)
            return

        if self._drag_rect_start and event.buttons() & Qt.MouseButton.LeftButton:
            self._drag_rect_current = point
            left, top, right, bottom = normalize_rect(
                (
                    self._drag_rect_start[0],
                    self._drag_rect_start[1],
                    point[0],
                    point[1],
                )
            )
            self._document.selection_rect = (left, top, right, bottom)
            self._document.selected_pixels = rect_points(self._document.selection_rect)
            self.selection_changed.emit(self._selection_summary())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_rect_start = None
            self._drag_rect_current = None
            self._moving_selection = False
            self._move_origin = None

    def _paint_point(self, point: tuple[int, int]) -> None:
        if self._document is None:
            return
        color = (0, 0, 0, 0) if self._document.use_transparent_color else self._document.current_color
        self._document.image.putpixel(point, color)
        self.image_changed.emit()
        self.update()

    def _pixel_rect(self, x: int, y: int) -> QRect:
        return QRect(x * self._zoom, y * self._zoom, self._zoom, self._zoom)

    def _draw_checker(self, painter: QPainter, rect: QRect) -> None:
        half = max(2, self._zoom // 2)
        painter.fillRect(rect, QColor("#2d2d2d"))
        painter.fillRect(rect.x(), rect.y(), half, half, QColor("#404040"))
        painter.fillRect(rect.x() + half, rect.y() + half, half, half, QColor("#404040"))

    def _draw_pixel_selection(self, painter: QPainter) -> None:
        if self._document is None:
            return
        painter.setPen(QPen(QColor("#7bd389"), 2))
        for x, y in self._document.selected_pixels:
            painter.drawRect(self._pixel_rect(x, y))

    def _draw_rect_selection(self, painter: QPainter) -> None:
        if self._document is None or self._document.selection_rect is None:
            return
        left, top, right, bottom = normalize_rect(self._document.selection_rect)
        rect = QRect(
            left * self._zoom,
            top * self._zoom,
            (right - left + 1) * self._zoom,
            (bottom - top + 1) * self._zoom,
        )
        painter.setPen(QPen(QColor("#00d0ff"), 2, Qt.PenStyle.DashLine))
        painter.drawRect(rect)

    def _event_to_pixel(self, point: QPoint) -> tuple[int, int] | None:
        if self._document is None:
            return None
        x = point.x() // self._zoom
        y = point.y() // self._zoom
        if x < 0 or y < 0 or x >= self._document.image.width or y >= self._document.image.height:
            return None
        return x, y

    def _selection_summary(self) -> str:
        if self._document is None:
            return "No selection"
        if self._document.selection_rect is not None:
            left, top, right, bottom = normalize_rect(self._document.selection_rect)
            return f"Rect {left},{top} to {right},{bottom}"
        return f"Pixels selected: {len(self._document.selected_pixels)}"

    @staticmethod
    def _point_in_rect(point: tuple[int, int], rect: tuple[int, int, int, int]) -> bool:
        left, top, right, bottom = normalize_rect(rect)
        return left <= point[0] <= right and top <= point[1] <= bottom
