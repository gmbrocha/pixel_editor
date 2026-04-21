"""UI window for the procedural tileset template generator.

Layout: a left controls panel (tile size, two regions with colour/texture
modes, seed + reroll, grid + background toggles, generate + export
buttons) and a right-hand live preview that re-renders 300 ms after the
user stops fiddling with controls.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.qt_image import pil_image_to_qpixmap
from src.core.tileset_template import (
    QUICK_PRESETS,
    SUPPORTED_TILE_SIZES,
    TRANSITION_STYLE_HARD_BORDER,
    TRANSITION_STYLE_NONE,
    TRANSITION_STYLE_STONE_LIP,
    Color,
    RegionCSpec,
    RegionSpec,
    default_filename,
    generate_tileset_sheet,
)


# Max signed 32-bit so QSpinBox can hold any seed; spec wants a 32-bit value.
_SEED_MIN = 0
_SEED_MAX = 2_147_483_647
_DEBOUNCE_MS = 300


def _color_swatch_style(color: Color) -> str:
    r, g, b, _ = color
    return (
        f"QPushButton {{ background-color: rgb({r}, {g}, {b}); "
        f"border: 1px solid #222; min-width: 48px; min-height: 22px; }}"
    )


class _RegionControl(QGroupBox):
    """Editor for one region (Wall or Floor): name, fill mode, colour or
    tile-sized texture. Emits `changed` whenever any field updates."""

    def __init__(
        self,
        title: str,
        default_name: str,
        default_color: Color,
        on_change,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)
        self._on_change = on_change
        self._color: Color = default_color
        self._texture: Image.Image | None = None
        self._texture_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # --- Name field
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit(default_name)
        self._name_edit.setPlaceholderText("e.g. Stone, Dirt, Moss")
        self._name_edit.textChanged.connect(self._notify)
        name_row.addWidget(self._name_edit, 1)
        layout.addLayout(name_row)

        # --- Fill mode toggle
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Fill:"))
        self._mode_color = QRadioButton("Color")
        self._mode_texture = QRadioButton("Texture")
        self._mode_color.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self._mode_color)
        self._mode_group.addButton(self._mode_texture)
        self._mode_color.toggled.connect(self._on_mode_toggled)
        mode_row.addWidget(self._mode_color)
        mode_row.addWidget(self._mode_texture)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        # --- Stacked area: color picker page / texture page
        self._stack = QStackedWidget()

        color_page = QWidget()
        color_layout = QHBoxLayout(color_page)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.addWidget(QLabel("Color:"))
        self._color_button = QPushButton()
        self._color_button.setStyleSheet(_color_swatch_style(self._color))
        self._color_button.setToolTip(self._color_hex())
        self._color_button.clicked.connect(self._pick_color)
        color_layout.addWidget(self._color_button)
        self._color_hex_label = QLabel(self._color_hex())
        color_layout.addWidget(self._color_hex_label)
        color_layout.addStretch(1)
        self._stack.addWidget(color_page)

        texture_page = QWidget()
        tex_layout = QHBoxLayout(texture_page)
        tex_layout.setContentsMargins(0, 0, 0, 0)
        self._tex_import = QPushButton("Import…")
        self._tex_import.clicked.connect(self._import_texture)
        tex_layout.addWidget(self._tex_import)
        self._tex_label = QLabel("(none)")
        self._tex_label.setMinimumWidth(80)
        tex_layout.addWidget(self._tex_label, 1)
        self._tex_clear = QPushButton("Clear")
        self._tex_clear.clicked.connect(self._clear_texture)
        self._tex_clear.setEnabled(False)
        tex_layout.addWidget(self._tex_clear)
        self._stack.addWidget(texture_page)

        layout.addWidget(self._stack)

    # -- Public API -----------------------------------------------------

    def name(self) -> str:
        return self._name_edit.text().strip() or self.title()

    def to_spec(self, expected_tile_size: int) -> RegionSpec:
        """Build a RegionSpec, rejecting wrong-sized textures with a clear
        UI message before generation runs."""
        if self._mode_texture.isChecked():
            if self._texture is None:
                # Fall back to colour mode silently if texture was cleared.
                return RegionSpec(name=self.name(), color=self._color)
            if self._texture.size != (expected_tile_size, expected_tile_size):
                raise ValueError(
                    f"Texture for region '{self.name()}' must be exactly "
                    f"{expected_tile_size}x{expected_tile_size} pixels, "
                    f"got {self._texture.width}x{self._texture.height}."
                )
            return RegionSpec(name=self.name(), color=self._color, texture=self._texture)
        return RegionSpec(name=self.name(), color=self._color)

    def set_preset(self, name: str, color: Color) -> None:
        """Apply a preset: switch to colour mode and update the swatch."""
        self._name_edit.blockSignals(True)
        self._name_edit.setText(name)
        self._name_edit.blockSignals(False)
        self._color = color
        self._color_button.setStyleSheet(_color_swatch_style(self._color))
        self._color_button.setToolTip(self._color_hex())
        self._color_hex_label.setText(self._color_hex())
        # Force colour mode (preset overrides texture)
        if not self._mode_color.isChecked():
            self._mode_color.setChecked(True)
        self._notify()

    # -- Internal -------------------------------------------------------

    def _color_hex(self) -> str:
        r, g, b, _ = self._color
        return f"#{r:02x}{g:02x}{b:02x}"

    def _on_mode_toggled(self, _checked: bool) -> None:
        self._stack.setCurrentIndex(0 if self._mode_color.isChecked() else 1)
        self._notify()

    def _pick_color(self) -> None:
        r, g, b, a = self._color
        chosen = QColorDialog.getColor(QColor(r, g, b, a), self, "Pick region color")
        if not chosen.isValid():
            return
        self._color = (chosen.red(), chosen.green(), chosen.blue(), 255)
        self._color_button.setStyleSheet(_color_swatch_style(self._color))
        self._color_button.setToolTip(self._color_hex())
        self._color_hex_label.setText(self._color_hex())
        self._notify()

    def _import_texture(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import texture (PNG)",
            "",
            "PNG images (*.png);;All files (*)",
        )
        if not path:
            return
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as exc:  # broad: we want any IO/decode error here
            QMessageBox.warning(self, "Import failed", f"Couldn't open image:\n{exc}")
            return
        # We don't reject wrong dimensions here; the validity check happens
        # at generate time so the user can preview their colour fallback or
        # fix the tile size first. But we surface the dimensions in the UI.
        self._texture = img
        self._texture_path = path
        self._tex_label.setText(f"{Path(path).name} ({img.width}x{img.height})")
        self._tex_clear.setEnabled(True)
        self._notify()

    def _clear_texture(self) -> None:
        self._texture = None
        self._texture_path = None
        self._tex_label.setText("(none)")
        self._tex_clear.setEnabled(False)
        self._notify()

    def _notify(self) -> None:
        self._on_change()


class _RegionCControl(QGroupBox):
    """Editor for the optional Region C (transition lip).

    Collapsed/disabled by default - the only thing visible until the
    user ticks the enable checkbox is that checkbox itself. When
    enabled, the rest of the controls (name / fill mode / colour or
    texture / style + per-style params) appear underneath.

    The fill-mode block intentionally mirrors `_RegionControl` rather
    than inheriting from it: the enable wrapper and per-style stacked
    panel make a clean inheritance awkward, and the duplication is
    bounded.
    """

    def __init__(self, on_change, parent: QWidget | None = None) -> None:
        super().__init__("Region C — Transition (optional)", parent)
        self._on_change = on_change
        self._color: Color = (0xc8, 0xaa, 0x72, 0xff)
        self._texture: Image.Image | None = None
        self._texture_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        self._enable = QCheckBox("Enable transition region (C)")
        self._enable.setToolTip(
            "When off, edge and corner tiles render exactly as today - "
            "Region A and Region B meet directly at the silhouette."
        )
        self._enable.toggled.connect(self._on_enable_toggled)
        layout.addWidget(self._enable)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 4, 0, 0)
        content_layout.setSpacing(4)

        # --- Name field
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit("Transition")
        self._name_edit.setPlaceholderText("e.g. Pool Lip, Mortar Edge, Shadow")
        self._name_edit.textChanged.connect(self._notify)
        name_row.addWidget(self._name_edit, 1)
        content_layout.addLayout(name_row)

        # --- Fill mode toggle (Color / Texture)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Fill:"))
        self._mode_color = QRadioButton("Color")
        self._mode_texture = QRadioButton("Texture")
        self._mode_color.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self._mode_color)
        self._mode_group.addButton(self._mode_texture)
        self._mode_color.toggled.connect(self._on_mode_toggled)
        mode_row.addWidget(self._mode_color)
        mode_row.addWidget(self._mode_texture)
        mode_row.addStretch(1)
        content_layout.addLayout(mode_row)

        # Color page / texture page
        self._fill_stack = QStackedWidget()

        color_page = QWidget()
        color_layout = QHBoxLayout(color_page)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.addWidget(QLabel("Color:"))
        self._color_button = QPushButton()
        self._color_button.setStyleSheet(_color_swatch_style(self._color))
        self._color_button.setToolTip(self._color_hex())
        self._color_button.clicked.connect(self._pick_color)
        color_layout.addWidget(self._color_button)
        self._color_hex_label = QLabel(self._color_hex())
        color_layout.addWidget(self._color_hex_label)
        color_layout.addStretch(1)
        self._fill_stack.addWidget(color_page)

        texture_page = QWidget()
        tex_layout = QHBoxLayout(texture_page)
        tex_layout.setContentsMargins(0, 0, 0, 0)
        self._tex_import = QPushButton("Import…")
        self._tex_import.clicked.connect(self._import_texture)
        tex_layout.addWidget(self._tex_import)
        self._tex_label = QLabel("(none)")
        self._tex_label.setMinimumWidth(80)
        tex_layout.addWidget(self._tex_label, 1)
        self._tex_clear = QPushButton("Clear")
        self._tex_clear.clicked.connect(self._clear_texture)
        self._tex_clear.setEnabled(False)
        tex_layout.addWidget(self._tex_clear)
        self._fill_stack.addWidget(texture_page)
        content_layout.addWidget(self._fill_stack)

        # --- Transition style dropdown
        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("Style:"))
        self._style_combo = QComboBox()
        self._style_combo.addItem("None (flat fill)", TRANSITION_STYLE_NONE)
        self._style_combo.addItem("Hard Border", TRANSITION_STYLE_HARD_BORDER)
        self._style_combo.addItem("Stone Lip", TRANSITION_STYLE_STONE_LIP)
        self._style_combo.setCurrentIndex(2)  # Stone Lip default - the headline use case
        self._style_combo.currentIndexChanged.connect(self._on_style_changed)
        style_row.addWidget(self._style_combo, 1)
        content_layout.addLayout(style_row)

        # --- Style-specific parameter panels, swapped via a stacked widget
        self._style_stack = QStackedWidget()

        # None: single Depth (1-4)
        none_page = QWidget()
        none_layout = QFormLayout(none_page)
        none_layout.setContentsMargins(0, 0, 0, 0)
        self._none_depth = QSpinBox()
        self._none_depth.setRange(1, 4)
        self._none_depth.setValue(2)
        self._none_depth.valueChanged.connect(self._notify)
        none_layout.addRow("Depth (px):", self._none_depth)
        self._style_stack.addWidget(none_page)

        # Hard Border: single Depth (1-3)
        hb_page = QWidget()
        hb_layout = QFormLayout(hb_page)
        hb_layout.setContentsMargins(0, 0, 0, 0)
        self._hb_depth = QSpinBox()
        self._hb_depth.setRange(1, 3)
        self._hb_depth.setValue(1)
        self._hb_depth.valueChanged.connect(self._notify)
        hb_layout.addRow("Depth (px):", self._hb_depth)
        self._style_stack.addWidget(hb_page)

        # Stone Lip: min/max depth, wobble rate, follow pattern
        sl_page = QWidget()
        sl_layout = QFormLayout(sl_page)
        sl_layout.setContentsMargins(0, 0, 0, 0)
        self._sl_min = QSpinBox()
        self._sl_min.setRange(1, 3)
        self._sl_min.setValue(1)
        self._sl_min.valueChanged.connect(self._on_sl_min_changed)
        sl_layout.addRow("Min depth (px):", self._sl_min)
        self._sl_max = QSpinBox()
        self._sl_max.setRange(2, 6)
        self._sl_max.setValue(3)
        self._sl_max.valueChanged.connect(self._on_sl_max_changed)
        sl_layout.addRow("Max depth (px):", self._sl_max)
        self._sl_wobble = QSpinBox()
        self._sl_wobble.setRange(1, 6)
        self._sl_wobble.setValue(3)
        self._sl_wobble.setToolTip(
            "Low = slow undulation, high = rapid jagged changes"
        )
        self._sl_wobble.valueChanged.connect(self._notify)
        sl_layout.addRow("Wobble rate:", self._sl_wobble)
        self._sl_follow = QCheckBox("Follow pattern")
        self._sl_follow.setChecked(True)
        self._sl_follow.setToolTip(
            "Bias depth toward block/mortar pattern of the loaded "
            "Region A/B texture (best-effort - falls back to noise "
            "when no texture parameters are available)."
        )
        self._sl_follow.toggled.connect(self._notify)
        sl_layout.addRow("", self._sl_follow)
        self._style_stack.addWidget(sl_page)

        self._style_stack.setCurrentIndex(2)  # match the dropdown's default
        content_layout.addWidget(self._style_stack)

        layout.addWidget(self._content)
        self._content.setVisible(False)

    # -- Public API -----------------------------------------------------

    def is_enabled(self) -> bool:
        return self._enable.isChecked()

    def name(self) -> str:
        return self._name_edit.text().strip() or "Transition"

    def to_spec(self, expected_tile_size: int) -> RegionCSpec:
        """Build a RegionCSpec for the current UI state. Validates
        the texture (if any) the same way `_RegionControl` does."""
        texture: Image.Image | None = None
        if self._mode_texture.isChecked() and self._texture is not None:
            if self._texture.size != (expected_tile_size, expected_tile_size):
                raise ValueError(
                    f"Texture for region '{self.name()}' must be exactly "
                    f"{expected_tile_size}x{expected_tile_size} pixels, "
                    f"got {self._texture.width}x{self._texture.height}."
                )
            texture = self._texture

        style = str(self._style_combo.currentData())
        if style == TRANSITION_STYLE_NONE:
            depth = self._none_depth.value()
        elif style == TRANSITION_STYLE_HARD_BORDER:
            depth = self._hb_depth.value()
        else:
            depth = 2  # unused for stone_lip but kept so the dataclass round-trips
        # max is clamped >= min so a stale UI value can't invert the range
        sl_min = self._sl_min.value()
        sl_max = max(sl_min, self._sl_max.value())
        return RegionCSpec(
            name=self.name(),
            color=self._color,
            texture=texture,
            style=style,
            depth=depth,
            min_depth=sl_min,
            max_depth=sl_max,
            wobble_rate=self._sl_wobble.value(),
            follow_pattern=self._sl_follow.isChecked(),
        )

    # -- Internal -------------------------------------------------------

    def _color_hex(self) -> str:
        r, g, b, _ = self._color
        return f"#{r:02x}{g:02x}{b:02x}"

    def _on_enable_toggled(self, checked: bool) -> None:
        self._content.setVisible(checked)
        self._notify()

    def _on_mode_toggled(self, _checked: bool) -> None:
        self._fill_stack.setCurrentIndex(
            0 if self._mode_color.isChecked() else 1
        )
        self._notify()

    def _on_style_changed(self, _idx: int) -> None:
        style = str(self._style_combo.currentData())
        target = {
            TRANSITION_STYLE_NONE: 0,
            TRANSITION_STYLE_HARD_BORDER: 1,
            TRANSITION_STYLE_STONE_LIP: 2,
        }.get(style, 0)
        self._style_stack.setCurrentIndex(target)
        self._notify()

    def _on_sl_min_changed(self, value: int) -> None:
        # Keep max >= min in the UI so the user doesn't see an invalid range
        if self._sl_max.value() < value + 1 and value < self._sl_max.maximum():
            self._sl_max.blockSignals(True)
            self._sl_max.setValue(min(self._sl_max.maximum(), value + 1))
            self._sl_max.blockSignals(False)
        self._notify()

    def _on_sl_max_changed(self, value: int) -> None:
        if value < self._sl_min.value():
            self._sl_min.blockSignals(True)
            self._sl_min.setValue(max(self._sl_min.minimum(), value))
            self._sl_min.blockSignals(False)
        self._notify()

    def _pick_color(self) -> None:
        r, g, b, a = self._color
        chosen = QColorDialog.getColor(
            QColor(r, g, b, a), self, "Pick Region C color"
        )
        if not chosen.isValid():
            return
        self._color = (chosen.red(), chosen.green(), chosen.blue(), 255)
        self._color_button.setStyleSheet(_color_swatch_style(self._color))
        self._color_button.setToolTip(self._color_hex())
        self._color_hex_label.setText(self._color_hex())
        self._notify()

    def _import_texture(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Region C texture (PNG)",
            "",
            "PNG images (*.png);;All files (*)",
        )
        if not path:
            return
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as exc:
            QMessageBox.warning(self, "Import failed", f"Couldn't open image:\n{exc}")
            return
        self._texture = img
        self._texture_path = path
        self._tex_label.setText(f"{Path(path).name} ({img.width}x{img.height})")
        self._tex_clear.setEnabled(True)
        self._notify()

    def _clear_texture(self) -> None:
        self._texture = None
        self._texture_path = None
        self._tex_label.setText("(none)")
        self._tex_clear.setEnabled(False)
        self._notify()

    def _notify(self) -> None:
        self._on_change()


class TilesetTemplateWindow(QMainWindow):
    """Standalone, non-modal window for generating tileset template sheets.

    Lives independently of the main editor: nothing is shared, undo
    history isn't bridged, and multiple instances can be open at once.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tileset Template Generator")
        self.resize(1000, 720)

        self._current_sheet: Image.Image | None = None
        self._suspend_regen = False  # block regen while applying a preset

        # Debounce timer for live regeneration on input churn.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._regenerate)

        controls = self._build_controls()
        preview = self._build_preview()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(controls)
        splitter.addWidget(preview)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 660])

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(6, 6, 6, 6)
        central_layout.addWidget(splitter)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Ready")

        # First render uses a random seed (per spec: "default seed is
        # random on window open"). Use secrets so two windows opened
        # back-to-back don't accidentally collide.
        self._seed_spin.setValue(secrets.randbelow(_SEED_MAX) + 1)
        # The setValue above will already have queued a debounced regen.

    # -- UI construction ------------------------------------------------

    def _build_controls(self) -> QWidget:
        wrap = QWidget()
        wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # --- Tile size
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Tile size:"))
        self._tile_size_combo = QComboBox()
        for ts in SUPPORTED_TILE_SIZES:
            self._tile_size_combo.addItem(f"{ts} px", ts)
        self._tile_size_combo.setCurrentIndex(0)  # default 16
        self._tile_size_combo.currentIndexChanged.connect(self._schedule_regen)
        size_row.addWidget(self._tile_size_combo)
        size_row.addStretch(1)
        layout.addLayout(size_row)

        # --- Quick-load preset
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Load preset…"))
        self._preset_combo = QComboBox()
        self._preset_combo.addItem("(choose…)", None)
        for label, *_ in QUICK_PRESETS:
            self._preset_combo.addItem(label, label)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_chosen)
        preset_row.addWidget(self._preset_combo, 1)
        layout.addLayout(preset_row)

        # --- Regions A and B
        self._region_a = _RegionControl(
            "Region A — Wall", "Wall",
            (0x4a, 0x4a, 0x52, 0xff),
            on_change=self._schedule_regen,
        )
        self._region_b = _RegionControl(
            "Region B — Floor", "Floor",
            (0x7a, 0x5c, 0x3a, 0xff),
            on_change=self._schedule_regen,
        )
        self._region_c = _RegionCControl(on_change=self._schedule_regen)
        layout.addWidget(self._region_a)
        layout.addWidget(self._region_b)
        layout.addWidget(self._region_c)

        # --- Variation seed
        seed_group = QGroupBox("Variation seed")
        seed_layout = QHBoxLayout(seed_group)
        self._seed_spin = QSpinBox()
        self._seed_spin.setRange(_SEED_MIN, _SEED_MAX)
        self._seed_spin.setValue(1)
        self._seed_spin.valueChanged.connect(self._schedule_regen)
        seed_layout.addWidget(self._seed_spin, 1)
        self._reroll_button = QPushButton("🎲 Re-roll")
        self._reroll_button.setToolTip("Pick a new random seed")
        self._reroll_button.clicked.connect(self._reroll_seed)
        seed_layout.addWidget(self._reroll_button)
        layout.addWidget(seed_group)

        # --- Toggles
        toggle_group = QGroupBox("Display")
        toggle_layout = QVBoxLayout(toggle_group)
        self._grid_toggle = QCheckBox("Show grid overlay")
        self._grid_toggle.toggled.connect(self._schedule_regen)
        toggle_layout.addWidget(self._grid_toggle)
        self._transparent_toggle = QCheckBox("Transparent background")
        self._transparent_toggle.setChecked(True)
        self._transparent_toggle.toggled.connect(self._schedule_regen)
        toggle_layout.addWidget(self._transparent_toggle)
        layout.addWidget(toggle_group)

        # --- Action buttons
        action_row = QHBoxLayout()
        self._generate_button = QPushButton("Generate")
        self._generate_button.setToolTip("Force-regenerate the preview now")
        self._generate_button.clicked.connect(self._regenerate)
        action_row.addWidget(self._generate_button)
        self._export_button = QPushButton("Export PNG…")
        self._export_button.clicked.connect(self._export_png)
        action_row.addWidget(self._export_button)
        layout.addLayout(action_row)

        layout.addStretch(1)
        scroll.setWidget(inner)
        return wrap

    def _build_preview(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._preview_info = QLabel("(no preview yet)")
        self._preview_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._preview_info)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # A subtle checker-style background so transparent areas are visible.
        self._preview_label.setStyleSheet(
            "QLabel { background-color: #2b2b2b; color: #888; }"
        )
        self._preview_label.setMinimumSize(200, 200)
        self._preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll = QScrollArea()
        scroll.setWidget(self._preview_label)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll, 1)
        return wrap

    # -- Event handlers -------------------------------------------------

    def _schedule_regen(self, *_args) -> None:
        # Suspended during multi-field preset application so we only fire one
        # regen at the end.
        if self._suspend_regen:
            return
        self._debounce.start()

    def _reroll_seed(self) -> None:
        # Pick a new random seed; the spinbox change will trigger regen.
        self._seed_spin.setValue(secrets.randbelow(_SEED_MAX) + 1)

    def _on_preset_chosen(self, _idx: int) -> None:
        label = self._preset_combo.currentData()
        if label is None:
            return
        match = next((p for p in QUICK_PRESETS if p[0] == label), None)
        if match is None:
            return
        _, wall_name, wall_color, floor_name, floor_color = match
        # Apply both regions in one go, then trigger a single regeneration.
        self._suspend_regen = True
        try:
            self._region_a.set_preset(wall_name, wall_color)
            self._region_b.set_preset(floor_name, floor_color)
        finally:
            self._suspend_regen = False
        self._schedule_regen()
        # Reset the dropdown to the placeholder so re-selecting the same
        # preset later still fires currentIndexChanged.
        self._preset_combo.blockSignals(True)
        self._preset_combo.setCurrentIndex(0)
        self._preset_combo.blockSignals(False)

    def _current_tile_size(self) -> int:
        return int(self._tile_size_combo.currentData())

    def _regenerate(self) -> None:
        ts = self._current_tile_size()
        try:
            spec_a = self._region_a.to_spec(ts)
            spec_b = self._region_b.to_spec(ts)
            spec_c = (
                self._region_c.to_spec(ts)
                if self._region_c.is_enabled()
                else None
            )
        except ValueError as exc:
            self._preview_info.setText("⚠ Texture rejected — see status bar")
            self.statusBar().showMessage(str(exc), 8000)
            return

        try:
            sheet = generate_tileset_sheet(
                tile_size=ts,
                region_a=spec_a,
                region_b=spec_b,
                seed=int(self._seed_spin.value()),
                transparent_background=self._transparent_toggle.isChecked(),
                grid_overlay=self._grid_toggle.isChecked(),
                region_c=spec_c,
            )
        except ValueError as exc:
            self._preview_info.setText("⚠ Generation failed — see status bar")
            self.statusBar().showMessage(str(exc), 8000)
            return
        except Exception as exc:  # last-ditch safety net for the live preview
            self._preview_info.setText("⚠ Internal error — see status bar")
            self.statusBar().showMessage(f"Generation error: {exc}", 8000)
            return

        self._current_sheet = sheet
        pix = pil_image_to_qpixmap(sheet)
        self._preview_label.setPixmap(pix)
        self._preview_label.setMinimumSize(pix.size())
        self._preview_info.setText(
            f"Tile {ts}px · Sheet {sheet.width}x{sheet.height} · 47 tiles · seed {self._seed_spin.value()}"
        )
        self.statusBar().showMessage("Preview updated", 1500)

    def _export_png(self) -> None:
        if self._current_sheet is None:
            # Force one synchronous render so Export works even before the
            # debounce timer has fired.
            self._regenerate()
            if self._current_sheet is None:
                return

        suggested = default_filename(
            self._current_tile_size(), int(self._seed_spin.value())
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export tileset template as PNG",
            suggested,
            "PNG image (*.png)",
        )
        if not path:
            return
        try:
            self._current_sheet.save(path, "PNG")
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", f"Couldn't save:\n{exc}")
            return
        self.statusBar().showMessage(f"Exported to {path}", 5000)
