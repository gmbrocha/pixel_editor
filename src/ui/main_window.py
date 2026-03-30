from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.core.assets import SavedAsset, build_tilesheet
from src.core.document import EditorDocument
from src.core.extract_region import extract_to_preview
from src.core.image_io import load_image, save_image
from src.core.palette import (
    add_color_to_palette,
    export_palette_strip,
    load_palette_from_image,
    palette_from_image,
    quantize_to_palette,
)
from src.core.pixel_document import PixelDocument, create_blank_pixel_map
from src.ui.asset_tray import AssetTray
from src.ui.palette_panel import PalettePanel
from src.ui.pixel_editor_window import PixelEditorWindow
from src.ui.preview_panel import PreviewPanel
from src.ui.source_canvas import SourceCanvas


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.document = EditorDocument()
        self._asset_counter = 1
        self._pixel_windows: list[PixelEditorWindow] = []
        self.setWindowTitle("Pixels Tile And Sprite Editor")
        self.resize(1440, 920)

        self.source_canvas = SourceCanvas()
        self.preview_panel = PreviewPanel()
        self.palette_panel = PalettePanel()
        self.asset_tray = AssetTray()

        self._build_toolbar()
        self._build_layout()
        self._connect_signals()
        self.statusBar().showMessage("Import an image to begin")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        open_action = QAction("Open Image", self)
        open_action.triggered.connect(self.open_image)
        toolbar.addAction(open_action)

        clear_action = QAction("Clear Selections", self)
        clear_action.triggered.connect(self.source_canvas.clear_selections)
        toolbar.addAction(clear_action)

        delete_action = QAction("Delete Active", self)
        delete_action.triggered.connect(self.source_canvas.delete_active_selection)
        toolbar.addAction(delete_action)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Freehand: hold Shift and drag"))

    def _build_layout(self) -> None:
        central = QWidget()
        central_layout = QVBoxLayout(central)

        canvas_group = QGroupBox("Source Image")
        canvas_layout = QVBoxLayout(canvas_group)
        canvas_layout.addWidget(self.source_canvas)

        helper_label = QLabel(
            "Tips: left click adds polygon points, double click closes, drag handles to reshape, "
            "drag inside a region to move it, Shift + drag draws a freehand selection, "
            "mouse wheel zooms, middle mouse or Space + drag pans, and Ctrl + 0 resets the view."
        )
        helper_label.setWordWrap(True)
        canvas_layout.addWidget(helper_label)

        pixel_tools_group = QGroupBox("Pixel Map Tools")
        pixel_tools_layout = QVBoxLayout(pixel_tools_group)
        blank_size_row = QHBoxLayout()
        self.blank_width_spin = QSpinBox()
        self.blank_width_spin.setRange(1, 1024)
        self.blank_width_spin.setValue(16)
        self.blank_height_spin = QSpinBox()
        self.blank_height_spin.setRange(1, 1024)
        self.blank_height_spin.setValue(16)
        blank_size_row.addWidget(QLabel("X"))
        blank_size_row.addWidget(self.blank_width_spin)
        blank_size_row.addWidget(QLabel("Y"))
        blank_size_row.addWidget(self.blank_height_spin)

        self.open_blank_pixel_map_button = QPushButton("Open Blank Pixel Map")
        self.open_preview_pixel_editor_button = QPushButton("Open Preview In Pixel Editor")
        self.open_source_pixel_editor_button = QPushButton("Open Source In Pixel Editor")

        pixel_tools_layout.addLayout(blank_size_row)
        pixel_tools_layout.addWidget(self.open_blank_pixel_map_button)
        pixel_tools_layout.addWidget(self.open_preview_pixel_editor_button)
        pixel_tools_layout.addWidget(self.open_source_pixel_editor_button)
        canvas_layout.addWidget(pixel_tools_group)

        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.addWidget(self.preview_panel, 3)
        right_layout.addWidget(self.palette_panel, 2)

        top_splitter = QSplitter()
        top_splitter.addWidget(canvas_group)
        top_splitter.addWidget(right_column)
        top_splitter.setStretchFactor(0, 3)
        top_splitter.setStretchFactor(1, 2)

        asset_group = QGroupBox("Saved Tiles And Assets")
        asset_layout = QVBoxLayout(asset_group)
        asset_layout.addWidget(self.asset_tray)

        central_layout.addWidget(top_splitter, 1)
        central_layout.addWidget(asset_group)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.source_canvas.selections_changed.connect(self._on_selections_changed)
        self.source_canvas.status_changed.connect(self.statusBar().showMessage)
        self.preview_panel.settings_changed.connect(self._on_preview_settings_changed)
        self.preview_panel.save_requested.connect(self.save_preview_to_tray)
        self.palette_panel.derive_from_preview_requested.connect(self.derive_palette_from_preview)
        self.palette_panel.load_palette_requested.connect(self.load_palette)
        self.palette_panel.export_palette_requested.connect(self.export_palette)
        self.palette_panel.custom_color_requested.connect(self.add_custom_palette_color)
        self.palette_panel.apply_palette_to_preview_requested.connect(self.quantize_preview)
        self.palette_panel.apply_palette_to_source_requested.connect(self.apply_palette_to_source)
        self.asset_tray.import_requested.connect(self.import_asset)
        self.asset_tray.export_requested.connect(self.export_tilesheet)
        self.asset_tray.clear_requested.connect(self.clear_assets)
        self.asset_tray.remove_selected_requested.connect(self.remove_selected_assets)
        self.asset_tray.asset_open_requested.connect(self.open_asset_in_pixel_editor)
        self.open_blank_pixel_map_button.clicked.connect(self.open_blank_pixel_map)
        self.open_preview_pixel_editor_button.clicked.connect(self.open_preview_in_pixel_editor)
        self.open_source_pixel_editor_button.clicked.connect(self.open_source_in_pixel_editor)

    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "",
            "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)",
        )
        if not path:
            return

        try:
            image = load_image(path)
        except Exception as exc:  # pragma: no cover - GUI feedback
            QMessageBox.critical(self, "Open failed", str(exc))
            return

        self.document.source_image = image
        self.document.source_path = path
        self.document.selections.clear()
        self.document.preview_image = None
        self.source_canvas.set_image(image)
        self.source_canvas.set_selections([])
        self._refresh_preview()
        self.statusBar().showMessage(f"Loaded {Path(path).name}")

    def _on_selections_changed(self, selections) -> None:
        self.document.selections = list(selections)
        self._refresh_preview()

    def _on_preview_settings_changed(self, settings) -> None:
        self.document.preview_settings = settings
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self.document.source_image is None:
            self.document.preview_image = None
            self.preview_panel.set_preview_image(None)
            return

        self.document.preview_image = extract_to_preview(
            self.document.source_image,
            self.document.selections,
            self.document.preview_settings,
        )
        self.preview_panel.set_preview_image(self.document.preview_image)

    def derive_palette_from_preview(self) -> None:
        if self.document.preview_image is None:
            return
        palette = palette_from_image(
            self.document.preview_image,
            max_colors=self.palette_panel.max_colors(),
        )
        self.document.palette = palette
        self.palette_panel.set_palette(palette)
        self.statusBar().showMessage("Palette derived from preview")

    def load_palette(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Palette From Image",
            "",
            "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        try:
            palette = load_palette_from_image(path, max_colors=self.palette_panel.max_colors())
        except Exception as exc:  # pragma: no cover - GUI feedback
            QMessageBox.critical(self, "Palette load failed", str(exc))
            return
        self.document.palette = palette
        self.palette_panel.set_palette(palette)
        self.statusBar().showMessage(f"Loaded palette from {Path(path).name}")

    def export_palette(self) -> None:
        if not self.document.palette:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Palette",
            "palette.png",
            "PNG Image (*.png)",
        )
        if not path:
            return
        export_palette_strip(self.document.palette, path)
        self.statusBar().showMessage(f"Exported palette to {Path(path).name}")

    def add_custom_palette_color(self) -> None:
        initial_color = QColor(255, 255, 255, 255)
        if self.document.palette:
            initial_color = QColor(*self.document.palette[-1])
        color = QColorDialog.getColor(initial_color, self, "Add Custom Palette Color")
        if not color.isValid():
            return

        rgba = (color.red(), color.green(), color.blue(), color.alpha())
        self.document.palette = add_color_to_palette(
            self.document.palette,
            rgba,
            max_colors=self.palette_panel.max_colors(),
        )
        self.palette_panel.set_palette(self.document.palette)
        self.statusBar().showMessage("Added custom color to palette")

    def quantize_preview(self) -> None:
        if self.document.preview_image is None or not self.document.palette:
            return
        self.document.preview_image = quantize_to_palette(
            self.document.preview_image,
            self.document.palette,
        )
        self.preview_panel.set_preview_image(self.document.preview_image)
        self.statusBar().showMessage("Preview quantized to current palette")

    def apply_palette_to_source(self) -> None:
        if self.document.source_image is None or not self.document.palette:
            return
        self.document.source_image = quantize_to_palette(
            self.document.source_image,
            self.document.palette,
        )
        self.source_canvas.set_image(self.document.source_image)
        self.source_canvas.set_selections(self.document.selections)
        self._refresh_preview()
        self.statusBar().showMessage("Palette applied to source image")

    def save_preview_to_tray(self) -> None:
        if self.document.preview_image is None:
            return
        name = self._default_asset_name()
        self._add_asset(name, self.document.preview_image.copy())
        self._asset_counter += 1
        self.statusBar().showMessage(f"Saved preview as {name}")

    def import_asset(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Assets",
            "",
            "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)",
        )
        if not paths:
            return
        for path in paths:
            try:
                image = load_image(path)
            except Exception:
                continue
            self._add_asset(Path(path).stem, image, refresh=False)
        self.asset_tray.set_assets(self.document.assets)
        self.statusBar().showMessage(f"Imported {len(paths)} assets")

    def export_tilesheet(self) -> None:
        if not self.document.assets:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Tilesheet",
            "tilesheet.png",
            "PNG Image (*.png)",
        )
        if not path:
            return
        image = build_tilesheet(self.document.assets)
        save_image(image, path)
        self.statusBar().showMessage(f"Exported tilesheet to {Path(path).name}")

    def clear_assets(self) -> None:
        self.document.assets.clear()
        self.asset_tray.set_assets(self.document.assets)
        self.statusBar().showMessage("Cleared saved assets")

    def remove_selected_assets(self) -> None:
        selected_ids = set(self.asset_tray.selected_asset_ids())
        if not selected_ids:
            return
        self.document.assets = [
            asset for asset in self.document.assets if asset.id not in selected_ids
        ]
        self.asset_tray.set_assets(self.document.assets)
        self.statusBar().showMessage("Removed selected assets")

    def _default_asset_name(self) -> str:
        stem = "preview"
        if self.document.source_path:
            stem = Path(self.document.source_path).stem
        return f"{stem}_{self._asset_counter:03d}"

    def open_blank_pixel_map(self) -> None:
        document = create_blank_pixel_map(
            self.blank_width_spin.value(),
            self.blank_height_spin.value(),
        )
        document.palette = list(self.document.palette)
        self._open_pixel_editor(document)

    def open_preview_in_pixel_editor(self) -> None:
        if self.document.preview_image is None:
            self.statusBar().showMessage("No preview available to open")
            return
        document = PixelDocument(
            image=self.document.preview_image.copy(),
            name=self._default_asset_name(),
            palette=list(self.document.palette),
        )
        self._open_pixel_editor(document)

    def open_source_in_pixel_editor(self) -> None:
        if self.document.source_image is None:
            self.statusBar().showMessage("No source image loaded")
            return
        name = Path(self.document.source_path).stem if self.document.source_path else "source"
        document = PixelDocument(
            image=self.document.source_image.copy(),
            name=name,
            palette=list(self.document.palette),
        )
        self._open_pixel_editor(document)

    def open_asset_in_pixel_editor(self, asset_id: str) -> None:
        asset = next((item for item in self.document.assets if item.id == asset_id), None)
        if asset is None:
            return
        document = PixelDocument(
            image=asset.image.copy(),
            name=asset.name,
            palette=list(self.document.palette),
        )
        self._open_pixel_editor(document)

    def _open_pixel_editor(self, document: PixelDocument) -> None:
        window = PixelEditorWindow(document, self)
        window.asset_save_requested.connect(self._on_pixel_editor_asset_saved)
        window.destroyed.connect(lambda *_args, target=window: self._remove_pixel_window(target))
        self._pixel_windows.append(window)
        window.show()
        self.statusBar().showMessage(f"Opened pixel editor for {document.name}")

    def _remove_pixel_window(self, target: PixelEditorWindow) -> None:
        self._pixel_windows = [window for window in self._pixel_windows if window is not target]

    def _on_pixel_editor_asset_saved(self, name: str, image) -> None:
        self._add_asset(name, image.copy())
        self.statusBar().showMessage(f"Saved pixel editor output as {name}")

    def _add_asset(self, name: str, image, refresh: bool = True) -> None:
        self.document.assets.append(SavedAsset(name=name, image=image))
        if refresh:
            self.asset_tray.set_assets(self.document.assets)
