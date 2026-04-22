"""Texture Generator window: standalone subsystem with its own canvas,
ramp, palette, and texture-type plug points.

Three vertical regions:
   * left   : controls (canvas size, palette import, ramp generation,
              texture type and its params, generate, export)
   * centre : working canvas with toolbar (pencil/eraser/eyedropper,
              shift-drag rect fill, undo/redo, zoom)
   * right  : ramp editor (3-8 stops, double-click to recolor) and the
              active drawing colour
"""

from __future__ import annotations

import secrets
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.core.texture_generator import (
    BLOCKS_CRACK_MIN_CANVAS,
    BOARDS_KNOT_MIN_CANVAS,
    RAMP_MAX_STOPS,
    RAMP_MIN_STOPS,
    TEXTURE_TYPES,
    VEGETATION_STYLE_BOTH,
    VEGETATION_STYLE_GRASS,
    VEGETATION_STYLE_MOSS,
    BlocksParams,
    BoardsParams,
    BrickParams,
    Color,
    VegetationParams,
    generate_blocks_texture,
    generate_boards_texture,
    generate_brick_texture,
    generate_ramp,
    texture_type_default_filename,
    unique_colors_from_image,
    valid_brick_dimensions,
)
from src.ui.texture_canvas import (
    ALL_MODES,
    MODE_ERASER,
    MODE_EYEDROPPER,
    MODE_PENCIL,
    ZOOM_LEVELS,
    TextureCanvas,
)


_SEED_MIN = 0
_SEED_MAX = 2_147_483_647


def _hex(c: Color) -> str:
    r, g, b, _ = c
    return f"#{r:02x}{g:02x}{b:02x}"


def _swatch_style(c: Color, *, border: str = "#222", size: int = 22) -> str:
    r, g, b, _ = c
    return (
        f"QPushButton {{ background-color: rgb({r}, {g}, {b}); "
        f"border: 1px solid {border}; "
        f"min-width: {size}px; min-height: {size}px; "
        f"max-width: {size}px; max-height: {size}px; }}"
    )


_SNAP_FLASH_MS = 500
_SNAP_FLASH_STYLE = "QSpinBox { background-color: #fff7c2; }"
_NO_FIT_HELPER_TEXT = (
    "No clean fit possible at this mortar size. Try adjusting canvas size."
)


def _flash_snap(spin: QSpinBox) -> None:
    """Briefly tint `spin` yellow so the user notices the value was
    auto-snapped. The tint clears itself after `_SNAP_FLASH_MS` ms."""
    spin.setStyleSheet(_SNAP_FLASH_STYLE)
    QTimer.singleShot(_SNAP_FLASH_MS, lambda: spin.setStyleSheet(""))


def _nearest_valid(values: list[int], current: int) -> int:
    """Return the entry of `values` closest to `current`. Ties prefer the
    larger value (per spec). `values` must be non-empty."""
    return min(values, key=lambda v: (abs(v - current), -v))


class _BrickSnapHelper:
    """Auto-snap brick width / height to values that tile cleanly across
    the canvas. Shared by both the Brick and Blocks parameter panels
    since they expose identical `brick_w` / `brick_h` / `mortar` spin
    boxes (just relabeled).

    Wiring contract:
        * mortar.valueChanged -> snap both axes (silent, with flash)
        * canvas size change  -> snap both axes (silent, with flash)
        * brick_w/h.editingFinished -> snap that axis (silent, with flash)

    The spec deliberately does *not* snap on every keystroke or every
    spinner click - only on input commit (Enter / blur). That matches
    QSpinBox.editingFinished, which is what we wire."""

    def __init__(
        self,
        brick_w: QSpinBox,
        brick_h: QSpinBox,
        mortar: QSpinBox,
        no_fit_label: QLabel,
    ) -> None:
        self.brick_w = brick_w
        self.brick_h = brick_h
        self.mortar = mortar
        self.no_fit_label = no_fit_label
        self._w_min = brick_w.minimum()
        self._h_min = brick_h.minimum()
        self._canvas_w = 16
        self._canvas_h = 16

        self.mortar.valueChanged.connect(self._on_mortar_changed)
        self.brick_w.editingFinished.connect(self.snap_width)
        self.brick_h.editingFinished.connect(self.snap_height)

        self._refresh_no_fit_label()

    def update_canvas_size(self, w: int, h: int) -> None:
        """Push a new canvas size in. Snaps both axes only when the size
        actually changed - this keeps the panel quiet at construction
        time when the parent pushes the same default size that the panel
        already assumes."""
        new_w, new_h = int(w), int(h)
        changed = (new_w != self._canvas_w) or (new_h != self._canvas_h)
        self._canvas_w = new_w
        self._canvas_h = new_h
        if changed:
            self._snap_axis(self.brick_w, self._canvas_w, self._w_min)
            self._snap_axis(self.brick_h, self._canvas_h, self._h_min)
        self._refresh_no_fit_label()

    def snap_width(self) -> None:
        self._snap_axis(self.brick_w, self._canvas_w, self._w_min)
        self._refresh_no_fit_label()

    def snap_height(self) -> None:
        self._snap_axis(self.brick_h, self._canvas_h, self._h_min)
        self._refresh_no_fit_label()

    def _on_mortar_changed(self, _value: int) -> None:
        self._snap_axis(self.brick_w, self._canvas_w, self._w_min)
        self._snap_axis(self.brick_h, self._canvas_h, self._h_min)
        self._refresh_no_fit_label()

    def _snap_axis(self, spin: QSpinBox, canvas: int, minimum: int) -> None:
        valid = valid_brick_dimensions(canvas, int(self.mortar.value()), minimum)
        if not valid:
            # Edge case: nothing in the allowed range divides cleanly.
            # Per spec, leave the value alone - the helper text below the
            # field tells the user what to try.
            return
        current = int(spin.value())
        target = _nearest_valid(valid, current)
        if target != current:
            spin.setValue(target)
            _flash_snap(spin)

    def _refresh_no_fit_label(self) -> None:
        m = int(self.mortar.value())
        w_valid = valid_brick_dimensions(self._canvas_w, m, self._w_min)
        h_valid = valid_brick_dimensions(self._canvas_h, m, self._h_min)
        self.no_fit_label.setVisible(not w_valid or not h_valid)


# -- Imported-palette swatch grid ------------------------------------------


