from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QColor, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.core.animation_document import (
    AnchorPoint,
    AnimationFrame,
    AnimationProject,
    AnimationProjectError,
    FrameRect,
    FrameSequenceSpec,
    create_animation_project_from_gif,
    create_animation_project_from_sheet,
    create_blank_project,
    export_project_gif,
    export_project_metadata,
    load_animation_project,
    project_to_sheet,
    rotate_pixels_around_pivot,
    save_animation_project,
    track_to_sheet,
)
from src.core.image_io import load_image, save_image
from src.core.palette import add_color_to_palette, all_colors_from_image
from src.core.pixel_document import PixelDocument
from src.ui.animation_source_canvas import AnimationSourceCanvas
from src.ui.frame_strip_widget import FrameStripWidget
from src.ui.pixel_editor_window import ClickableColorButton
from src.ui.pixel_grid_canvas import PixelGridCanvas


class AnimationEditorWindow(QMainWindow):
    """Linked-sheet animation extraction, pixel editing, and playback studio."""

    def __init__(
        self, parent: QWidget | None = None, initial_palette: list | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pixel Forge - Animation Studio")
        self.resize(1480, 940)

        palette = list(initial_palette or [])
        self._project = create_blank_project(
            128, 32, frame_size=(32, 32), name="animation", palette=palette
        )
        track = self._project.add_track(
            "Track", FrameSequenceSpec(0, 0, 32, 32, 4, 32, 0)
        )
        self._project_path: Path | None = None
        self._dirty = False
        self._current_track_id: str | None = track.id
        self._current_frame_index = 0
        self._playback_direction = 1
        self._selected_color = (0, 0, 0, 255)
        self._updating_controls = False
        self._pending_frame_edit = False
        self._frame_image_cache: dict[tuple[str, int], Image.Image] = {}
        self._drag_palette_active = False
        self._drag_palette_previous_radio: QRadioButton | None = None
        self._drag_palette_previous_draw_selection = False

        self._play_timer = QTimer(self)
        self._play_timer.setSingleShot(True)
        self._edit_commit_timer = QTimer(self)
        self._edit_commit_timer.setSingleShot(True)
        self._edit_commit_timer.setInterval(120)

        self._source_canvas = AnimationSourceCanvas()
        self._frame_canvas = PixelGridCanvas()
        self._frame_doc = self._new_frame_document()
        self._frame_canvas.set_document(self._frame_doc)
        self._frame_strip = FrameStripWidget()

        self._create_controls()
        self._build_toolbar()
        self._build_layout()
        self._connect_signals()
        self._set_project(self._project, path=None, dirty=False)

    # ------------------------------------------------------------------ setup

    def _create_controls(self) -> None:
        self._track_combo = QComboBox()
        self._track_name_edit = QLineEdit("Track")
        self._track_up_button = QPushButton("Up")
        self._track_down_button = QPushButton("Down")
        self._track_rename_button = QPushButton("Rename")
        self._track_delete_button = QPushButton("Delete")

        self._origin_x_spin = QSpinBox()
        self._origin_y_spin = QSpinBox()
        self._frame_w_spin = QSpinBox()
        self._frame_h_spin = QSpinBox()
        self._frame_count_spin = QSpinBox()
        self._step_x_spin = QSpinBox()
        self._step_y_spin = QSpinBox()
        for spin in (self._origin_x_spin, self._origin_y_spin):
            spin.setRange(0, 16384)
        for spin in (self._frame_w_spin, self._frame_h_spin):
            spin.setRange(1, 4096)
            spin.setValue(32)
        self._frame_count_spin.setRange(1, 1024)
        self._frame_count_spin.setValue(4)
        for spin in (self._step_x_spin, self._step_y_spin):
            spin.setRange(-16384, 16384)
        self._step_x_spin.setValue(32)

        self._stride_right_button = QPushButton("Right")
        self._stride_left_button = QPushButton("Left")
        self._stride_down_button = QPushButton("Down")
        self._stride_up_button = QPushButton("Up")
        self._add_track_button = QPushButton("Add Track")
        self._replace_track_button = QPushButton("Replace Selected")
        self._geometry_status = QLabel()
        self._geometry_status.setWordWrap(True)

        self._source_zoom_spin = QSpinBox()
        self._source_zoom_spin.setRange(1, 32)
        self._source_zoom_spin.setValue(2)
        self._source_view_combo = QComboBox()
        self._source_view_combo.addItem("Working sheet", "working")
        self._source_view_combo.addItem("Original baseline", "original")

        self._frame_zoom_spin = QSpinBox()
        self._frame_zoom_spin.setRange(1, 64)
        self._frame_zoom_spin.setValue(20)
        self._paint_radio = QRadioButton("Paint")
        self._erase_radio = QRadioButton("Erase")
        self._picker_radio = QRadioButton("Picker")
        self._fill_radio = QRadioButton("Fill Rect")
        self._line_radio = QRadioButton("Line")
        self._ellipse_radio = QRadioButton("Ellipse")
        self._select_radio = QRadioButton("Select")
        self._stamp_radio = QRadioButton("Stamp")
        self._anchor_radio = QRadioButton("Anchor")
        self._pivot_radio = QRadioButton("Pivot")
        self._paint_radio.setChecked(True)

        self._clean_stroke_check = QCheckBox("Clean Stroke")
        self._right_erase_check = QCheckBox("Right-click Erase")
        self._draw_selection_check = QCheckBox("Draw Selection")
        self._mirror_check = QCheckBox("Mirror")
        self._copy_stamp_button = QPushButton("Copy Selection as Stamp")
        self._flip_stamp_h_button = QPushButton("Flip Stamp H")
        self._flip_stamp_v_button = QPushButton("Flip Stamp V")
        self._undo_last_action_button = QPushButton("Undo Last Action")
        self._undo_last_action_button.setToolTip(
            "Undo one completed frame-editing action. Shortcut: Ctrl+Z"
        )
        self._color_button = QPushButton("Pick Color")
        self._drag_palette_button = QPushButton("Drag Select Colors")
        self._transparent_button = QPushButton("Transparent")

        self._onion_check = QCheckBox("Onion skin")
        self._onion_next_check = QCheckBox("Show next")
        self._onion_opacity = QSlider(Qt.Orientation.Horizontal)
        self._onion_opacity.setRange(10, 80)
        self._onion_opacity.setValue(35)

        self._palette_container = QWidget()
        self._palette_layout = QGridLayout(self._palette_container)
        self._palette_layout.setContentsMargins(0, 0, 0, 0)
        self._palette_layout.setSpacing(2)

        self._anchor_name_edit = QLineEdit("weapon")
        self._anchor_list = QListWidget()
        self._delete_anchor_button = QPushButton("Delete Anchor")
        self._rotation_spin = QSpinBox()
        self._rotation_spin.setRange(-360, 360)
        self._rotation_spin.setSuffix(" deg")
        self._rotate_selection_button = QPushButton("Rotate Selection")

        self._preview_label = QLabel()
        self._preview_label.setMinimumSize(280, 280)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet(
            "background: #252525; border: 1px solid #555;"
        )
        self._play_button = QPushButton("Play")
        self._stop_button = QPushButton("Stop")
        self._first_button = QPushButton("|<")
        self._previous_button = QPushButton("<")
        self._next_button = QPushButton(">")
        self._last_button = QPushButton(">|")
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 60)
        self._fps_spin.setValue(8)
        self._fps_spin.setSuffix(" fps")
        self._playback_mode_combo = QComboBox()
        self._playback_mode_combo.addItem("Once", "once")
        self._playback_mode_combo.addItem("Loop", "loop")
        self._playback_mode_combo.addItem("Ping Pong", "ping_pong")
        self._playback_mode_combo.setCurrentIndex(1)
        self._range_start_spin = QSpinBox()
        self._range_end_spin = QSpinBox()
        self._frame_duration_spin = QSpinBox()
        self._frame_duration_spin.setRange(1, 60)
        self._frame_duration_spin.setSuffix("x")
        self._frame_label_edit = QLineEdit()
        self._analysis_label = QLabel("No frame selected")
        self._analysis_label.setWordWrap(True)
        self._reset_frame_button = QPushButton("Reset Frame from Original")
        self._reset_track_button = QPushButton("Reset Track from Original")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Animation Studio")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addAction("New", self._new_project)
        toolbar.addAction("Open Project", self._open_project)
        toolbar.addAction("Save", self._save_project)
        toolbar.addAction("Save As", self._save_project_as)
        toolbar.addSeparator()
        toolbar.addAction("Open Sheet", self._open_sheet)
        toolbar.addAction("Import GIF", self._open_gif)
        toolbar.addAction("Save Edited Sheet As", self._save_edited_sheet)
        toolbar.addSeparator()
        toolbar.addAction("Export Track PNG", self._export_track_png)
        toolbar.addAction("Export All PNG", self._export_all_png)
        toolbar.addAction("Export GIF", self._export_gif)
        toolbar.addAction("Export JSON", self._export_metadata)
        toolbar.addSeparator()
        self._undo_action = QAction("Undo Last Action", self)
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._undo_action.setToolTip(
            "Undo one completed frame-editing action. Shortcut: Ctrl+Z"
        )
        self._undo_action.triggered.connect(self._undo)
        toolbar.addAction(self._undo_action)
        self.addAction(self._undo_action)
        self._redo_action = QAction("Redo", self)
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._redo_action.triggered.connect(self._redo)
        toolbar.addAction(self._redo_action)
        self.addAction(self._redo_action)

    def _build_layout(self) -> None:
        source_tab = QWidget()
        source_layout = QVBoxLayout(source_tab)
        source_header = QHBoxLayout()
        source_header.addWidget(QLabel("View"))
        source_header.addWidget(self._source_view_combo)
        source_header.addWidget(QLabel("Zoom"))
        source_header.addWidget(self._source_zoom_spin)
        source_header.addStretch(1)
        source_layout.addLayout(source_header)

        geometry_group = QGroupBox("Build a track from the selected first frame")
        geometry_layout = QGridLayout(geometry_group)
        geometry_layout.addWidget(QLabel("Track"), 0, 0)
        geometry_layout.addWidget(self._track_name_edit, 0, 1, 1, 3)
        geometry_layout.addWidget(QLabel("Origin X"), 1, 0)
        geometry_layout.addWidget(self._origin_x_spin, 1, 1)
        geometry_layout.addWidget(QLabel("Origin Y"), 1, 2)
        geometry_layout.addWidget(self._origin_y_spin, 1, 3)
        geometry_layout.addWidget(QLabel("Frame W"), 2, 0)
        geometry_layout.addWidget(self._frame_w_spin, 2, 1)
        geometry_layout.addWidget(QLabel("Frame H"), 2, 2)
        geometry_layout.addWidget(self._frame_h_spin, 2, 3)
        geometry_layout.addWidget(QLabel("Frames"), 3, 0)
        geometry_layout.addWidget(self._frame_count_spin, 3, 1)
        geometry_layout.addWidget(QLabel("Step X"), 3, 2)
        geometry_layout.addWidget(self._step_x_spin, 3, 3)
        geometry_layout.addWidget(QLabel("Step Y"), 4, 2)
        geometry_layout.addWidget(self._step_y_spin, 4, 3)
        preset_row = QHBoxLayout()
        for button in (
            self._stride_right_button,
            self._stride_left_button,
            self._stride_down_button,
            self._stride_up_button,
        ):
            preset_row.addWidget(button)
        geometry_layout.addLayout(preset_row, 4, 0, 1, 2)
        action_row = QHBoxLayout()
        action_row.addWidget(self._add_track_button)
        action_row.addWidget(self._replace_track_button)
        geometry_layout.addLayout(action_row, 5, 0, 1, 4)
        geometry_layout.addWidget(self._geometry_status, 6, 0, 1, 4)
        source_layout.addWidget(geometry_group)

        source_scroll = QScrollArea()
        source_scroll.setWidgetResizable(False)
        source_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        source_scroll.setWidget(self._source_canvas)
        self._source_canvas.set_scroll_area(source_scroll)
        source_layout.addWidget(source_scroll, 1)

        frame_tab = QWidget()
        frame_layout = QVBoxLayout(frame_tab)
        mode_group = QButtonGroup(self)
        mode_row = QGridLayout()
        radios = (
            self._paint_radio,
            self._erase_radio,
            self._picker_radio,
            self._fill_radio,
            self._line_radio,
            self._ellipse_radio,
            self._select_radio,
            self._stamp_radio,
            self._anchor_radio,
            self._pivot_radio,
        )
        for index, radio in enumerate(radios):
            mode_group.addButton(radio)
            mode_row.addWidget(radio, index // 5, index % 5)
        frame_layout.addLayout(mode_row)

        option_row = QHBoxLayout()
        option_row.addWidget(self._clean_stroke_check)
        option_row.addWidget(self._right_erase_check)
        option_row.addWidget(self._draw_selection_check)
        option_row.addWidget(self._mirror_check)
        option_row.addWidget(QLabel("Zoom"))
        option_row.addWidget(self._frame_zoom_spin)
        option_row.addStretch(1)
        frame_layout.addLayout(option_row)

        paint_row = QHBoxLayout()
        paint_row.addWidget(self._color_button)
        palette_choice_label = QLabel("or")
        palette_choice_label.setStyleSheet("color: #999;")
        paint_row.addWidget(palette_choice_label)
        paint_row.addWidget(self._drag_palette_button)
        paint_row.addWidget(self._transparent_button)
        paint_row.addWidget(self._copy_stamp_button)
        paint_row.addWidget(self._flip_stamp_h_button)
        paint_row.addWidget(self._flip_stamp_v_button)
        paint_row.addWidget(self._undo_last_action_button)
        paint_row.addStretch(1)
        frame_layout.addLayout(paint_row)

        onion_row = QHBoxLayout()
        onion_row.addWidget(self._onion_check)
        onion_row.addWidget(QLabel("Opacity"))
        onion_row.addWidget(self._onion_opacity)
        onion_row.addWidget(self._onion_next_check)
        frame_layout.addLayout(onion_row)
        frame_layout.addWidget(self._palette_container)

        frame_scroll = QScrollArea()
        frame_scroll.setWidgetResizable(False)
        frame_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_scroll.setWidget(self._frame_canvas)
        self._frame_canvas.set_scroll_area(frame_scroll)
        frame_layout.addWidget(frame_scroll, 1)

        advanced = QGroupBox("Advanced frame data")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced_outer = QVBoxLayout(advanced)
        advanced_body = QWidget()
        advanced_layout = QGridLayout(advanced_body)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.addWidget(QLabel("Anchor name"), 0, 0)
        advanced_layout.addWidget(self._anchor_name_edit, 0, 1)
        advanced_layout.addWidget(self._delete_anchor_button, 0, 2)
        self._anchor_list.setMaximumHeight(100)
        advanced_layout.addWidget(self._anchor_list, 1, 0, 1, 3)
        advanced_layout.addWidget(QLabel("Rotation"), 2, 0)
        advanced_layout.addWidget(self._rotation_spin, 2, 1)
        advanced_layout.addWidget(self._rotate_selection_button, 2, 2)
        advanced_outer.addWidget(advanced_body)
        advanced_body.setVisible(False)
        advanced.toggled.connect(advanced_body.setVisible)
        frame_layout.addWidget(advanced)

        self._left_tabs = QTabWidget()
        self._left_tabs.addTab(source_tab, "Source Sheet")
        self._left_tabs.addTab(frame_tab, "Frame Editor")

        right = QWidget()
        right_layout = QVBoxLayout(right)
        track_group = QGroupBox("Direction Tracks")
        track_layout = QGridLayout(track_group)
        track_layout.addWidget(self._track_combo, 0, 0, 1, 4)
        track_layout.addWidget(self._track_up_button, 1, 0)
        track_layout.addWidget(self._track_down_button, 1, 1)
        track_layout.addWidget(self._track_rename_button, 1, 2)
        track_layout.addWidget(self._track_delete_button, 1, 3)
        right_layout.addWidget(track_group)

        preview_group = QGroupBox("Built Animation")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.addWidget(self._preview_label, 1)
        playback_row = QHBoxLayout()
        for button in (
            self._first_button,
            self._previous_button,
            self._play_button,
            self._stop_button,
            self._next_button,
            self._last_button,
        ):
            playback_row.addWidget(button)
        preview_layout.addLayout(playback_row)
        timing_row = QHBoxLayout()
        timing_row.addWidget(self._fps_spin)
        timing_row.addWidget(QLabel("Playback"))
        timing_row.addWidget(self._playback_mode_combo)
        timing_row.addWidget(QLabel("Range"))
        timing_row.addWidget(self._range_start_spin)
        timing_row.addWidget(QLabel("to"))
        timing_row.addWidget(self._range_end_spin)
        preview_layout.addLayout(timing_row)
        right_layout.addWidget(preview_group, 1)

        frame_group = QGroupBox("Timeline")
        frame_group_layout = QVBoxLayout(frame_group)
        strip_scroll = QScrollArea()
        strip_scroll.setWidgetResizable(False)
        strip_scroll.setWidget(self._frame_strip)
        strip_scroll.setMaximumHeight(125)
        frame_group_layout.addWidget(strip_scroll)
        frame_form = QFormLayout()
        frame_form.addRow("Frame duration", self._frame_duration_spin)
        frame_form.addRow("Frame label", self._frame_label_edit)
        frame_group_layout.addLayout(frame_form)
        right_layout.addWidget(frame_group)

        analysis_group = QGroupBox("Frame Analysis")
        analysis_layout = QVBoxLayout(analysis_group)
        analysis_layout.addWidget(self._analysis_label)
        reset_row = QHBoxLayout()
        reset_row.addWidget(self._reset_frame_button)
        reset_row.addWidget(self._reset_track_button)
        analysis_layout.addLayout(reset_row)
        right_layout.addWidget(analysis_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._left_tabs)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([900, 520])
        self.setCentralWidget(splitter)

    def _connect_signals(self) -> None:
        self._source_canvas.selection_changed.connect(self._on_source_selection)
        self._source_canvas.status_changed.connect(self.statusBar().showMessage)
        self._source_canvas.zoom_changed.connect(self._source_zoom_spin.setValue)
        self._source_zoom_spin.valueChanged.connect(self._source_canvas.set_zoom)
        self._source_view_combo.currentIndexChanged.connect(self._refresh_source_image)

        geometry_spins = (
            self._origin_x_spin,
            self._origin_y_spin,
            self._frame_w_spin,
            self._frame_h_spin,
            self._frame_count_spin,
            self._step_x_spin,
            self._step_y_spin,
        )
        for spin in geometry_spins:
            spin.valueChanged.connect(self._update_geometry_preview)
        self._stride_right_button.clicked.connect(lambda: self._set_stride(1, 0))
        self._stride_left_button.clicked.connect(lambda: self._set_stride(-1, 0))
        self._stride_down_button.clicked.connect(lambda: self._set_stride(0, 1))
        self._stride_up_button.clicked.connect(lambda: self._set_stride(0, -1))
        self._add_track_button.clicked.connect(self._add_track)
        self._replace_track_button.clicked.connect(self._replace_track)

        self._track_combo.currentIndexChanged.connect(self._on_track_selected)
        self._track_up_button.clicked.connect(lambda: self._move_track(-1))
        self._track_down_button.clicked.connect(lambda: self._move_track(1))
        self._track_rename_button.clicked.connect(self._rename_track)
        self._track_delete_button.clicked.connect(self._delete_track)

        for radio in (
            self._paint_radio,
            self._erase_radio,
            self._picker_radio,
            self._fill_radio,
            self._line_radio,
            self._ellipse_radio,
            self._select_radio,
            self._stamp_radio,
            self._anchor_radio,
            self._pivot_radio,
        ):
            radio.toggled.connect(self._update_editor_mode)
        self._frame_zoom_spin.valueChanged.connect(self._frame_canvas.set_zoom)
        self._frame_canvas.zoom_changed.connect(self._frame_zoom_spin.setValue)
        self._frame_canvas.image_changed.connect(self._on_frame_image_changed)
        self._frame_canvas.edit_started.connect(self._on_frame_edit_started)
        self._frame_canvas.edit_finished.connect(self._on_frame_edit_finished)
        self._frame_canvas.selection_changed.connect(self.statusBar().showMessage)
        self._frame_canvas.selection_finished.connect(
            self._finish_drag_palette_selection
        )
        self._frame_canvas.status_changed.connect(self.statusBar().showMessage)
        self._frame_canvas.point_clicked.connect(self._on_frame_point_clicked)
        self._clean_stroke_check.toggled.connect(
            self._frame_canvas.set_clean_stroke_enabled
        )
        self._right_erase_check.toggled.connect(
            self._frame_canvas.set_right_click_transparent_enabled
        )
        self._draw_selection_check.toggled.connect(
            self._frame_canvas.set_draw_selection_enabled
        )
        self._mirror_check.toggled.connect(self._frame_canvas.set_mirror)
        self._copy_stamp_button.clicked.connect(self._copy_selection_as_stamp)
        self._flip_stamp_h_button.clicked.connect(
            self._frame_canvas.flip_stamp_horizontal
        )
        self._flip_stamp_v_button.clicked.connect(
            self._frame_canvas.flip_stamp_vertical
        )
        self._undo_last_action_button.clicked.connect(self._undo)
        self._color_button.clicked.connect(self._pick_color)
        self._drag_palette_button.clicked.connect(self._begin_drag_palette_selection)
        self._transparent_button.clicked.connect(
            lambda: self._erase_radio.setChecked(True)
        )
        self._onion_check.toggled.connect(self._apply_onion_skin)
        self._onion_next_check.toggled.connect(self._apply_onion_skin)
        self._onion_opacity.valueChanged.connect(self._apply_onion_skin)
        self._delete_anchor_button.clicked.connect(self._delete_anchor)
        self._rotate_selection_button.clicked.connect(self._rotate_selection)
        self._edit_commit_timer.timeout.connect(self._flush_frame_edit)

        self._frame_strip.frame_selected.connect(self._select_frame)
        self._frame_strip.frame_reordered.connect(self._reorder_frame)
        self._frame_strip.range_selected.connect(self._set_playback_range)
        self._play_button.clicked.connect(self._toggle_play)
        self._stop_button.clicked.connect(self._stop_playback)
        self._first_button.clicked.connect(self._go_first)
        self._previous_button.clicked.connect(lambda: self._step_frame(-1))
        self._next_button.clicked.connect(lambda: self._step_frame(1))
        self._last_button.clicked.connect(self._go_last)
        self._play_timer.timeout.connect(self._advance_playback)
        self._fps_spin.valueChanged.connect(self._on_fps_changed)
        self._playback_mode_combo.currentIndexChanged.connect(
            self._on_playback_mode_changed
        )
        self._range_start_spin.valueChanged.connect(self._reset_playback_direction)
        self._range_end_spin.valueChanged.connect(self._reset_playback_direction)
        self._frame_duration_spin.valueChanged.connect(self._on_duration_changed)
        self._frame_label_edit.editingFinished.connect(self._on_label_changed)
        self._reset_frame_button.clicked.connect(self._reset_frame)
        self._reset_track_button.clicked.connect(self._reset_track)

    # --------------------------------------------------------------- projects

    def _set_project(
        self,
        project: AnimationProject,
        *,
        path: Path | None,
        dirty: bool,
    ) -> None:
        self._pause_playback()
        self._pending_frame_edit = False
        self._edit_commit_timer.stop()
        self._project = project
        self._frame_image_cache.clear()
        self._project_path = path
        self._current_track_id = project.tracks[0].id if project.tracks else None
        self._current_frame_index = 0
        self._fps_spin.blockSignals(True)
        self._fps_spin.setValue(project.fps)
        self._fps_spin.blockSignals(False)
        self._playback_mode_combo.blockSignals(True)
        mode_index = self._playback_mode_combo.findData(project.playback_mode)
        self._playback_mode_combo.setCurrentIndex(max(0, mode_index))
        self._playback_mode_combo.blockSignals(False)
        self._playback_direction = 1
        self._sync_track_combo()
        self._refresh_source_image()
        self._refresh_palette()
        if self._current_track_id is not None:
            self._load_track_geometry()
        else:
            self._on_source_selection(
                (
                    0,
                    0,
                    min(project.frame_width, project.sheet_size[0]),
                    min(project.frame_height, project.sheet_size[1]),
                )
            )
        self._load_frame(0, flush=False)
        self._set_dirty(dirty)
        self.statusBar().showMessage(
            f"Animation project: {project.name} ({project.sheet_size[0]}x{project.sheet_size[1]})"
        )

    def _new_project(self) -> None:
        if not self._maybe_close_project():
            return
        width, ok = QInputDialog.getInt(
            self, "New Animation", "Frame width:", 32, 1, 4096
        )
        if not ok:
            return
        height, ok = QInputDialog.getInt(
            self, "New Animation", "Frame height:", 32, 1, 4096
        )
        if not ok:
            return
        count, ok = QInputDialog.getInt(
            self, "New Animation", "Frame count:", 4, 1, 1024
        )
        if not ok:
            return
        project = create_blank_project(
            width * count,
            height,
            frame_size=(width, height),
            palette=list(self._project.palette),
        )
        project.add_track(
            "Track", FrameSequenceSpec(0, 0, width, height, count, width, 0)
        )
        self._set_project(project, path=None, dirty=True)

    def _open_sheet(self) -> None:
        if not self._maybe_close_project():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Sprite Sheet",
            "",
            "Images (*.png *.bmp *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        try:
            image = load_image(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        frame_width = min(32, image.width)
        frame_height = min(32, image.height)
        project = create_animation_project_from_sheet(
            image,
            name=Path(path).stem,
            frame_size=(frame_width, frame_height),
            fps=self._fps_spin.value(),
            palette=list(self._project.palette),
            source_path=path,
        )
        self._set_project(project, path=None, dirty=True)

    def _open_gif(self) -> None:
        if not self._maybe_close_project():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Animated GIF",
            "",
            "GIF Images (*.gif)",
        )
        if not path:
            return
        try:
            project = create_animation_project_from_gif(
                path,
                palette=list(self._project.palette),
            )
        except (AnimationProjectError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "GIF import failed", str(exc))
            return
        self._set_project(project, path=None, dirty=True)
        self.statusBar().showMessage(
            f"Imported {len(project.tracks[0].frames)} GIF frames from "
            f"{Path(path).name}"
        )

    def _open_project(self) -> None:
        if not self._maybe_close_project():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Animation Project", "", "Pixel Forge Animation (*.pfa)"
        )
        if not path:
            return
        try:
            project = load_animation_project(path)
        except (AnimationProjectError, OSError) as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self._set_project(project, path=Path(path), dirty=False)

    def _save_project(self) -> bool:
        self._flush_frame_edit()
        if self._project_path is None:
            return self._save_project_as()
        try:
            save_animation_project(self._project, self._project_path)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self._set_dirty(False)
        self.statusBar().showMessage(f"Saved project to {self._project_path.name}")
        return True

    def _save_project_as(self) -> bool:
        self._flush_frame_edit()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Animation Project",
            f"{self._project.name}.pfa",
            "Pixel Forge Animation (*.pfa)",
        )
        if not path:
            return False
        if not path.lower().endswith(".pfa"):
            path += ".pfa"
        self._project_path = Path(path)
        return self._save_project()

    def _save_edited_sheet(self) -> None:
        self._flush_frame_edit()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Edited Sprite Sheet As",
            f"{self._project.name}_edited.png",
            "PNG (*.png)",
        )
        if path:
            save_image(self._project.working_sheet, path)
            self.statusBar().showMessage(f"Saved edited sheet to {Path(path).name}")

    def _maybe_close_project(self) -> bool:
        self._flush_frame_edit()
        if not self._dirty:
            return True
        choice = QMessageBox.warning(
            self,
            "Unsaved Animation Project",
            "Save changes to the animation project?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Save:
            return self._save_project()
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._maybe_close_project():
            event.accept()
        else:
            event.ignore()

    # ------------------------------------------------------------ source setup

    def _current_spec(self) -> FrameSequenceSpec:
        return FrameSequenceSpec(
            self._origin_x_spin.value(),
            self._origin_y_spin.value(),
            self._frame_w_spin.value(),
            self._frame_h_spin.value(),
            self._frame_count_spin.value(),
            self._step_x_spin.value(),
            self._step_y_spin.value(),
        )

    def _on_source_selection(self, rect: FrameRect) -> None:
        self._updating_controls = True
        self._origin_x_spin.setValue(rect[0])
        self._origin_y_spin.setValue(rect[1])
        self._frame_w_spin.setValue(rect[2])
        self._frame_h_spin.setValue(rect[3])
        self._updating_controls = False
        self._update_geometry_preview()

    def _set_stride(self, horizontal: int, vertical: int) -> None:
        self._step_x_spin.setValue(horizontal * self._frame_w_spin.value())
        self._step_y_spin.setValue(vertical * self._frame_h_spin.value())

    def _update_geometry_preview(self) -> None:
        if self._updating_controls:
            return
        spec = self._current_spec()
        errors = spec.validation_errors(self._project.sheet_size)
        if self._project.tracks and (
            spec.frame_width != self._project.frame_width
            or spec.frame_height != self._project.frame_height
        ):
            errors.append(
                f"Project tracks use {self._project.frame_width}x{self._project.frame_height} frames."
            )
        selected_id = self._current_track_id
        overlaps = self._project.overlaps_for_spec(spec, excluding_track_id=selected_id)
        overlap_rects = {rect for pair in overlaps for rect in pair}
        frames: list[tuple[FrameRect, bool, bool]] = []
        sheet_width, sheet_height = self._project.sheet_size
        for rect in spec.rectangles():
            x, y, width, height = rect
            valid = (
                x >= 0
                and y >= 0
                and x + width <= sheet_width
                and y + height <= sheet_height
            )
            frames.append((rect, valid, rect in overlap_rects))
        self._source_canvas.set_frame_rects(frames)
        self._source_canvas.set_selection(
            (spec.origin_x, spec.origin_y, spec.frame_width, spec.frame_height)
        )
        self._add_track_button.setEnabled(not errors)
        self._replace_track_button.setEnabled(not errors and selected_id is not None)
        if errors:
            self._geometry_status.setStyleSheet("color: #ff6b78;")
            self._geometry_status.setText(errors[0])
        elif overlaps:
            self._geometry_status.setStyleSheet("color: #ffb347;")
            self._geometry_status.setText(
                "Valid, but mapped rectangles overlap. Shared pixels will update together."
            )
        else:
            self._geometry_status.setStyleSheet("color: #64dc91;")
            self._geometry_status.setText(
                f"Valid: {spec.count} frames, step ({spec.step_x}, {spec.step_y})."
            )

    def _add_track(self) -> None:
        try:
            track = self._project.add_track(
                self._track_name_edit.text(), self._current_spec()
            )
        except AnimationProjectError as exc:
            QMessageBox.warning(self, "Cannot add track", str(exc))
            return
        self._current_track_id = track.id
        self._current_frame_index = 0
        self._sync_track_combo()
        self._load_frame(0)
        self._set_dirty(True)

    def _replace_track(self) -> None:
        if self._current_track_id is None:
            return
        choice = QMessageBox.question(
            self,
            "Replace Track",
            "Replace this track's extraction geometry and reset its frame metadata?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            track = self._project.replace_track(
                self._current_track_id,
                self._track_name_edit.text(),
                self._current_spec(),
            )
        except AnimationProjectError as exc:
            QMessageBox.warning(self, "Cannot replace track", str(exc))
            return
        self._current_track_id = track.id
        self._current_frame_index = 0
        self._frame_image_cache.clear()
        self._sync_track_combo()
        self._load_frame(0)
        self._set_dirty(True)

    def _sync_track_combo(self) -> None:
        self._track_combo.blockSignals(True)
        self._track_combo.clear()
        selected_index = -1
        for index, track in enumerate(self._project.tracks):
            self._track_combo.addItem(track.name, track.id)
            if track.id == self._current_track_id:
                selected_index = index
        self._track_combo.setCurrentIndex(selected_index)
        self._track_combo.blockSignals(False)
        enabled = selected_index >= 0
        for button in (
            self._track_up_button,
            self._track_down_button,
            self._track_rename_button,
            self._track_delete_button,
        ):
            button.setEnabled(enabled)

    def _on_track_selected(self, index: int) -> None:
        if index < 0:
            return
        self._flush_frame_edit()
        self._current_track_id = self._track_combo.itemData(index)
        self._current_frame_index = 0
        self._load_track_geometry()
        self._load_frame(0, flush=False)

    def _load_track_geometry(self) -> None:
        if self._current_track_id is None:
            return
        track = self._project.track(self._current_track_id)
        spec = track.spec
        self._updating_controls = True
        self._track_name_edit.setText(track.name)
        self._origin_x_spin.setValue(spec.origin_x)
        self._origin_y_spin.setValue(spec.origin_y)
        self._frame_w_spin.setValue(spec.frame_width)
        self._frame_h_spin.setValue(spec.frame_height)
        self._frame_count_spin.setValue(spec.count)
        self._step_x_spin.setValue(spec.step_x)
        self._step_y_spin.setValue(spec.step_y)
        self._updating_controls = False
        self._update_geometry_preview()

    def _rename_track(self) -> None:
        if self._current_track_id is None:
            return
        track = self._project.track(self._current_track_id)
        name, ok = QInputDialog.getText(
            self, "Rename Track", "Track name:", text=track.name
        )
        if not ok:
            return
        track.name = self._project.unique_track_name(name, excluding_id=track.id)
        self._track_name_edit.setText(track.name)
        self._sync_track_combo()
        self._set_dirty(True)

    def _move_track(self, delta: int) -> None:
        if self._current_track_id is None:
            return
        self._project.move_track(self._current_track_id, delta)
        self._sync_track_combo()
        self._set_dirty(True)

    def _delete_track(self) -> None:
        if self._current_track_id is None:
            return
        track = self._project.track(self._current_track_id)
        choice = QMessageBox.question(self, "Delete Track", f"Delete '{track.name}'?")
        if choice != QMessageBox.StandardButton.Yes:
            return
        index = self._project.track_index(track.id)
        self._project.delete_track(track.id)
        self._frame_image_cache.clear()
        if self._project.tracks:
            self._current_track_id = self._project.tracks[
                min(index, len(self._project.tracks) - 1)
            ].id
        else:
            self._current_track_id = None
        self._current_frame_index = 0
        self._sync_track_combo()
        if self._current_track_id is not None:
            self._load_track_geometry()
        self._load_frame(0)
        self._set_dirty(True)

    # -------------------------------------------------------------- frame edit

    def _new_frame_document(self) -> PixelDocument:
        if self._current_track_id is None:
            image = Image.new(
                "RGBA",
                (self._project.frame_width, self._project.frame_height),
                (0, 0, 0, 0),
            )
        else:
            image = self._project.frame_image(
                self._current_track_id, self._current_frame_index
            )
        document = PixelDocument(
            image=image,
            name=f"{self._project.name}_frame_{self._current_frame_index + 1}",
            palette=list(self._project.palette),
        )
        document.current_color = self._selected_color
        document.use_transparent_color = (
            self._erase_radio.isChecked() if hasattr(self, "_erase_radio") else False
        )
        return document

    def _load_frame(self, index: int, *, flush: bool = True) -> None:
        if flush:
            self._flush_frame_edit()
        if self._current_track_id is None:
            self._current_frame_index = 0
            self._frame_doc = self._new_frame_document()
            self._frame_canvas.set_document(self._frame_doc)
            self._frame_strip.set_frames([], 0)
            self._preview_label.clear()
            self._analysis_label.setText("Add a direction track to begin editing.")
            self._source_canvas.set_active_rect(None)
            self._update_range_controls()
            return
        track = self._project.track(self._current_track_id)
        if not track.frames:
            return
        self._current_frame_index = max(0, min(index, len(track.frames) - 1))
        self._frame_doc = self._new_frame_document()
        self._frame_canvas.set_document(self._frame_doc)
        self._frame_canvas.set_zoom(self._frame_zoom_spin.value())
        frame = track.frames[self._current_frame_index]
        self._frame_canvas.set_anchor_points(
            [(anchor.x, anchor.y, anchor.name) for anchor in frame.anchors]
        )
        self._frame_canvas.set_pivot_point(frame.pivot)
        self._apply_onion_skin()
        self._sync_frame_strip()
        self._frame_strip.set_current(self._current_frame_index)
        self._source_canvas.set_active_rect(frame.source_rect)
        self._frame_duration_spin.blockSignals(True)
        self._frame_duration_spin.setValue(frame.duration_ticks)
        self._frame_duration_spin.blockSignals(False)
        self._frame_label_edit.setText(frame.label)
        self._update_anchor_list()
        self._update_range_controls()
        self._refresh_preview()
        self._refresh_analysis()
        self.statusBar().showMessage(
            f"{track.name}: frame {self._current_frame_index + 1} of {len(track.frames)}"
        )

    def _select_frame(self, index: int) -> None:
        self._load_frame(index)

    def _reorder_frame(self, from_index: int, to_index: int) -> None:
        if self._current_track_id is None:
            return
        self._flush_frame_edit()
        track = self._project.track(self._current_track_id)
        if not (
            0 <= from_index < len(track.frames) and 0 <= to_index < len(track.frames)
        ):
            return
        frame = track.frames.pop(from_index)
        track.frames.insert(to_index, frame)
        self._current_frame_index = to_index
        self._load_frame(to_index, flush=False)
        self._set_dirty(True)

    def _set_playback_range(self, start: int, end: int) -> None:
        self._range_start_spin.setValue(start + 1)
        self._range_end_spin.setValue(end + 1)
        self._playback_direction = 1

    def _on_frame_image_changed(self) -> None:
        if self._current_track_id is None:
            return
        self._pause_playback()
        self._pending_frame_edit = True
        if not self._frame_canvas.pixel_edit_in_progress():
            self._edit_commit_timer.start()
        self._refresh_preview(use_editor=True)

    def _on_frame_edit_started(self) -> None:
        self._pause_playback()
        self._edit_commit_timer.stop()
        self._flush_frame_edit()

    def _on_frame_edit_finished(self, _before_image: object) -> None:
        self._edit_commit_timer.stop()
        self._flush_frame_edit()

    def _flush_frame_edit(self) -> None:
        self._edit_commit_timer.stop()
        if not self._pending_frame_edit or self._current_track_id is None:
            return
        self._pending_frame_edit = False
        changed = self._project.commit_frame_image(
            self._current_track_id,
            self._current_frame_index,
            self._frame_doc.image,
            "Edit animation frame",
        )
        if changed is None:
            return
        self._invalidate_frame_cache(changed)
        self._refresh_source_image()
        self._sync_frame_strip()
        self._refresh_preview()
        self._refresh_analysis()
        self._set_dirty(True)

    def _update_editor_mode(self) -> None:
        if self._paint_radio.isChecked() or self._erase_radio.isChecked():
            mode = "paint"
        elif self._picker_radio.isChecked():
            mode = "picker"
        elif self._fill_radio.isChecked():
            mode = "fill"
        elif self._line_radio.isChecked():
            mode = "line"
        elif self._ellipse_radio.isChecked():
            mode = "ellipse"
        elif self._select_radio.isChecked():
            mode = "select"
        elif self._stamp_radio.isChecked():
            mode = "stamp"
        elif self._anchor_radio.isChecked():
            mode = "anchor"
        else:
            mode = "pivot"
        self._frame_doc.use_transparent_color = self._erase_radio.isChecked()
        self._frame_doc.current_color = self._selected_color
        self._frame_canvas.set_mode(mode)

    def _on_frame_point_clicked(self, x: int, y: int, button: int) -> None:
        if (
            button != int(Qt.MouseButton.LeftButton.value)
            or self._current_track_id is None
        ):
            return
        if self._picker_radio.isChecked():
            self._set_color(self._frame_doc.image.getpixel((x, y)))
            self._paint_radio.setChecked(True)
            return
        frame = self._project.track(self._current_track_id).frames[
            self._current_frame_index
        ]
        if self._anchor_radio.isChecked():
            frame.anchors.append(
                AnchorPoint(self._anchor_name_edit.text().strip() or "anchor", x, y)
            )
            self._update_anchor_list()
            self._frame_canvas.set_anchor_points(
                [(anchor.x, anchor.y, anchor.name) for anchor in frame.anchors]
            )
            self._set_dirty(True)
        elif self._pivot_radio.isChecked():
            frame.pivot = (x, y)
            self._frame_canvas.set_pivot_point(frame.pivot)
            self._set_dirty(True)

    def _copy_selection_as_stamp(self) -> None:
        stamp = self._frame_doc.copy_selection_image(compact=True)
        if stamp is None:
            self.statusBar().showMessage("Select pixels before copying a stamp")
            return
        self._frame_canvas.set_stamp_image(stamp)
        self._stamp_radio.setChecked(True)
        self.statusBar().showMessage(f"Copied {stamp.width}x{stamp.height} stamp")

    def _pick_color(self) -> None:
        color = QColor(*self._selected_color)
        selected = QColorDialog.getColor(
            color,
            self,
            "Pick Paint Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if selected.isValid():
            self._set_color(
                (selected.red(), selected.green(), selected.blue(), selected.alpha())
            )
            self._project.palette = add_color_to_palette(
                self._project.palette, self._selected_color
            )
            self._refresh_palette()
            self._set_dirty(True)

    def _begin_drag_palette_selection(self) -> None:
        if self._drag_palette_active:
            return
        self._drag_palette_previous_radio = next(
            (
                radio
                for radio in (
                    self._paint_radio,
                    self._erase_radio,
                    self._picker_radio,
                    self._fill_radio,
                    self._line_radio,
                    self._ellipse_radio,
                    self._select_radio,
                    self._stamp_radio,
                    self._anchor_radio,
                    self._pivot_radio,
                )
                if radio.isChecked()
            ),
            self._paint_radio,
        )
        self._drag_palette_previous_draw_selection = (
            self._draw_selection_check.isChecked()
        )
        self._drag_palette_active = True
        self._drag_palette_button.setEnabled(False)
        self._frame_doc.clear_selection()
        self._frame_canvas.update()
        self._draw_selection_check.setChecked(False)
        self._select_radio.setChecked(True)
        self.statusBar().showMessage(
            "Drag a rectangle on the current frame to load its visible colors"
        )

    def _finish_drag_palette_selection(
        self, left: int, top: int, right: int, bottom: int
    ) -> None:
        if not self._drag_palette_active:
            return
        region = self._frame_doc.image.crop((left, top, right + 1, bottom + 1))
        extracted = all_colors_from_image(region)
        palette = extracted[:64]
        self._project.palette = palette
        self._frame_doc.palette = list(palette)
        self._refresh_palette()
        self._set_dirty(True)

        previous_radio = self._drag_palette_previous_radio
        restore_draw_selection = self._drag_palette_previous_draw_selection
        self._drag_palette_active = False
        self._drag_palette_previous_radio = None
        self._drag_palette_button.setEnabled(True)
        self._frame_doc.clear_selection()
        self._frame_canvas.update()
        if previous_radio is not None:
            previous_radio.setChecked(True)
        self._draw_selection_check.setChecked(restore_draw_selection)

        width = right - left + 1
        height = bottom - top + 1
        detail = (
            f"Loaded {len(palette)} colors from the selected {width}x{height} region"
        )
        if len(extracted) > len(palette):
            detail += f" ({len(extracted)} found; palette limited to 64)"
        self.statusBar().showMessage(detail)

    def _set_color(self, color: tuple[int, int, int, int]) -> None:
        self._selected_color = tuple(color)
        self._frame_doc.current_color = self._selected_color
        self._frame_doc.use_transparent_color = self._selected_color[3] == 0
        if self._selected_color[3] == 0:
            self._erase_radio.setChecked(True)
        elif self._erase_radio.isChecked():
            self._paint_radio.setChecked(True)
        self._update_color_button()

    def _refresh_palette(self) -> None:
        while self._palette_layout.count():
            item = self._palette_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, color in enumerate(self._project.palette[:64]):
            button = ClickableColorButton(color)
            button.clicked_color.connect(self._set_color)
            self._palette_layout.addWidget(button, index // 16, index % 16)
        if not self._project.palette:
            self._palette_layout.addWidget(QLabel("No project palette"), 0, 0)
        self._update_color_button()

    def _update_color_button(self) -> None:
        red, green, blue, alpha = self._selected_color
        self._color_button.setStyleSheet(
            f"background: rgba({red}, {green}, {blue}, {alpha});"
        )

    def _apply_onion_skin(self) -> None:
        if self._current_track_id is None or not self._onion_check.isChecked():
            self._frame_canvas.set_onion_skin(None, None)
            return
        track = self._project.track(self._current_track_id)
        previous = (
            self._project.frame_image(track.id, self._current_frame_index - 1)
            if self._current_frame_index > 0
            else None
        )
        following = (
            self._project.frame_image(track.id, self._current_frame_index + 1)
            if self._onion_next_check.isChecked()
            and self._current_frame_index + 1 < len(track.frames)
            else None
        )
        self._frame_canvas.set_onion_skin(
            previous, following, self._onion_opacity.value() / 100.0
        )

    def _update_anchor_list(self) -> None:
        self._anchor_list.clear()
        if self._current_track_id is None:
            return
        frame = self._project.track(self._current_track_id).frames[
            self._current_frame_index
        ]
        for anchor in frame.anchors:
            self._anchor_list.addItem(f"{anchor.name}: ({anchor.x}, {anchor.y})")

    def _delete_anchor(self) -> None:
        if self._current_track_id is None:
            return
        frame = self._project.track(self._current_track_id).frames[
            self._current_frame_index
        ]
        row = self._anchor_list.currentRow()
        if 0 <= row < len(frame.anchors):
            del frame.anchors[row]
            self._update_anchor_list()
            self._frame_canvas.set_anchor_points(
                [(anchor.x, anchor.y, anchor.name) for anchor in frame.anchors]
            )
            self._set_dirty(True)

    def _rotate_selection(self) -> None:
        if self._current_track_id is None:
            return
        selected = self._frame_doc.selected_points()
        frame = self._project.track(self._current_track_id).frames[
            self._current_frame_index
        ]
        if not selected or frame.pivot is None:
            self.statusBar().showMessage("Select pixels and place a pivot first")
            return
        angle = self._rotation_spin.value()
        if angle == 0:
            return
        self._frame_doc.image = rotate_pixels_around_pivot(
            self._frame_doc.image, selected, frame.pivot, angle
        )
        self._frame_canvas.invalidate_render_cache()
        self._pending_frame_edit = True
        self._flush_frame_edit()

    def _undo(self) -> None:
        self._flush_frame_edit()
        transaction = self._project.undo()
        if transaction is None:
            self.statusBar().showMessage("Nothing to undo")
            return
        self._refresh_after_sheet_change(transaction.rect)
        self._set_dirty(True)
        self.statusBar().showMessage(f"Undid: {transaction.description}")

    def _redo(self) -> None:
        self._flush_frame_edit()
        transaction = self._project.redo()
        if transaction is None:
            self.statusBar().showMessage("Nothing to redo")
            return
        self._refresh_after_sheet_change(transaction.rect)
        self._set_dirty(True)
        self.statusBar().showMessage(f"Redid: {transaction.description}")

    def _reset_frame(self) -> None:
        if self._current_track_id is None:
            return
        self._flush_frame_edit()
        rect = self._project.reset_frame(
            self._current_track_id, self._current_frame_index
        )
        if rect is not None:
            self._refresh_after_sheet_change(rect)
            self._set_dirty(True)

    def _reset_track(self) -> None:
        if self._current_track_id is None:
            return
        self._flush_frame_edit()
        track = self._project.track(self._current_track_id)
        choice = QMessageBox.question(
            self,
            "Reset Track",
            f"Reset every mapped frame in '{track.name}' from the original sheet?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        rect = self._project.reset_track(track.id)
        if rect is not None:
            self._refresh_after_sheet_change(rect)
            self._set_dirty(True)

    def _refresh_after_sheet_change(self, _rect: FrameRect) -> None:
        self._pending_frame_edit = False
        self._invalidate_frame_cache(_rect)
        self._refresh_source_image()
        self._load_frame(self._current_frame_index, flush=False)

    # --------------------------------------------------------------- playback

    def _toggle_play(self) -> None:
        if self._play_timer.isActive():
            self._pause_playback()
            return
        if self._current_track_id is None:
            return
        self._flush_frame_edit()
        start = max(0, self._range_start_spin.value() - 1)
        end = max(start, self._range_end_spin.value() - 1)
        if self._project.playback_mode == "once" and self._current_frame_index >= end:
            self._load_frame(start)
        elif self._project.playback_mode == "ping_pong":
            if self._current_frame_index <= start:
                self._playback_direction = 1
            elif self._current_frame_index >= end:
                self._playback_direction = -1
        self._play_button.setText("Pause")
        self._schedule_playback_tick()

    def _pause_playback(self) -> None:
        self._play_timer.stop()
        if hasattr(self, "_play_button"):
            self._play_button.setText("Play")

    def _stop_playback(self) -> None:
        self._pause_playback()
        self._playback_direction = 1
        if self._current_track_id is not None:
            self._load_frame(max(0, self._range_start_spin.value() - 1))

    def _schedule_playback_tick(self) -> None:
        if self._current_track_id is None:
            return
        frame = self._project.track(self._current_track_id).frames[
            self._current_frame_index
        ]
        interval = max(
            10, round(1000 / self._project.fps) * max(1, frame.duration_ticks)
        )
        self._play_timer.start(interval)

    def _advance_playback(self) -> None:
        if self._current_track_id is None:
            return
        start = max(0, self._range_start_spin.value() - 1)
        end = max(start, self._range_end_spin.value() - 1)
        mode = self._project.playback_mode
        if mode == "once":
            if self._current_frame_index >= end:
                self._pause_playback()
                return
            target = self._current_frame_index + 1
        elif mode == "ping_pong":
            if start == end:
                target = start
            else:
                if self._current_frame_index <= start:
                    self._playback_direction = 1
                elif self._current_frame_index >= end:
                    self._playback_direction = -1
                target = self._current_frame_index + self._playback_direction
                target = max(start, min(end, target))
        elif self._current_frame_index >= end:
            target = start
        else:
            target = self._current_frame_index + 1
        self._load_frame(target)
        self._play_button.setText("Pause")
        self._schedule_playback_tick()

    def _step_frame(self, delta: int) -> None:
        self._pause_playback()
        if self._current_track_id is None:
            return
        track = self._project.track(self._current_track_id)
        self._load_frame(
            max(0, min(len(track.frames) - 1, self._current_frame_index + delta))
        )

    def _go_first(self) -> None:
        self._pause_playback()
        if self._current_track_id is not None:
            self._load_frame(0)

    def _go_last(self) -> None:
        self._pause_playback()
        if self._current_track_id is not None:
            self._load_frame(
                len(self._project.track(self._current_track_id).frames) - 1
            )

    def _on_fps_changed(self, value: int) -> None:
        self._project.fps = value
        self._set_dirty(True)
        if self._play_timer.isActive():
            self._schedule_playback_tick()

    def _on_playback_mode_changed(self, _index: int) -> None:
        mode = self._playback_mode_combo.currentData()
        if mode not in {"once", "loop", "ping_pong"}:
            return
        self._pause_playback()
        self._project.playback_mode = mode
        self._playback_direction = 1
        self._set_dirty(True)

    def _reset_playback_direction(self, _value: int | None = None) -> None:
        self._playback_direction = 1

    def _on_duration_changed(self, value: int) -> None:
        if self._current_track_id is None or self._updating_controls:
            return
        frame = self._project.track(self._current_track_id).frames[
            self._current_frame_index
        ]
        if frame.duration_ticks != value:
            frame.duration_ticks = value
            self._sync_frame_strip()
            self._set_dirty(True)

    def _on_label_changed(self) -> None:
        if self._current_track_id is None:
            return
        frame = self._project.track(self._current_track_id).frames[
            self._current_frame_index
        ]
        if frame.label != self._frame_label_edit.text():
            frame.label = self._frame_label_edit.text()
            self._sync_frame_strip()
            self._set_dirty(True)

    def _update_range_controls(self) -> None:
        count = (
            len(self._project.track(self._current_track_id).frames)
            if self._current_track_id is not None
            else 1
        )
        count = max(1, count)
        range_changed = self._range_end_spin.maximum() != count
        self._range_start_spin.setRange(1, count)
        self._range_end_spin.setRange(1, count)
        if range_changed:
            self._range_start_spin.setValue(1)
            self._range_end_spin.setValue(count)
        elif self._range_start_spin.value() > self._range_end_spin.value():
            self._range_start_spin.setValue(self._range_end_spin.value())

    # -------------------------------------------------------- preview/analysis

    def _sync_frame_strip(self) -> None:
        if self._current_track_id is None:
            self._frame_strip.set_frames([], 0)
            return
        track = self._project.track(self._current_track_id)
        frames = [
            AnimationFrame(
                image=(
                    self._frame_doc.image.copy()
                    if index == self._current_frame_index and self._pending_frame_edit
                    else self._cached_frame_image(track.id, index)
                ),
                duration_ticks=frame.duration_ticks,
                label=frame.label,
            )
            for index, frame in enumerate(track.frames)
        ]
        self._frame_strip.set_frames(frames, self._current_frame_index)

    def _cached_frame_image(self, track_id: str, frame_index: int) -> Image.Image:
        key = (track_id, frame_index)
        cached = self._frame_image_cache.get(key)
        if cached is None:
            cached = self._project.frame_image(track_id, frame_index)
            self._frame_image_cache[key] = cached
        return cached.copy()

    def _invalidate_frame_cache(self, changed_rect: FrameRect | None = None) -> None:
        if changed_rect is None:
            self._frame_image_cache.clear()
            return
        for key in self._project.intersecting_frames(changed_rect):
            self._frame_image_cache.pop(key, None)

    def _refresh_preview(self, *, use_editor: bool = False) -> None:
        if self._current_track_id is None:
            self._preview_label.clear()
            return
        from src.core.qt_image import pil_image_to_qpixmap

        image = (
            self._frame_doc.image
            if use_editor
            else self._project.frame_image(
                self._current_track_id, self._current_frame_index
            )
        )
        pixmap = pil_image_to_qpixmap(image).scaled(
            self._preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._preview_label.setPixmap(pixmap)

    def _refresh_analysis(self) -> None:
        if self._current_track_id is None:
            self._analysis_label.setText("No frame selected")
            return
        track = self._project.track(self._current_track_id)
        frame = track.frames[self._current_frame_index]
        image = self._project.frame_image(track.id, self._current_frame_index)
        alpha = image.getchannel("A")
        opaque_bounds = alpha.getbbox()
        occupied = sum(1 for value in alpha.get_flattened_data() if value > 0)
        difference_count = 0
        difference_bounds = None
        if self._current_frame_index > 0:
            previous = self._project.frame_image(
                track.id, self._current_frame_index - 1
            )
            difference = ImageChops.difference(image, previous)
            difference_bounds = difference.getbbox()
            difference_count = sum(
                1
                for pixel in difference.get_flattened_data()
                if any(channel != 0 for channel in pixel)
            )
        rect_text = (
            str(frame.source_rect) if frame.source_rect is not None else "detached"
        )
        self._analysis_label.setText(
            f"Frame {self._current_frame_index + 1}/{len(track.frames)} | Source {rect_text}\n"
            f"Opaque bounds: {opaque_bounds or 'empty'} | Occupied pixels: {occupied}\n"
            f"Changed vs previous: {difference_count} | Change bounds: {difference_bounds or 'none'}"
        )

    def _refresh_source_image(self) -> None:
        if not hasattr(self, "_source_view_combo"):
            return
        image = (
            self._project.original_sheet
            if self._source_view_combo.currentData() == "original"
            else self._project.working_sheet
        )
        if self._source_canvas.selection() is None:
            self._source_canvas.set_image(image)
        else:
            self._source_canvas.refresh_image(image)
        if self._current_track_id is not None:
            frame = self._project.track(self._current_track_id).frames[
                self._current_frame_index
            ]
            self._source_canvas.set_active_rect(frame.source_rect)

    # ---------------------------------------------------------------- exports

    def _export_track_png(self) -> None:
        self._flush_frame_edit()
        if self._current_track_id is None:
            return
        track = self._project.track(self._current_track_id)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Track",
            f"{self._project.name}_{track.name}.png",
            "PNG (*.png)",
        )
        if path:
            save_image(track_to_sheet(self._project, track.id), path)

    def _export_all_png(self) -> None:
        self._flush_frame_edit()
        if not self._project.tracks:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export All Tracks", f"{self._project.name}_tracks.png", "PNG (*.png)"
        )
        if path:
            save_image(project_to_sheet(self._project), path)

    def _export_gif(self) -> None:
        self._flush_frame_edit()
        if self._current_track_id is None:
            return
        track = self._project.track(self._current_track_id)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export GIF", f"{self._project.name}_{track.name}.gif", "GIF (*.gif)"
        )
        if path:
            export_project_gif(self._project, track.id, path)

    def _export_metadata(self) -> None:
        self._flush_frame_edit()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Metadata",
            f"{self._project.name}_animation.json",
            "JSON (*.json)",
        )
        if path:
            export_project_metadata(self._project, path)

    # ---------------------------------------------------------------- utility

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        marker = "*" if dirty else ""
        location = self._project_path.name if self._project_path else self._project.name
        self.setWindowTitle(f"Pixel Forge - Animation Studio - {location}{marker}")
