from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.assets import SavedAsset
from src.core.qt_image import pil_image_to_qpixmap


class AssetTray(QWidget):
    import_requested = Signal()
    export_requested = Signal()
    clear_requested = Signal()
    remove_selected_requested = Signal()
    asset_open_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setFlow(QListWidget.Flow.LeftToRight)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setWrapping(False)
        self.list_widget.setSpacing(8)
        self.list_widget.setIconSize(QSize(64, 64))
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.setMinimumHeight(140)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)

        import_button = QPushButton("Add From File")
        import_button.clicked.connect(self.import_requested.emit)

        export_button = QPushButton("Export Tilesheet")
        export_button.clicked.connect(self.export_requested.emit)

        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self.remove_selected_requested.emit)

        clear_button = QPushButton("Clear All")
        clear_button.clicked.connect(self.clear_requested.emit)

        header = QHBoxLayout()
        header.addWidget(import_button)
        header.addWidget(export_button)
        header.addWidget(remove_button)
        header.addWidget(clear_button)
        header.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.list_widget)

    def set_assets(self, assets: list[SavedAsset]) -> None:
        self.list_widget.clear()
        for asset in assets:
            item = QListWidgetItem(asset.name)
            item.setData(Qt.ItemDataRole.UserRole, asset.id)
            item.setIcon(QIcon(pil_image_to_qpixmap(asset.image)))
            self.list_widget.addItem(item)

    def selected_asset_ids(self) -> list[str]:
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.list_widget.selectedItems()
        ]

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        asset_id = item.data(Qt.ItemDataRole.UserRole)
        if asset_id:
            self.asset_open_requested.emit(asset_id)