class _PaletteSwatchPanel(QGroupBox):
    """Scrollable grid of every unique colour from the imported palette
    image. Click a swatch to select it as the texture-generator base
    colour."""

    color_picked = Signal(int, int, int, int)
    cleared = Signal()

    _COLS = 6
    _SWATCH_PX = 22

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Imported palette", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self._info = QLabel("(no palette loaded)")
        self._info.setWordWrap(True)
        layout.addWidget(self._info)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setMinimumHeight(120)
        self._inner = QWidget()
        self._grid = QGridLayout(self._inner)
        self._grid.setContentsMargins(2, 2, 2, 2)
        self._grid.setSpacing(2)
        self._scroll.setWidget(self._inner)
        layout.addWidget(self._scroll, 1)

        self._selected: Color | None = None

    def selected(self) -> Color | None:
        return self._selected

    def has_palette(self) -> bool:
        return self._grid.count() > 0

    def set_colors(self, colors: list[Color]) -> None:
        # Wipe existing swatches.
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._selected = None
        if not colors:
            self._info.setText("(no palette loaded)")
            self.cleared.emit()
            return
        self._info.setText(f"{len(colors)} unique colours - click to select base")
        for i, c in enumerate(colors):
            row, col = divmod(i, self._COLS)
            btn = QPushButton()
            btn.setStyleSheet(_swatch_style(c, size=self._SWATCH_PX))
            btn.setToolTip(_hex(c))
            btn.clicked.connect(lambda _checked=False, color=c: self._on_clicked(color))
            self._grid.addWidget(btn, row, col)

    def _on_clicked(self, color: Color) -> None:
        self._selected = color
        self.color_picked.emit(*color)


# -- Ramp editor ------------------------------------------------------------


class _RampEditor(QGroupBox):
    """Row of swatches representing the current ramp (lightest left,
    darkest right). Click a swatch to set it as the active drawing
    colour; double-click to recolour the stop via QColorDialog."""

    stop_clicked = Signal(int, int, int, int)   # selected as active color
    stops_changed = Signal()                     # ramp itself changed

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Ramp (light -> dark, double-click to edit)", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self._row_widget = QWidget()
        self._row = QHBoxLayout(self._row_widget)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(4)
        layout.addWidget(self._row_widget)

        self._hex_widget = QWidget()
        self._hex_row = QHBoxLayout(self._hex_widget)
        self._hex_row.setContentsMargins(0, 0, 0, 0)
        self._hex_row.setSpacing(4)
        layout.addWidget(self._hex_widget)

        self._stops: list[Color] = []
        self._buttons: list[QPushButton] = []
        self._labels: list[QLabel] = []

    def stops(self) -> list[Color]:
        return list(self._stops)

    def set_stops(self, stops: list[Color]) -> None:
        self._stops = [tuple(c) for c in stops]  # type: ignore[misc]
        self._rebuild()
        self.stops_changed.emit()

    def _rebuild(self) -> None:
        for w in self._buttons + self._labels:
            w.deleteLater()
        self._buttons.clear()
        self._labels.clear()

        for idx, color in enumerate(self._stops):
            btn = _RampStopButton(color, idx)
            btn.clicked_color.connect(self._on_stop_clicked)
            btn.dblclicked_index.connect(self._on_stop_dblclicked)
            self._row.addWidget(btn)
            self._buttons.append(btn)

            lbl = QLabel(_hex(color))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("QLabel { font-size: 10px; color: #ccc; }")
            self._hex_row.addWidget(lbl)
            self._labels.append(lbl)

    def _on_stop_clicked(self, r: int, g: int, b: int, a: int) -> None:
        self.stop_clicked.emit(r, g, b, a)

    def _on_stop_dblclicked(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._stops):
            return
        old = self._stops[idx]
        chosen = QColorDialog.getColor(
            QColor(old[0], old[1], old[2], old[3]),
            self,
            f"Recolor stop {idx + 1}",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not chosen.isValid():
            return
        new_color: Color = (chosen.red(), chosen.green(), chosen.blue(), chosen.alpha())
        self._stops[idx] = new_color
        self._rebuild()
        self.stops_changed.emit()
        # Make the just-edited colour active so the user can keep painting
        # with what they just defined - matches the spec's "changes are
        # immediate and live" intent.
        self.stop_clicked.emit(*new_color)


class _RampStopButton(QPushButton):
    """A single coloured swatch in the ramp row that emits separate
    signals for click and double-click, so the parent can decide what to
    do with each."""

    clicked_color = Signal(int, int, int, int)
    dblclicked_index = Signal(int)

    def __init__(self, color: Color, index: int) -> None:
        super().__init__()
        self._color = color
        self._index = index
        self.setStyleSheet(_swatch_style(color, size=32))
        self.setToolTip(f"Stop {index + 1}: {_hex(color)}")
        self.clicked.connect(self._emit_click)

    def _emit_click(self) -> None:
        self.clicked_color.emit(*self._color)

    def mouseDoubleClickEvent(self, event):  # noqa: ARG002
        self.dblclicked_index.emit(self._index)


# -- Vegetation sub-panel (shared by Brick + Blocks) -----------------------


class _VegetationParamPanel(QWidget):
    """Style / coverage / colour for the vegetation pass.

    Lives inside Brick and Blocks parameter panels under a parent
    "Vegetation" checkbox - the parent decides when to show / hide this
    widget. The panel itself only emits `params_changed` when any of
    its controls move; whether vegetation is *applied* is up to the
    parent's checkbox state (read via `parent_panel.is_enabled()`).
    """

    params_changed = Signal()

    DEFAULT_COLOR: Color = (0x4a, 0x7a, 0x3a, 0xff)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color: Color = self.DEFAULT_COLOR

        layout = QGridLayout(self)
        # Indent under the parent checkbox for visual hierarchy.
        layout.setContentsMargins(18, 2, 0, 2)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)

        # Style radios
        layout.addWidget(QLabel("Style:"), 0, 0)
        style_row = QHBoxLayout()
        style_row.setContentsMargins(0, 0, 0, 0)
        self._style_moss = QRadioButton("Moss")
        self._style_grass = QRadioButton("Grass")
        self._style_both = QRadioButton("Both")
        self._style_both.setChecked(True)
        self._style_group = QButtonGroup(self)
        self._style_group.setExclusive(True)
        self._style_group.addButton(self._style_moss)
        self._style_group.addButton(self._style_grass)
        self._style_group.addButton(self._style_both)
        for r in (self._style_moss, self._style_grass, self._style_both):
            style_row.addWidget(r)
        style_row.addStretch(1)
        layout.addLayout(style_row, 0, 1)

        # Coverage slider with live percent label
        layout.addWidget(QLabel("Coverage:"), 1, 0)
        cov_row = QHBoxLayout()
        cov_row.setContentsMargins(0, 0, 0, 0)
        self._coverage = QSlider(Qt.Orientation.Horizontal)
        self._coverage.setRange(0, 100)
        self._coverage.setValue(30)
        self._coverage.setTickPosition(QSlider.TickPosition.NoTicks)
        cov_row.addWidget(self._coverage, 1)
        self._coverage_label = QLabel("30%")
        self._coverage_label.setMinimumWidth(36)
        self._coverage_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        cov_row.addWidget(self._coverage_label)
        layout.addLayout(cov_row, 1, 1)

        # Colour picker - swatch button + live hex label
        layout.addWidget(QLabel("Color:"), 2, 0)
        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        self._color_button = QPushButton()
        self._color_button.setStyleSheet(_swatch_style(self._color, size=22))
        self._color_button.setToolTip("Click to choose vegetation color")
        self._color_button.clicked.connect(self._pick_color)
        color_row.addWidget(self._color_button)
        self._color_hex = QLabel(_hex(self._color))
        self._color_hex.setStyleSheet("QLabel { color: #ccc; font-size: 10px; }")
        color_row.addWidget(self._color_hex)
        color_row.addStretch(1)
        layout.addLayout(color_row, 2, 1)

        for r in (self._style_moss, self._style_grass, self._style_both):
            r.toggled.connect(self.params_changed)
        self._coverage.valueChanged.connect(self._on_coverage_changed)

    def _on_coverage_changed(self, value: int) -> None:
        self._coverage_label.setText(f"{value}%")
        self.params_changed.emit()

    def _pick_color(self) -> None:
        r, g, b, a = self._color
        chosen = QColorDialog.getColor(
            QColor(r, g, b, a), self, "Pick vegetation color"
        )
        if not chosen.isValid():
            return
        self._color = (chosen.red(), chosen.green(), chosen.blue(), 255)
        self._color_button.setStyleSheet(_swatch_style(self._color, size=22))
        self._color_hex.setText(_hex(self._color))
        self.params_changed.emit()

    def to_params(self) -> VegetationParams:
        if self._style_moss.isChecked():
            style = VEGETATION_STYLE_MOSS
        elif self._style_grass.isChecked():
            style = VEGETATION_STYLE_GRASS
        else:
            style = VEGETATION_STYLE_BOTH
        return VegetationParams(
            style=style,
            coverage=float(self._coverage.value()) / 100.0,
            color=self._color,
        )


