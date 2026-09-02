from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QWheelEvent
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core.character_forge import (
    CAMERA_HEIGHT_LABELS,
    DEFAULT_SPRITE_STYLE,
    CHARACTER_SLOT_LABELS,
    CHARACTER_SLOTS,
    DIRECTION_LABELS,
    CharacterAnimation,
    CharacterCatalog,
    CharacterForgeError,
    clear_character_image_cache,
    composite_character_animation,
    create_default_catalog,
    create_default_recipe,
    export_character,
    extract_character_frame,
    load_part_animation,
    load_recipe,
    local_recipe_directory,
    local_recipe_path,
    part_default_main_color,
    randomize_recipe,
    save_recipe,
    validate_catalog,
    validate_recipe,
)
from src.core.image_io import save_image
from src.core.pixel_document import PixelDocument
from src.core.qt_image import pil_image_to_qpixmap
from src.ui.pixel_editor_window import PixelEditorWindow

SLOT_LABELS = CHARACTER_SLOT_LABELS


class CharacterPreviewLabel(QLabel):
    """Pixel preview that exposes wheel motion as discrete zoom steps."""

    zoom_step_requested = Signal(int)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        self.zoom_step_requested.emit(1 if delta > 0 else -1)
        event.accept()


class CharacterForgeWindow(QMainWindow):
    """Assemble, preview, save, and export modular animated characters."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        catalog: CharacterCatalog | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Character Forge")
        self.resize(1240, 840)

        self.catalog = catalog or create_default_catalog()
        validate_catalog(self.catalog)
        self.recipe = create_default_recipe()
        available_ids = {part.id for part in self.catalog.parts}
        for slot, part_id in tuple(self.recipe.parts.items()):
            if part_id not in available_ids:
                self.recipe.parts[slot] = None
        self._sheet = None
        self._frame_index = 0
        self._playback_step = 0
        self._updating_controls = False
        self._part_selection_history: list[str] = []
        self._pixel_windows: list[PixelEditorWindow] = []

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)

        self._build_ui()
        self._connect_signals()
        self._sync_recipe_to_controls()
        self._on_animation_changed()
        self._timer.start()
        self.play_button.setText("Pause")
        self.statusBar().showMessage(
            "Character recipe drives a pixel-perfect composite of the locked base sheets"
        )

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        animation_group = QGroupBox("Animation & Base")
        animation_group.setMaximumWidth(285)
        animation_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        animation_layout = QVBoxLayout(animation_group)
        animation_form = QFormLayout()

        self.base_combo = QComboBox()
        self.base_combo.setObjectName("characterBaseCombo")
        for base in self.catalog.bases:
            self.base_combo.addItem(base.name, base.id)
        self.base_combo.setEnabled(self.base_combo.count() > 1)
        animation_form.addRow("Base", self.base_combo)

        self.sprite_style_combo = QComboBox()
        self.sprite_style_combo.setObjectName("characterSpriteStyleCombo")
        for style_id, style_name in self.catalog.sprite_styles.items():
            self.sprite_style_combo.addItem(style_name, style_id)
        animation_form.addRow("Sprite style", self.sprite_style_combo)

        self.animation_combo = QComboBox()
        self.animation_combo.setObjectName("characterAnimationCombo")
        initial_base = self.catalog.bases[0]
        for animation in initial_base.animations.values():
            self.animation_combo.addItem(animation.name, animation.id)
        animation_form.addRow("Animation", self.animation_combo)

        self.camera_height_combo = QComboBox()
        self.camera_height_combo.setObjectName("characterCameraHeightCombo")
        for camera_height in initial_base.camera_heights:
            self.camera_height_combo.addItem(
                CAMERA_HEIGHT_LABELS.get(camera_height, camera_height), camera_height
            )
        animation_form.addRow("Camera height", self.camera_height_combo)

        self.direction_combo = QComboBox()
        self.direction_combo.setObjectName("characterDirectionCombo")
        animation_form.addRow("Direction", self.direction_combo)

        self.zoom_combo = QComboBox()
        self.zoom_combo.setObjectName("characterZoomCombo")
        for zoom in (1, 2, 4, 8):
            self.zoom_combo.addItem(f"{zoom}x", zoom)
        self.zoom_combo.setCurrentIndex(self.zoom_combo.findData(8))
        self.zoom_combo.setToolTip(
            "Choose a preview scale, or use the mouse wheel over the preview"
        )
        animation_form.addRow("Preview zoom", self.zoom_combo)
        animation_layout.addLayout(animation_form)

        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("characterPlayButton")
        animation_layout.addWidget(self.play_button)

        source_note = QLabel(
            "The supplied base geometry is locked. Character parts are transparent, "
            "sheet-aligned overlays."
        )
        source_note.setWordWrap(True)
        source_note.setStyleSheet("color: palette(mid);")
        animation_layout.addWidget(source_note)
        animation_layout.addStretch(1)

        preview_group = QGroupBox("Character Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = CharacterPreviewLabel()
        self.preview_label.setObjectName("characterPreview")
        self.preview_label.setToolTip("Mouse wheel: zoom preview in or out")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(530, 530)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview_label.setStyleSheet(
            "background-color: #272727; border: 1px solid #555;"
        )
        preview_layout.addWidget(self.preview_label, 1)
        self.frame_label = QLabel()
        self.frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.frame_label)

        parts_group = QGroupBox("Character Recipe")
        parts_group.setMaximumWidth(405)
        parts_layout = QVBoxLayout(parts_group)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name"))
        self.name_edit = QLineEdit("character")
        self.name_edit.setObjectName("characterNameEdit")
        name_row.addWidget(self.name_edit, 1)
        parts_layout.addLayout(name_row)

        selector_grid = QGridLayout()
        selector_grid.setColumnStretch(1, 1)
        self.part_combos: dict[str, QComboBox] = {}
        self.edit_part_buttons: dict[str, QPushButton] = {}
        for row, slot in enumerate(CHARACTER_SLOTS):
            selector_grid.addWidget(QLabel(SLOT_LABELS[slot]), row, 0)
            combo = QComboBox()
            combo.setObjectName(f"characterPart_{slot}")
            combo.addItem("None", None)
            for part in self.catalog.parts_for_slot(
                slot,
                initial_base.id,
                self.recipe.camera_height,
                self.recipe.sprite_style,
            ):
                suffix = " (Incomplete)" if part.status == "incomplete" else ""
                combo.addItem(f"{part.name}{suffix}", part.id)
            combo.setEnabled(combo.count() > 1)
            selector_grid.addWidget(combo, row, 1)
            self.part_combos[slot] = combo

            edit_button = QPushButton("Edit Sheet...")
            edit_button.setObjectName(f"characterEdit_{slot}")
            edit_button.setToolTip(
                "Open the selected part's current animation sheet in Pixel Forge"
            )
            edit_button.setEnabled(False)
            selector_grid.addWidget(edit_button, row, 2)
            self.edit_part_buttons[slot] = edit_button
        parts_layout.addLayout(selector_grid)

        self.reload_catalog_button = QPushButton("Reload Components")
        self.reload_catalog_button.setObjectName("characterReloadComponents")
        parts_layout.addWidget(self.reload_catalog_button)

        color_row = QHBoxLayout()
        self.part_color_label = QLabel("Part main color")
        self.part_color_button = QPushButton("Color...")
        self.part_color_button.setObjectName("characterPartMainColorButton")
        self.reset_part_color_button = QPushButton("Reset")
        self.reset_part_color_button.setObjectName("characterPartMainColorReset")
        color_row.addWidget(self.part_color_label)
        color_row.addWidget(self.part_color_button, 1)
        color_row.addWidget(self.reset_part_color_button)
        parts_layout.addLayout(color_row)

        random_frame = QFrame()
        random_layout = QHBoxLayout(random_frame)
        random_layout.setContentsMargins(0, 0, 0, 0)
        random_layout.addWidget(QLabel("Seed"))
        self.seed_spin = QSpinBox()
        self.seed_spin.setObjectName("characterSeedSpin")
        self.seed_spin.setRange(0, 999_999_999)
        self.seed_spin.setValue(1)
        random_layout.addWidget(self.seed_spin, 1)
        self.randomize_button = QPushButton("Randomize")
        self.randomize_button.setObjectName("characterRandomizeButton")
        random_layout.addWidget(self.randomize_button)
        parts_layout.addWidget(random_frame)

        parts_layout.addStretch(1)
        save_load_row = QHBoxLayout()
        self.save_button = QPushButton("Save Character")
        self.save_button.setObjectName("characterSaveButton")
        self.load_button = QPushButton("Load Character")
        self.load_button.setObjectName("characterLoadButton")
        save_load_row.addWidget(self.save_button)
        save_load_row.addWidget(self.load_button)
        parts_layout.addLayout(save_load_row)

        self.export_button = QPushButton("Export Character")
        self.export_button.setObjectName("characterExportButton")
        parts_layout.addWidget(self.export_button)

        root.addWidget(animation_group)
        root.addWidget(preview_group, 1)
        root.addWidget(parts_group)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.base_combo.currentIndexChanged.connect(self._on_base_changed)
        self.sprite_style_combo.currentIndexChanged.connect(
            self._on_sprite_style_changed
        )
        self.animation_combo.currentIndexChanged.connect(self._on_animation_changed)
        self.camera_height_combo.currentIndexChanged.connect(
            self._on_camera_height_changed
        )
        self.direction_combo.currentIndexChanged.connect(self._on_direction_changed)
        self.zoom_combo.currentIndexChanged.connect(self._render_frame)
        self.preview_label.zoom_step_requested.connect(self._step_preview_zoom)
        self.play_button.clicked.connect(self._toggle_playback)
        self.name_edit.textChanged.connect(self._on_name_changed)
        for slot, combo in self.part_combos.items():
            combo.currentIndexChanged.connect(
                lambda _index, selected_slot=slot: self._on_part_changed(selected_slot)
            )
        for slot, button in self.edit_part_buttons.items():
            button.clicked.connect(
                lambda _checked=False, selected_slot=slot: self._edit_part(
                    selected_slot
                )
            )
        self.part_color_button.clicked.connect(self._choose_part_color)
        self.reset_part_color_button.clicked.connect(self._reset_part_color)
        self.randomize_button.clicked.connect(self._randomize)
        self.reload_catalog_button.clicked.connect(self._reload_catalog)
        self.save_button.clicked.connect(self._save_character)
        self.load_button.clicked.connect(self._load_character)
        self.export_button.clicked.connect(self._export_character)

    @property
    def current_animation_id(self) -> str:
        value = self.animation_combo.currentData()
        return value if isinstance(value, str) else "idle"

    @property
    def current_camera_height(self) -> str:
        value = self.camera_height_combo.currentData()
        return value if isinstance(value, str) else "low"

    @property
    def current_sprite_style(self) -> str:
        value = self.sprite_style_combo.currentData()
        return value if isinstance(value, str) else DEFAULT_SPRITE_STYLE

    @property
    def current_direction(self) -> str:
        value = self.direction_combo.currentData()
        return value if isinstance(value, str) else "front"

    def _on_base_changed(self) -> None:
        if self._updating_controls:
            return
        base_id = self.base_combo.currentData()
        if isinstance(base_id, str):
            self.recipe.base_id = base_id
        base = self.catalog.base(self.recipe.base_id)
        self._updating_controls = True
        try:
            current_animation = self.current_animation_id
            self.animation_combo.clear()
            for animation in base.animations.values():
                self.animation_combo.addItem(animation.name, animation.id)
            animation_index = self.animation_combo.findData(current_animation)
            self.animation_combo.setCurrentIndex(max(0, animation_index))
            current_camera_height = self.recipe.camera_height
            self.camera_height_combo.clear()
            for camera_height in base.camera_heights:
                self.camera_height_combo.addItem(
                    CAMERA_HEIGHT_LABELS.get(camera_height, camera_height), camera_height
                )
            if current_camera_height not in base.camera_heights:
                current_camera_height = "low" if "low" in base.camera_heights else base.camera_heights[0]
                self.recipe.camera_height = current_camera_height
            self.camera_height_combo.setCurrentIndex(
                max(0, self.camera_height_combo.findData(current_camera_height))
            )
            for slot, combo in self.part_combos.items():
                selected = self.recipe.parts.get(slot)
                combo.clear()
                combo.addItem("None", None)
                for part in self.catalog.parts_for_slot(
                    slot,
                    base.id,
                    self.recipe.camera_height,
                    self.recipe.sprite_style,
                ):
                    suffix = " (Incomplete)" if part.status == "incomplete" else ""
                    combo.addItem(f"{part.name}{suffix}", part.id)
                if combo.findData(selected) < 0:
                    self.recipe.parts[slot] = None
                    self.recipe.part_colors.pop(selected, None)
                    selected = None
                combo.setCurrentIndex(max(0, combo.findData(selected)))
                combo.setEnabled(combo.count() > 1)
                self._update_edit_button_state(slot)
        finally:
            self._updating_controls = False
        self._update_part_color_controls()
        self._on_animation_changed()

    def _on_sprite_style_changed(self) -> None:
        if self._updating_controls:
            return
        self.recipe.sprite_style = self.current_sprite_style
        self._on_camera_height_changed()

    def _on_camera_height_changed(self) -> None:
        if self._updating_controls:
            return
        self.recipe.camera_height = self.current_camera_height
        self._updating_controls = True
        try:
            for slot, combo in self.part_combos.items():
                selected = self.recipe.parts.get(slot)
                combo.clear()
                combo.addItem("None", None)
                for part in self.catalog.parts_for_slot(
                    slot,
                    self.recipe.base_id,
                    self.recipe.camera_height,
                    self.recipe.sprite_style,
                ):
                    suffix = " (Incomplete)" if part.status == "incomplete" else ""
                    combo.addItem(f"{part.name}{suffix}", part.id)
                if combo.findData(selected) < 0:
                    self.recipe.parts[slot] = None
                    if selected is not None:
                        self.recipe.part_colors.pop(selected, None)
                    selected = None
                combo.setCurrentIndex(max(0, combo.findData(selected)))
                combo.setEnabled(combo.count() > 1)
                self._update_edit_button_state(slot)
        finally:
            self._updating_controls = False
        self._update_part_color_controls()
        self._refresh_composite()

    def _on_animation_changed(self) -> None:
        if self._updating_controls:
            return
        base = self.catalog.base(self.recipe.base_id)
        animation = base.animations[self.current_animation_id]
        previous_direction = self.current_direction
        self.direction_combo.blockSignals(True)
        self.direction_combo.clear()
        for direction in animation.directions:
            self.direction_combo.addItem(DIRECTION_LABELS[direction], direction)
        direction_index = self.direction_combo.findData(previous_direction)
        self.direction_combo.setCurrentIndex(max(0, direction_index))
        self.direction_combo.blockSignals(False)
        self._reset_direction_playback(animation)
        self._timer.setInterval(animation.frame_duration_ms(self._frame_index))
        for slot in CHARACTER_SLOTS:
            self._update_edit_button_state(slot)
        self._refresh_composite()

    def _on_direction_changed(self, _index: int = 0) -> None:
        base = self.catalog.base(self.recipe.base_id)
        animation = base.animations[self.current_animation_id]
        self._reset_direction_playback(animation)
        self._timer.setInterval(animation.frame_duration_ms(self._frame_index))
        self._render_frame()

    def _reset_direction_playback(self, animation: CharacterAnimation) -> None:
        playback = animation.playback_frames(self.current_direction)
        self._playback_step = 0
        self._frame_index = playback[0]

    def _on_part_changed(self, slot: str) -> None:
        if self._updating_controls:
            return
        previous_id = self.recipe.parts.get(slot)
        value = self.part_combos[slot].currentData()
        self.recipe.parts[slot] = value if isinstance(value, str) else None
        self._remember_part_selection(slot)
        if previous_id is not None and previous_id != value:
            self.recipe.part_colors.pop(previous_id, None)
        if isinstance(value, str):
            selected_part = self.catalog.part(value)
            for other_slot, other_id in tuple(self.recipe.parts.items()):
                if other_slot == slot or other_id is None:
                    continue
                other_part = self.catalog.part(other_id)
                if selected_part.claimed_slots & other_part.claimed_slots:
                    self.recipe.parts[other_slot] = None
                    self.recipe.part_colors.pop(other_id, None)
                    combo = self.part_combos[other_slot]
                    combo.blockSignals(True)
                    combo.setCurrentIndex(max(0, combo.findData(None)))
                    combo.blockSignals(False)
                    self._update_edit_button_state(other_slot)
        self._update_edit_button_state(slot)
        self._update_part_color_controls()
        self.recipe.random_seed = None
        self._refresh_composite()

    def _on_name_changed(self, name: str) -> None:
        if not self._updating_controls:
            self.recipe.name = name.strip() or "character"

    def _step_preview_zoom(self, step: int) -> None:
        if step == 0:
            return
        index = self.zoom_combo.currentIndex()
        target = max(0, min(self.zoom_combo.count() - 1, index + (1 if step > 0 else -1)))
        if target != index:
            self.zoom_combo.setCurrentIndex(target)

    def _refresh_composite(self) -> None:
        try:
            self._sheet = composite_character_animation(
                self.catalog, self.recipe, self.current_animation_id
            )
        except CharacterForgeError as exc:
            self._sheet = None
            self.preview_label.clear()
            QMessageBox.critical(self, "Character composition failed", str(exc))
            return
        self._render_frame()

    def _render_frame(self) -> None:
        if self._sheet is None:
            return
        base = self.catalog.base(self.recipe.base_id)
        animation = base.animations[self.current_animation_id]
        frame_count = animation.frame_count(self.current_direction)
        playback = animation.playback_frames(self.current_direction)
        if self._frame_index >= frame_count:
            self._playback_step = 0
            self._frame_index = playback[0]
        frame = extract_character_frame(
            self._sheet,
            animation,
            self.current_direction,
            self._frame_index,
        )
        zoom = self.zoom_combo.currentData()
        zoom_factor = zoom if isinstance(zoom, int) else 1
        pixmap = pil_image_to_qpixmap(frame)
        if zoom_factor != 1:
            pixmap = pixmap.scaled(
                frame.width * zoom_factor,
                frame.height * zoom_factor,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        self.preview_label.setPixmap(pixmap)
        cycle_note = (
            f"  |  Cycle {self._playback_step + 1}/{len(playback)}"
            if tuple(playback) != tuple(range(frame_count))
            else ""
        )
        self.frame_label.setText(
            f"Frame {self._frame_index + 1}/{frame_count}{cycle_note}  |  "
            f"{animation.frame_duration_ms(self._frame_index)} ms  |  "
            f"{animation.frame_size[0]}x{animation.frame_size[1]} frame  |  "
            f"{self._sheet.width}x{self._sheet.height} sheet"
        )

    def _advance_frame(self) -> None:
        base = self.catalog.base(self.recipe.base_id)
        animation = base.animations[self.current_animation_id]
        playback = animation.playback_frames(self.current_direction)
        self._playback_step = (self._playback_step + 1) % len(playback)
        self._frame_index = playback[self._playback_step]
        self._timer.setInterval(animation.frame_duration_ms(self._frame_index))
        self._render_frame()

    def _toggle_playback(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self.play_button.setText("Play")
        else:
            base = self.catalog.base(self.recipe.base_id)
            animation = base.animations[self.current_animation_id]
            self._timer.setInterval(animation.frame_duration_ms(self._frame_index))
            self._timer.start()
            self.play_button.setText("Pause")

    def _randomize(self) -> None:
        self.recipe = randomize_recipe(
            self.catalog,
            self.recipe.base_id,
            self.seed_spin.value(),
            name=self.name_edit.text().strip() or "character",
            camera_height=self.recipe.camera_height,
            sprite_style=self.recipe.sprite_style,
        )
        self._part_selection_history.clear()
        self._sync_recipe_to_controls()
        self._refresh_composite()
        self.statusBar().showMessage(
            f"Randomized character deterministically with seed {self.recipe.random_seed}"
        )

    def _reload_catalog(self) -> None:
        try:
            catalog = create_default_catalog(include_incomplete=True)
            validate_catalog(catalog)
        except CharacterForgeError as exc:
            QMessageBox.critical(self, "Reload components failed", str(exc))
            return
        self.catalog = catalog
        clear_character_image_cache()
        available_ids = {part.id for part in catalog.parts}
        self._updating_controls = True
        try:
            selected_base = self.recipe.base_id
            if all(base.id != selected_base for base in catalog.bases):
                selected_base = catalog.bases[0].id
                self.recipe.base_id = selected_base
            self.base_combo.clear()
            for base in catalog.bases:
                self.base_combo.addItem(base.name, base.id)
            self.base_combo.setCurrentIndex(
                max(0, self.base_combo.findData(selected_base))
            )
            self.base_combo.setEnabled(self.base_combo.count() > 1)
            self.sprite_style_combo.clear()
            for style_id, style_name in catalog.sprite_styles.items():
                self.sprite_style_combo.addItem(style_name, style_id)
            if self.recipe.sprite_style not in catalog.sprite_styles:
                self.recipe.sprite_style = DEFAULT_SPRITE_STYLE
            self.sprite_style_combo.setCurrentIndex(
                max(
                    0,
                    self.sprite_style_combo.findData(self.recipe.sprite_style),
                )
            )
            current_animation = self.current_animation_id
            self.animation_combo.clear()
            for animation in catalog.base(selected_base).animations.values():
                self.animation_combo.addItem(animation.name, animation.id)
            self.animation_combo.setCurrentIndex(
                max(0, self.animation_combo.findData(current_animation))
            )
            base = catalog.base(selected_base)
            if self.recipe.camera_height not in base.camera_heights:
                self.recipe.camera_height = (
                    "low" if "low" in base.camera_heights else base.camera_heights[0]
                )
            self.camera_height_combo.clear()
            for camera_height in base.camera_heights:
                self.camera_height_combo.addItem(
                    CAMERA_HEIGHT_LABELS.get(camera_height, camera_height), camera_height
                )
            self.camera_height_combo.setCurrentIndex(
                max(0, self.camera_height_combo.findData(self.recipe.camera_height))
            )
            for slot, combo in self.part_combos.items():
                selected = self.recipe.parts.get(slot)
                combo.clear()
                combo.addItem("None", None)
                for part in catalog.parts_for_slot(
                    slot,
                    self.recipe.base_id,
                    self.recipe.camera_height,
                    self.recipe.sprite_style,
                ):
                    suffix = " (Incomplete)" if part.status == "incomplete" else ""
                    combo.addItem(f"{part.name}{suffix}", part.id)
                combo.setEnabled(combo.count() > 1)
                if selected not in available_ids:
                    self.recipe.parts[slot] = None
                    selected = None
                combo.setCurrentIndex(max(0, combo.findData(selected)))
                self._update_edit_button_state(slot)
        finally:
            self._updating_controls = False
        self._update_part_color_controls()
        self._refresh_composite()
        self.statusBar().showMessage(f"Reloaded {len(catalog.parts)} component(s)")

    def _sync_recipe_to_controls(self) -> None:
        self._updating_controls = True
        try:
            base_index = self.base_combo.findData(self.recipe.base_id)
            if base_index >= 0:
                self.base_combo.setCurrentIndex(base_index)
            base = self.catalog.base(self.recipe.base_id)
            style_index = self.sprite_style_combo.findData(
                self.recipe.sprite_style
            )
            if style_index < 0:
                self.recipe.sprite_style = DEFAULT_SPRITE_STYLE
                style_index = self.sprite_style_combo.findData(
                    self.recipe.sprite_style
                )
            self.sprite_style_combo.setCurrentIndex(max(0, style_index))
            current_animation = self.current_animation_id
            self.animation_combo.clear()
            for animation in base.animations.values():
                self.animation_combo.addItem(animation.name, animation.id)
            self.animation_combo.setCurrentIndex(
                max(0, self.animation_combo.findData(current_animation))
            )
            self.camera_height_combo.clear()
            for camera_height in base.camera_heights:
                self.camera_height_combo.addItem(
                    CAMERA_HEIGHT_LABELS.get(camera_height, camera_height), camera_height
                )
            camera_index = self.camera_height_combo.findData(self.recipe.camera_height)
            if camera_index >= 0:
                self.camera_height_combo.setCurrentIndex(camera_index)
            self.name_edit.setText(self.recipe.name)
            if self.recipe.random_seed is not None:
                self.seed_spin.setValue(self.recipe.random_seed)
            for slot, combo in self.part_combos.items():
                part_id = self.recipe.parts.get(slot)
                combo.clear()
                combo.addItem("None", None)
                for part in self.catalog.parts_for_slot(
                    slot,
                    self.recipe.base_id,
                    self.recipe.camera_height,
                    self.recipe.sprite_style,
                ):
                    suffix = " (Incomplete)" if part.status == "incomplete" else ""
                    combo.addItem(f"{part.name}{suffix}", part.id)
                index = combo.findData(part_id)
                combo.setCurrentIndex(max(index, 0))
                combo.setEnabled(combo.count() > 1)
                self._update_edit_button_state(slot)
            self._update_part_color_controls()
        finally:
            self._updating_controls = False

    def _update_edit_button_state(self, slot: str) -> None:
        part_id = self.recipe.parts.get(slot)
        button = self.edit_part_buttons[slot]
        if part_id is None:
            button.setEnabled(False)
            button.setToolTip("Select a character part first")
            return
        part = self.catalog.part(part_id)
        available = (
            part.animation_path(
                self.current_animation_id,
                self.recipe.camera_height,
                self.recipe.sprite_style,
            )
            is not None
        )
        button.setEnabled(available)
        if available:
            button.setToolTip(
                "Open the selected part's current animation sheet in Pixel Forge"
            )
        else:
            button.setToolTip(
                f"{part.name} does not have a {self.current_animation_id} sheet yet"
            )

    def _remember_part_selection(self, slot: str) -> None:
        if slot in self._part_selection_history:
            self._part_selection_history.remove(slot)
        if self.recipe.parts.get(slot) is not None:
            self._part_selection_history.append(slot)

    def _active_part(self):
        self._part_selection_history = [
            slot
            for slot in self._part_selection_history
            if self.recipe.parts.get(slot) is not None
        ]
        for slot in CHARACTER_SLOTS:
            if (
                self.recipe.parts.get(slot) is not None
                and slot not in self._part_selection_history
            ):
                self._part_selection_history.append(slot)
        if not self._part_selection_history:
            return None
        slot = self._part_selection_history[-1]
        part_id = self.recipe.parts[slot]
        return slot, self.catalog.part(part_id)

    def _update_part_color_controls(self) -> None:
        active = self._active_part()
        if active is None:
            self.part_color_label.setText("Part main color")
            self.part_color_button.setText("Unavailable")
            self.part_color_button.setStyleSheet("")
            self.part_color_button.setEnabled(False)
            self.reset_part_color_button.setEnabled(False)
            return

        _slot, part = active
        self.part_color_label.setText(f"{part.name} main color")
        if not part.color_ramp or part.ramp_main_color is None:
            self.part_color_button.setText("Unavailable")
            self.part_color_button.setStyleSheet("")
            self.part_color_button.setToolTip(
                f"{part.name} does not define a recolorable shade ramp"
            )
            self.part_color_button.setEnabled(False)
            self.reset_part_color_button.setEnabled(False)
            return
        default_color = part_default_main_color(part)
        color = self.recipe.part_colors.get(part.id, default_color or "#000000")
        qt_color = QColor(color)
        foreground = "#111111" if qt_color.lightness() > 150 else "#FFFFFF"
        self.part_color_button.setText(color)
        self.part_color_button.setStyleSheet(
            f"background-color: {color}; color: {foreground};"
        )
        self.part_color_button.setToolTip(
            f"Recolor {part.name} using its authored {len(part.color_ramp)}-shade ramp"
        )
        self.part_color_button.setEnabled(True)
        self.reset_part_color_button.setEnabled(part.id in self.recipe.part_colors)

    def _choose_part_color(self) -> None:
        active = self._active_part()
        if active is None:
            return
        _slot, part = active
        if not part.color_ramp or part.ramp_main_color is None:
            return
        default_color = part_default_main_color(part) or "#000000"
        current_color = self.recipe.part_colors.get(part.id, default_color)
        selected = QColorDialog.getColor(
            QColor(current_color),
            self,
            f"Choose {part.name} Main Color",
        )
        if not selected.isValid():
            return
        selected_hex = selected.name(QColor.NameFormat.HexRgb).upper()
        if selected_hex == default_color:
            self.recipe.part_colors.pop(part.id, None)
        else:
            self.recipe.part_colors[part.id] = selected_hex
        self.recipe.random_seed = None
        self._update_part_color_controls()
        self._refresh_composite()

    def _reset_part_color(self) -> None:
        active = self._active_part()
        if active is None:
            return
        _slot, part = active
        if not part.color_ramp or part.ramp_main_color is None:
            return
        self.recipe.part_colors.pop(part.id, None)
        self.recipe.random_seed = None
        self._update_part_color_controls()
        self._refresh_composite()

    def _save_character(self) -> None:
        self.recipe.name = self.name_edit.text().strip() or "character"
        path = local_recipe_path(self.recipe.name)
        if path.exists():
            answer = QMessageBox.question(
                self,
                "Replace saved character?",
                f"{path.name} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            save_recipe(self.recipe, path)
        except (OSError, CharacterForgeError) as exc:
            QMessageBox.critical(self, "Save Character failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved character recipe to {path}")

    def _load_character(self) -> None:
        directory = local_recipe_directory()
        directory.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Character",
            str(directory),
            "Pixel Forge Character (*.json)",
        )
        if not path:
            return
        try:
            recipe = load_recipe(path)
            validate_recipe(self.catalog, recipe)
        except CharacterForgeError as exc:
            QMessageBox.critical(self, "Load Character failed", str(exc))
            return
        self.recipe = recipe
        self._part_selection_history.clear()
        self._sync_recipe_to_controls()
        self._refresh_composite()
        self.statusBar().showMessage(f"Loaded character recipe from {Path(path).name}")

    def _export_character(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Export Character Sprite Sheets",
            str(Path.home()),
        )
        if not directory:
            return
        self.recipe.name = self.name_edit.text().strip() or "character"
        try:
            outputs = export_character(self.catalog, self.recipe, directory)
        except (OSError, CharacterForgeError) as exc:
            QMessageBox.critical(self, "Export Character failed", str(exc))
            return
        self.statusBar().showMessage(
            f"Exported {len(outputs) - 1} sprite sheets and recipe to {directory}"
        )

    def _edit_part(self, slot: str) -> None:
        part_id = self.recipe.parts.get(slot)
        if part_id is None:
            self.statusBar().showMessage(
                f"Select a {SLOT_LABELS[slot].lower()} part first"
            )
            return
        part = self.catalog.part(part_id)
        animation_id = self.current_animation_id
        try:
            sheet = load_part_animation(
                self.catalog,
                part_id,
                animation_id,
                self.recipe.camera_height,
                self.recipe.sprite_style,
            )
        except CharacterForgeError as exc:
            QMessageBox.critical(self, "Open part failed", str(exc))
            return

        document = PixelDocument(
            image=sheet,
            name=f"{part.id}-{animation_id}",
        )
        window = PixelEditorWindow(document, None)
        window.asset_save_requested.connect(
            lambda name, image, selected_part=part, selected_animation=animation_id: (
                self._save_edited_part_copy(
                    selected_part.slot,
                    selected_part.id,
                    selected_animation,
                    name,
                    image,
                )
            )
        )
        window.destroyed.connect(
            lambda *_args, target=window: self._remove_pixel_window(target)
        )
        self._pixel_windows.append(window)
        window.show()
        self.statusBar().showMessage(
            f"Opened {part.name} {animation_id} sheet in Pixel Forge; "
            "Save Image writes an edited copy"
        )

    def _save_edited_part_copy(
        self,
        slot: str,
        part_id: str,
        animation_id: str,
        name: str,
        image,
    ) -> None:
        directory = (
            Path.home() / ".pixelforge" / "character-parts-edited" / slot / part_id
        )
        directory.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Edited Character Part Copy",
            str(directory / f"{name or animation_id}.png"),
            "PNG Image (*.png)",
        )
        if not path:
            return
        save_image(image, path)
        self.statusBar().showMessage(f"Saved edited part copy to {path}")

    def _remove_pixel_window(self, target: PixelEditorWindow) -> None:
        self._pixel_windows = [
            window for window in self._pixel_windows if window is not target
        ]
