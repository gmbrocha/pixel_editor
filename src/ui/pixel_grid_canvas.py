from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal, QSize
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
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
        self._frame_grid: tuple[int, int] | None = None
        self._onion_prev: 'Image.Image | None' = None
        self._onion_next: 'Image.Image | None' = None
        self._onion_opacity: float = 0.35
        self._anchor_points: list[tuple[int, int, str]] = []
        self._pivot_point: tuple[int, int] | None = None
        self._drag_rect_start: tuple[int, int] | None = None
        self._drag_rect_current: tuple[int, int] | None = None
        self._moving_selection = False
        self._move_origin: tuple[int, int] | None = None
        self._last_paint_point: tuple[int, int] | None = None
        self._fill_rect_start: tuple[int, int] | None = None
        self._fill_rect_current: tuple[int, int] | None = None
        self._mirror = False
        self._transparent_color: QColor | None = None
        self._stamp: 'Image.Image | None' = None
        self._stamp_hover: tuple[int, int] | None = None
        self._reference_image: 'QPixmap | None' = None
        self._reference_opacity: float = 0.5
        self.setMouseTracking(True)
        self.setMinimumSize(360, 360)
        self.setToolTip(
            "Paint mode: click or drag to paint. Shift+drag fills a rectangle.\n"
            "Select mode: drag to create a rectangle, Ctrl+click toggles pixels.\n"
            "Stamp mode: click to place the copied stamp.\n"
            "Alt+drag inside a selection moves it."
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
        if mode != "stamp":
            self._stamp_hover = None
        self.status_changed.emit(f"Pixel editor mode: {mode}")
        self.update()

    def set_zoom(self, zoom: int) -> None:
        self._zoom = zoom
        self.updateGeometry()
        self.update()

    def set_onion_skin(
        self,
        prev_image: 'Image.Image | None' = None,
        next_image: 'Image.Image | None' = None,
        opacity: float = 0.35,
    ) -> None:
        self._onion_prev = prev_image
        self._onion_next = next_image
        self._onion_opacity = max(0.0, min(1.0, opacity))
        self.update()

    def set_anchor_points(self, anchors: list[tuple[int, int, str]]) -> None:
        self._anchor_points = list(anchors)
        self.update()

    def set_pivot_point(self, pivot: tuple[int, int] | None) -> None:
        self._pivot_point = pivot
        self.update()

    def set_frame_grid(self, frame_size: tuple[int, int] | None) -> None:
        """When set, draws thicker borders at each frame cell of size (width, height) in pixels."""
        self._frame_grid = frame_size
        self.update()

    def set_mirror(self, enabled: bool) -> None:
        self._mirror = enabled
        self.update()

    def mirror_enabled(self) -> bool:
        return self._mirror

    def set_transparent_display_color(self, color: QColor | None) -> None:
        """Set a solid color to represent transparent pixels, or None for checkerboard."""
        self._transparent_color = color
        self.update()

    def copy_stamp(self) -> bool:
        """Capture the current selection rect as a stamp. Returns True if successful."""
        if self._document is None or self._document.selection_rect is None:
            return False
        left, top, right, bottom = normalize_rect(self._document.selection_rect)
        img = self._document.image
        left = max(0, left)
        top = max(0, top)
        right = min(img.width - 1, right)
        bottom = min(img.height - 1, bottom)
        if right < left or bottom < top:
            return False
        self._stamp = img.crop((left, top, right + 1, bottom + 1)).copy()
        return True

    def stamp_image(self) -> 'Image.Image | None':
        return self._stamp

    def has_stamp(self) -> bool:
        return self._stamp is not None

    def set_reference_image(self, pixmap: QPixmap | None) -> None:
        self._reference_image = pixmap
        self.update()

    def set_reference_opacity(self, opacity: float) -> None:
        self._reference_opacity = max(0.0, min(1.0, opacity))
        self.update()

    def has_reference(self) -> bool:
        return self._reference_image is not None

    def clear_reference(self) -> None:
        self._reference_image = None
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#202020"))
        if self._document is None:
            painter.setPen(QColor("#bdbdbd"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No pixel document loaded")
            return

        image = self._document.image
        z = self._zoom
        canvas_w = image.width * z
        canvas_h = image.height * z

        if self._reference_image is not None:
            painter.setOpacity(self._reference_opacity)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(0, 0, canvas_w, canvas_h, self._reference_image)
            painter.setOpacity(1.0)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        self._draw_onion_layer(painter, self._onion_prev, image.width, image.height, self._onion_opacity)
        self._draw_onion_layer(painter, self._onion_next, image.width, image.height, self._onion_opacity * 0.6)

        has_ref = self._reference_image is not None
        for y in range(image.height):
            for x in range(image.width):
                pixel = image.getpixel((x, y))
                rect = self._pixel_rect(x, y)
                if pixel[3] == 0:
                    if not has_ref:
                        self._draw_checker(painter, rect)
                else:
                    painter.fillRect(rect, QColor(*pixel))
                painter.setPen(QPen(QColor(40, 40, 40, 80 if has_ref else 255), 1))
                painter.drawRect(rect)

        self._draw_anchor_points(painter)
        self._draw_pivot_point(painter)
        self._draw_frame_grid_overlay(painter, image.width, image.height)
        self._draw_mirror_axis(painter, image.width, image.height)

        self._draw_pixel_selection(painter)
        self._draw_rect_selection(painter)
        self._draw_fill_rect_preview(painter)
        self._draw_stamp_preview(painter)

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
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._fill_rect_start = point
                    self._fill_rect_current = point
                    self.update()
                else:
                    self._last_paint_point = point
                    self._paint_point(point)
            return

        if self._mode == "stamp":
            if event.button() == Qt.MouseButton.LeftButton and self._stamp is not None:
                self._place_stamp(point)
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

        if self._mode == "stamp":
            self._stamp_hover = point
            self.update()
            return

        if self._mode == "paint" and event.buttons() & Qt.MouseButton.LeftButton:
            if self._fill_rect_start is not None:
                self._fill_rect_current = point
                self.update()
                return
            if self._last_paint_point is not None and self._last_paint_point != point:
                for p in self._bresenham(self._last_paint_point, point):
                    self._paint_point(p)
            else:
                self._paint_point(point)
            self._last_paint_point = point
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
            if self._fill_rect_start is not None and self._fill_rect_current is not None:
                self._fill_rect(self._fill_rect_start, self._fill_rect_current)
                self._fill_rect_start = None
                self._fill_rect_current = None
            self._drag_rect_start = None
            self._drag_rect_current = None
            self._moving_selection = False
            self._move_origin = None
            self._last_paint_point = None

    def _paint_point(self, point: tuple[int, int]) -> None:
        if self._document is None:
            return
        color = (0, 0, 0, 0) if self._document.use_transparent_color else self._document.current_color
        self._document.image.putpixel(point, color)
        if self._mirror:
            mx = self._document.image.width - 1 - point[0]
            if mx != point[0] and 0 <= mx < self._document.image.width:
                self._document.image.putpixel((mx, point[1]), color)
        self.image_changed.emit()
        self.update()

    def _fill_rect(self, p0: tuple[int, int], p1: tuple[int, int]) -> None:
        if self._document is None:
            return
        left, top, right, bottom = normalize_rect((p0[0], p0[1], p1[0], p1[1]))
        color = (0, 0, 0, 0) if self._document.use_transparent_color else self._document.current_color
        img = self._document.image
        for y in range(max(0, top), min(img.height, bottom + 1)):
            for x in range(max(0, left), min(img.width, right + 1)):
                img.putpixel((x, y), color)
                if self._mirror:
                    mx = img.width - 1 - x
                    if mx != x and 0 <= mx < img.width:
                        img.putpixel((mx, y), color)
        self.image_changed.emit()
        self.update()

    def _place_stamp(self, point: tuple[int, int]) -> None:
        if self._document is None or self._stamp is None:
            return
        img = self._document.image
        sw, sh = self._stamp.size
        ox = point[0] - sw // 2
        oy = point[1] - sh // 2
        for sy in range(sh):
            for sx in range(sw):
                px = self._stamp.getpixel((sx, sy))
                tx, ty = ox + sx, oy + sy
                if 0 <= tx < img.width and 0 <= ty < img.height and px[3] > 0:
                    img.putpixel((tx, ty), px)
                    if self._mirror:
                        mx = img.width - 1 - tx
                        if mx != tx and 0 <= mx < img.width:
                            img.putpixel((mx, ty), px)
        self.image_changed.emit()
        self.update()

    def _pixel_rect(self, x: int, y: int) -> QRect:
        return QRect(x * self._zoom, y * self._zoom, self._zoom, self._zoom)

    def _draw_mirror_axis(self, painter: QPainter, img_w: int, img_h: int) -> None:
        if not self._mirror:
            return
        z = self._zoom
        x = img_w * z / 2.0
        painter.setPen(QPen(QColor(255, 100, 100, 90), 2, Qt.PenStyle.DashLine))
        painter.drawLine(int(x), 0, int(x), img_h * z)

    def _draw_frame_grid_overlay(self, painter: QPainter, img_w: int, img_h: int) -> None:
        if self._frame_grid is None:
            return
        fw, fh = self._frame_grid
        if fw < 1 or fh < 1:
            return
        pen = QPen(QColor("#e8a317"), 2)
        painter.setPen(pen)
        z = self._zoom
        for x in range(fw, img_w, fw):
            painter.drawLine(x * z, 0, x * z, img_h * z)
        for y in range(fh, img_h, fh):
            painter.drawLine(0, y * z, img_w * z, y * z)
        painter.drawRect(0, 0, img_w * z, img_h * z)

    def _draw_onion_layer(
        self,
        painter: QPainter,
        layer: 'Image.Image | None',
        img_w: int,
        img_h: int,
        opacity: float,
    ) -> None:
        if layer is None:
            return
        z = self._zoom
        for y in range(min(layer.height, img_h)):
            for x in range(min(layer.width, img_w)):
                px = layer.getpixel((x, y))
                if px[3] == 0:
                    continue
                c = QColor(px[0], px[1], px[2], int(px[3] * opacity))
                painter.fillRect(x * z, y * z, z, z, c)

    def _draw_anchor_points(self, painter: QPainter) -> None:
        z = self._zoom
        pen = QPen(QColor("#ff4444"), 2)
        for ax, ay, name in self._anchor_points:
            cx = ax * z + z // 2
            cy = ay * z + z // 2
            arm = max(3, z // 3)
            painter.setPen(pen)
            painter.drawLine(cx - arm, cy, cx + arm, cy)
            painter.drawLine(cx, cy - arm, cx, cy + arm)
            if z >= 10:
                painter.drawText(cx + arm + 2, cy + 4, name)

    def _draw_pivot_point(self, painter: QPainter) -> None:
        if self._pivot_point is None:
            return
        z = self._zoom
        cx = self._pivot_point[0] * z + z // 2
        cy = self._pivot_point[1] * z + z // 2
        r = max(4, z // 2)
        painter.setPen(QPen(QColor("#ff8800"), 2))
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        painter.drawLine(cx - r, cy, cx + r, cy)
        painter.drawLine(cx, cy - r, cx, cy + r)

    def _draw_checker(self, painter: QPainter, rect: QRect) -> None:
        if self._transparent_color is not None:
            painter.fillRect(rect, self._transparent_color)
            return
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

    def _draw_stamp_preview(self, painter: QPainter) -> None:
        if self._mode != "stamp" or self._stamp is None or self._stamp_hover is None:
            return
        z = self._zoom
        sw, sh = self._stamp.size
        ox = self._stamp_hover[0] - sw // 2
        oy = self._stamp_hover[1] - sh // 2
        for sy in range(sh):
            for sx in range(sw):
                px = self._stamp.getpixel((sx, sy))
                if px[3] == 0:
                    continue
                tx, ty = ox + sx, oy + sy
                c = QColor(px[0], px[1], px[2], 120)
                painter.fillRect(tx * z, ty * z, z, z, c)
        rect = QRect(ox * z, oy * z, sw * z, sh * z)
        painter.setPen(QPen(QColor("#00d0ff"), 1, Qt.PenStyle.DashLine))
        painter.drawRect(rect)

    def _draw_fill_rect_preview(self, painter: QPainter) -> None:
        if self._fill_rect_start is None or self._fill_rect_current is None or self._document is None:
            return
        left, top, right, bottom = normalize_rect(
            (self._fill_rect_start[0], self._fill_rect_start[1],
             self._fill_rect_current[0], self._fill_rect_current[1])
        )
        z = self._zoom
        if self._document.use_transparent_color:
            preview_color = QColor(255, 255, 255, 40)
        else:
            c = self._document.current_color
            preview_color = QColor(c[0], c[1], c[2], 80)
        rect = QRect(left * z, top * z, (right - left + 1) * z, (bottom - top + 1) * z)
        painter.fillRect(rect, preview_color)
        painter.setPen(QPen(QColor("#ffcc00"), 2, Qt.PenStyle.DashLine))
        painter.drawRect(rect)

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
    def _bresenham(p0: tuple[int, int], p1: tuple[int, int]) -> list[tuple[int, int]]:
        """All pixel coordinates on the line from p0 to p1 (inclusive), skipping p0."""
        x0, y0 = p0
        x1, y1 = p1
        points: list[tuple[int, int]] = []
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            if (x0, y0) != p0:
                points.append((x0, y0))
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy
        return points

    @staticmethod
    def _point_in_rect(point: tuple[int, int], rect: tuple[int, int, int, int]) -> bool:
        left, top, right, bottom = normalize_rect(rect)
        return left <= point[0] <= right and top <= point[1] <= bottom