# -- Brick parameter panel --------------------------------------------------


class _BrickParamPanel(QGroupBox):
    """Edit the parameters of `BrickParams`. Emits `params_changed` whenever
    the user touches anything (the parent uses this only for status text;
    generation is still triggered by the explicit Generate button)."""

    params_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Brick parameters", parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)

        layout.addWidget(QLabel("Brick width:"), 0, 0)
        self.brick_w = QSpinBox()
        self.brick_w.setRange(2, 1024)
        self.brick_w.setValue(6)
        layout.addWidget(self.brick_w, 0, 1)

        layout.addWidget(QLabel("Brick height:"), 1, 0)
        self.brick_h = QSpinBox()
        self.brick_h.setRange(1, 1024)
        self.brick_h.setValue(3)
        layout.addWidget(self.brick_h, 1, 1)

        layout.addWidget(QLabel("Mortar (px):"), 2, 0)
        self.mortar = QSpinBox()
        self.mortar.setRange(1, 3)
        self.mortar.setValue(1)
        layout.addWidget(self.mortar, 2, 1)

        layout.addWidget(QLabel("Row offset:"), 3, 0)
        self.row_offset = QDoubleSpinBox()
        self.row_offset.setRange(0.0, 1.0)
        self.row_offset.setSingleStep(0.05)
        self.row_offset.setDecimals(2)
        self.row_offset.setValue(0.5)
        layout.addWidget(self.row_offset, 3, 1)

        layout.addWidget(QLabel("Color variance:"), 4, 0)
        self.color_variance = QSpinBox()
        self.color_variance.setRange(0, 4)
        self.color_variance.setValue(2)
        layout.addWidget(self.color_variance, 4, 1)

        self.bevel = QCheckBox("Bevel highlights / shadows")
        self.bevel.setChecked(True)
        layout.addWidget(self.bevel, 5, 0, 1, 2)

        self._highlight_length_label = QLabel("Highlight length:")
        layout.addWidget(self._highlight_length_label, 6, 0)
        self.highlight_length = QSpinBox()
        self.highlight_length.setRange(10, 100)
        self.highlight_length.setValue(50)
        self.highlight_length.setSuffix("%")
        self.highlight_length.setToolTip(
            "How far the bevel highlight runs along the top and left "
            "edges of each brick. 100% = full edge; 50% = stops halfway. "
            "The top-left corner pixel is always lit."
        )
        layout.addWidget(self.highlight_length, 6, 1)

        self.soft_corners = QCheckBox("Soft corners")
        self.soft_corners.setToolTip(
            "Let mortar win at T-junction armpits and soften bevel corner "
            "transitions with intermediate ramp stops."
        )
        layout.addWidget(self.soft_corners, 7, 0, 1, 2)

        self.vegetation_enable = QCheckBox("Vegetation")
        self.vegetation_enable.setToolTip(
            "Optional moss / grass overlay in the mortar gaps"
        )
        layout.addWidget(self.vegetation_enable, 8, 0, 1, 2)

        self.vegetation_panel = _VegetationParamPanel()
        self.vegetation_panel.setVisible(False)
        layout.addWidget(self.vegetation_panel, 9, 0, 1, 2)

        # Edge-case helper: only shown when the current canvas + mortar
        # combination admits zero valid brick dimensions on either axis
        # (e.g. canvas is a prime number and mortar is large). Normal
        # snapping is silent.
        self._no_fit_label = QLabel(_NO_FIT_HELPER_TEXT)
        self._no_fit_label.setWordWrap(True)
        self._no_fit_label.setStyleSheet(
            "QLabel { color: #d8a44a; font-size: 11px; }"
        )
        self._no_fit_label.setVisible(False)
        layout.addWidget(self._no_fit_label, 10, 0, 1, 2)

        for w in (
            self.brick_w, self.brick_h, self.mortar,
            self.color_variance, self.highlight_length,
        ):
            w.valueChanged.connect(self.params_changed)
        self.row_offset.valueChanged.connect(self.params_changed)
        self.bevel.toggled.connect(self.params_changed)
        self.bevel.toggled.connect(self._refresh_highlight_length_visible)
        self.soft_corners.toggled.connect(self.params_changed)
        self.vegetation_enable.toggled.connect(self._on_vegetation_toggled)
        self.vegetation_panel.params_changed.connect(self.params_changed)

        self._snap = _BrickSnapHelper(
            self.brick_w, self.brick_h, self.mortar, self._no_fit_label,
        )
        self._refresh_highlight_length_visible()

    def _on_vegetation_toggled(self, checked: bool) -> None:
        self.vegetation_panel.setVisible(checked)
        self.params_changed.emit()

    def _refresh_highlight_length_visible(self) -> None:
        on = self.bevel.isChecked()
        self._highlight_length_label.setVisible(on)
        self.highlight_length.setVisible(on)

    def to_params(self) -> BrickParams:
        veg = (
            self.vegetation_panel.to_params()
            if self.vegetation_enable.isChecked()
            else None
        )
        return BrickParams(
            brick_width=int(self.brick_w.value()),
            brick_height=int(self.brick_h.value()),
            mortar=int(self.mortar.value()),
            row_offset=float(self.row_offset.value()),
            color_variance=int(self.color_variance.value()),
            bevel=bool(self.bevel.isChecked()),
            highlight_length=int(self.highlight_length.value()),
            soft_corners=bool(self.soft_corners.isChecked()),
            vegetation=veg,
        )

    def update_canvas_size(self, w: int, h: int) -> None:
        self._snap.update_canvas_size(w, h)


