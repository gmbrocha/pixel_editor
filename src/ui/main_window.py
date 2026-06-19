from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QFrame,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QToolBar,
    QToolButton,
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
    load_palette_from_source,
    palette_from_image_with_debug,
    quantize_to_palette,
    sort_palette,
)
from src.core.persistent_palette import add_color_persistent, color_tooltip
from src.core.pixel_document import (
    PixelDocument,
    create_blank_pixel_map,
    replace_color_with_transparent,
    replace_light_background_with_transparent,
    replace_similar_color_with_transparent,
)
from src.ui.asset_tray import AssetTray
from src.ui.palette_panel import PalettePanel
from src.ui.persistent_palette_widget import PersistentPaletteWidget
from src.ui.animation_editor_window import AnimationEditorWindow
from src.ui.pixel_editor_window import PixelEditorWindow
from src.ui.preview_panel import PreviewPanel
from src.ui.reference_mapper_window import ReferenceMapperWindow
from src.ui.source_canvas import SourceCanvas
from src.ui.tile_layout_window import TileLayoutWindow
from src.ui.tileset_processor_window import TilesetProcessorWindow
from src.ui.tileset_template_window import TilesetTemplateWindow
from src.ui.texture_generator_window import TextureGeneratorWindow


class CollapsibleSection(QWidget):
    def __init__(self, title: str, expanded: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._toggle_button = QToolButton()
        self._toggle_button.setText(title)
        self._toggle_button.setCheckable(True)
        self._toggle_button.setChecked(expanded)
        self._toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle_button.toggled.connect(self._set_expanded)

        self._content = QFrame()
        self._content.setFrameShape(QFrame.Shape.StyledPanel)
        self._content.setVisible(expanded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addWidget(self._toggle_button)
        layout.addWidget(self._content)

        self._set_expanded(expanded)

    def set_content_layout(self, layout: QLayout) -> None:
        self._content.setLayout(layout)

    def _set_expanded(self, expanded: bool) -> None:
        self._toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self._content.setVisible(expanded)
        self.updateGeometry()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.document = EditorDocument()
        self._asset_counter = 1
        self._pixel_windows: list[PixelEditorWindow] = []
        self._tool_windows: list[QMainWindow] = []
        self.setWindowTitle("PixelForge")
        self.resize(1440, 920)

        self._eyedropper_active = False
        self._selected_transparency_color = (255, 255, 255, 255)
        self._transparency_keys: list[tuple[int, int, int, int]] = [(255, 255, 255, 255)]

        self.source_canvas = SourceCanvas()
        self.preview_panel = PreviewPanel()
        self.palette_panel = PalettePanel()
        self.asset_tray = AssetTray()
        self.persistent_palette = PersistentPaletteWidget()

        self._build_toolbar()
        self._build_layout()
        self._connect_signals()

        self._eyedropper_shortcut = QShortcut(QKeySequence("I"), self)
        self._eyedropper_shortcut.activated.connect(self._toggle_eyedropper)
        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._escape_shortcut.activated.connect(self._cancel_eyedropper)

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
        self._eyedropper_action = QAction("Eyedropper (I)", self)
        self._eyedropper_action.setCheckable(True)
        self._eyedropper_action.triggered.connect(self._toggle_eyedropper)
        toolbar.addAction(self._eyedropper_action)

        toolbar.addSeparator()
        anim_action = QAction("Animation Editor…", self)
        anim_action.triggered.connect(self.open_animation_editor)
        toolbar.addAction(anim_action)
        ref_action = QAction("Reference Grid Mapper…", self)
        ref_action.triggered.connect(self.open_reference_mapper)
        toolbar.addAction(ref_action)
        tile_layout_action = QAction("Tile Layout…", self)
        tile_layout_action.triggered.connect(self.open_tile_layout)
        toolbar.addAction(tile_layout_action)

        toolbar.addSeparator()
        tileset_proc_action = QAction("Tileset Processor…", self)
        tileset_proc_action.triggered.connect(self.open_tileset_processor)
        toolbar.addAction(tileset_proc_action)
        tileset_template_action = QAction("Create Tileset Template…", self)
        tileset_template_action.triggered.connect(self.open_tileset_template)
        toolbar.addAction(tileset_template_action)
        texture_gen_action = QAction("Texture Generator…", self)
        texture_gen_action.triggered.connect(self.open_texture_generator)
        toolbar.addAction(texture_gen_action)

    def _build_layout(self) -> None:
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(4, 4, 4, 4)

        self._canvas_group = QGroupBox("Source Image")
        canvas_layout = QVBoxLayout(self._canvas_group)
        canvas_layout.addWidget(self.source_canvas, 1)

        rect_tool_row = QHBoxLayout()
        rect_tool_row.addWidget(QLabel("Drop rectangle:"))
        self.rect_w_spin = QSpinBox()
        self.rect_w_spin.setRange(1, 4096)
        self.rect_w_spin.setValue(16)
        self.rect_h_spin = QSpinBox()
        self.rect_h_spin.setRange(1, 4096)
        self.rect_h_spin.setValue(16)
        rect_tool_row.addWidget(QLabel("W"))
        rect_tool_row.addWidget(self.rect_w_spin)
        rect_tool_row.addWidget(QLabel("H"))
        rect_tool_row.addWidget(self.rect_h_spin)
        self.drop_rect_button = QPushButton("Drop")
        self.drop_rect_button.clicked.connect(self._drop_rect_selection)
        rect_tool_row.addWidget(self.drop_rect_button)
        rect_tool_row.addStretch(1)
        canvas_layout.addLayout(rect_tool_row)

        self._pixel_tools_group = QGroupBox("Pixel Map Tools")
        self._pixel_tools_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        pixel_tools_layout = QGridLayout(self._pixel_tools_group)
        pixel_tools_layout.setHorizontalSpacing(8)
        pixel_tools_layout.setVerticalSpacing(6)
        for column in range(4):
            pixel_tools_layout.setColumnStretch(column, 1)

        blank_size_widget = QWidget()
        blank_size_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        blank_size_row = QHBoxLayout(blank_size_widget)
        blank_size_row.setContentsMargins(0, 0, 0, 0)
        blank_size_row.setSpacing(4)
        self.blank_width_spin = QSpinBox()
        self.blank_width_spin.setRange(1, 1024)
        self.blank_width_spin.setValue(16)
        self.blank_height_spin = QSpinBox()
        self.blank_height_spin.setRange(1, 1024)
        self.blank_height_spin.setValue(16)
        blank_size_row.addWidget(QLabel("Blank"))
        blank_size_row.addWidget(QLabel("X"))
        blank_size_row.addWidget(self.blank_width_spin)
        blank_size_row.addWidget(QLabel("Y"))
        blank_size_row.addWidget(self.blank_height_spin)
        blank_size_row.addStretch(1)

        self.open_blank_pixel_map_button = QPushButton("Open Blank Pixel Map")
        self.open_preview_pixel_editor_button = QPushButton("Open Preview In PixelForge")
        self.open_source_pixel_editor_button = QPushButton("Open Source In PixelForge")
        self.open_source_headless_button = QPushButton("Open Source Headless")
        self.remove_white_background_button = QPushButton("Remove White Background")
        self.remove_key_range_button = QPushButton("Remove Key Range")
        self.add_transparency_key_button = QPushButton("Add Picked Key")
        self.remove_transparency_key_button = QPushButton("Remove Key")
        self.apply_all_transparency_keys_button = QPushButton("Apply All Keys")
        self.remove_light_background_button = QPushButton("Remove Light BG")
        for btn in (
            self.open_blank_pixel_map_button,
            self.open_preview_pixel_editor_button,
            self.open_source_pixel_editor_button,
            self.open_source_headless_button,
            self.remove_white_background_button,
            self.remove_key_range_button,
            self.add_transparency_key_button,
            self.remove_transparency_key_button,
            self.apply_all_transparency_keys_button,
            self.remove_light_background_button,
        ):
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.transparency_color_swatch = QFrame()
        self.transparency_color_swatch.setFixedSize(28, 20)
        self.transparency_color_label = QLabel("#FFFFFFFF")
        self.transparency_key_combo = QComboBox()

        self.eyedropper_sample_size_combo = QComboBox()
        for sample_size in (1, 3, 5, 9):
            self.eyedropper_sample_size_combo.addItem(f"{sample_size} px", sample_size)
        self.eyedropper_sample_method_combo = QComboBox()
        self.eyedropper_sample_method_combo.addItem("Median", "median")
        self.eyedropper_sample_method_combo.addItem("Average", "average")

        self.transparency_tolerance_spin = QSpinBox()
        self.transparency_tolerance_spin.setRange(0, 441)
        self.transparency_tolerance_spin.setValue(30)
        self.transparency_tolerance_spin.setToolTip("RGB distance from the sampled color")

        self.light_brightness_spin = QSpinBox()
        self.light_brightness_spin.setRange(0, 255)
        self.light_brightness_spin.setValue(235)
        self.light_brightness_spin.setToolTip("Minimum brightness removed by Light BG")
        self.light_saturation_spin = QSpinBox()
        self.light_saturation_spin.setRange(0, 255)
        self.light_saturation_spin.setValue(28)
        self.light_saturation_spin.setToolTip("Maximum saturation removed by Light BG")

        pixel_tools_layout.addWidget(blank_size_widget, 0, 0)
        pixel_tools_layout.addWidget(self.open_blank_pixel_map_button, 0, 1)
        pixel_tools_layout.addWidget(self.open_preview_pixel_editor_button, 0, 2)
        pixel_tools_layout.addWidget(self.open_source_pixel_editor_button, 0, 3)
        pixel_tools_layout.addWidget(self.open_source_headless_button, 1, 0)
        pixel_tools_layout.addWidget(self.remove_white_background_button, 1, 1)

        self.transparency_key_section = CollapsibleSection("Transparency Key", expanded=False)
        transparency_layout = QGridLayout()
        transparency_layout.setContentsMargins(8, 6, 8, 6)
        transparency_layout.setHorizontalSpacing(8)
        transparency_layout.setVerticalSpacing(6)
        for column in range(4):
            transparency_layout.setColumnStretch(column, 1)

        picked_widget = QWidget()
        picked_row = QHBoxLayout(picked_widget)
        picked_row.setContentsMargins(0, 0, 0, 0)
        picked_row.setSpacing(4)
        picked_row.addWidget(QLabel("Picked"))
        picked_row.addWidget(self.transparency_color_swatch)
        picked_row.addWidget(self.transparency_color_label)
        picked_row.addStretch(1)

        sample_widget = QWidget()
        sample_row = QHBoxLayout(sample_widget)
        sample_row.setContentsMargins(0, 0, 0, 0)
        sample_row.setSpacing(4)
        sample_row.addWidget(QLabel("Sample"))
        sample_row.addWidget(self.eyedropper_sample_size_combo)
        sample_row.addWidget(self.eyedropper_sample_method_combo)

        tolerance_widget = QWidget()
        tolerance_row = QHBoxLayout(tolerance_widget)
        tolerance_row.setContentsMargins(0, 0, 0, 0)
        tolerance_row.setSpacing(4)
        tolerance_row.addWidget(QLabel("Tolerance"))
        tolerance_row.addWidget(self.transparency_tolerance_spin)
        tolerance_row.addStretch(1)

        key_picker_widget = QWidget()
        key_picker_row = QHBoxLayout(key_picker_widget)
        key_picker_row.setContentsMargins(0, 0, 0, 0)
        key_picker_row.setSpacing(4)
        key_picker_row.addWidget(QLabel("Keys"))
        key_picker_row.addWidget(self.transparency_key_combo, 1)

        key_actions_widget = QWidget()
        key_row = QHBoxLayout(key_actions_widget)
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.setSpacing(4)
        key_row.addWidget(self.add_transparency_key_button)
        key_row.addWidget(self.remove_transparency_key_button)

        light_widget = QWidget()
        light_row = QHBoxLayout(light_widget)
        light_row.setContentsMargins(0, 0, 0, 0)
        light_row.setSpacing(4)
        light_row.addWidget(QLabel("Light B"))
        light_row.addWidget(self.light_brightness_spin)
        light_row.addWidget(QLabel("Sat"))
        light_row.addWidget(self.light_saturation_spin)
        light_row.addStretch(1)

        transparency_layout.addWidget(picked_widget, 0, 0)
        transparency_layout.addWidget(sample_widget, 0, 1)
        transparency_layout.addWidget(tolerance_widget, 0, 2)
        transparency_layout.addWidget(key_picker_widget, 0, 3)
        transparency_layout.addWidget(key_actions_widget, 1, 0, 1, 2)
        transparency_layout.addWidget(self.remove_key_range_button, 1, 2)
        transparency_layout.addWidget(self.apply_all_transparency_keys_button, 1, 3)
        transparency_layout.addWidget(light_widget, 2, 0, 1, 2)
        transparency_layout.addWidget(self.remove_light_background_button, 2, 2)
        self.transparency_key_section.set_content_layout(transparency_layout)
        pixel_tools_layout.addWidget(self.transparency_key_section, 2, 0, 1, 4)
        self._refresh_transparency_key_ui()

        pixel_tools_row = QHBoxLayout()
        pixel_tools_row.addWidget(self._pixel_tools_group, 1)
        canvas_layout.addLayout(pixel_tools_row)

        palette_merged = QGroupBox("Palette")
        palette_merged.setMinimumHeight(40)
        palette_merged_layout = QVBoxLayout(palette_merged)
        palette_merged_layout.addWidget(self.palette_panel)
        palette_merged_layout.addWidget(self.persistent_palette)

        self.preview_panel.setMinimumHeight(40)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setHandleWidth(6)
        right_splitter.setChildrenCollapsible(False)
        right_splitter.addWidget(self.preview_panel)
        right_splitter.addWidget(palette_merged)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)
        right_splitter.setSizes([420, 280])

        self._canvas_group.setMinimumWidth(200)
        self._canvas_group.setMinimumHeight(100)

        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setHandleWidth(6)
        top_splitter.setChildrenCollapsible(False)
        top_splitter.addWidget(self._canvas_group)
        top_splitter.addWidget(right_splitter)
        top_splitter.setStretchFactor(0, 4)
        top_splitter.setStretchFactor(1, 1)
        top_splitter.setSizes([1060, 380])

        self._asset_group = QGroupBox("Saved Tiles And Assets")
        self._asset_group.setMinimumHeight(40)
        asset_layout = QVBoxLayout(self._asset_group)
        asset_layout.addWidget(self.asset_tray)

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.setHandleWidth(6)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(self._asset_group)
        main_splitter.setStretchFactor(0, 5)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([720, 200])

        central_layout.addWidget(main_splitter, 1)
        self.setCentralWidget(central)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_source_panel_widths()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_source_panel_widths()

    def _apply_source_panel_widths(self) -> None:
        w = self._canvas_group.width()
        if w < 80:
            return
        self._pixel_tools_group.setMaximumWidth(max(100, w - 8))
        bw = max(130, int((w - 64) / 4))
        self.open_blank_pixel_map_button.setMaximumWidth(bw)
        self.open_preview_pixel_editor_button.setMaximumWidth(bw)
        self.open_source_pixel_editor_button.setMaximumWidth(bw)
        self.open_source_headless_button.setMaximumWidth(bw)
        self.remove_white_background_button.setMaximumWidth(bw)
        self.remove_key_range_button.setMaximumWidth(bw)
        self.add_transparency_key_button.setMaximumWidth(bw)
        self.remove_transparency_key_button.setMaximumWidth(bw)
        self.apply_all_transparency_keys_button.setMaximumWidth(bw)
        self.remove_light_background_button.setMaximumWidth(bw)

    def _connect_signals(self) -> None:
        self.source_canvas.selections_changed.connect(self._on_selections_changed)
        self.source_canvas.status_changed.connect(self.statusBar().showMessage)
        self.source_canvas.color_picked.connect(self._on_eyedropper_color)
        self.preview_panel.color_picked.connect(self._on_eyedropper_color)
        self.preview_panel.settings_changed.connect(self._on_preview_settings_changed)
        self.preview_panel.save_requested.connect(self.save_preview_to_tray)
        self.preview_panel.load_reference_palette_requested.connect(self.load_reference_palette)
        self.preview_panel.clear_reference_palette_requested.connect(self.clear_reference_palette)
        self.palette_panel.derive_from_preview_requested.connect(self.derive_palette_from_preview)
        self.palette_panel.load_palette_requested.connect(self.load_palette)
        self.palette_panel.export_palette_requested.connect(self.export_palette)
        self.palette_panel.custom_color_requested.connect(self.add_custom_palette_color)
        self.palette_panel.color_remove_requested.connect(self.remove_palette_color)
        self.palette_panel.color_edit_requested.connect(self.edit_palette_color)
        self.palette_panel.sort_palette_requested.connect(self.organize_palette)
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
        self.open_source_headless_button.clicked.connect(self.open_source_headless_in_pixel_editor)
        self.remove_white_background_button.clicked.connect(self.remove_white_background)
        self.remove_key_range_button.clicked.connect(self.remove_selected_key_range)
        self.add_transparency_key_button.clicked.connect(self.add_picked_transparency_key)
        self.remove_transparency_key_button.clicked.connect(self.remove_selected_transparency_key)
        self.apply_all_transparency_keys_button.clicked.connect(self.apply_all_transparency_keys)
        self.remove_light_background_button.clicked.connect(self.remove_light_background)
        self.eyedropper_sample_size_combo.currentIndexChanged.connect(self._update_eyedropper_sampling)
        self.eyedropper_sample_method_combo.currentIndexChanged.connect(self._update_eyedropper_sampling)
        self._update_eyedropper_sampling()

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
        sample_mode = self.palette_panel.sample_mode()
        palette, debug = palette_from_image_with_debug(
            self.document.preview_image,
            max_colors=self.palette_panel.max_colors(),
            selection=sample_mode,
            settings=self.palette_panel.extraction_settings(),
        )
        self.document.palette = palette
        self.palette_panel.set_palette(palette)
        debug_quantize_source = (
            debug.quantize_source_image
            if debug.quantize_source_image is not None
            else self.document.preview_image
        )
        self.palette_panel.set_extraction_debug(
            self.document.preview_image,
            debug,
            quantize_to_palette(debug_quantize_source, palette),
        )
        self.statusBar().showMessage(
            f"Palette derived from preview ({sample_mode} sampling, {len(palette)} colors)"
        )

    def load_palette(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Palette From Image",
            "",
            "Images (*.png *.bmp *.gif *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        sample_mode = self.palette_panel.sample_mode()
        try:
            source_image = Image.open(path).convert("RGBA")
            palette, debug = palette_from_image_with_debug(
                source_image,
                max_colors=self.palette_panel.max_colors(),
                selection=sample_mode,
                settings=self.palette_panel.extraction_settings(),
            )
        except Exception as exc:  # pragma: no cover - GUI feedback
            QMessageBox.critical(self, "Palette load failed", str(exc))
            return
        self.document.palette = palette
        self.palette_panel.set_palette(palette)
        debug_quantize_source = (
            debug.quantize_source_image
            if debug.quantize_source_image is not None
            else source_image
        )
        self.palette_panel.set_extraction_debug(
            source_image,
            debug,
            quantize_to_palette(debug_quantize_source, palette),
        )
        self.statusBar().showMessage(
            f"Loaded palette from {Path(path).name} ({sample_mode} sampling, {len(palette)} colors)"
        )

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

    def load_reference_palette(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Reference Palette",
            "",
            "Palette Sources (*.png *.bmp *.gif *.jpg *.jpeg *.webp *.txt *.hex *.pal)",
        )
        if not path:
            return
        try:
            palette = load_palette_from_source(path, max_colors=256)
        except Exception as exc:  # pragma: no cover - GUI feedback
            QMessageBox.critical(self, "Reference palette load failed", str(exc))
            return

        self.preview_panel.set_reference_palette(palette, Path(path).name)
        self.statusBar().showMessage(
            f"Loaded reference palette from {Path(path).name} ({len(palette)} colors)"
        )

    def clear_reference_palette(self) -> None:
        self.preview_panel.set_reference_palette([], None)
        self.statusBar().showMessage("Cleared reference palette")

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

    def remove_palette_color(self, index: int) -> None:
        if not self.document.palette or not (0 <= index < len(self.document.palette)):
            return
        self.document.palette = [c for i, c in enumerate(self.document.palette) if i != index]
        self.palette_panel.set_palette(self.document.palette)
        self.statusBar().showMessage(f"Removed palette color at index {index}")

    def edit_palette_color(self, index: int) -> None:
        if not self.document.palette or not (0 <= index < len(self.document.palette)):
            return
        initial_color = QColor(*self.document.palette[index])
        color = QColorDialog.getColor(initial_color, self, "Edit Palette Color")
        if not color.isValid():
            return
        rgba = (color.red(), color.green(), color.blue(), color.alpha())
        self.document.palette = list(self.document.palette)
        self.document.palette[index] = rgba
        self.palette_panel.set_palette(self.document.palette)
        self.statusBar().showMessage(f"Updated palette color at index {index}")

    def organize_palette(self, mode: str) -> None:
        if not self.document.palette:
            self.statusBar().showMessage("No palette to organize")
            return
        self.document.palette = sort_palette(self.document.palette, mode)
        self.palette_panel.set_palette(self.document.palette)
        self.statusBar().showMessage(f"Palette organized by {mode}")

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

    def remove_white_background(self) -> None:
        if self.document.source_image is None:
            self.statusBar().showMessage("No source image loaded")
            return

        updated, replaced = replace_color_with_transparent(
            self.document.source_image,
            (255, 255, 255, 255),
        )
        if replaced == 0:
            self.statusBar().showMessage("No pure white background pixels found")
            return

        self.document.source_image = updated
        self.source_canvas.set_image(self.document.source_image)
        self.source_canvas.set_selections(self.document.selections)
        self._refresh_preview()
        self.statusBar().showMessage(
            f"Removed {replaced} pure white pixel{'s' if replaced != 1 else ''} from source image"
        )

    def remove_selected_key_range(self) -> None:
        color = self._current_transparency_key()
        if color is None:
            self.statusBar().showMessage("No transparency key selected")
            return
        self._remove_similar_colors([color])

    def apply_all_transparency_keys(self) -> None:
        if not self._transparency_keys:
            self.statusBar().showMessage("No transparency keys to apply")
            return
        self._remove_similar_colors(self._transparency_keys)

    def remove_light_background(self) -> None:
        if self.document.source_image is None:
            self.statusBar().showMessage("No source image loaded")
            return

        updated, replaced = replace_light_background_with_transparent(
            self.document.source_image,
            self.light_brightness_spin.value(),
            self.light_saturation_spin.value(),
        )
        if replaced == 0:
            self.statusBar().showMessage("No light background pixels matched")
            return

        self._replace_source_image(updated)
        self.statusBar().showMessage(
            f"Removed {replaced} light background pixel{'s' if replaced != 1 else ''}"
        )

    def add_picked_transparency_key(self) -> None:
        color = self._selected_transparency_color
        if color[3] == 0:
            self.statusBar().showMessage("Transparent pixels cannot be used as a key")
            return
        if color not in self._transparency_keys:
            self._transparency_keys.append(color)
        self._refresh_transparency_key_ui(select=color)
        self.statusBar().showMessage(f"Added transparency key {color_tooltip(color)}")

    def remove_selected_transparency_key(self) -> None:
        color = self._current_transparency_key()
        if color is None:
            return
        self._transparency_keys = [item for item in self._transparency_keys if item != color]
        self._refresh_transparency_key_ui()
        self.statusBar().showMessage(f"Removed transparency key {color_tooltip(color)}")

    def _remove_similar_colors(self, colors: list[tuple[int, int, int, int]]) -> None:
        if self.document.source_image is None:
            self.statusBar().showMessage("No source image loaded")
            return

        updated = self.document.source_image
        total_replaced = 0
        tolerance = self.transparency_tolerance_spin.value()
        for color in colors:
            updated, replaced = replace_similar_color_with_transparent(updated, color, tolerance)
            total_replaced += replaced

        if total_replaced == 0:
            self.statusBar().showMessage("No pixels matched the transparency key range")
            return

        self._replace_source_image(updated)
        key_word = "key" if len(colors) == 1 else "keys"
        self.statusBar().showMessage(
            f"Removed {total_replaced} pixel{'s' if total_replaced != 1 else ''} using {len(colors)} {key_word}"
        )

    def _replace_source_image(self, image) -> None:
        self.document.source_image = image
        self.source_canvas.set_image(self.document.source_image)
        self.source_canvas.set_selections(self.document.selections)
        self._refresh_preview()

    def _current_transparency_key(self) -> tuple[int, int, int, int] | None:
        index = self.transparency_key_combo.currentIndex()
        if 0 <= index < len(self._transparency_keys):
            return self._transparency_keys[index]
        return None

    def _refresh_transparency_key_ui(self, select: tuple[int, int, int, int] | None = None) -> None:
        self._update_transparency_color_swatch()
        self.transparency_key_combo.blockSignals(True)
        self.transparency_key_combo.clear()
        for color in self._transparency_keys:
            self.transparency_key_combo.addItem(color_tooltip(color))
        if select in self._transparency_keys:
            self.transparency_key_combo.setCurrentIndex(self._transparency_keys.index(select))
        self.transparency_key_combo.blockSignals(False)

    def _update_transparency_color_swatch(self) -> None:
        r, g, b, a = self._selected_transparency_color
        self.transparency_color_swatch.setStyleSheet(
            f"background: rgba({r}, {g}, {b}, {a}); border: 1px solid #555;"
        )
        self.transparency_color_label.setText(color_tooltip(self._selected_transparency_color))

    def _update_eyedropper_sampling(self) -> None:
        sample_size = int(self.eyedropper_sample_size_combo.currentData() or 1)
        method = str(self.eyedropper_sample_method_combo.currentData() or "median")
        self.source_canvas.set_eyedropper_sampling(sample_size, method)
        self.preview_panel.set_eyedropper_sampling(sample_size, method)

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

    def open_source_headless_in_pixel_editor(self) -> None:
        if self.document.source_image is None:
            self.statusBar().showMessage("No source image loaded")
            return
        name = Path(self.document.source_path).stem if self.document.source_path else "source"
        document = PixelDocument(
            image=self.document.source_image.copy(),
            name=name,
            palette=list(self.document.palette),
        )
        self._open_pixel_editor(document, headless=True)

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

    def _open_pixel_editor(self, document: PixelDocument, *, headless: bool = False) -> None:
        window = PixelEditorWindow(document, self, headless=headless)
        window.asset_save_requested.connect(self._on_pixel_editor_asset_saved)
        window.destroyed.connect(lambda *_args, target=window: self._remove_pixel_window(target))
        self._pixel_windows.append(window)
        window.show()
        if headless:
            self.statusBar().showMessage(f"Opened PixelForge headless for {document.name}")
        else:
            self.statusBar().showMessage(f"Opened PixelForge for {document.name}")

    def _remove_pixel_window(self, target: PixelEditorWindow) -> None:
        self._pixel_windows = [window for window in self._pixel_windows if window is not target]

    def open_animation_editor(self) -> None:
        window = AnimationEditorWindow(self, initial_palette=list(self.document.palette))
        window.destroyed.connect(lambda *_args, target=window: self._remove_tool_window(target))
        self._tool_windows.append(window)
        window.show()
        self.statusBar().showMessage("Opened animation editor")

    def open_reference_mapper(self) -> None:
        window = ReferenceMapperWindow(self, initial_palette=list(self.document.palette))
        window.destroyed.connect(lambda *_args, target=window: self._remove_tool_window(target))
        self._tool_windows.append(window)
        window.show()
        self.statusBar().showMessage("Opened reference grid mapper")

    def open_tile_layout(self) -> None:
        window = TileLayoutWindow(None, initial_palette=list(self.document.palette))
        window.destroyed.connect(lambda *_args, target=window: self._remove_tool_window(target))
        self._tool_windows.append(window)
        window.show()
        self.statusBar().showMessage("Opened tile layout")

    def open_tileset_processor(self) -> None:
        window = TilesetProcessorWindow(self)
        window.destroyed.connect(lambda *_args, target=window: self._remove_tool_window(target))
        self._tool_windows.append(window)
        window.show()
        self.statusBar().showMessage("Opened tileset processor")

    def open_tileset_template(self) -> None:
        # Independent, non-modal window. Keep a strong ref in
        # `_tool_windows` so it isn't GC'd while open, and drop it on
        # destroy so multiple instances are allowed.
        window = TilesetTemplateWindow(self)
        window.destroyed.connect(lambda *_args, target=window: self._remove_tool_window(target))
        self._tool_windows.append(window)
        window.show()
        self.statusBar().showMessage("Opened tileset template generator")

    def open_texture_generator(self) -> None:
        # Same lifecycle pattern as the other tool windows.
        window = TextureGeneratorWindow(self)
        window.destroyed.connect(lambda *_args, target=window: self._remove_tool_window(target))
        self._tool_windows.append(window)
        window.show()
        self.statusBar().showMessage("Opened texture generator")

    def _drop_rect_selection(self) -> None:
        if self.document.source_image is None:
            self.statusBar().showMessage("Load an image first")
            return
        w = self.rect_w_spin.value()
        h = self.rect_h_spin.value()
        self.source_canvas.drop_rect_selection(w, h)
        self.statusBar().showMessage(f"Dropped {w}x{h} rectangle — drag to position, right-click to delete")

    def _remove_tool_window(self, target: QMainWindow) -> None:
        self._tool_windows = [window for window in self._tool_windows if window is not target]

    def _toggle_eyedropper(self) -> None:
        self._set_eyedropper(not self._eyedropper_active)

    def _cancel_eyedropper(self) -> None:
        if self._eyedropper_active:
            self._set_eyedropper(False)

    def _set_eyedropper(self, active: bool) -> None:
        self._eyedropper_active = active
        self._eyedropper_action.setChecked(active)
        self.source_canvas.set_eyedropper(active)
        self.preview_panel.set_eyedropper(active)
        if active:
            self.statusBar().showMessage("Eyedropper active — click a pixel to pick its color (Escape to cancel)")
        else:
            self.statusBar().showMessage("Eyedropper deactivated")

    def _on_eyedropper_color(self, rgba: tuple) -> None:
        color = (int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3]))
        self._selected_transparency_color = color
        self._update_transparency_color_swatch()
        is_new = self.persistent_palette.add_color(color)

        self.document.palette = add_color_to_palette(
            self.document.palette,
            color,
            max_colors=self.palette_panel.max_colors(),
        )
        self.palette_panel.set_palette(self.document.palette)

        for win in self._pixel_windows:
            win.add_external_color(color)

        hex_str = color_tooltip(color)
        if is_new:
            self.statusBar().showMessage(f"Picked {hex_str}")
        else:
            self.statusBar().showMessage(f"Already in palette: {hex_str}")

    def _on_pixel_editor_asset_saved(self, name: str, image) -> None:
        self._add_asset(name, image.copy())
        self.statusBar().showMessage(f"Saved PixelForge output as {name}")

    def _add_asset(self, name: str, image, refresh: bool = True) -> None:
        self.document.assets.append(SavedAsset(name=name, image=image))
        if refresh:
            self.asset_tray.set_assets(self.document.assets)
