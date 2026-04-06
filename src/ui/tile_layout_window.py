from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.core.image_io import load_image, save_image
from src.core.pixel_document import PixelDocument
from src.core.tile_layout import PlacedTile, next_free_position
from src.ui.assembly_grid_widget import AssemblyGridWidget
from src.ui.pixel_grid_canvas import PixelGridCanvas
from src.ui.tile_layout_canvas import TileLayoutCanvas


class TileLayoutWindow(QMainWindow):
    """Three-pane tile layout editor: Assembly Grid | Sheet | Selected composite."""

    def __init__(self, parent: QWidget | None = None, initial_palette: list | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tile Layout")
        self.resize(1400, 900)
        self._tiles: list[PlacedTile] = []
        self._tile_w = 16
        self._tile_h = 16
        self._palette = list(initial_palette or [])

        self._composite_origin: tuple[int, int] = (0, 0)
        self._composite_cells: list[tuple[int, int]] = []

        self._selection_label = QLabel("No tiles selected")
        self._layout_canvas = TileLayoutCanvas()

        self._assembly = AssemblyGridWidget()

        self._sheet_zoom = QSpinBox()
        self._sheet_zoom.setRange(4, 48)
        self._sheet_zoom.setValue(16)

        self._asm_cols_spin = QSpinBox()
        self._asm_cols_spin.setRange(1, 128)
        self._asm_cols_spin.setValue(4)
        self._asm_rows_spin = QSpinBox()
        self._asm_rows_spin.setRange(1, 128)
        self._asm_rows_spin.setValue(4)
        self._asm_zoom_spin = QSpinBox()
        self._asm_zoom_spin.setRange(2, 48)
        self._asm_zoom_spin.setValue(16)

        self._pixel_doc: PixelDocument | None = None
        self._pixel_canvas = PixelGridCanvas()
        self._pixel_zoom = QSpinBox()
        self._pixel_zoom.setRange(8, 48)
        self._pixel_zoom.setValue(20)

        self._paint_radio = QRadioButton("Paint")
        self._select_radio = QRadioButton("Select (Alt+drag)")
        self._paint_radio.setChecked(True)

        self._color_preview = QLabel()
        self._color_preview.setFixedSize(28, 28)
        self._current_color: tuple[int, int, int, int] = (0, 0, 0, 255)
        self._update_color_preview()
        self._transparent_btn = QPushButton("Transparent (erase)")
        self._transparent_btn.setCheckable(True)
        self._pick_color_btn = QPushButton("Pick color…")
        self._palette_from_pixels_btn = QPushButton("Palette from pixels")

        self._palette_buttons: list[QPushButton] = []

        self._build_toolbar()
        self._build_layout()
        self._connect_signals()

        self._layout_canvas.set_zoom(self._sheet_zoom.value())
        self._assembly.set_zoom(self._asm_zoom_spin.value())
        self._pixel_canvas.set_zoom(self._pixel_zoom.value())
        self._pixel_canvas.set_mode("paint")
        self._sync_layout_canvas()
        self._update_selected_pane()
        self.statusBar().showMessage(
            "Add PNGs to the Sheet. Drag tiles to the Assembly Grid. Select grid cells to composite-edit."
        )

    def _build_toolbar(self) -> None:
        tb = QToolBar("Tile layout")
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addAction("Add tiles…", self._add_tiles)
        tb.addAction("Remove selected sheet tiles", self._remove_selected)
        tb.addAction("Export sheet tiles…", self._export_sheet_folder)
        tb.addSeparator()
        tb.addAction("Export grid tiles…", self._export_grid_tiles)
        tb.addAction("Apply edits to grid", self._apply_edits_to_grid)

    def _build_layout(self) -> None:
        # --- Assembly Grid (left) ---
        asm_group = QGroupBox("Assembly Grid")
        asm_l = QVBoxLayout(asm_group)
        dim_row = QHBoxLayout()
        dim_row.addWidget(QLabel("Cols"))
        dim_row.addWidget(self._asm_cols_spin)
        dim_row.addWidget(QLabel("Rows"))
        dim_row.addWidget(self._asm_rows_spin)
        clear_btn = QPushButton("Clear Grid")
        clear_btn.clicked.connect(self._assembly.clear_grid)
        dim_row.addWidget(clear_btn)
        dim_row.addStretch(1)
        asm_l.addLayout(dim_row)
        az_row = QHBoxLayout()
        az_row.addWidget(QLabel("Zoom"))
        az_row.addWidget(self._asm_zoom_spin)
        az_row.addStretch(1)
        asm_l.addLayout(az_row)
        asm_scroll = QScrollArea()
        asm_scroll.setWidgetResizable(True)
        asm_scroll.setWidget(self._assembly)
        asm_l.addWidget(asm_scroll, 1)

        # --- Sheet (right) ---
        sheet_group = QGroupBox("Sheet (tile source)")
        sheet_l = QVBoxLayout(sheet_group)
        sz_row = QHBoxLayout()
        sz_row.addWidget(QLabel("Zoom"))
        sz_row.addWidget(self._sheet_zoom)
        sz_row.addStretch(1)
        sheet_l.addLayout(sz_row)
        sheet_l.addWidget(self._selection_label)
        sheet_scroll = QScrollArea()
        sheet_scroll.setWidgetResizable(True)
        sheet_scroll.setWidget(self._layout_canvas)
        sheet_l.addWidget(sheet_scroll, 1)

        top_split = QSplitter(Qt.Orientation.Horizontal)
        top_split.addWidget(asm_group)
        top_split.addWidget(sheet_group)
        top_split.setStretchFactor(0, 3)
        top_split.setStretchFactor(1, 2)

        # --- Selected (bottom) ---
        mode_group = QButtonGroup(self)
        mode_group.addButton(self._paint_radio)
        mode_group.addButton(self._select_radio)

        edit_group = QGroupBox("Selected")
        edit_l = QVBoxLayout(edit_group)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Pixel zoom"))
        controls.addWidget(self._pixel_zoom)
        controls.addWidget(self._paint_radio)
        controls.addWidget(self._select_radio)
        controls.addWidget(self._color_preview)
        controls.addWidget(self._pick_color_btn)
        controls.addWidget(self._transparent_btn)
        controls.addWidget(self._palette_from_pixels_btn)
        controls.addStretch(1)
        edit_l.addLayout(controls)
        self._palette_row = QHBoxLayout()
        self._palette_row.setSpacing(2)
        self._palette_row.addStretch(1)
        edit_l.addLayout(self._palette_row)
        pscroll = QScrollArea()
        pscroll.setWidgetResizable(True)
        pscroll.setWidget(self._pixel_canvas)
        edit_l.addWidget(pscroll, 1)

        main_split = QSplitter(Qt.Orientation.Vertical)
        main_split.addWidget(top_split)
        main_split.addWidget(edit_group)
        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 2)

        central = QWidget()
        cl = QVBoxLayout(central)
        cl.addWidget(main_split)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self._sheet_zoom.valueChanged.connect(self._layout_canvas.set_zoom)
        self._asm_zoom_spin.valueChanged.connect(self._assembly.set_zoom)
        self._asm_cols_spin.valueChanged.connect(self._on_asm_dims_changed)
        self._asm_rows_spin.valueChanged.connect(self._on_asm_dims_changed)
        self._pixel_zoom.valueChanged.connect(self._pixel_canvas.set_zoom)
        self._paint_radio.toggled.connect(self._on_pixel_mode)
        self._select_radio.toggled.connect(self._on_pixel_mode)
        self._pixel_canvas.image_changed.connect(self._on_pixel_image_changed)
        self._layout_canvas.status_changed.connect(self.statusBar().showMessage)
        self._layout_canvas.selection_changed.connect(self._on_sheet_selection)
        self._assembly.selection_changed.connect(self._on_assembly_selection)
        self._assembly.grid_changed.connect(self._on_assembly_grid_changed)
        self._pick_color_btn.clicked.connect(self._pick_color)
        self._transparent_btn.toggled.connect(self._on_transparent_toggled)
        self._palette_from_pixels_btn.clicked.connect(self._palette_from_current)

    def _on_asm_dims_changed(self) -> None:
        self._assembly.set_dimensions(self._asm_cols_spin.value(), self._asm_rows_spin.value())

    def _on_sheet_selection(self, summary: str) -> None:
        self._selection_label.setText(summary)

    def _on_assembly_selection(self, cells: list[tuple[int, int]]) -> None:
        self._update_selected_pane()

    def _on_assembly_grid_changed(self) -> None:
        self._assembly.set_tile_size(self._tile_w, self._tile_h)

    def _on_pixel_mode(self) -> None:
        mode = "paint" if self._paint_radio.isChecked() else "select"
        self._pixel_canvas.set_mode(mode)

    def _on_pixel_image_changed(self) -> None:
        self._pixel_canvas.update()

    def _on_transparent_toggled(self, checked: bool) -> None:
        if self._pixel_doc is not None:
            self._pixel_doc.use_transparent_color = checked

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(
            QColor(*self._current_color[:3]),
            self,
            "Pick paint color",
        )
        if c.isValid():
            self._current_color = (c.red(), c.green(), c.blue(), 255)
            self._update_color_preview()
            if self._pixel_doc is not None:
                self._pixel_doc.current_color = self._current_color

    def _palette_from_current(self) -> None:
        if self._pixel_doc is None:
            return
        img = self._pixel_doc.image
        colors: list[tuple[int, int, int, int]] = []
        seen: set[tuple[int, int, int, int]] = set()
        for y in range(img.height):
            for x in range(img.width):
                px = img.getpixel((x, y))
                if px[3] == 0:
                    continue
                c = (px[0], px[1], px[2], px[3])
                if c not in seen:
                    seen.add(c)
                    colors.append(c)
        self._palette = colors
        if self._pixel_doc is not None:
            self._pixel_doc.palette = list(colors)
        self._rebuild_palette_buttons()
        self.statusBar().showMessage(f"Palette: {len(colors)} color(s) from current pixels")

    def _rebuild_palette_buttons(self) -> None:
        for btn in self._palette_buttons:
            self._palette_row.removeWidget(btn)
            btn.deleteLater()
        self._palette_buttons.clear()
        for color in self._palette:
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            r, g, b, a = color
            btn.setStyleSheet(
                f"background-color: rgba({r},{g},{b},{a}); border: 1px solid #666;"
            )
            btn.setToolTip(f"#{r:02X}{g:02X}{b:02X}  RGBA({r},{g},{b},{a})")
            btn.clicked.connect(lambda _checked=False, c=color: self._set_color_from_palette(c))
            self._palette_row.insertWidget(self._palette_row.count() - 1, btn)
            self._palette_buttons.append(btn)

    def _set_color_from_palette(self, color: tuple[int, int, int, int]) -> None:
        self._current_color = color
        self._update_color_preview()
        if self._pixel_doc is not None:
            self._pixel_doc.current_color = color
        self._transparent_btn.setChecked(False)

    def _update_color_preview(self) -> None:
        r, g, b, a = self._current_color
        self._color_preview.setStyleSheet(
            f"background-color: rgba({r},{g},{b},{a}); border: 1px solid #888;"
        )

    def _sync_layout_canvas(self) -> None:
        self._layout_canvas.set_tiles(self._tiles, self._tile_w, self._tile_h)
        self._assembly.set_tile_size(self._tile_w, self._tile_h)

    def _build_composite(self, cells: list[tuple[int, int]]) -> Image.Image | None:
        if not cells:
            return None
        grid = self._assembly.grid_data()
        filled = [(c, grid[c]) for c in cells if c in grid]
        if not filled:
            return None
        col_min = min(c[0] for c, _ in filled)
        row_min = min(c[1] for c, _ in filled)
        col_max = max(c[0] for c, _ in filled)
        row_max = max(c[1] for c, _ in filled)
        tw, th = self._tile_w, self._tile_h
        w = (col_max - col_min + 1) * tw
        h = (row_max - row_min + 1) * th
        composite = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
        for (col, row), img in filled:
            x = (col - col_min) * tw
            y = (row - row_min) * th
            composite.paste(img, (x, y))
        return composite

    def _update_selected_pane(self) -> None:
        cells = self._assembly.selected_cells()
        composite = self._build_composite(cells)
        if composite is None:
            self._pixel_doc = None
            blank = Image.new("RGBA", (max(1, self._tile_w), max(1, self._tile_h)), (0, 0, 0, 0))
            self._pixel_canvas.set_document(PixelDocument(image=blank, name="none", palette=list(self._palette)))
            self._pixel_canvas.set_frame_grid(None)
            self._pixel_canvas.setEnabled(False)
            self._composite_cells = []
            return

        col_min = min(c[0] for c in cells)
        row_min = min(c[1] for c in cells)
        self._composite_origin = (col_min, row_min)
        self._composite_cells = list(cells)

        self._pixel_doc = PixelDocument(
            image=composite,
            name="composite",
            palette=list(self._palette),
            current_color=self._current_color,
            use_transparent_color=self._transparent_btn.isChecked(),
        )
        self._pixel_canvas.set_document(self._pixel_doc)
        self._pixel_canvas.set_frame_grid((self._tile_w, self._tile_h))
        self._pixel_canvas.setEnabled(True)

    def _slice_composite(self) -> dict[tuple[int, int], Image.Image]:
        """Slice the current composite image back into tile-sized chunks keyed by grid position."""
        if self._pixel_doc is None or not self._composite_cells:
            return {}
        img = self._pixel_doc.image
        tw, th = self._tile_w, self._tile_h
        col_min, row_min = self._composite_origin
        result: dict[tuple[int, int], Image.Image] = {}
        for cell in self._composite_cells:
            x = (cell[0] - col_min) * tw
            y = (cell[1] - row_min) * th
            if x + tw <= img.width and y + th <= img.height:
                tile_img = img.crop((x, y, x + tw, y + th)).copy()
                result[cell] = tile_img
        return result

    def _apply_edits_to_grid(self) -> None:
        slices = self._slice_composite()
        if not slices:
            self.statusBar().showMessage("Nothing to apply")
            return
        for pos, img in slices.items():
            self._assembly.place_tile(pos[0], pos[1], img)
        self._assembly.update()
        self.statusBar().showMessage(f"Applied edits to {len(slices)} grid cell(s)")

    def _export_grid_tiles(self) -> None:
        grid = self._assembly.grid_data()
        if not grid:
            QMessageBox.information(self, "Export", "Assembly grid is empty.")
            return

        slices = self._slice_composite() if self._pixel_doc is not None and self._composite_cells else {}
        merged = dict(grid)
        merged.update(slices)

        folder = QFileDialog.getExistingDirectory(self, "Export grid tiles to folder")
        if not folder:
            return
        base = Path(folder)
        used: set[str] = set()
        count = 0
        for (col, row), img in sorted(merged.items()):
            name = f"tile_{col}_{row}.png"
            n = 1
            while name in used or (base / name).exists():
                n += 1
                name = f"tile_{col}_{row}_{n}.png"
            used.add(name)
            save_image(img, base / name)
            count += 1
        self.statusBar().showMessage(f"Exported {count} grid tile(s) to {folder}")

    def _add_tiles(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add tiles (same dimensions)",
            "",
            "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)",
        )
        if not paths:
            return
        errors: list[str] = []
        for path in paths:
            try:
                img = load_image(path)
            except Exception as exc:
                errors.append(f"{Path(path).name}: {exc}")
                continue
            if not self._tiles:
                self._tile_w, self._tile_h = img.size
            elif img.size != (self._tile_w, self._tile_h):
                errors.append(
                    f"{Path(path).name}: expected {self._tile_w}x{self._tile_h}, got {img.width}x{img.height}"
                )
                continue
            tile = PlacedTile.from_file(path, img.copy())
            col, row = next_free_position(self._tiles)
            tile.grid_x = col
            tile.grid_y = row
            self._tiles.append(tile)
        self._sync_layout_canvas()
        if errors:
            QMessageBox.warning(
                self,
                "Some files skipped",
                "\n".join(errors[:12]) + ("\n..." if len(errors) > 12 else ""),
            )
        self.statusBar().showMessage(f"{len(self._tiles)} tile(s) in sheet")

    def _remove_selected(self) -> None:
        if not self._layout_canvas.selected_ids():
            self.statusBar().showMessage("No tiles selected to remove")
            return
        self._layout_canvas.remove_selected()
        if not self._tiles:
            self._tile_w = 16
            self._tile_h = 16
        self._sync_layout_canvas()
        self.statusBar().showMessage("Removed selected tiles")

    def _export_sheet_folder(self) -> None:
        if not self._tiles:
            QMessageBox.information(self, "Export", "Add tiles first.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Export tiles to folder")
        if not folder:
            return
        base = Path(folder)
        used: set[str] = set()
        for t in self._tiles:
            name = t.name
            candidate = name + ".png"
            n = 1
            while candidate in used or (base / candidate).exists():
                n += 1
                candidate = f"{name}_{n}.png"
            used.add(candidate)
            save_image(t.image, base / candidate)
        self.statusBar().showMessage(f"Exported {len(self._tiles)} file(s) to {folder}")