# -- Blocks parameter panel -------------------------------------------------


class _BlocksParamPanel(QGroupBox):
    """Brick parameters with two extra detail toggles (Surface Dings,
    Cracks) and a non-blocking warning when cracks are enabled at small
    canvas sizes."""

    params_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Block parameters", parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)

        layout.addWidget(QLabel("Block width:"), 0, 0)
        self.brick_w = QSpinBox()
        self.brick_w.setRange(4, 1024)
        self.brick_w.setValue(8)
        layout.addWidget(self.brick_w, 0, 1)

        layout.addWidget(QLabel("Block height:"), 1, 0)
        self.brick_h = QSpinBox()
        self.brick_h.setRange(3, 1024)
        self.brick_h.setValue(6)
        layout.addWidget(self.brick_h, 1, 1)

        layout.addWidget(QLabel("Mortar (px):"), 2, 0)
        self.mortar = QSpinBox()
        self.mortar.setRange(1, 3)
        self.mortar.setValue(1)
        layout.addWidget(self.mortar, 2, 1)

        layout.addWidget(QLabel("Row offset:"), 3, 0)
        self.row_offset = QDoubleSpinBox()
        self.row_offset.setRange(0.0, 1.0)
        self.row_offset.setSingleStep(0.05)
        self.row_offset.setDecimals(2)
        self.row_offset.setValue(0.5)
        layout.addWidget(self.row_offset, 3, 1)

        layout.addWidget(QLabel("Color variance:"), 4, 0)
        self.color_variance = QSpinBox()
        self.color_variance.setRange(0, 4)
        self.color_variance.setValue(2)
        layout.addWidget(self.color_variance, 4, 1)

        self.bevel = QCheckBox("Bevel highlights / shadows")
        self.bevel.setChecked(True)
        layout.addWidget(self.bevel, 5, 0, 1, 2)

        self._highlight_length_label = QLabel("Highlight length:")
        layout.addWidget(self._highlight_length_label, 6, 0)
        self.highlight_length = QSpinBox()
        self.highlight_length.setRange(10, 100)
        self.highlight_length.setValue(50)
        self.highlight_length.setSuffix("%")
        self.highlight_length.setToolTip(
            "How far the bevel highlight runs along the top and left "
            "edges of each block. 100% = full edge; 50% = stops halfway. "
            "The top-left corner pixel is always lit."
        )
        layout.addWidget(self.highlight_length, 6, 1)

        self.soft_corners = QCheckBox("Soft corners")
        self.soft_corners.setToolTip(
            "Let mortar win at T-junction armpits and soften bevel corner "
            "transitions with intermediate ramp stops."
        )
        layout.addWidget(self.soft_corners, 7, 0, 1, 2)

        self.surface_dings = QCheckBox("Surface dings")
        self.surface_dings.setChecked(True)
        self.surface_dings.setToolTip(
            "Aliased surface chips and pits on block faces."
        )
        layout.addWidget(self.surface_dings, 8, 0, 1, 2)

        self._ding_amount_label = QLabel("Ding amount:")
        layout.addWidget(self._ding_amount_label, 9, 0)
        self.ding_amount = QSpinBox()
        self.ding_amount.setRange(0, 100)
        self.ding_amount.setValue(50)
        self.ding_amount.setSuffix("%")
        self.ding_amount.setToolTip(
            "Higher values place dings on more blocks and allow more/larger blobs."
        )
        layout.addWidget(self.ding_amount, 9, 1)

        self.cracks = QCheckBox("Cracks")
        self.cracks.setToolTip(
            "Vertical-primary stress cracks anchored to one mortar seam."
        )
        layout.addWidget(self.cracks, 10, 0, 1, 2)

        self._crack_amount_label = QLabel("Crack amount:")
        layout.addWidget(self._crack_amount_label, 11, 0)
        self.crack_amount = QSpinBox()
        self.crack_amount.setRange(0, 100)
        self.crack_amount.setValue(40)
        self.crack_amount.setSuffix("%")
        self.crack_amount.setToolTip(
            "Higher values increase crack frequency and average crack length."
        )
        layout.addWidget(self.crack_amount, 11, 1)

        # Non-blocking warning shown only when cracks are enabled and the
        # canvas is small enough that the detail wouldn't read.
        self._small_canvas_warning = QLabel(
            f"⚠ Cracks may not be visible at small canvas sizes (< {BLOCKS_CRACK_MIN_CANVAS}px)."
        )
        self._small_canvas_warning.setWordWrap(True)
        self._small_canvas_warning.setStyleSheet(
            "QLabel { color: #d8a44a; font-size: 11px; }"
        )
        self._small_canvas_warning.setVisible(False)
        layout.addWidget(self._small_canvas_warning, 12, 0, 1, 2)

        # Edge-case helper: only shown when the current canvas + mortar
        # combination admits zero valid block dimensions on either axis.
        # Normal snapping is silent (subtle yellow flash on the affected
        # spinbox; no warning text).
        self._no_fit_label = QLabel(_NO_FIT_HELPER_TEXT)
        self._no_fit_label.setWordWrap(True)
        self._no_fit_label.setStyleSheet(
            "QLabel { color: #d8a44a; font-size: 11px; }"
        )
        self._no_fit_label.setVisible(False)
        layout.addWidget(self._no_fit_label, 13, 0, 1, 2)

        self.vegetation_enable = QCheckBox("Vegetation")
        self.vegetation_enable.setToolTip(
            "Optional moss / grass overlay in the mortar gaps and cracks"
        )
        layout.addWidget(self.vegetation_enable, 14, 0, 1, 2)

        self.vegetation_panel = _VegetationParamPanel()
        self.vegetation_panel.setVisible(False)
        layout.addWidget(self.vegetation_panel, 15, 0, 1, 2)

        self._canvas_w = 16
        self._canvas_h = 16
        for w in (
            self.brick_w, self.brick_h, self.mortar,
            self.color_variance, self.highlight_length,
            self.ding_amount, self.crack_amount,
        ):
            w.valueChanged.connect(self.params_changed)
        self.row_offset.valueChanged.connect(self.params_changed)
        for cb in (self.bevel, self.soft_corners, self.surface_dings, self.cracks):
            cb.toggled.connect(self.params_changed)
        self.bevel.toggled.connect(self._refresh_highlight_length_visible)
        self.surface_dings.toggled.connect(self._refresh_detail_amount_enabled)
        self.cracks.toggled.connect(self._refresh_warning)
        self.cracks.toggled.connect(self._refresh_detail_amount_enabled)
        self.vegetation_enable.toggled.connect(self._on_vegetation_toggled)
        self.vegetation_panel.params_changed.connect(self.params_changed)
        self._refresh_warning()
        self._refresh_highlight_length_visible()
        self._refresh_detail_amount_enabled()

        self._snap = _BrickSnapHelper(
            self.brick_w, self.brick_h, self.mortar, self._no_fit_label,
        )

    def _on_vegetation_toggled(self, checked: bool) -> None:
        self.vegetation_panel.setVisible(checked)
        self.params_changed.emit()

    def _refresh_highlight_length_visible(self) -> None:
        on = self.bevel.isChecked()
        self._highlight_length_label.setVisible(on)
        self.highlight_length.setVisible(on)

    def _refresh_detail_amount_enabled(self) -> None:
        dings_on = self.surface_dings.isChecked()
        self._ding_amount_label.setEnabled(dings_on)
        self.ding_amount.setEnabled(dings_on)

        cracks_on = self.cracks.isChecked()
        self._crack_amount_label.setEnabled(cracks_on)
        self.crack_amount.setEnabled(cracks_on)

    def to_params(self) -> BlocksParams:
        veg = (
            self.vegetation_panel.to_params()
            if self.vegetation_enable.isChecked()
            else None
        )
        return BlocksParams(
            brick_width=int(self.brick_w.value()),
            brick_height=int(self.brick_h.value()),
            mortar=int(self.mortar.value()),
            row_offset=float(self.row_offset.value()),
            color_variance=int(self.color_variance.value()),
            bevel=bool(self.bevel.isChecked()),
            highlight_length=int(self.highlight_length.value()),
            soft_corners=bool(self.soft_corners.isChecked()),
            surface_dings=bool(self.surface_dings.isChecked()),
            ding_amount=int(self.ding_amount.value()),
            cracks=bool(self.cracks.isChecked()),
            crack_amount=int(self.crack_amount.value()),
            vegetation=veg,
        )

    def update_canvas_size(self, w: int, h: int) -> None:
        self._canvas_w = int(w)
        self._canvas_h = int(h)
        self._refresh_warning()
        self._snap.update_canvas_size(w, h)

    def _refresh_warning(self) -> None:
        small = (
            self._canvas_w < BLOCKS_CRACK_MIN_CANVAS
            or self._canvas_h < BLOCKS_CRACK_MIN_CANVAS
        )
        self._small_canvas_warning.setVisible(self.cracks.isChecked() and small)


