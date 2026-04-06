from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.core.animation_document import (
    AnchorPoint,
    AnimationDocument,
    AnimationFrame,
    create_blank_animation,
    export_animation_metadata,
    export_gif,
    frames_to_sheet,
    rotate_pixels_around_pivot,
)
from src.core.image_io import load_image, save_image
from src.core.palette import (
    add_color_to_palette,
    export_palette_strip,
    load_palette_from_image,
    palette_from_image,
)
from src.core.persistent_palette import merge_palettes
from src.core.pixel_document import (
    PixelDocument,
    darken_image,
    flip_image_horizontal,
    flip_image_vertical,
    lighten_image,
    push_image_history,
    rotate_image_clockwise,
    rotate_image_counterclockwise,
    undo_image_history,
)
from src.ui.frame_strip_widget import FrameStripWidget
from src.ui.pixel_editor_window import ClickableColorButton
from src.ui.pixel_grid_canvas import PixelGridCanvas


class AnimationEditorWindow(QMainWindow):
    """Full-featured frame-based animation editor with onion skin, playback, anchors, and rotation tool."""

    def __init__(self, parent: QWidget | None = None, initial_palette: list | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Animation Editor")
        self.resize(1300, 920)

        pal = list(initial_palette or [])
        self._anim = create_blank_animation(32, 32, 4, pal)
        self._current_index = 0

        self._pixel_doc = self._doc_for_frame(0)
        self._canvas = PixelGridCanvas()
        self._canvas.set_document(self._pixel_doc)

        self._frame_strip = FrameStripWidget()

        self._zoom_spin = QSpinBox()
        self._zoom_spin.setRange(4, 64)
        self._zoom_spin.setValue(20)

        self._paint_radio = QRadioButton("Paint")
        self._select_radio = QRadioButton("Select")
        self._anchor_radio = QRadioButton("Set Anchor")
        self._pivot_radio = QRadioButton("Set Pivot")
        self._paint_radio.setChecked(True)

        self._onion_check = QCheckBox("Onion skin")
        self._onion_check.setChecked(False)
        self._onion_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._onion_opacity_slider.setRange(10, 80)
        self._onion_opacity_slider.setValue(35)
        self._onion_next_check = QCheckBox("Show next frame")

        self._play_button = QPushButton("Play")
        self._fps_combo = QComboBox()
        for fps in [4, 8, 12, 16, 24]:
            self._fps_combo.addItem(f"{fps} fps", fps)
        self._fps_combo.setCurrentIndex(2)
        self._range_start = QSpinBox()
        self._range_end = QSpinBox()
        self._timer = QTimer(self)

        self._preview_label = QLabel()
        self._preview_label.setFixedSize(200, 200)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet("background: #2a2a2a; border: 1px solid #555;")

        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(1, 10)
        self._duration_spin.setSuffix("x")

        self._anchor_name_combo = QComboBox()
        self._anchor_name_combo.setEditable(True)
        self._anchor_name_combo.addItems(["weapon", "head", "hand_l", "hand_r", "foot_l", "foot_r"])
        self._anchor_list_label = QLabel("No anchors")
        self._delete_anchor_button = QPushButton("Delete Selected Anchor")

        self._rotation_spin = QSpinBox()
        self._rotation_spin.setRange(-360, 360)
        self._rotation_spin.setSuffix("°")
        self._rotation_spin.setValue(0)
        self._commit_rotation_button = QPushButton("Commit Rotated Frame")

        self._color_preview = QLabel()
        self._color_preview.setFixedSize(32, 32)
        self._palette_container = QWidget()
        self._palette_layout = QHBoxLayout(self._palette_container)
        self._palette_layout.setContentsMargins(0, 0, 0, 0)

        self._frame_w_spin = QSpinBox()
        self._frame_w_spin.setRange(1, 512)
        self._frame_w_spin.setValue(32)
        self._frame_h_spin = QSpinBox()
        self._frame_h_spin.setRange(1, 512)
        self._frame_h_spin.setValue(32)
        self._frame_count_spin = QSpinBox()
        self._frame_count_spin.setRange(1, 256)
        self._frame_count_spin.setValue(4)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 255)
        self._opacity_slider.setValue(255)
        self._opacity_spin = QSpinBox()
        self._opacity_spin.setRange(0, 255)
        self._opacity_spin.setValue(255)

        self._build_toolbar()
        self._build_layout()
        self._connect_signals()

        self._canvas.set_zoom(self._zoom_spin.value())
        self._canvas.set_mode("paint")
        self._refresh_palette_buttons()
        self._update_color_preview()
        self._sync_frame_strip()
        self._apply_onion_skin()
        self._update_range_spins()

    def _doc_for_frame(self, index: int) -> PixelDocument:
        if index < 0 or index >= len(self._anim.frames):
            from PIL import Image
            return PixelDocument(image=Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
        frame = self._anim.frames[index]
        return PixelDocument(
            image=frame.image,
            name=f"frame_{index}",
            palette=list(self._anim.palette),
            current_color=self._anim.current_color,
            use_transparent_color=self._anim.use_transparent_color,
        )

    def _build_toolbar(self) -> None:
        tb = QToolBar("Animation")
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addAction("New blank…", self._new_blank)
        tb.addAction("Open base image…", self._open_base_image)
        tb.addAction("Import sheet…", self._import_sheet)
        tb.addSeparator()
        tb.addAction("Export sheet…", self._export_sheet)
        tb.addAction("Export GIF…", self._export_gif)
        tb.addAction("Export metadata…", self._export_metadata)
        tb.addSeparator()
        tb.addAction("Copy frame", self._copy_frame)
        tb.addAction("Delete frame", self._delete_frame)
        tb.addSeparator()
        tb.addAction("Flip H", self._flip_h)
        tb.addAction("Flip V", self._flip_v)
        tb.addAction("Rot CW", self._rot_cw)
        tb.addAction("Rot CCW", self._rot_ccw)
        tb.addSeparator()
        self._mirror_action = QAction("Mirror", self)
        self._mirror_action.setCheckable(True)
        self._mirror_action.toggled.connect(self._pixel_canvas.set_mirror)
        tb.addAction(self._mirror_action)

        tb.addSeparator()
        tb.addWidget(QLabel("Zoom"))
        tb.addWidget(self._zoom_spin)

    def _build_layout(self) -> None:
        new_group = QGroupBox("New / Import")
        ng = QHBoxLayout(new_group)
        ng.addWidget(QLabel("W"))
        ng.addWidget(self._frame_w_spin)
        ng.addWidget(QLabel("H"))
        ng.addWidget(self._frame_h_spin)
        ng.addWidget(QLabel("Frames"))
        ng.addWidget(self._frame_count_spin)
        new_btn = QPushButton("Create")
        new_btn.clicked.connect(self._new_blank)
        ng.addWidget(new_btn)

        mode_group = QButtonGroup(self)
        mode_group.addButton(self._paint_radio)
        mode_group.addButton(self._select_radio)
        mode_group.addButton(self._anchor_radio)
        mode_group.addButton(self._pivot_radio)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self._paint_radio)
        mode_row.addWidget(self._select_radio)
        mode_row.addWidget(self._anchor_radio)
        mode_row.addWidget(self._pivot_radio)

        onion_row = QHBoxLayout()
        onion_row.addWidget(self._onion_check)
        onion_row.addWidget(QLabel("Opacity"))
        onion_row.addWidget(self._onion_opacity_slider)
        onion_row.addWidget(self._onion_next_check)

        canvas_scroll = QScrollArea()
        canvas_scroll.setWidgetResizable(True)
        canvas_scroll.setWidget(self._canvas)

        canvas_col = QVBoxLayout()
        canvas_col.addWidget(new_group)
        canvas_col.addLayout(mode_row)
        canvas_col.addLayout(onion_row)
        canvas_col.addWidget(canvas_scroll, 1)

        play_row = QHBoxLayout()
        play_row.addWidget(self._play_button)
        play_row.addWidget(self._fps_combo)
        play_row.addWidget(QLabel("Range"))
        play_row.addWidget(self._range_start)
        play_row.addWidget(QLabel("–"))
        play_row.addWidget(self._range_end)

        timing_row = QHBoxLayout()
        timing_row.addWidget(QLabel("Frame duration"))
        timing_row.addWidget(self._duration_spin)
        timing_row.addStretch(1)

        playback_group = QGroupBox("Playback")
        pg = QVBoxLayout(playback_group)
        pg.addLayout(play_row)
        pg.addWidget(self._preview_label, 0, Qt.AlignmentFlag.AlignHCenter)
        pg.addLayout(timing_row)

        anchor_group = QGroupBox("Anchors")
        ag = QVBoxLayout(anchor_group)
        a_row = QHBoxLayout()
        a_row.addWidget(QLabel("Name"))
        a_row.addWidget(self._anchor_name_combo)
        ag.addLayout(a_row)
        ag.addWidget(self._anchor_list_label)
        ag.addWidget(self._delete_anchor_button)

        rotation_group = QGroupBox("Rotation / Pivot")
        rg = QVBoxLayout(rotation_group)
        r_row = QHBoxLayout()
        r_row.addWidget(QLabel("Angle"))
        r_row.addWidget(self._rotation_spin)
        r_row.addWidget(self._commit_rotation_button)
        rg.addLayout(r_row)
        rg.addWidget(QLabel("Set pivot mode, click canvas to place. Select pixels, set angle, commit."))

        color_group = QGroupBox("Paint")
        cg = QVBoxLayout(color_group)
        cg.addWidget(QLabel("Color"))
        cg.addWidget(self._color_preview)
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity"))
        opacity_row.addWidget(self._opacity_slider)
        opacity_row.addWidget(self._opacity_spin)
        cg.addLayout(opacity_row)
        pick_btn = QPushButton("Pick color…")
        pick_btn.clicked.connect(self._pick_color)
        trans_btn = QPushButton("Transparent")
        trans_btn.clicked.connect(self._use_transparent)
        cg.addWidget(pick_btn)
        cg.addWidget(trans_btn)
        cg.addWidget(QLabel("Palette"))
        cg.addWidget(self._palette_container)
        pal_load = QPushButton("Load palette…")
        pal_load.clicked.connect(self._load_palette)
        pal_from = QPushButton("Palette from frame")
        pal_from.clicked.connect(self._palette_from_frame)
        cg.addWidget(pal_load)
        cg.addWidget(pal_from)

        right_col = QWidget()
        rl = QVBoxLayout(right_col)
        rl.addWidget(playback_group)
        rl.addWidget(anchor_group)
        rl.addWidget(rotation_group)
        rl.addWidget(color_group)
        rl.addStretch(1)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right_col)

        top = QSplitter()
        canvas_widget = QWidget()
        canvas_widget.setLayout(canvas_col)
        top.addWidget(canvas_widget)
        top.addWidget(right_scroll)
        top.setStretchFactor(0, 3)
        top.setStretchFactor(1, 1)

        frame_group = QGroupBox("Frames (click to select, Shift+click range, drag to reorder)")
        fg = QVBoxLayout(frame_group)
        strip_scroll = QScrollArea()
        strip_scroll.setWidgetResizable(True)
        strip_scroll.setWidget(self._frame_strip)
        strip_scroll.setMaximumHeight(120)
        fg.addWidget(strip_scroll)

        central = QWidget()
        cl = QVBoxLayout(central)
        cl.addWidget(top, 1)
        cl.addWidget(frame_group)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self._zoom_spin.valueChanged.connect(self._canvas.set_zoom)
        self._canvas.image_changed.connect(self._on_canvas_changed)
        self._canvas.status_changed.connect(self.statusBar().showMessage)
        self._canvas.selection_changed.connect(lambda _: None)

        self._frame_strip.frame_selected.connect(self._go_to_frame)
        self._frame_strip.frame_reordered.connect(self._reorder_frame)
        self._frame_strip.range_selected.connect(self._on_range_selected)

        self._paint_radio.toggled.connect(self._on_mode)
        self._select_radio.toggled.connect(self._on_mode)
        self._anchor_radio.toggled.connect(self._on_mode)
        self._pivot_radio.toggled.connect(self._on_mode)

        self._onion_check.toggled.connect(self._apply_onion_skin)
        self._onion_opacity_slider.valueChanged.connect(self._apply_onion_skin)
        self._onion_next_check.toggled.connect(self._apply_onion_skin)

        self._play_button.clicked.connect(self._toggle_play)
        self._timer.timeout.connect(self._advance_frame)
        self._fps_combo.currentIndexChanged.connect(self._update_timer_interval)

        self._duration_spin.valueChanged.connect(self._on_duration_changed)
        self._delete_anchor_button.clicked.connect(self._delete_anchor)
        self._commit_rotation_button.clicked.connect(self._commit_rotation)

        self._opacity_slider.valueChanged.connect(self._opacity_spin.setValue)
        self._opacity_spin.valueChanged.connect(self._opacity_slider.setValue)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)

    def _on_mode(self) -> None:
        if self._paint_radio.isChecked():
            self._canvas.set_mode("paint")
        elif self._select_radio.isChecked():
            self._canvas.set_mode("select")
        elif self._anchor_radio.isChecked():
            self._canvas.set_mode("paint")
            self.statusBar().showMessage("Click canvas to place anchor")
        elif self._pivot_radio.isChecked():
            self._canvas.set_mode("paint")
            self.statusBar().showMessage("Click canvas to set pivot point")

    def _on_canvas_changed(self) -> None:
        self._canvas.update()
        self._sync_frame_strip()
        self._refresh_preview()

    def _go_to_frame(self, index: int) -> None:
        self._save_current_frame()
        self._current_index = index
        self._pixel_doc = self._doc_for_frame(index)
        self._canvas.set_document(self._pixel_doc)
        self._apply_onion_skin()
        self._update_anchor_label()
        f = self._anim.frames[index]
        self._duration_spin.blockSignals(True)
        self._duration_spin.setValue(f.duration_ticks)
        self._duration_spin.blockSignals(False)
        self._frame_strip.set_current(index)
        self._refresh_preview()
        self.statusBar().showMessage(f"Frame {index}")

    def _save_current_frame(self) -> None:
        if 0 <= self._current_index < len(self._anim.frames):
            self._anim.current_color = self._pixel_doc.current_color
            self._anim.use_transparent_color = self._pixel_doc.use_transparent_color

    def _sync_frame_strip(self) -> None:
        self._frame_strip.set_frames(self._anim.frames, self._current_index)

    def _apply_onion_skin(self) -> None:
        if not self._onion_check.isChecked():
            self._canvas.set_onion_skin(None, None)
            return
        opacity = self._onion_opacity_slider.value() / 100.0
        prev_img = self._anim.frames[self._current_index - 1].image if self._current_index > 0 else None
        next_img = None
        if self._onion_next_check.isChecked() and self._current_index + 1 < len(self._anim.frames):
            next_img = self._anim.frames[self._current_index + 1].image
        self._canvas.set_onion_skin(prev_img, next_img, opacity)

    def _update_range_spins(self) -> None:
        n = max(0, len(self._anim.frames) - 1)
        self._range_start.setRange(0, n)
        self._range_end.setRange(0, n)
        self._range_end.setValue(n)

    def _toggle_play(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._play_button.setText("Play")
            return
        if not self._anim.frames:
            return
        self._update_timer_interval()
        self._timer.start()
        self._play_button.setText("Stop")

    def _update_timer_interval(self) -> None:
        fps = self._fps_combo.currentData() or 10
        self._timer.setInterval(max(10, int(1000 / fps)))

    def _advance_frame(self) -> None:
        lo = self._range_start.value()
        hi = self._range_end.value()
        if lo > hi:
            lo, hi = hi, lo
        n = len(self._anim.frames)
        if n == 0:
            self._timer.stop()
            self._play_button.setText("Play")
            return
        lo = max(0, min(lo, n - 1))
        hi = max(0, min(hi, n - 1))
        cur = self._current_index
        frame = self._anim.frames[cur] if 0 <= cur < n else None
        ticks = frame.duration_ticks if frame else 1
        if not hasattr(self, "_tick_counter"):
            self._tick_counter = 0
        self._tick_counter += 1
        if self._tick_counter < ticks:
            return
        self._tick_counter = 0
        next_i = cur + 1
        if next_i > hi:
            next_i = lo
        if next_i < lo:
            next_i = lo
        self._go_to_frame(next_i)

    def _refresh_preview(self) -> None:
        from src.core.qt_image import pil_image_to_qpixmap

        idx = self._current_index
        if idx < 0 or idx >= len(self._anim.frames):
            self._preview_label.clear()
            return
        pm = pil_image_to_qpixmap(self._anim.frames[idx].image)
        scaled = pm.scaled(
            self._preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._preview_label.setPixmap(scaled)

    def _new_blank(self) -> None:
        w = self._frame_w_spin.value()
        h = self._frame_h_spin.value()
        n = self._frame_count_spin.value()
        self._anim = create_blank_animation(w, h, n, self._anim.palette)
        self._current_index = 0
        self._pixel_doc = self._doc_for_frame(0)
        self._canvas.set_document(self._pixel_doc)
        self._sync_frame_strip()
        self._apply_onion_skin()
        self._update_range_spins()
        self._refresh_preview()
        self.statusBar().showMessage(f"Created {n} blank {w}x{h} frames")

    def _open_base_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open base image", "", "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)")
        if not path:
            return
        try:
            img = load_image(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        n = self._frame_count_spin.value()
        from src.core.animation_document import create_animation_from_base
        self._anim = create_animation_from_base(img, n, self._anim.palette)
        self._frame_w_spin.setValue(img.width)
        self._frame_h_spin.setValue(img.height)
        self._current_index = 0
        self._pixel_doc = self._doc_for_frame(0)
        self._canvas.set_document(self._pixel_doc)
        self._sync_frame_strip()
        self._apply_onion_skin()
        self._update_range_spins()
        self._refresh_preview()
        self.statusBar().showMessage(f"Loaded {Path(path).name} as base — {n} frames")

    def _import_sheet(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import sprite sheet", "", "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)")
        if not path:
            return
        try:
            img = load_image(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        fw, fh = self._frame_w_spin.value(), self._frame_h_spin.value()
        cols = max(1, img.width // fw)
        rows = max(1, img.height // fh)
        frames: list[AnimationFrame] = []
        for r in range(rows):
            for c in range(cols):
                left, top = c * fw, r * fh
                if left + fw > img.width or top + fh > img.height:
                    continue
                crop = img.crop((left, top, left + fw, top + fh)).copy()
                frames.append(AnimationFrame(image=crop))
        if not frames:
            QMessageBox.warning(self, "Import", "No frames found with that cell size.")
            return
        self._anim.frames = frames
        self._current_index = 0
        self._pixel_doc = self._doc_for_frame(0)
        self._canvas.set_document(self._pixel_doc)
        self._sync_frame_strip()
        self._apply_onion_skin()
        self._update_range_spins()
        self._refresh_preview()
        self.statusBar().showMessage(f"Imported {len(frames)} frames from sheet")

    def _export_sheet(self) -> None:
        if not self._anim.frames:
            return
        cols, ok = self._ask_columns()
        if not ok:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export sprite sheet", f"{self._anim.name}_sheet.png", "PNG (*.png)")
        if not path:
            return
        sheet = frames_to_sheet(self._anim.frames, cols)
        save_image(sheet, path)
        self.statusBar().showMessage(f"Exported sheet to {Path(path).name}")

    def _export_gif(self) -> None:
        if not self._anim.frames:
            return
        fps = self._fps_combo.currentData() or 10
        path, _ = QFileDialog.getSaveFileName(self, "Export GIF", f"{self._anim.name}.gif", "GIF (*.gif)")
        if not path:
            return
        export_gif(self._anim.frames, path, fps=fps, loop=True)
        self.statusBar().showMessage(f"Exported GIF to {Path(path).name}")

    def _export_metadata(self) -> None:
        if not self._anim.frames:
            return
        cols, ok = self._ask_columns()
        if not ok:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export metadata", f"{self._anim.name}_meta.json", "JSON (*.json)")
        if not path:
            return
        export_animation_metadata(self._anim, path, cols)
        self.statusBar().showMessage(f"Exported metadata to {Path(path).name}")

    def _ask_columns(self) -> tuple[int, bool]:
        from PySide6.QtWidgets import QInputDialog
        cols, ok = QInputDialog.getInt(self, "Columns", "Number of columns for sprite sheet:", 4, 1, 64)
        return cols, ok

    def _copy_frame(self) -> None:
        if not self._anim.frames:
            return
        self._save_current_frame()
        src = self._anim.frames[self._current_index]
        new_frame = AnimationFrame(
            image=src.image.copy(),
            duration_ticks=src.duration_ticks,
            anchors=list(src.anchors),
        )
        self._anim.frames.insert(self._current_index + 1, new_frame)
        self._sync_frame_strip()
        self._update_range_spins()
        self._go_to_frame(self._current_index + 1)
        self.statusBar().showMessage(f"Copied frame {self._current_index - 1} → {self._current_index}")

    def _delete_frame(self) -> None:
        if len(self._anim.frames) <= 1:
            self.statusBar().showMessage("Cannot delete the last frame")
            return
        rng = self._frame_strip.selected_range()
        if rng:
            lo, hi = rng
            del self._anim.frames[lo:hi + 1]
            self._current_index = min(lo, len(self._anim.frames) - 1)
        else:
            del self._anim.frames[self._current_index]
            self._current_index = min(self._current_index, len(self._anim.frames) - 1)
        self._pixel_doc = self._doc_for_frame(self._current_index)
        self._canvas.set_document(self._pixel_doc)
        self._sync_frame_strip()
        self._apply_onion_skin()
        self._update_range_spins()
        self._refresh_preview()
        self.statusBar().showMessage(f"Deleted frame(s). Now {len(self._anim.frames)} frames")

    def _reorder_frame(self, from_idx: int, to_idx: int) -> None:
        frames = self._anim.frames
        if from_idx < 0 or from_idx >= len(frames) or to_idx < 0 or to_idx >= len(frames):
            return
        frame = frames.pop(from_idx)
        frames.insert(to_idx, frame)
        self._current_index = to_idx
        self._pixel_doc = self._doc_for_frame(to_idx)
        self._canvas.set_document(self._pixel_doc)
        self._sync_frame_strip()
        self._apply_onion_skin()
        self._refresh_preview()
        self.statusBar().showMessage(f"Moved frame {from_idx} → {to_idx}")

    def _on_range_selected(self, lo: int, hi: int) -> None:
        self.statusBar().showMessage(f"Selected frames {lo}–{hi}")

    def _on_duration_changed(self, v: int) -> None:
        if 0 <= self._current_index < len(self._anim.frames):
            self._anim.frames[self._current_index].duration_ticks = v
            self._sync_frame_strip()

    def _flip_h(self) -> None:
        self._transform_current(flip_image_horizontal)

    def _flip_v(self) -> None:
        self._transform_current(flip_image_vertical)

    def _rot_cw(self) -> None:
        self._transform_current(rotate_image_clockwise)

    def _rot_ccw(self) -> None:
        self._transform_current(rotate_image_counterclockwise)

    def _transform_current(self, func) -> None:
        if not self._anim.frames:
            return
        rng = self._frame_strip.selected_range()
        if rng:
            for i in range(rng[0], rng[1] + 1):
                self._anim.frames[i].image = func(self._anim.frames[i].image)
        else:
            self._anim.frames[self._current_index].image = func(self._anim.frames[self._current_index].image)
        self._pixel_doc = self._doc_for_frame(self._current_index)
        self._canvas.set_document(self._pixel_doc)
        self._sync_frame_strip()
        self._refresh_preview()

    def _update_anchor_label(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._anim.frames):
            self._anchor_list_label.setText("No anchors")
            self._canvas.set_anchor_points([])
            return
        anchors = self._anim.frames[self._current_index].anchors
        if not anchors:
            self._anchor_list_label.setText("No anchors")
            self._canvas.set_anchor_points([])
            return
        lines = [f"{a.name}: ({a.x}, {a.y})" for a in anchors]
        self._anchor_list_label.setText("\n".join(lines))
        self._canvas.set_anchor_points([(a.x, a.y, a.name) for a in anchors])

    def _delete_anchor(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._anim.frames):
            return
        anchors = self._anim.frames[self._current_index].anchors
        if anchors:
            anchors.pop()
            self._update_anchor_label()

    def _commit_rotation(self) -> None:
        if not self._anim.frames or not self._pixel_doc.selected_pixels:
            self.statusBar().showMessage("Select pixels and set a pivot first")
            return
        pivot = self._canvas._pivot_point
        if pivot is None:
            self.statusBar().showMessage("Set a pivot point first (Pivot mode, click canvas)")
            return
        angle = self._rotation_spin.value()
        if angle == 0:
            return
        src = self._anim.frames[self._current_index]
        rotated = rotate_pixels_around_pivot(
            src.image, self._pixel_doc.selected_pixels, pivot, angle,
        )
        new_frame = AnimationFrame(image=rotated, duration_ticks=src.duration_ticks)
        self._anim.frames.insert(self._current_index + 1, new_frame)
        self._sync_frame_strip()
        self._update_range_spins()
        self._go_to_frame(self._current_index + 1)
        self.statusBar().showMessage(f"Committed rotated frame at {angle}°")

    def _pick_color(self) -> None:
        initial = QColor(*self._pixel_doc.current_color)
        dialog = QColorDialog(initial, self)
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        if dialog.exec() != QColorDialog.DialogCode.Accepted:
            return
        c = dialog.selectedColor()
        color = (c.red(), c.green(), c.blue(), c.alpha())
        self._pixel_doc.current_color = color
        self._pixel_doc.use_transparent_color = color[3] == 0
        self._anim.current_color = color
        self._anim.palette = add_color_to_palette(self._anim.palette, color)
        self._refresh_palette_buttons()
        self._update_color_preview()

    def _use_transparent(self) -> None:
        r, g, b, _ = self._pixel_doc.current_color
        self._pixel_doc.current_color = (r, g, b, 0)
        self._pixel_doc.use_transparent_color = True
        self._update_color_preview()

    def _on_opacity_changed(self, alpha: int) -> None:
        r, g, b, _ = self._pixel_doc.current_color
        self._pixel_doc.current_color = (r, g, b, alpha)
        self._pixel_doc.use_transparent_color = alpha == 0
        self._update_color_preview()

    def _load_palette(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Palette", "", "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)")
        if not path:
            return
        try:
            pal = load_palette_from_image(path, max_colors=64)
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        self._anim.palette = pal
        self._pixel_doc.palette = list(pal)
        self._refresh_palette_buttons()

    def _palette_from_frame(self) -> None:
        if not self._anim.frames:
            return
        pal = palette_from_image(self._anim.frames[self._current_index].image, max_colors=64)
        self._anim.palette = pal
        self._pixel_doc.palette = list(pal)
        self._refresh_palette_buttons()

    def _refresh_palette_buttons(self) -> None:
        while self._palette_layout.count():
            item = self._palette_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not self._anim.palette:
            self._palette_layout.addWidget(QLabel("No palette"))
            return
        for color in self._anim.palette:
            btn = ClickableColorButton(color)
            btn.clicked_color.connect(self._set_color)
            self._palette_layout.addWidget(btn)
        self._palette_layout.addStretch(1)

    def _set_color(self, color: tuple[int, int, int, int]) -> None:
        self._pixel_doc.current_color = color
        self._pixel_doc.use_transparent_color = color[3] == 0
        self._anim.current_color = color
        self._opacity_slider.setValue(color[3])
        self._update_color_preview()

    def _update_color_preview(self) -> None:
        if self._pixel_doc.use_transparent_color:
            self._color_preview.setText("T")
            self._color_preview.setStyleSheet("background: #444; color: white; border: 1px solid #888;")
            return
        r, g, b, a = self._pixel_doc.current_color
        self._color_preview.setText("")
        self._color_preview.setStyleSheet(
            "background: rgba(%d, %d, %d, %d); border: 1px solid #111;" % (r, g, b, a)
        )

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)

    def _canvas_click_override(self, point: tuple[int, int]) -> bool:
        """Called before normal canvas paint when in anchor/pivot mode. Returns True if handled."""
        if self._anchor_radio.isChecked():
            name = self._anchor_name_combo.currentText() or "anchor"
            if 0 <= self._current_index < len(self._anim.frames):
                self._anim.frames[self._current_index].anchors.append(
                    AnchorPoint(name=name, x=point[0], y=point[1])
                )
                self._update_anchor_label()
                self.statusBar().showMessage(f"Anchor '{name}' at ({point[0]}, {point[1]})")
            return True
        if self._pivot_radio.isChecked():
            self._canvas.set_pivot_point(point)
            self.statusBar().showMessage(f"Pivot set at ({point[0]}, {point[1]})")
            return True
        return False

    def _install_canvas_click_override(self) -> None:
        original_press = self._canvas.mousePressEvent

        def patched(event):
            if self._canvas._document is None:
                return
            pt = self._canvas._event_to_pixel(event.position().toPoint())
            if pt is not None and event.button() == Qt.MouseButton.LeftButton:
                if self._canvas_click_override(pt):
                    return
            original_press(event)

        self._canvas.mousePressEvent = patched

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._install_canvas_click_override()
