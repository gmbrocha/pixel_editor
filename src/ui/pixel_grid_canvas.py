from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from PIL import Image, ImageDraw

from PySide6.QtCore import QPoint, QRect, Qt, Signal, QSize, QTimer
from PySide6.QtGui import QColor, QBrush, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import QScrollArea, QWidget

from src.core.pixel_document import (
    PixelDocument,
    move_rect_contents,
    normalize_rect,
    rect_points,
    selection_points_from_perimeter,
)


_ISO_GUIDE_STEP_X = 2
_ISO_GUIDE_STEP_Y = 1
_ISO_GUIDE_DEFAULT_STEPS = 6
_ISO_GUIDE_MAX_STEPS = 512
_ISO_GUIDE_HIT_RADIUS_SCREEN = 10


@dataclass(slots=True)
class IsometricGuide:
    anchor: tuple[int, int]
    direction: int
    steps: int


class PixelGridCanvas(QWidget):
    image_changed = Signal()
    selection_changed = Signal(str)
    status_changed = Signal(str)
    zoom_changed = Signal(int)
    flood_erase_requested = Signal(int, int)
    isometric_guide_changed = Signal(str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._document: PixelDocument | None = None
        self._zoom = 20
        self._view_margin = 600
        self._last_image_size: tuple[int, int] | None = None
        self._mode = "paint"
        self._frame_grid: tuple[int, int] | None = None
        self._onion_prev: 'Image.Image | None' = None
        self._onion_next: 'Image.Image | None' = None
        self._onion_opacity: float = 0.35
        self._anchor_points: list[tuple[int, int, str]] = []
        self._pivot_point: tuple[int, int] | None = None
        self._drag_rect_start: tuple[int, int] | None = None
        self._drag_rect_current: tuple[int, int] | None = None
        self._draw_selection_enabled = False
        self._draw_selection_points: list[tuple[int, int]] = []
        self._moving_selection = False
        self._move_origin: tuple[int, int] | None = None
        self._resizing_selection = False
        self._resize_handle: str | None = None
        self._resize_anchor_rect: tuple[int, int, int, int] | None = None
        self._last_paint_point: tuple[int, int] | None = None
        self._clean_stroke_enabled = False
        self._clean_stroke_points: set[tuple[int, int]] = set()
        self._fill_rect_start: tuple[int, int] | None = None
        self._fill_rect_current: tuple[int, int] | None = None
        self._line_key_down = False
        self._line_start: tuple[int, int] | None = None
        self._line_current: tuple[int, int] | None = None
        self._ellipse_key_down = False
        self._ellipse_start: tuple[int, int] | None = None
        self._ellipse_current: tuple[int, int] | None = None
        self._mirror = False
        self._transparent_color: QColor | None = None
        self._stamp: 'Image.Image | None' = None
        self._stamp_hover: tuple[int, int] | None = None
        self._reference_image: 'QPixmap | None' = None
        self._reference_opacity: float = 0.5
        self._isometric_guide: IsometricGuide | None = None
        self._isometric_guide_steps: int = _ISO_GUIDE_DEFAULT_STEPS
        self._isometric_guide_drag: str | None = None
        self._isometric_guide_drag_origin: tuple[float, float] | None = None
        self._isometric_guide_drag_anchor_origin: tuple[int, int] | None = None
        self._isometric_guide_drag_end_origin: tuple[int, int] | None = None
        self._mid_drag: bool = False
        self._mid_drag_origin: QPoint | None = None
        self._parent_scroll: QScrollArea | None = None
        self._render_qimage: QImage | None = None
        self._render_cache_dirty = True
        self._onion_qimage_cache: dict[int, QImage] = {}
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(
            "Paint mode: click or drag to paint. Shift+drag fills a rectangle. Hold L and drag to draw a line. Hold C and drag to draw an ellipse.\n"
            "Select mode: drag to create a rectangle, Ctrl+click toggles pixels.\n"
            "Draw Selection: click perimeter cells, then click the start or adjacent closing cell.\n"
            "Stamp mode: click to place the copied stamp.\n"
            "Guide mode: click to place an isometric guide, drag the guide to move it, or drag handles to resize.\n"
            "Alt+drag inside a selection moves it.\n"
            "Clean Stroke avoids repeated pixels and 2x2 double-pixel corners while dragging.\n"
            "Middle-mouse drag or arrow keys to pan the view."
        )

    def sizeHint(self) -> QSize:
        margin = self._view_margin * 2
        if self._document is None:
            return QSize(480 + margin, 480 + margin)
        return QSize(
            self._document.image.width * self._zoom + 1 + margin,
            self._document.image.height * self._zoom + 1 + margin,
        )

    def minimumSizeHint(self) -> QSize:
        # QScrollArea uses minimumSizeHint (not sizeHint) to decide when scroll
        # bars are needed. Returning the same size guarantees the scroll area
        # always treats us as the full image+margin size, even with
        # widgetResizable enabled.
        return self.sizeHint()

    def _apply_canvas_size(self) -> None:
        """Force the widget to the size of its sizeHint, in case the scroll area
        is in widgetResizable=False mode and won't size us automatically."""
        target = self.sizeHint()
        if self.size() != target:
            self.resize(target)

    def set_document(self, document: PixelDocument) -> None:
        size_changed = (
            self._last_image_size is None
            or self._last_image_size != (document.image.width, document.image.height)
        )
        self._document = document
        self._cancel_line_preview()
        self._cancel_ellipse_preview()
        self._last_image_size = (document.image.width, document.image.height)
        self.invalidate_render_cache(update=False)
        self.updateGeometry()
        self._apply_canvas_size()
        self.update()
        if size_changed:
            QTimer.singleShot(0, self.center_view_on_image)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        if mode != "paint":
            self._cancel_line_preview()
            self._cancel_ellipse_preview()
        if mode != "select":
            self._cancel_draw_selection(emit_status=False)
            self._resizing_selection = False
            self._resize_handle = None
            self._resize_anchor_rect = None
        if mode != "stamp":
            self._stamp_hover = None
        if mode != "iso_guide":
            self._cancel_isometric_guide_drag()
        if mode == "flood_erase":
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif mode == "iso_guide":
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if self._isometric_guide is not None
                else Qt.CursorShape.CrossCursor
            )
        else:
            self.unsetCursor()
        self.status_changed.emit(f"Pixel editor mode: {mode}")
        self.update()

    def set_draw_selection_enabled(self, enabled: bool) -> None:
        self._draw_selection_enabled = bool(enabled)
        if not self._draw_selection_enabled:
            self._cancel_draw_selection()
        elif self._mode == "select":
            self._resizing_selection = False
            self._resize_handle = None
            self._resize_anchor_rect = None
            self.unsetCursor()
            self.status_changed.emit(
                "Draw Selection: click perimeter cells, then click the start cell to close"
            )
        self.update()

    def set_clean_stroke_enabled(self, enabled: bool) -> None:
        self._clean_stroke_enabled = bool(enabled)
        self._clean_stroke_points.clear()
        self.status_changed.emit(
            "Clean Stroke enabled: continuous paint avoids double pixels"
            if self._clean_stroke_enabled
            else "Clean Stroke disabled"
        )

    def set_zoom(self, zoom: int) -> None:
        if zoom == self._zoom:
            return
        scroll = self._scroll_area()
        focus_image_xy: tuple[float, float] | None = None
        if scroll is not None and self._document is not None:
            viewport = scroll.viewport()
            cx = scroll.horizontalScrollBar().value() + viewport.width() / 2.0
            cy = scroll.verticalScrollBar().value() + viewport.height() / 2.0
            focus_image_xy = (
                (cx - self._view_margin) / self._zoom,
                (cy - self._view_margin) / self._zoom,
            )

        self._zoom = zoom
        self.updateGeometry()
        self._apply_canvas_size()
        self.update()

        if focus_image_xy is not None and scroll is not None:
            ix, iy = focus_image_xy
            target_x = int(self._view_margin + ix * self._zoom - viewport.width() / 2.0)
            target_y = int(self._view_margin + iy * self._zoom - viewport.height() / 2.0)
            QTimer.singleShot(0, lambda: self._set_scroll_position(target_x, target_y))

    def set_onion_skin(
        self,
        prev_image: 'Image.Image | None' = None,
        next_image: 'Image.Image | None' = None,
        opacity: float = 0.35,
    ) -> None:
        self._onion_prev = prev_image
        self._onion_next = next_image
        self._onion_opacity = max(0.0, min(1.0, opacity))
        self._onion_qimage_cache.clear()
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
        """Capture the current selection as a stamp. Returns True if successful."""
        if self._document is None:
            return False
        stamp = self._document.copy_selection_image(compact=True)
        if stamp is None:
            return False
        self._stamp = stamp
        return True

    def stamp_image(self) -> 'Image.Image | None':
        return self._stamp

    def has_stamp(self) -> bool:
        return self._stamp is not None

    def flip_stamp_horizontal(self) -> bool:
        if self._stamp is None:
            return False
        self._stamp = self._flip_stamp_image(self._stamp, "horizontal")
        self.update()
        return True

    def flip_stamp_vertical(self) -> bool:
        if self._stamp is None:
            return False
        self._stamp = self._flip_stamp_image(self._stamp, "vertical")
        self.update()
        return True

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

    def show_isometric_guide(self, direction: str, steps: int | None = None) -> None:
        guide_direction = self._isometric_direction_sign(direction)
        guide_steps = self._coerce_isometric_steps(
            steps if steps is not None else self._isometric_guide_steps
        )
        self._isometric_guide_steps = guide_steps
        if self._document is None:
            return

        if self._isometric_guide is None:
            anchor = self._default_isometric_anchor(guide_direction, guide_steps)
        else:
            start, end = self._isometric_guide_endpoints(self._isometric_guide)
            center = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
            anchor = self._isometric_anchor_from_center(center, guide_direction, guide_steps)

        self._isometric_guide = IsometricGuide(anchor, guide_direction, guide_steps)
        self._emit_isometric_guide_changed()
        self.status_changed.emit(
            f"Isometric guide {self._isometric_direction_label(guide_direction)}: "
            f"{guide_steps} step{'s' if guide_steps != 1 else ''} at 1/2 slope"
        )
        if self._mode == "iso_guide":
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()

    def set_isometric_guide_steps(self, steps: int) -> None:
        guide_steps = self._coerce_isometric_steps(steps)
        self._isometric_guide_steps = guide_steps
        if self._isometric_guide is None:
            return
        if guide_steps == self._isometric_guide.steps:
            return
        start, end = self._isometric_guide_endpoints(self._isometric_guide)
        center = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
        self._isometric_guide.steps = guide_steps
        self._isometric_guide.anchor = self._isometric_anchor_from_center(
            center,
            self._isometric_guide.direction,
            guide_steps,
        )
        self._emit_isometric_guide_changed()
        self.update()

    def clear_isometric_guide(self) -> None:
        if self._isometric_guide is None:
            return
        self._isometric_guide = None
        self._cancel_isometric_guide_drag()
        self.isometric_guide_changed.emit("", 0)
        if self._mode == "iso_guide":
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.status_changed.emit("Isometric guide cleared")
        self.update()

    def _pil_to_qpixmap(self, pil_img) -> QPixmap:
        return QPixmap.fromImage(self._pil_to_qimage(pil_img))

    def _pil_to_qimage(self, pil_img) -> QImage:
        """Convert a PIL RGBA image to a copied QImage through a bulk numpy path."""
        arr = np.asarray(pil_img.convert("RGBA"))
        h, w = arr.shape[:2]
        qimg = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        return qimg.copy()

    def invalidate_render_cache(self, *, update: bool = True) -> None:
        self._render_cache_dirty = True
        self._render_qimage = None
        if update:
            self.update()

    def _ensure_render_cache(self) -> QImage | None:
        if self._document is None:
            return None
        if not self._render_cache_dirty and self._render_qimage is not None:
            return self._render_qimage
        self._render_qimage = self._pil_to_qimage(self._document.composite_visible())
        self._render_cache_dirty = False
        return self._render_qimage

    def _refresh_cached_pixel(self, x: int, y: int) -> None:
        if (
            self._document is None
            or self._render_cache_dirty
            or self._render_qimage is None
            or x < 0
            or y < 0
            or x >= self._render_qimage.width()
            or y >= self._render_qimage.height()
        ):
            return
        r, g, b, a = self._composited_pixel_at(x, y)
        self._render_qimage.setPixelColor(x, y, QColor(r, g, b, a))

    def _composited_pixel_at(self, x: int, y: int) -> tuple[int, int, int, int]:
        if self._document is None:
            return (0, 0, 0, 0)
        out_r = out_g = out_b = 0.0
        out_a = 0.0
        for layer in self._document.layers:
            if not layer.visible:
                continue
            r, g, b, a = layer.image.getpixel((x, y))
            src_a = a / 255.0
            if src_a <= 0.0:
                continue
            next_a = src_a + out_a * (1.0 - src_a)
            if next_a <= 0.0:
                continue
            out_r = (r * src_a + out_r * out_a * (1.0 - src_a)) / next_a
            out_g = (g * src_a + out_g * out_a * (1.0 - src_a)) / next_a
            out_b = (b * src_a + out_b * out_a * (1.0 - src_a)) / next_a
            out_a = next_a
        return (
            int(round(out_r)),
            int(round(out_g)),
            int(round(out_b)),
            int(round(out_a * 255.0)),
        )

    def _update_pixel_rect(self, x: int, y: int) -> None:
        z = self._zoom
        pad = 2 if z >= 6 else 1
        self.update(
            QRect(
                self._view_margin + x * z - pad,
                self._view_margin + y * z - pad,
                z + pad * 2,
                z + pad * 2,
            )
        )

    def _visible_image_rect(self, event_rect: QRect, img_w: int, img_h: int) -> QRect:
        z = self._zoom
        m = self._view_margin
        left = max(0, math.floor((event_rect.left() - m) / z))
        top = max(0, math.floor((event_rect.top() - m) / z))
        right = min(img_w, math.ceil((event_rect.right() + 1 - m) / z))
        bottom = min(img_h, math.ceil((event_rect.bottom() + 1 - m) / z))
        if right <= left or bottom <= top:
            return QRect()
        return QRect(left, top, right - left, bottom - top)

    def _target_rect_for_source(self, source: QRect) -> QRect:
        z = self._zoom
        return QRect(source.x() * z, source.y() * z, source.width() * z, source.height() * z)

    def _scaled_source_rect(self, source: QRect, source_w: int, source_h: int, target_w: int, target_h: int) -> QRect:
        left = int(round(source.x() * source_w / target_w))
        top = int(round(source.y() * source_h / target_h))
        right = int(round((source.x() + source.width()) * source_w / target_w))
        bottom = int(round((source.y() + source.height()) * source_h / target_h))
        return QRect(left, top, max(0, right - left), max(0, bottom - top))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        event_rect = event.rect()
        painter.fillRect(event_rect, QColor("#1a1a1a"))
        if self._document is None:
            painter.setPen(QColor("#bdbdbd"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No pixel document loaded")
            return

        render_image = self._ensure_render_cache()
        if render_image is None:
            return
        z = self._zoom
        img_w, img_h = render_image.width(), render_image.height()
        canvas_w = img_w * z
        canvas_h = img_h * z

        m = self._view_margin
        visible_source = self._visible_image_rect(event_rect, img_w, img_h)
        if visible_source.isNull():
            return
        visible_target = self._target_rect_for_source(visible_source)
        painter.fillRect(
            QRect(m - 8, m - 8, canvas_w + 16, canvas_h + 16).intersected(event_rect),
            QColor("#202020"),
        )
        painter.translate(m, m)

        if self._reference_image is not None:
            painter.setOpacity(self._reference_opacity)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            reference_source = self._scaled_source_rect(
                visible_source,
                self._reference_image.width(),
                self._reference_image.height(),
                img_w,
                img_h,
            )
            painter.drawPixmap(visible_target, self._reference_image, reference_source)
            painter.setOpacity(1.0)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        self._draw_onion_layer_fast(painter, self._onion_prev, visible_source, self._onion_opacity)
        self._draw_onion_layer_fast(painter, self._onion_next, visible_source, self._onion_opacity * 0.6)

        has_ref = self._reference_image is not None

        if not has_ref:
            if self._transparent_color is not None:
                painter.fillRect(visible_target, self._transparent_color)
            else:
                self._draw_checker(painter, visible_target)

        painter.drawImage(visible_target, render_image, visible_source)

        # Grid lines — skip at very low zoom for performance
        if z >= 6:
            grid_alpha = 80 if has_ref else 180
            pen = QPen(QColor(40, 40, 40, grid_alpha), 1)
            painter.setPen(pen)
            x_start = visible_source.left()
            x_stop = visible_source.right() + 1
            y_start = visible_source.top()
            y_stop = visible_source.bottom() + 1
            for x in range(x_start, x_stop + 1):
                painter.drawLine(x * z, y_start * z, x * z, y_stop * z)
            for y in range(y_start, y_stop + 1):
                painter.drawLine(x_start * z, y * z, x_stop * z, y * z)

        self._draw_anchor_points(painter)
        self._draw_pivot_point(painter)
        self._draw_frame_grid_overlay(painter, img_w, img_h)
        self._draw_mirror_axis(painter, img_w, img_h)

        self._draw_pixel_selection(painter)
        self._draw_rect_selection(painter)
        self._draw_selection_perimeter_preview(painter)
        self._draw_fill_rect_preview(painter)
        self._draw_line_preview(painter)
        self._draw_ellipse_preview(painter)
        self._draw_stamp_preview(painter)
        self._draw_isometric_guide(painter)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if event.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag = True
            self._mid_drag_origin = event.globalPosition().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if self._document is None:
            return

        if self._mode == "iso_guide":
            self._handle_isometric_guide_press(event)
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

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._mode == "select"
            and not self._draw_selection_enabled
            and self._document.selection_rect is not None
        ):
            handle = self._selection_resize_handle_at(point)
            if handle is not None:
                self._resizing_selection = True
                self._resize_handle = handle
                self._resize_anchor_rect = normalize_rect(self._document.selection_rect)
                self.status_changed.emit(f"Resizing selection: {handle.replace('-', ' ')}")
                self._update_hover_cursor(point)
                return

        if self._mode == "flood_erase":
            if event.button() == Qt.MouseButton.LeftButton:
                self.flood_erase_requested.emit(point[0], point[1])
            return

        if self._mode == "paint":
            if event.button() == Qt.MouseButton.LeftButton:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._fill_rect_start = point
                    self._fill_rect_current = point
                    self.update()
                elif self._ellipse_key_down:
                    self._ellipse_start = point
                    self._ellipse_current = point
                    self.status_changed.emit("Ellipse preview: release left mouse to paint")
                    self.update()
                elif self._line_key_down:
                    self._line_start = point
                    self._line_current = point
                    self.status_changed.emit("Line preview: release left mouse to paint")
                    self.update()
                else:
                    self._last_paint_point = point
                    self._clean_stroke_points.clear()
                    self._paint_stroke_point(point)
            return

        if self._mode == "stamp":
            if event.button() == Qt.MouseButton.LeftButton and self._stamp is not None:
                self._place_stamp(point)
            return

        if self._mode == "select" and self._draw_selection_enabled:
            if event.button() == Qt.MouseButton.LeftButton:
                self._handle_draw_selection_click(point)
            elif event.button() == Qt.MouseButton.RightButton:
                self._cancel_draw_selection()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self._document.selection_rect is not None:
                self._document.selected_pixels = self._document.selected_points()
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
        if self._mid_drag and self._mid_drag_origin is not None:
            scroll = self._scroll_area()
            if scroll is not None:
                delta = event.globalPosition().toPoint() - self._mid_drag_origin
                scroll.horizontalScrollBar().setValue(scroll.horizontalScrollBar().value() - delta.x())
                scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().value() - delta.y())
                self._mid_drag_origin = event.globalPosition().toPoint()
            return

        if self._document is None:
            return

        if self._mode == "iso_guide":
            self._handle_isometric_guide_move(event)
            return

        point = self._event_to_pixel(event.position().toPoint())
        if point is None:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                self._update_hover_cursor(None)
            return

        if not (event.buttons() & Qt.MouseButton.LeftButton):
            self._update_hover_cursor(point)
            if self._mode != "stamp":
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
                self.invalidate_render_cache(update=False)
                self.image_changed.emit()
                self.selection_changed.emit(self._selection_summary())
                self.update()
            return

        if self._resizing_selection and self._resize_handle and self._resize_anchor_rect:
            left, top, right, bottom = self._resized_selection_rect(point)
            self._document.selection_rect = (left, top, right, bottom)
            self._document.selected_pixels = rect_points(self._document.selection_rect)
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
            if self._line_start is not None:
                self._line_current = point
                self.update()
                return
            if self._ellipse_start is not None:
                self._ellipse_current = point
                self.update()
                return
            if self._last_paint_point is not None and self._last_paint_point != point:
                for p in self._bresenham(self._last_paint_point, point):
                    self._paint_stroke_point(p)
            else:
                self._paint_stroke_point(point)
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
            if self._isometric_guide_drag is not None:
                self._cancel_isometric_guide_drag()
                if self._mode == "iso_guide":
                    self.setCursor(
                        Qt.CursorShape.OpenHandCursor
                        if self._isometric_guide is not None
                        else Qt.CursorShape.CrossCursor
                    )
                return
            if self._fill_rect_start is not None and self._fill_rect_current is not None:
                self._fill_rect(self._fill_rect_start, self._fill_rect_current)
                self._fill_rect_start = None
                self._fill_rect_current = None
            if self._line_start is not None and self._line_current is not None:
                self._paint_line(self._line_start, self._line_current)
                self._line_start = None
                self._line_current = None
            if self._ellipse_start is not None and self._ellipse_current is not None:
                self._paint_ellipse(self._ellipse_start, self._ellipse_current)
                self._ellipse_start = None
                self._ellipse_current = None
            self._drag_rect_start = None
            self._drag_rect_current = None
            self._moving_selection = False
            self._move_origin = None
            self._resizing_selection = False
            self._resize_handle = None
            self._resize_anchor_rect = None
            self._last_paint_point = None
            self._clean_stroke_points.clear()
            if self._document is not None:
                self._update_hover_cursor(self._event_to_pixel(event.position().toPoint()))
        if event.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag = False
            self._mid_drag_origin = None
            if self._document is None:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self._update_hover_cursor(self._event_to_pixel(event.position().toPoint()))

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        step = max(1, self._zoom // 5)
        new_zoom = self._zoom + step if delta > 0 else self._zoom - step
        new_zoom = max(1, min(64, new_zoom))
        if new_zoom != self._zoom:
            self.set_zoom(new_zoom)
            self.zoom_changed.emit(new_zoom)

    def set_scroll_area(self, scroll: QScrollArea) -> None:
        self._parent_scroll = scroll
        self._apply_canvas_size()
        QTimer.singleShot(0, self.center_view_on_image)

    def _scroll_area(self) -> QScrollArea | None:
        if self._parent_scroll is not None:
            return self._parent_scroll
        p = self.parentWidget()
        while p is not None:
            if isinstance(p, QScrollArea):
                return p
            p = p.parentWidget()
        return None

    def _set_scroll_position(self, x: int, y: int) -> None:
        scroll = self._scroll_area()
        if scroll is None:
            return
        h_bar = scroll.horizontalScrollBar()
        v_bar = scroll.verticalScrollBar()
        h_bar.setValue(max(h_bar.minimum(), min(h_bar.maximum(), x)))
        v_bar.setValue(max(v_bar.minimum(), min(v_bar.maximum(), y)))

    def center_view_on_image(self) -> None:
        """Scroll the parent scroll area so the image is centered in the viewport."""
        scroll = self._scroll_area()
        if scroll is None or self._document is None:
            return
        viewport = scroll.viewport()
        img_w = self._document.image.width * self._zoom
        img_h = self._document.image.height * self._zoom
        target_x = int(self._view_margin + img_w / 2 - viewport.width() / 2)
        target_y = int(self._view_margin + img_h / 2 - viewport.height() / 2)
        self._set_scroll_position(target_x, target_y)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self._draw_selection_points:
            self._cancel_draw_selection()
            event.accept()
            return

        if event.key() == Qt.Key.Key_L and not event.isAutoRepeat():
            self._line_key_down = True
            event.accept()
            return
        if (
            event.key() == Qt.Key.Key_C
            and not event.isAutoRepeat()
            and not (
                event.modifiers()
                & (
                    Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.AltModifier
                    | Qt.KeyboardModifier.MetaModifier
                )
            )
        ):
            self._ellipse_key_down = True
            event.accept()
            return

        scroll = self._scroll_area()
        if scroll is None:
            super().keyPressEvent(event)
            return

        key = event.key()
        h_bar = scroll.horizontalScrollBar()
        v_bar = scroll.verticalScrollBar()
        small_step = max(8, self._zoom * 2)
        large_step = max(scroll.viewport().width(), scroll.viewport().height()) // 2

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            step = large_step
        else:
            step = small_step

        if key == Qt.Key.Key_Left:
            h_bar.setValue(h_bar.value() - step)
        elif key == Qt.Key.Key_Right:
            h_bar.setValue(h_bar.value() + step)
        elif key == Qt.Key.Key_Up:
            v_bar.setValue(v_bar.value() - step)
        elif key == Qt.Key.Key_Down:
            v_bar.setValue(v_bar.value() + step)
        elif key == Qt.Key.Key_PageUp:
            v_bar.setValue(v_bar.value() - scroll.viewport().height())
        elif key == Qt.Key.Key_PageDown:
            v_bar.setValue(v_bar.value() + scroll.viewport().height())
        elif key == Qt.Key.Key_Home:
            self.center_view_on_image()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_L and not event.isAutoRepeat():
            self._line_key_down = False
            event.accept()
            return
        if event.key() == Qt.Key.Key_C and not event.isAutoRepeat() and self._ellipse_key_down:
            self._ellipse_key_down = False
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:
        self._line_key_down = False
        self._ellipse_key_down = False
        self._cancel_line_preview()
        self._cancel_ellipse_preview()
        self._cancel_isometric_guide_drag()
        super().focusOutEvent(event)

    def _paint_point(self, point: tuple[int, int]) -> None:
        if self._document is None:
            return
        color = (0, 0, 0, 0) if self._document.use_transparent_color else self._document.current_color
        self._document.image.putpixel(point, color)
        self._refresh_cached_pixel(point[0], point[1])
        self._update_pixel_rect(point[0], point[1])
        if self._mirror:
            mx = self._document.image.width - 1 - point[0]
            if mx != point[0] and 0 <= mx < self._document.image.width:
                self._document.image.putpixel((mx, point[1]), color)
                self._refresh_cached_pixel(mx, point[1])
                self._update_pixel_rect(mx, point[1])
        self.image_changed.emit()

    def _paint_stroke_point(self, point: tuple[int, int]) -> None:
        if not self._clean_stroke_enabled:
            self._paint_point(point)
            return
        if point in self._clean_stroke_points:
            return
        if self._would_create_clean_stroke_double(point):
            return
        self._clean_stroke_points.add(point)
        self._paint_point(point)

    def _would_create_clean_stroke_double(self, point: tuple[int, int]) -> bool:
        x, y = point
        painted = self._clean_stroke_points
        for ox in (-1, 0):
            for oy in (-1, 0):
                block = {
                    (x + ox, y + oy),
                    (x + ox + 1, y + oy),
                    (x + ox, y + oy + 1),
                    (x + ox + 1, y + oy + 1),
                }
                if point in block and block - {point} <= painted:
                    return True
        return False

    def _paint_line(self, p0: tuple[int, int], p1: tuple[int, int]) -> None:
        if self._document is None:
            return
        points = [p0]
        points.extend(self._bresenham(p0, p1))
        color = (0, 0, 0, 0) if self._document.use_transparent_color else self._document.current_color
        img = self._document.image
        for x, y in points:
            img.putpixel((x, y), color)
            if self._mirror:
                mx = img.width - 1 - x
                if mx != x and 0 <= mx < img.width:
                    img.putpixel((mx, y), color)
        self.invalidate_render_cache(update=False)
        self.image_changed.emit()
        self.update()

    def _paint_ellipse(self, p0: tuple[int, int], p1: tuple[int, int]) -> None:
        if self._document is None:
            return
        points = self._ellipse_outline(p0, p1)
        color = (0, 0, 0, 0) if self._document.use_transparent_color else self._document.current_color
        img = self._document.image
        for x, y in points:
            img.putpixel((x, y), color)
            if self._mirror:
                mx = img.width - 1 - x
                if mx != x and 0 <= mx < img.width:
                    img.putpixel((mx, y), color)
        self.invalidate_render_cache(update=False)
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
        self.invalidate_render_cache(update=False)
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
        self.invalidate_render_cache(update=False)
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

    def _draw_isometric_guide(self, painter: QPainter) -> None:
        if self._isometric_guide is None:
            return
        start, end = self._isometric_guide_endpoints(self._isometric_guide)
        z = self._zoom
        sx = (start[0] + 0.5) * z
        sy = (start[1] + 0.5) * z
        ex = (end[0] + 0.5) * z
        ey = (end[1] + 0.5) * z
        active = self._mode == "iso_guide"

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(0, 0, 0, 165), 5))
        painter.drawLine(int(round(sx)), int(round(sy)), int(round(ex)), int(round(ey)))
        painter.setPen(QPen(QColor(0, 208, 255, 230 if active else 175), 2))
        painter.drawLine(int(round(sx)), int(round(sy)), int(round(ex)), int(round(ey)))

        radius = max(4, min(9, z // 2))
        painter.setBrush(QColor(0, 208, 255, 230 if active else 150))
        painter.setPen(QPen(QColor(8, 28, 34, 230), 1))
        painter.drawEllipse(
            int(round(sx - radius)),
            int(round(sy - radius)),
            radius * 2,
            radius * 2,
        )
        painter.drawEllipse(
            int(round(ex - radius)),
            int(round(ey - radius)),
            radius * 2,
            radius * 2,
        )
        painter.restore()

    def _draw_onion_layer_fast(
        self,
        painter: QPainter,
        layer: 'Image.Image | None',
        visible_source: QRect,
        opacity: float,
    ) -> None:
        if layer is None:
            return
        cache_key = id(layer)
        image = self._onion_qimage_cache.get(cache_key)
        if image is None:
            image = self._pil_to_qimage(layer)
            self._onion_qimage_cache[cache_key] = image
        visible_source = visible_source.intersected(QRect(0, 0, image.width(), image.height()))
        if visible_source.isNull():
            return
        visible_target = self._target_rect_for_source(visible_source)
        painter.setOpacity(opacity)
        painter.drawImage(visible_target, image, visible_source)
        painter.setOpacity(1.0)

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
        tile = max(8, min(24, self._zoom * 2))
        pixmap = QPixmap(tile * 2, tile * 2)
        pixmap.fill(QColor("#2d2d2d"))
        tile_painter = QPainter(pixmap)
        tile_painter.fillRect(0, 0, tile, tile, QColor("#404040"))
        tile_painter.fillRect(tile, tile, tile, tile, QColor("#404040"))
        tile_painter.end()
        painter.fillRect(rect, QBrush(pixmap))

    def _draw_pixel_selection(self, painter: QPainter) -> None:
        if self._document is None:
            return
        painter.setPen(QPen(QColor("#7bd389"), 2))
        for x, y in self._document.selected_pixels:
            painter.drawRect(self._pixel_rect(x, y))

    def _draw_selection_perimeter_preview(self, painter: QPainter) -> None:
        if self._document is None or not self._draw_selection_points:
            return
        outline = self._draw_selection_outline(close=False)
        fill = QColor(255, 204, 0, 55)
        for x, y in outline:
            painter.fillRect(self._pixel_rect(x, y), fill)
        painter.setPen(QPen(QColor("#ffcc00"), 2))
        for x, y in outline:
            painter.drawRect(self._pixel_rect(x, y))
        first_x, first_y = self._draw_selection_points[0]
        painter.setPen(QPen(QColor("#00d0ff"), 2))
        painter.drawRect(self._pixel_rect(first_x, first_y))

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

    def _draw_line_preview(self, painter: QPainter) -> None:
        if self._line_start is None or self._line_current is None or self._document is None:
            return
        z = self._zoom
        if self._document.use_transparent_color:
            preview_color = QColor(255, 255, 255, 70)
        else:
            c = self._document.current_color
            preview_color = QColor(c[0], c[1], c[2], 120)
        outline = QPen(QColor("#ffcc00"), 2, Qt.PenStyle.DashLine)
        points = [self._line_start]
        points.extend(self._bresenham(self._line_start, self._line_current))
        for x, y in points:
            painter.fillRect(x * z, y * z, z, z, preview_color)
            if self._mirror:
                mx = self._document.image.width - 1 - x
                if mx != x and 0 <= mx < self._document.image.width:
                    painter.fillRect(mx * z, y * z, z, z, preview_color)
        painter.setPen(outline)
        sx, sy = self._line_start
        ex, ey = self._line_current
        painter.drawLine(
            sx * z + z // 2,
            sy * z + z // 2,
            ex * z + z // 2,
            ey * z + z // 2,
        )

    def _draw_ellipse_preview(self, painter: QPainter) -> None:
        if self._ellipse_start is None or self._ellipse_current is None or self._document is None:
            return
        z = self._zoom
        if self._document.use_transparent_color:
            preview_color = QColor(255, 255, 255, 70)
        else:
            c = self._document.current_color
            preview_color = QColor(c[0], c[1], c[2], 120)
        points = self._ellipse_outline(self._ellipse_start, self._ellipse_current)
        for x, y in points:
            painter.fillRect(x * z, y * z, z, z, preview_color)
            if self._mirror:
                mx = self._document.image.width - 1 - x
                if mx != x and 0 <= mx < self._document.image.width:
                    painter.fillRect(mx * z, y * z, z, z, preview_color)

        left, top, right, bottom = normalize_rect(
            (
                self._ellipse_start[0],
                self._ellipse_start[1],
                self._ellipse_current[0],
                self._ellipse_current[1],
            )
        )
        rect = QRect(left * z, top * z, (right - left + 1) * z, (bottom - top + 1) * z)
        painter.setPen(QPen(QColor("#ffcc00"), 2, Qt.PenStyle.DashLine))
        painter.drawEllipse(rect)

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
        if self._mode != "select":
            return
        handle_size = max(4, min(self._zoom, 10))
        handle_half = handle_size // 2
        painter.setPen(QPen(QColor("#0b1f26"), 1))
        painter.setBrush(QBrush(QColor("#00d0ff")))
        for hx, hy in self._selection_handle_widget_points(left, top, right, bottom):
            painter.drawRect(QRect(hx - handle_half, hy - handle_half, handle_size, handle_size))

    def _handle_isometric_guide_press(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.clear_isometric_guide()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return

        image_point = self._event_to_image_float(event.position().toPoint())
        if self._isometric_guide is None:
            self._place_isometric_guide_at(image_point)
            return

        hit = self._hit_test_isometric_guide(image_point)
        if hit is None:
            self._place_isometric_guide_at(image_point)
            return

        self._isometric_guide_drag = hit
        self._isometric_guide_drag_origin = image_point
        self._isometric_guide_drag_anchor_origin = self._isometric_guide.anchor
        _, end = self._isometric_guide_endpoints(self._isometric_guide)
        self._isometric_guide_drag_end_origin = end
        if hit == "move":
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.status_changed.emit("Moving isometric guide")
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.status_changed.emit("Resizing isometric guide")

    def _handle_isometric_guide_move(self, event: QMouseEvent) -> None:
        image_point = self._event_to_image_float(event.position().toPoint())
        if self._isometric_guide is None:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        if (
            self._isometric_guide_drag == "move"
            and self._isometric_guide_drag_origin is not None
            and self._isometric_guide_drag_anchor_origin is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            dx = int(round(image_point[0] - self._isometric_guide_drag_origin[0]))
            dy = int(round(image_point[1] - self._isometric_guide_drag_origin[1]))
            anchor = (
                self._isometric_guide_drag_anchor_origin[0] + dx,
                self._isometric_guide_drag_anchor_origin[1] + dy,
            )
            if anchor != self._isometric_guide.anchor:
                self._isometric_guide.anchor = anchor
                self.update()
            return

        if (
            self._isometric_guide_drag in {"start", "end"}
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self._resize_isometric_guide(image_point, self._isometric_guide_drag)
            return

        hit = self._hit_test_isometric_guide(image_point)
        if hit == "move":
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif hit in {"start", "end"}:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def _place_isometric_guide_at(self, image_point: tuple[float, float]) -> None:
        direction = self._isometric_guide.direction if self._isometric_guide else -1
        steps = (
            self._isometric_guide.steps
            if self._isometric_guide is not None
            else self._isometric_guide_steps
        )
        anchor = (int(round(image_point[0] - 0.5)), int(round(image_point[1] - 0.5)))
        self._isometric_guide = IsometricGuide(anchor, direction, steps)
        self._emit_isometric_guide_changed()
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.status_changed.emit(
            f"Placed isometric guide {self._isometric_direction_label(direction)} "
            f"at {anchor[0]},{anchor[1]}"
        )
        self.update()

    def _resize_isometric_guide(self, image_point: tuple[float, float], handle: str) -> None:
        if self._isometric_guide is None:
            return
        direction = self._isometric_guide.direction

        if handle == "end":
            start = self._isometric_guide.anchor
            start_center = (start[0] + 0.5, start[1] + 0.5)
            steps = self._isometric_steps_from_projection(start_center, image_point, direction)
            anchor = start
        else:
            fixed_end = self._isometric_guide_drag_end_origin
            if fixed_end is None:
                _, fixed_end = self._isometric_guide_endpoints(self._isometric_guide)
            fixed_center = (fixed_end[0] + 0.5, fixed_end[1] + 0.5)
            reverse_point = (
                fixed_center[0] + (fixed_center[0] - image_point[0]),
                fixed_center[1] + (fixed_center[1] - image_point[1]),
            )
            steps = self._isometric_steps_from_projection(fixed_center, reverse_point, direction)
            anchor = (
                fixed_end[0] - _ISO_GUIDE_STEP_X * steps,
                fixed_end[1] - direction * _ISO_GUIDE_STEP_Y * steps,
            )

        if anchor == self._isometric_guide.anchor and steps == self._isometric_guide.steps:
            return
        self._isometric_guide.anchor = anchor
        self._isometric_guide.steps = steps
        self._isometric_guide_steps = steps
        self._emit_isometric_guide_changed()
        self.status_changed.emit(
            f"Isometric guide: {steps} step{'s' if steps != 1 else ''} at 1/2 slope"
        )
        self.update()

    def _hit_test_isometric_guide(self, image_point: tuple[float, float]) -> str | None:
        if self._isometric_guide is None:
            return None
        start, end = self._isometric_guide_endpoints(self._isometric_guide)
        start_center = (start[0] + 0.5, start[1] + 0.5)
        end_center = (end[0] + 0.5, end[1] + 0.5)
        tolerance = max(0.35, _ISO_GUIDE_HIT_RADIUS_SCREEN / max(1, self._zoom))

        if self._point_distance(image_point, start_center) <= tolerance:
            return "start"
        if self._point_distance(image_point, end_center) <= tolerance:
            return "end"
        if self._distance_to_segment(image_point, start_center, end_center) <= tolerance:
            return "move"
        return None

    def _event_to_image_float(self, point: QPoint) -> tuple[float, float]:
        return (
            (point.x() - self._view_margin) / self._zoom,
            (point.y() - self._view_margin) / self._zoom,
        )

    def _event_to_pixel(self, point: QPoint) -> tuple[int, int] | None:
        if self._document is None:
            return None
        x = (point.x() - self._view_margin) // self._zoom
        y = (point.y() - self._view_margin) // self._zoom
        if x < 0 or y < 0 or x >= self._document.image.width or y >= self._document.image.height:
            return None
        return x, y

    def _selection_handle_widget_points(
        self,
        left: int,
        top: int,
        right: int,
        bottom: int,
    ) -> list[tuple[int, int]]:
        z = self._zoom
        rect_left = left * z
        rect_top = top * z
        rect_right = (right + 1) * z
        rect_bottom = (bottom + 1) * z
        mid_x = (rect_left + rect_right) // 2
        mid_y = (rect_top + rect_bottom) // 2
        return [
            (rect_left, rect_top),
            (mid_x, rect_top),
            (rect_right, rect_top),
            (rect_left, mid_y),
            (rect_right, mid_y),
            (rect_left, rect_bottom),
            (mid_x, rect_bottom),
            (rect_right, rect_bottom),
        ]

    def _selection_resize_handle_at(self, point: tuple[int, int]) -> str | None:
        if self._document is None or self._document.selection_rect is None:
            return None
        left, top, right, bottom = normalize_rect(self._document.selection_rect)
        x, y = point
        on_left = x == left and top <= y <= bottom
        on_right = x == right and top <= y <= bottom
        on_top = y == top and left <= x <= right
        on_bottom = y == bottom and left <= x <= right
        if on_left and on_top:
            return "top-left"
        if on_right and on_top:
            return "top-right"
        if on_left and on_bottom:
            return "bottom-left"
        if on_right and on_bottom:
            return "bottom-right"
        if on_left:
            return "left"
        if on_right:
            return "right"
        if on_top:
            return "top"
        if on_bottom:
            return "bottom"
        return None

    def _resized_selection_rect(self, point: tuple[int, int]) -> tuple[int, int, int, int]:
        if self._resize_anchor_rect is None or self._resize_handle is None:
            raise RuntimeError("Selection resize requested without an active handle")
        left, top, right, bottom = self._resize_anchor_rect
        x, y = point
        if "left" in self._resize_handle:
            left = x
        if "right" in self._resize_handle:
            right = x
        if "top" in self._resize_handle:
            top = y
        if "bottom" in self._resize_handle:
            bottom = y
        return normalize_rect((left, top, right, bottom))

    def _update_hover_cursor(self, point: tuple[int, int] | None) -> None:
        if self._mid_drag:
            return
        if self._mode == "flood_erase":
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        if self._resizing_selection and self._resize_handle is not None:
            handle = self._resize_handle
        elif self._mode == "select" and point is not None and not self._draw_selection_enabled:
            handle = self._selection_resize_handle_at(point)
        else:
            handle = None

        if handle in {"left", "right"}:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif handle in {"top", "bottom"}:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif handle in {"top-left", "bottom-right"}:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle in {"top-right", "bottom-left"}:
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.unsetCursor()

    def _cancel_line_preview(self) -> None:
        if self._line_start is None and self._line_current is None:
            return
        self._line_start = None
        self._line_current = None
        self.update()

    def _cancel_ellipse_preview(self) -> None:
        if self._ellipse_start is None and self._ellipse_current is None:
            return
        self._ellipse_start = None
        self._ellipse_current = None
        self.update()

    def _cancel_isometric_guide_drag(self) -> None:
        self._isometric_guide_drag = None
        self._isometric_guide_drag_origin = None
        self._isometric_guide_drag_anchor_origin = None
        self._isometric_guide_drag_end_origin = None

    def _handle_draw_selection_click(self, point: tuple[int, int]) -> None:
        if self._document is None:
            return
        if not self._draw_selection_points:
            self._draw_selection_points = [point]
            self.selection_changed.emit("Drawing selection perimeter: 1 cell")
            self.status_changed.emit(
                "Draw Selection: continue around the perimeter, then click the start cell to close"
            )
            self.update()
            return

        if point == self._draw_selection_points[-1]:
            return

        closes_on_start = len(self._draw_selection_points) >= 3 and point == self._draw_selection_points[0]
        closes_adjacent = (
            len(self._draw_selection_points) >= 4
            and point != self._draw_selection_points[0]
            and self._is_adjacent(point, self._draw_selection_points[0])
        )

        if closes_on_start:
            self._complete_draw_selection()
            return

        self._draw_selection_points.append(point)
        if closes_adjacent:
            self._complete_draw_selection()
            return

        count = len(self._draw_selection_points)
        self.selection_changed.emit(f"Drawing selection perimeter: {count} cells")
        self.update()

    def _complete_draw_selection(self) -> None:
        if self._document is None:
            return
        selected = selection_points_from_perimeter(
            self._draw_selection_points,
            self._document.image.width,
            self._document.image.height,
        )
        self._document.selection_rect = None
        self._document.selected_pixels = selected
        self._draw_selection_points = []
        self.selection_changed.emit(self._selection_summary())
        self.status_changed.emit(
            f"Draw Selection completed: {len(selected)} pixel{'s' if len(selected) != 1 else ''} selected"
        )
        self.update()

    def _cancel_draw_selection(self, *, emit_status: bool = True) -> None:
        if not self._draw_selection_points:
            return
        self._draw_selection_points = []
        self.selection_changed.emit(self._selection_summary())
        if emit_status:
            self.status_changed.emit("Draw Selection canceled")
        self.update()

    def _draw_selection_outline(self, *, close: bool) -> set[tuple[int, int]]:
        if not self._draw_selection_points:
            return set()
        points = list(self._draw_selection_points)
        outline: set[tuple[int, int]] = {points[0]}
        pairs = list(zip(points, points[1:]))
        if close and len(points) >= 3:
            pairs.append((points[-1], points[0]))
        for start, end in pairs:
            outline.add(start)
            outline.update(self._bresenham(start, end))
        return outline

    @staticmethod
    def _is_adjacent(first: tuple[int, int], second: tuple[int, int]) -> bool:
        return max(abs(first[0] - second[0]), abs(first[1] - second[1])) <= 1

    @staticmethod
    def _flip_stamp_image(stamp: 'Image.Image', orientation: str) -> 'Image.Image':
        if orientation == "horizontal":
            return stamp.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        return stamp.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    def _default_isometric_anchor(self, direction: int, steps: int) -> tuple[int, int]:
        if self._document is None:
            return (0, 0)
        width = self._document.image.width
        height = self._document.image.height
        x = int(round((width - 1 - _ISO_GUIDE_STEP_X * steps) / 2.0))
        if direction < 0:
            y = int(round((height - 1 + _ISO_GUIDE_STEP_Y * steps) / 2.0))
        else:
            y = int(round((height - 1 - _ISO_GUIDE_STEP_Y * steps) / 2.0))
        return (max(0, x), max(0, min(height - 1, y)))

    def _emit_isometric_guide_changed(self) -> None:
        if self._isometric_guide is None:
            return
        self.isometric_guide_changed.emit(
            self._isometric_direction_label(self._isometric_guide.direction),
            self._isometric_guide.steps,
        )

    @staticmethod
    def _isometric_guide_endpoints(guide: IsometricGuide) -> tuple[tuple[int, int], tuple[int, int]]:
        return guide.anchor, PixelGridCanvas._isometric_guide_end(
            guide.anchor,
            guide.direction,
            guide.steps,
        )

    @staticmethod
    def _isometric_guide_end(
        anchor: tuple[int, int],
        direction: int,
        steps: int,
    ) -> tuple[int, int]:
        return (
            anchor[0] + _ISO_GUIDE_STEP_X * steps,
            anchor[1] + direction * _ISO_GUIDE_STEP_Y * steps,
        )

    @staticmethod
    def _isometric_anchor_from_center(
        center: tuple[float, float],
        direction: int,
        steps: int,
    ) -> tuple[int, int]:
        return (
            int(round(center[0] - (_ISO_GUIDE_STEP_X * steps) / 2.0)),
            int(round(center[1] - (direction * _ISO_GUIDE_STEP_Y * steps) / 2.0)),
        )

    @staticmethod
    def _isometric_steps_from_projection(
        origin: tuple[float, float],
        point: tuple[float, float],
        direction: int,
    ) -> int:
        step_x = float(_ISO_GUIDE_STEP_X)
        step_y = float(direction * _ISO_GUIDE_STEP_Y)
        dx = point[0] - origin[0]
        dy = point[1] - origin[1]
        projected = (dx * step_x + dy * step_y) / (step_x * step_x + step_y * step_y)
        return max(1, min(_ISO_GUIDE_MAX_STEPS, int(round(projected))))

    @staticmethod
    def _coerce_isometric_steps(steps: int) -> int:
        return max(1, min(_ISO_GUIDE_MAX_STEPS, int(steps)))

    @staticmethod
    def _isometric_direction_sign(direction: str) -> int:
        return 1 if direction in {"\\", "backslash", "down"} else -1

    @staticmethod
    def _isometric_direction_label(direction: int) -> str:
        return "\\" if direction > 0 else "/"

    @staticmethod
    def _point_distance(first: tuple[float, float], second: tuple[float, float]) -> float:
        return math.hypot(first[0] - second[0], first[1] - second[1])

    @staticmethod
    def _distance_to_segment(
        point: tuple[float, float],
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> float:
        vx = end[0] - start[0]
        vy = end[1] - start[1]
        length_sq = vx * vx + vy * vy
        if length_sq <= 0.0:
            return PixelGridCanvas._point_distance(point, start)
        t = ((point[0] - start[0]) * vx + (point[1] - start[1]) * vy) / length_sq
        t = max(0.0, min(1.0, t))
        closest = (start[0] + vx * t, start[1] + vy * t)
        return PixelGridCanvas._point_distance(point, closest)

    def _selection_summary(self) -> str:
        if self._document is None:
            return "No selection"
        if self._document.selection_rect is not None:
            left, top, right, bottom = normalize_rect(self._document.selection_rect)
            return f"Rect {left},{top} to {right},{bottom}"
        if not self._document.selected_pixels:
            return "No selection"
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
    def _ellipse_outline(p0: tuple[int, int], p1: tuple[int, int]) -> list[tuple[int, int]]:
        left, top, right, bottom = normalize_rect((p0[0], p0[1], p1[0], p1[1]))
        width = right - left + 1
        height = bottom - top + 1

        if width == 1 and height == 1:
            return [(left, top)]
        if width == 1:
            return [(left, y) for y in range(top, bottom + 1)]
        if height == 1:
            return [(x, top) for x in range(left, right + 1)]

        mask = Image.new("1", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, width - 1, height - 1), outline=1)
        pixels = mask.load()
        points: list[tuple[int, int]] = []
        for y in range(height):
            for x in range(width):
                if pixels[x, y]:
                    points.append((left + x, top + y))
        return points

    @staticmethod
    def _point_in_rect(point: tuple[int, int], rect: tuple[int, int, int, int]) -> bool:
        left, top, right, bottom = normalize_rect(rect)
        return left <= point[0] <= right and top <= point[1] <= bottom