# -- Boards parameter panel -------------------------------------------------


class _BoardsParamPanel(QGroupBox):
    """Edit the parameters of `BoardsParams`. Mirrors the brick/blocks
    panel API - same signal, same `to_params()` / `update_canvas_size()`
    surface - so the parent window can swap panels generically."""

    params_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Boards parameters", parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)

        row = 0
        layout.addWidget(QLabel("Plank width:"), row, 0)
        self.plank_width = QSpinBox()
        self.plank_width.setRange(3, 1024)
        self.plank_width.setValue(6)
        layout.addWidget(self.plank_width, row, 1)
        row += 1

        layout.addWidget(QLabel("Orientation:"), row, 0)
        self.orientation = QComboBox()
        self.orientation.addItem("Horizontal", "horizontal")
        self.orientation.addItem("Vertical", "vertical")
        layout.addWidget(self.orientation, row, 1)
        row += 1

        layout.addWidget(QLabel("Gap (px):"), row, 0)
        self.gap = QSpinBox()
        self.gap.setRange(1, 2)
        self.gap.setValue(1)
        layout.addWidget(self.gap, row, 1)
        row += 1

        layout.addWidget(QLabel("Color variance:"), row, 0)
        self.color_variance = QSpinBox()
        self.color_variance.setRange(0, 4)
        self.color_variance.setValue(2)
        layout.addWidget(self.color_variance, row, 1)
        row += 1

        layout.addWidget(QLabel("Edge wobble:"), row, 0)
        self.edge_wobble = QSpinBox()
        self.edge_wobble.setRange(0, 4)
        self.edge_wobble.setValue(2)
        layout.addWidget(self.edge_wobble, row, 1)
        row += 1

        layout.addWidget(QLabel("Grain density:"), row, 0)
        self.grain_density = QSpinBox()
        self.grain_density.setRange(1, 6)
        self.grain_density.setValue(3)
        layout.addWidget(self.grain_density, row, 1)
        row += 1

        layout.addWidget(QLabel("Grain waviness:"), row, 0)
        self.grain_waviness = QSpinBox()
        self.grain_waviness.setRange(0, 4)
        self.grain_waviness.setValue(2)
        layout.addWidget(self.grain_waviness, row, 1)
        row += 1

        self.bevel = QCheckBox("Bevel highlights / shadows")
        self.bevel.setChecked(True)
        layout.addWidget(self.bevel, row, 0, 1, 2)
        row += 1

        self.knots = QCheckBox("Knots")
        self.knots.setChecked(True)
        layout.addWidget(self.knots, row, 0, 1, 2)
        row += 1

        layout.addWidget(QLabel("Knots per sheet:"), row, 0)
        self.knots_per_sheet = QSpinBox()
        self.knots_per_sheet.setRange(0, 6)
        self.knots_per_sheet.setValue(2)
        layout.addWidget(self.knots_per_sheet, row, 1)
        row += 1

        # Non-blocking warning per spec - the threshold is on the axis
        # *perpendicular* to plank length (i.e. the canvas dimension that
        # planks stack along), so it depends on orientation.
        self._small_canvas_warning = QLabel(
            f"⚠ Knots may not render well at small canvas sizes "
            f"(< {BOARDS_KNOT_MIN_CANVAS}px in plank-width axis)."
        )
        self._small_canvas_warning.setWordWrap(True)
        self._small_canvas_warning.setStyleSheet(
            "QLabel { color: #d8a44a; font-size: 11px; }"
        )
        self._small_canvas_warning.setVisible(False)
        layout.addWidget(self._small_canvas_warning, row, 0, 1, 2)

        self._canvas_w = 16
        self._canvas_h = 16
        for w in (
            self.plank_width, self.gap, self.color_variance,
            self.edge_wobble, self.grain_density, self.grain_waviness,
            self.knots_per_sheet,
        ):
            w.valueChanged.connect(self.params_changed)
        for cb in (self.bevel, self.knots):
            cb.toggled.connect(self.params_changed)
        self.orientation.currentIndexChanged.connect(self.params_changed)
        # Warning toggles when knots, orientation, or canvas size change.
        self.knots.toggled.connect(self._refresh_warning)
        self.orientation.currentIndexChanged.connect(self._refresh_warning)
        self._refresh_warning()

    def to_params(self) -> BoardsParams:
        return BoardsParams(
            plank_width=int(self.plank_width.value()),
            orientation=str(self.orientation.currentData()),
            gap=int(self.gap.value()),
            color_variance=int(self.color_variance.value()),
            edge_wobble=int(self.edge_wobble.value()),
            grain_density=int(self.grain_density.value()),
            grain_waviness=int(self.grain_waviness.value()),
            bevel=bool(self.bevel.isChecked()),
            knots=bool(self.knots.isChecked()),
            knots_per_sheet=int(self.knots_per_sheet.value()),
        )

    def update_canvas_size(self, w: int, h: int) -> None:
        self._canvas_w = int(w)
        self._canvas_h = int(h)
        self._refresh_warning()

    def _refresh_warning(self) -> None:
        orient = str(self.orientation.currentData())
        # Plank-width axis = canvas height (horizontal) or canvas width (vertical).
        width_axis = self._canvas_h if orient == "horizontal" else self._canvas_w
        small = width_axis < BOARDS_KNOT_MIN_CANVAS
        self._small_canvas_warning.setVisible(self.knots.isChecked() and small)


