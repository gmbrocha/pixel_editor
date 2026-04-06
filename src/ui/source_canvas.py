from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget
from PIL import Image

from src.core.selection_models import (
    RegionSelection,
    nearest_point_index,
    point_in_polygon,
)


class SourceCanvas(QWidget):
    selections_changed = Signal(object)
    status_changed = Signal(str)
    color_picked = Signal(tuple)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image: Image.Image | None = None
        self._selections: list[RegionSelection] = []
        self._tool_mode = "polygon"
        self._current_polygon: list[tuple[float, float]] = []
        self._current_freehand: list[tuple[float, float]] = []
        self._active_selection_id: str | None = None
        self._drag_vertex: tuple[str, int] | None = None
        self._drag_selection_id: str | None = None
        self._last_drag_point: tuple[float, float] | None = None
        self._zoom_factor = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._is_panning = False
        self._pan_anchor = QPointF()
        self._space_pan_mode = False
        self._eyedropper_mode = False
        self.setMinimumSize(480, 360)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:
        return QSize(720, 540)

    def set_image(self, image: Image.Image | None) -> None:
        self._image = image
        self._current_polygon.clear()
        self._current_freehand.clear()
        self._zoom_factor = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self.update()

    def set_selections(self, selections: list[RegionSelection]) -> None:
        self._selections = list(selections)
        if self._active_selection_id and not any(
            item.id == self._active_selection_id for item in self._selections
        ):
            self._active_selection_id = None
        self.update()

    def set_tool_mode(self, mode: str) -> None:
        self._tool_mode = mode

    def set_eyedropper(self, enabled: bool) -> None:
        self._eyedropper_mode = enabled
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()

    def clear_selections(self) -> None:
        self._selections = []
        self._active_selection_id = None
        self._current_polygon.clear()
        self._current_freehand.clear()
        self.selections_changed.emit(self._selections)
        self.update()

    def delete_active_selection(self) -> None:
        if not self._active_selection_id:
            return
        self._selections = [
            item for item in self._selections if item.id != self._active_selection_id
        ]
        self._active_selection_id = None
        self.selections_changed.emit(self._selections)
        self.update()

    def delete_selection(self, selection_id: str) -> None:
        self._selections = [s for s in self._selections if s.id != selection_id]
        if self._active_selection_id == selection_id:
            self._active_selection_id = None
        self.selections_changed.emit(self._selections)
        self.update()

    def drop_rect_selection(self, width: int, height: int) -> None:
        """Place a width x height rectangle selection at the center of the visible image."""
        if self._image is None:
            return
        cx = self._image.width / 2.0
        cy = self._image.height / 2.0
        hw, hh = width / 2.0, height / 2.0
        points = [
            (cx - hw, cy - hh),
            (cx + hw, cy - hh),
            (cx + hw, cy + hh),
            (cx - hw, cy + hh),
        ]
        selection = RegionSelection(kind="rect", points=points)
        self._selections.append(selection)
        self._active_selection_id = selection.id
        self.selections_changed.emit(self._selections)
        self.status_changed.emit(f"Dropped {width}x{height} rectangle")
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._draw_background(painter)

        image_rect = self._target_rect()
        if self._image and image_rect:
            painter.drawImage(image_rect, self._pil_to_qimage())
            self._draw_regions(painter, image_rect)
        else:
            painter.setPen(QColor("#bbbbbb"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Import an image to begin")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._image and self._should_start_pan(event):
            self._is_panning = True
            self._pan_anchor = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.status_changed.emit("Panning source image")
            return

        image_point = self._widget_to_image(event.position())
        if image_point is None:
            return

        if self._eyedropper_mode and event.button() == Qt.MouseButton.LeftButton and self._image is not None:
            px = int(max(0, min(image_point[0], self._image.width - 1)))
            py = int(max(0, min(image_point[1], self._image.height - 1)))
            rgba = self._image.convert("RGBA").getpixel((px, py))
            self.color_picked.emit(tuple(rgba))
            return

        self.setFocus()

        if (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self._current_freehand = [image_point]
            self.status_changed.emit("Freehand selection started")
            self.update()
            return

        vertex_hit = self._hit_test_vertex(image_point)
        if event.button() == Qt.MouseButton.LeftButton and vertex_hit is not None:
            selection_id, point_index = vertex_hit
            self._active_selection_id = selection_id
            self._drag_vertex = (selection_id, point_index)
            self.update()
            return

        selection_hit = self._hit_test_selection(image_point)
        if event.button() == Qt.MouseButton.LeftButton and selection_hit is not None:
            self._active_selection_id = selection_hit.id
            self._drag_selection_id = selection_hit.id
            self._last_drag_point = image_point
            self.update()
            return

        if event.button() == Qt.MouseButton.RightButton:
            hit = self._hit_test_selection(image_point)
            if hit is not None:
                self.delete_selection(hit.id)
                self.status_changed.emit(f"Deleted selection")
                return
            self._current_polygon.clear()
            self.status_changed.emit("Cancelled current polygon")
            self.update()
            return

        if event.button() != Qt.MouseButton.LeftButton or self._tool_mode != "polygon":
            return

        if self._current_polygon:
            first = self._current_polygon[0]
            if self._distance_squared(first, image_point) <= self._handle_radius_image() ** 2 and len(self._current_polygon) >= 3:
                self._finish_polygon()
                return

        self._current_polygon.append(image_point)
        self.status_changed.emit(f"Polygon point {len(self._current_polygon)} added")
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_panning:
            delta = event.position() - self._pan_anchor
            self._pan_offset += delta
            self._pan_anchor = event.position()
            self.update()
            return

        image_point = self._widget_to_image(event.position())
        if image_point is None:
            return

        if self._current_freehand and event.buttons() & Qt.MouseButton.LeftButton:
            self._current_freehand.append(image_point)
            self.update()
            return

        if self._drag_vertex and event.buttons() & Qt.MouseButton.LeftButton:
            selection_id, point_index = self._drag_vertex
            self._replace_selection_point(selection_id, point_index, image_point)
            return

        if (
            self._drag_selection_id
            and self._last_drag_point
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            dx = image_point[0] - self._last_drag_point[0]
            dy = image_point[1] - self._last_drag_point[1]
            self._translate_selection(self._drag_selection_id, dx, dy)
            self._last_drag_point = image_point
            return

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._is_panning and self._is_pan_release(event):
            self._is_panning = False
            self.unsetCursor()
            self.status_changed.emit("Pan complete")
            return

        if event.button() == Qt.MouseButton.LeftButton and len(self._current_freehand) >= 3:
            selection = RegionSelection(kind="freehand", points=list(self._current_freehand))
            self._selections.append(selection)
            self._active_selection_id = selection.id
            self._current_freehand.clear()
            self.selections_changed.emit(self._selections)
            self.status_changed.emit("Freehand selection created")
            self.update()

        self._drag_vertex = None
        self._drag_selection_id = None
        self._last_drag_point = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._image is None:
            super().wheelEvent(event)
            return

        angle_delta = event.angleDelta().y()
        if angle_delta == 0:
            return

        old_rect = self._target_rect()
        if old_rect is None:
            return

        old_zoom = self._zoom_factor
        zoom_step = 1.15 if angle_delta > 0 else 1 / 1.15
        self._zoom_factor = max(0.2, min(32.0, self._zoom_factor * zoom_step))
        if abs(self._zoom_factor - old_zoom) < 1e-9:
            return

        cursor = event.position()
        if old_rect.contains(cursor):
            image_x = (cursor.x() - old_rect.x()) / old_rect.width()
            image_y = (cursor.y() - old_rect.y()) / old_rect.height()
            new_rect = self._target_rect()
            if new_rect is not None:
                target_x = new_rect.x() + image_x * new_rect.width()
                target_y = new_rect.y() + image_y * new_rect.height()
                self._pan_offset += QPointF(cursor.x() - target_x, cursor.y() - target_y)

        self.update()
        self.status_changed.emit(f"Zoom: {self._zoom_factor:.2f}x")

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and len(self._current_polygon) >= 3:
            self._finish_polygon()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            if self._current_polygon:
                self._current_polygon.pop()
                self.status_changed.emit("Removed last polygon point")
                self.update()
                return
            self.delete_active_selection()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and len(self._current_polygon) >= 3:
            self._finish_polygon()
            return
        if event.key() == Qt.Key.Key_0 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._zoom_factor = 1.0
            self._pan_offset = QPointF(0.0, 0.0)
            self.status_changed.emit("Reset source view")
            self.update()
            return
        if event.key() == Qt.Key.Key_Space:
            self._space_pan_mode = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._space_pan_mode = False
            if not self._is_panning:
                self.unsetCursor()
            return
        super().keyReleaseEvent(event)

    def _draw_background(self, painter: QPainter) -> None:
        tile = 24
        color_a = QColor("#2a2a2a")
        color_b = QColor("#333333")
        for y in range(0, self.height(), tile):
            for x in range(0, self.width(), tile):
                painter.fillRect(
                    x,
                    y,
                    tile,
                    tile,
                    color_a if (x // tile + y // tile) % 2 == 0 else color_b,
                )

    def _draw_regions(self, painter: QPainter, _image_rect: QRectF) -> None:
        for selection in self._selections:
            is_active = selection.id == self._active_selection_id
            pen = QPen(QColor("#00d0ff" if is_active else "#ffd166"), 2.0)
            painter.setPen(pen)
            painter.setBrush(QColor(0, 208, 255, 36) if is_active else QColor(255, 209, 102, 28))
            path = self._selection_path(selection.points)
            painter.drawPath(path)
            for point in selection.points:
                widget_point = self._image_to_widget(point)
                painter.setBrush(QColor("#0d1b2a" if is_active else "#6d4c00"))
                painter.drawEllipse(widget_point, 4, 4)

        if self._current_polygon:
            painter.setPen(QPen(QColor("#7bd389"), 2.0, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(123, 211, 137, 28))
            path = self._selection_path(self._current_polygon, closed=False)
            painter.drawPath(path)
            for point in self._current_polygon:
                painter.drawEllipse(self._image_to_widget(point), 3, 3)

        if len(self._current_freehand) >= 2:
            painter.setPen(QPen(QColor("#ff7b7b"), 2.0))
            painter.setBrush(QColor(255, 123, 123, 24))
            path = self._selection_path(self._current_freehand, closed=False)
            painter.drawPath(path)

    def _selection_path(
        self,
        points: list[tuple[float, float]],
        closed: bool = True,
    ) -> QPainterPath:
        path = QPainterPath()
        if not points:
            return path
        first = self._image_to_widget(points[0])
        path.moveTo(first)
        for point in points[1:]:
            path.lineTo(self._image_to_widget(point))
        if closed and len(points) >= 3:
            path.closeSubpath()
        return path

    def _target_rect(self) -> QRectF | None:
        if not self._image:
            return None

        available_width = max(1, self.width() - 24)
        available_height = max(1, self.height() - 24)
        fit_scale = min(
            available_width / self._image.width,
            available_height / self._image.height,
        )
        scale = fit_scale * self._zoom_factor
        draw_width = self._image.width * scale
        draw_height = self._image.height * scale
        x = (self.width() - draw_width) / 2 + self._pan_offset.x()
        y = (self.height() - draw_height) / 2 + self._pan_offset.y()
        return QRectF(x, y, draw_width, draw_height)

    def _widget_to_image(self, point: QPointF) -> tuple[float, float] | None:
        rect = self._target_rect()
        if not self._image or rect is None or not rect.contains(point):
            return None

        x = (point.x() - rect.x()) * self._image.width / rect.width()
        y = (point.y() - rect.y()) * self._image.height / rect.height()
        x = max(0.0, min(self._image.width - 1.0, x))
        y = max(0.0, min(self._image.height - 1.0, y))
        return x, y

    def _image_to_widget(self, point: tuple[float, float]) -> QPointF:
        rect = self._target_rect()
        if not self._image or rect is None:
            return QPointF()
        x = rect.x() + point[0] * rect.width() / self._image.width
        y = rect.y() + point[1] * rect.height() / self._image.height
        return QPointF(x, y)

    def _pil_to_qimage(self):
        from src.core.qt_image import pil_image_to_qimage

        return pil_image_to_qimage(self._image)

    def _handle_radius_image(self) -> float:
        rect = self._target_rect()
        if not self._image or rect is None:
            return 8.0
        scale = rect.width() / self._image.width
        return max(3.0, 7.0 / max(scale, 1e-6))

    def _hit_test_vertex(self, image_point: tuple[float, float]) -> tuple[str, int] | None:
        radius = self._handle_radius_image()
        for selection in reversed(self._selections):
            point_index = nearest_point_index(image_point, selection.points, radius)
            if point_index is not None:
                return selection.id, point_index
        return None

    def _hit_test_selection(self, image_point: tuple[float, float]) -> RegionSelection | None:
        for selection in reversed(self._selections):
            if point_in_polygon(image_point, selection.points):
                return selection
        return None

    def _replace_selection_point(
        self,
        selection_id: str,
        point_index: int,
        point: tuple[float, float],
    ) -> None:
        updated: list[RegionSelection] = []
        for selection in self._selections:
            if selection.id == selection_id:
                updated.append(selection.with_point(point_index, point))
            else:
                updated.append(selection)
        self._selections = updated
        self.selections_changed.emit(self._selections)
        self.update()

    def _translate_selection(self, selection_id: str, dx: float, dy: float) -> None:
        updated: list[RegionSelection] = []
        for selection in self._selections:
            if selection.id == selection_id:
                updated.append(selection.translated(dx, dy))
            else:
                updated.append(selection)
        self._selections = updated
        self.selections_changed.emit(self._selections)
        self.update()

    def _finish_polygon(self) -> None:
        selection = RegionSelection(kind="polygon", points=list(self._current_polygon))
        self._selections.append(selection)
        self._active_selection_id = selection.id
        self._current_polygon.clear()
        self.selections_changed.emit(self._selections)
        self.status_changed.emit("Polygon selection created")
        self.update()

    @staticmethod
    def _distance_squared(
        left: tuple[float, float],
        right: tuple[float, float],
    ) -> float:
        return (left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2

    def _should_start_pan(self, event: QMouseEvent) -> bool:
        return event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton
            and self._space_pan_mode
        )

    @staticmethod
    def _is_pan_release(event: QMouseEvent) -> bool:
        return event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton)