# -- Active-color swatch ----------------------------------------------------


class _ActiveColorSwatch(QGroupBox):
    """Big swatch reflecting the current drawing colour."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Active color", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self._swatch = QFrame()
        self._swatch.setMinimumSize(64, 48)
        self._swatch.setFrameShape(QFrame.Shape.Box)
        layout.addWidget(self._swatch)

        self._hex_label = QLabel("#ffffff")
        self._hex_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._hex_label)
        self.set_color((255, 255, 255, 255))

    def set_color(self, color: Color) -> None:
        r, g, b, _ = color
        self._swatch.setStyleSheet(
            f"QFrame {{ background-color: rgb({r}, {g}, {b}); border: 1px solid #222; }}"
        )
        self._hex_label.setText(_hex(color))


# -- Main window ------------------------------------------------------------


class TextureGeneratorWindow(QMainWindow):
    """Self-contained Texture Generator. Multiple instances may coexist
    with the main editor, the tileset generator, and each other."""

    DEFAULT_W = 16
    DEFAULT_H = 16

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Texture Generator")
        self.resize(1280, 760)

        self._base_color: Color | None = None
        self._build_ui()

        # Status, default seed (random per spec for the tileset generator,
        # not strictly required here but it gives a visible default).
        self._seed_spin.setValue(secrets.randbelow(_SEED_MAX) + 1)
        self.statusBar().showMessage("Ready - import a palette or pick a base color")

    # -- UI construction -----------------------------------------------

    def _build_ui(self) -> None:
        self._canvas = TextureCanvas(self.DEFAULT_W, self.DEFAULT_H)
        self._canvas.color_picked.connect(self._on_canvas_picked_color)
        self._canvas.status_changed.connect(self.statusBar().showMessage)
        self._canvas.cursor_pixel_changed.connect(self._on_cursor_pixel)
        self._canvas.zoom_changed.connect(self._on_zoom_changed)
        self._canvas.mode_changed.connect(self._on_mode_changed)

        left = self._build_left_panel()
        centre = self._build_center_panel()
        right = self._build_right_panel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left)
        splitter.addWidget(centre)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([320, 700, 280])

        wrap = QWidget()
        wrap_layout = QHBoxLayout(wrap)
        wrap_layout.setContentsMargins(6, 6, 6, 6)
        wrap_layout.addWidget(splitter)
        self.setCentralWidget(wrap)

        # Window-level shortcuts so undo/redo work even when focus is on
        # a control widget rather than the canvas.
        self._undo_action = QAction("Undo", self)
        self._undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self._undo_action.triggered.connect(self._canvas.undo)
        self.addAction(self._undo_action)
        self._redo_action = QAction("Redo", self)
        self._redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self._redo_action.triggered.connect(self._canvas.redo)
        self.addAction(self._redo_action)

    def _build_left_panel(self) -> QWidget:
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # --- Canvas size
        size_group = QGroupBox("Canvas size")
        size_layout = QGridLayout(size_group)
        size_layout.addWidget(QLabel("Width:"), 0, 0)
        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 1024)
        self._width_spin.setValue(self.DEFAULT_W)
        size_layout.addWidget(self._width_spin, 0, 1)
        size_layout.addWidget(QLabel("Height:"), 1, 0)
        self._height_spin = QSpinBox()
        self._height_spin.setRange(1, 1024)
        self._height_spin.setValue(self.DEFAULT_H)
        size_layout.addWidget(self._height_spin, 1, 1)
        resize_btn = QPushButton("Resize Canvas")
        resize_btn.clicked.connect(self._do_resize_canvas)
        size_layout.addWidget(resize_btn, 2, 0, 1, 2)
        layout.addWidget(size_group)

        # --- Import palette + swatch grid
        palette_group = QGroupBox("Palette")
        palette_layout = QVBoxLayout(palette_group)
        import_btn = QPushButton("Import Palette…")
        import_btn.clicked.connect(self._import_palette)
        palette_layout.addWidget(import_btn)
        self._palette_panel = _PaletteSwatchPanel()
        self._palette_panel.color_picked.connect(self._on_base_color_chosen)
        palette_layout.addWidget(self._palette_panel, 1)
        layout.addWidget(palette_group, 1)

        # --- Ramp generation
        ramp_gen_group = QGroupBox("Generate Ramp")
        ramp_gen_layout = QGridLayout(ramp_gen_group)
        ramp_gen_layout.addWidget(QLabel("Base color:"), 0, 0)
        self._base_color_swatch = QFrame()
        self._base_color_swatch.setMinimumSize(40, 22)
        self._base_color_swatch.setFrameShape(QFrame.Shape.Box)
        self._set_base_color_swatch(None)
        ramp_gen_layout.addWidget(self._base_color_swatch, 0, 1)
        ramp_gen_layout.addWidget(QLabel("Swatches:"), 1, 0)
        self._ramp_count_spin = QSpinBox()
        self._ramp_count_spin.setRange(RAMP_MIN_STOPS, RAMP_MAX_STOPS)
        self._ramp_count_spin.setValue(5)
        ramp_gen_layout.addWidget(self._ramp_count_spin, 1, 1)
        self._gen_ramp_btn = QPushButton("Generate Ramp")
        self._gen_ramp_btn.clicked.connect(self._generate_ramp)
        self._gen_ramp_btn.setEnabled(False)
        ramp_gen_layout.addWidget(self._gen_ramp_btn, 2, 0, 1, 2)
        layout.addWidget(ramp_gen_group)

        # --- Texture type + Generate
        tex_group = QGroupBox("Texture")
        tex_layout = QVBoxLayout(tex_group)
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Type:"))
        self._type_combo = QComboBox()
        for t in TEXTURE_TYPES:
            self._type_combo.addItem(t, t)
        self._type_combo.currentIndexChanged.connect(self._on_texture_type_changed)
        type_row.addWidget(self._type_combo, 1)
        tex_layout.addLayout(type_row)

        # One parameter panel per texture type, swapped by a stack so each
        # type keeps its own independent state.
        self._param_panels: dict[str, QWidget] = {
            "Brick": _BrickParamPanel(),
            "Blocks": _BlocksParamPanel(),
            "Boards": _BoardsParamPanel(),
        }
        self._param_stack = QStackedWidget()
        for name in TEXTURE_TYPES:
            self._param_stack.addWidget(self._param_panels[name])
        tex_layout.addWidget(self._param_stack)

        seed_row = QHBoxLayout()
        seed_row.addWidget(QLabel("Seed:"))
        self._seed_spin = QSpinBox()
        self._seed_spin.setRange(_SEED_MIN, _SEED_MAX)
        self._seed_spin.setValue(1)
        seed_row.addWidget(self._seed_spin, 1)
        reroll = QPushButton("🎲 Re-roll")
        reroll.clicked.connect(self._reroll_seed)
        seed_row.addWidget(reroll)
        tex_layout.addLayout(seed_row)

        gen_btn = QPushButton("Generate Texture")
        gen_btn.clicked.connect(self._generate_texture)
        tex_layout.addWidget(gen_btn)

        layout.addWidget(tex_group)

        # --- Export
        export_btn = QPushButton("Export PNG")
        export_btn.clicked.connect(self._export_png)
        layout.addWidget(export_btn)

        layout.addStretch(1)
        scroll.setWidget(inner)
        return wrap

    def _build_center_panel(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toolbar: pencil / eraser / eyedropper, undo/redo, zoom dropdown.
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self._tool_buttons: dict[str, QAction] = {}
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        for mode, label, shortcut in (
            (MODE_PENCIL, "Pencil (P)", "P"),
            (MODE_ERASER, "Eraser (E)", "E"),
            (MODE_EYEDROPPER, "Eyedropper (I)", "I"),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(lambda _checked=False, m=mode: self._canvas.set_mode(m))
            toolbar.addAction(act)
            self._tool_buttons[mode] = act
        self._tool_buttons[MODE_PENCIL].setChecked(True)
        toolbar.addSeparator()
        undo_act = QAction("Undo (Ctrl+Z)", self)
        undo_act.triggered.connect(self._canvas.undo)
        toolbar.addAction(undo_act)
        redo_act = QAction("Redo (Ctrl+Shift+Z)", self)
        redo_act.triggered.connect(self._canvas.redo)
        toolbar.addAction(redo_act)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Zoom: "))
        self._zoom_combo = QComboBox()
        for z in ZOOM_LEVELS:
            self._zoom_combo.addItem(f"{z}x", z)
        self._zoom_combo.setCurrentText(f"{self._canvas.zoom()}x")
        self._zoom_combo.currentIndexChanged.connect(self._on_zoom_combo_changed)
        toolbar.addWidget(self._zoom_combo)
        layout.addWidget(toolbar)

        # Cursor / canvas info bar.
        self._cursor_info = QLabel("(canvas)")
        self._cursor_info.setStyleSheet("QLabel { color: #aaa; }")
        layout.addWidget(self._cursor_info)

        # Scrollable canvas in the centre.
        canvas_scroll = QScrollArea()
        canvas_scroll.setWidget(self._canvas)
        canvas_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(canvas_scroll, 1)
        return wrap

    def _build_right_panel(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(6, 6, 6, 6)

        self._ramp_editor = _RampEditor()
        self._ramp_editor.stop_clicked.connect(self._on_ramp_stop_picked)
        self._ramp_editor.stops_changed.connect(self._on_ramp_changed)
        layout.addWidget(self._ramp_editor)

        self._active_swatch = _ActiveColorSwatch()
        layout.addWidget(self._active_swatch)
        layout.addStretch(1)
        return wrap

    # -- Helpers --------------------------------------------------------

    def _set_base_color_swatch(self, color: Color | None) -> None:
        if color is None:
            self._base_color_swatch.setStyleSheet(
                "QFrame { background: repeating-linear-gradient(45deg, #444, #444 5px, #2b2b2b 5px, #2b2b2b 10px); border: 1px solid #222; }"
            )
        else:
            r, g, b, _ = color
            self._base_color_swatch.setStyleSheet(
                f"QFrame {{ background-color: rgb({r}, {g}, {b}); border: 1px solid #222; }}"
            )

    # -- Canvas / palette / ramp interaction ---------------------------

    def _do_resize_canvas(self) -> None:
        new_w = int(self._width_spin.value())
        new_h = int(self._height_spin.value())
        if new_w == self._canvas.image().width and new_h == self._canvas.image().height:
            self.statusBar().showMessage("Canvas size unchanged")
            return
        if self._canvas.has_content():
            answer = QMessageBox.question(
                self,
                "Resize canvas?",
                "Resizing will clear the existing canvas. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._canvas.resize_canvas(new_w, new_h)
        self._sync_panel_canvas_size()
        self.statusBar().showMessage(f"Canvas resized to {new_w}x{new_h}")

    def _sync_panel_canvas_size(self) -> None:
        """Push the current canvas size down into every parameter panel so
        size-dependent UI (e.g. the cracks-too-small warning) stays
        accurate after a resize."""
        img = self._canvas.image()
        for panel in self._param_panels.values():
            if hasattr(panel, "update_canvas_size"):
                panel.update_canvas_size(img.width, img.height)

    def _import_palette(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import palette image",
            "",
            "PNG images (*.png);;All images (*.png *.jpg *.jpeg *.bmp);;All files (*)",
        )
        if not path:
            return
        try:
            colors = unique_colors_from_image(path)
        except Exception as exc:  # any decode/IO failure
            QMessageBox.warning(self, "Import failed", f"Couldn't load palette:\n{exc}")
            return
        self._palette_panel.set_colors(colors)
        self.statusBar().showMessage(
            f"Imported {len(colors)} unique colors from {Path(path).name}"
        )

    def _on_base_color_chosen(self, r: int, g: int, b: int, a: int) -> None:
        color: Color = (r, g, b, a)
        self._base_color = color
        self._set_base_color_swatch(color)
        self._gen_ramp_btn.setEnabled(True)
        # Also adopt as the active drawing color; it's almost always what
        # the user wants after picking a swatch.
        self._set_active_color(color)
        self.statusBar().showMessage(f"Base color set to {_hex(color)}")

    def _generate_ramp(self) -> None:
        if self._base_color is None:
            return
        n = int(self._ramp_count_spin.value())
        try:
            stops = generate_ramp(self._base_color, n)
        except ValueError as exc:
            self.statusBar().showMessage(str(exc), 5000)
            return
        self._ramp_editor.set_stops(stops)
        self.statusBar().showMessage(
            f"Ramp generated: {n} stops from {_hex(self._base_color)}"
        )

    def _on_ramp_stop_picked(self, r: int, g: int, b: int, a: int) -> None:
        self._set_active_color((r, g, b, a))

    def _on_ramp_changed(self) -> None:
        # Status bar feedback only - generation still requires the explicit
        # button so users don't lose their painted-over canvas to a stray
        # double-click.
        n = len(self._ramp_editor.stops())
        if n:
            self.statusBar().showMessage(f"Ramp updated ({n} stops)")

    def _set_active_color(self, color: Color) -> None:
        self._canvas.set_active_color(*color)
        self._active_swatch.set_color(color)

    def _on_canvas_picked_color(self, r: int, g: int, b: int, a: int) -> None:
        self._set_active_color((r, g, b, a))

    def _on_cursor_pixel(self, x: int, y: int) -> None:
        if x < 0 or y < 0:
            self._cursor_info.setText("(off canvas)")
        else:
            r, g, bl, a = self._canvas.image().getpixel((x, y))
            self._cursor_info.setText(
                f"({x:>3},{y:>3})  pixel #{r:02x}{bl:02x}{bl:02x}  alpha {a}"
            )

    def _on_zoom_combo_changed(self, _idx: int) -> None:
        self._canvas.set_zoom(int(self._zoom_combo.currentData()))

    def _on_zoom_changed(self, zoom: int) -> None:
        # Sync the combo if the canvas changed zoom via key/wheel/etc.
        i = self._zoom_combo.findData(zoom)
        if i >= 0 and self._zoom_combo.currentIndex() != i:
            self._zoom_combo.blockSignals(True)
            self._zoom_combo.setCurrentIndex(i)
            self._zoom_combo.blockSignals(False)

    def _on_mode_changed(self, mode: str) -> None:
        # Keep the toolbar buttons in lockstep with the canvas mode (e.g.
        # when the user pressed P/E/I shortcuts on the canvas).
        for m, act in self._tool_buttons.items():
            act.blockSignals(True)
            act.setChecked(m == mode)
            act.blockSignals(False)

    def _on_texture_type_changed(self, _idx: int) -> None:
        t = self._type_combo.currentData()
        panel = self._param_panels.get(t)
        if panel is not None:
            self._param_stack.setCurrentWidget(panel)
            # Hand the panel the current canvas size so its size-dependent
            # warnings (e.g. cracks-too-small) reflect reality immediately.
            img = self._canvas.image()
            if hasattr(panel, "update_canvas_size"):
                panel.update_canvas_size(img.width, img.height)
        self.statusBar().showMessage(f"Texture type: {t}")

    def _reroll_seed(self) -> None:
        self._seed_spin.setValue(secrets.randbelow(_SEED_MAX) + 1)

    # -- Generate texture ---------------------------------------------

    def _generate_texture(self) -> None:
        stops = self._ramp_editor.stops()
        if not stops:
            QMessageBox.information(
                self,
                "Need a ramp",
                "Pick a base color and click \"Generate Ramp\" before "
                "generating a texture.",
            )
            return
        if self._canvas.has_content():
            answer = QMessageBox.question(
                self,
                "Overwrite canvas?",
                "Generating will replace the canvas contents. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        texture_type = self._type_combo.currentData()
        w = self._canvas.image().width
        h = self._canvas.image().height
        seed = int(self._seed_spin.value())

        try:
            if texture_type == "Brick":
                brick_params = self._param_panels["Brick"].to_params()
                result = generate_brick_texture(
                    width=w,
                    height=h,
                    ramp_colors=stops,
                    params=brick_params,
                    seed=seed,
                )
            elif texture_type == "Blocks":
                blocks_params = self._param_panels["Blocks"].to_params()
                result = generate_blocks_texture(
                    width=w,
                    height=h,
                    ramp_colors=stops,
                    params=blocks_params,
                    seed=seed,
                )
            elif texture_type == "Boards":
                boards_params = self._param_panels["Boards"].to_params()
                result = generate_boards_texture(
                    width=w,
                    height=h,
                    ramp_colors=stops,
                    params=boards_params,
                    seed=seed,
                )
            else:
                raise ValueError(f"Unknown texture type: {texture_type}")
        except Exception as exc:
            QMessageBox.warning(self, "Generation failed", str(exc))
            return

        # Push the pre-generation snapshot onto the undo stack first, then
        # replace the image without snapshotting again - one Ctrl+Z rolls
        # back to whatever the user had painted.
        before = self._canvas.image_copy()
        self._canvas.push_external_snapshot(before)
        self._canvas.set_image(result, snapshot=False)
        self.statusBar().showMessage(
            f"Generated {texture_type} {w}x{h} (seed {seed})"
        )

    # -- Export -------------------------------------------------------

    def _export_png(self) -> None:
        img = self._canvas.image()
        texture_type = str(self._type_combo.currentData())
        suggested = texture_type_default_filename(texture_type, img.width, img.height)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export texture as PNG",
            suggested,
            "PNG image (*.png)",
        )
        if not path:
            return
        try:
            img.save(path, "PNG")
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", f"Couldn't save:\n{exc}")
            return
        self.statusBar().showMessage(f"Exported to {path}", 5000)
