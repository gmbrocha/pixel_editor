from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.pixel_document import PixelDocument


class _LayerListWidget(QListWidget):
    """List widget that starts inline rename when the already-selected row is
    clicked again on its label area. Click on the checkbox toggles visibility
    only and never starts a rename."""

    rename_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        item = self.itemAt(event.position().toPoint())
        if item is not None and item is self.currentItem():
            # Don't trigger rename when the click lands on the checkbox area
            # at the very left edge of the row.
            rect = self.visualItemRect(item)
            if event.position().x() - rect.x() > 24:
                self.rename_requested.emit(self.row(item))
        super().mousePressEvent(event)


class LayerPanel(QGroupBox):
    """Panel listing the document's layers in stack order (top of the list =
    visually on top of the canvas).

    Emits `layers_changed` whenever any structural or visibility change is
    made so the host window can refresh the canvas.
    """

    layers_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Layers", parent)
        self._document: PixelDocument | None = None
        self._suppress_signals = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._list = _LayerListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setUniformItemSizes(True)
        self._list.setToolTip(
            "Stack order: top = renders on top.\n"
            "Click the checkbox to toggle visibility.\n"
            "Click an already-selected layer (or press F2) to rename inline."
        )
        layout.addWidget(self._list, 1)

        button_row = QHBoxLayout()
        button_row.setSpacing(2)
        self._add_button = QPushButton("+")
        self._add_button.setToolTip("Add a new transparent layer above the active layer")
        self._delete_button = QPushButton("-")
        self._delete_button.setToolTip("Delete the active layer (cannot delete the last layer)")
        self._up_button = QPushButton("Up")
        self._up_button.setToolTip("Move the active layer up in the stack (toward the top)")
        self._down_button = QPushButton("Down")
        self._down_button.setToolTip("Move the active layer down in the stack (toward the bottom)")
        button_row.addWidget(self._add_button)
        button_row.addWidget(self._delete_button)
        button_row.addWidget(self._up_button)
        button_row.addWidget(self._down_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self._list.currentRowChanged.connect(self._on_current_row_changed)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.rename_requested.connect(self._begin_rename)
        self._add_button.clicked.connect(self._add_layer)
        self._delete_button.clicked.connect(self._delete_active)
        self._up_button.clicked.connect(self._move_active_up)
        self._down_button.clicked.connect(self._move_active_down)

    # --- Public API ---------------------------------------------------------

    def set_document(self, document: PixelDocument) -> None:
        self._document = document
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the list widget from the current document state."""
        if self._document is None:
            return
        self._suppress_signals = True
        try:
            self._list.clear()
            # Display top-of-stack first (= last item in the layers list).
            for layer in reversed(self._document.layers):
                item = QListWidgetItem(layer.name)
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEditable
                )
                item.setCheckState(
                    Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked
                )
                self._list.addItem(item)
            self._list.setCurrentRow(self._display_row_for(self._document.active_layer_index))
        finally:
            self._suppress_signals = False
        self._update_button_states()

    # --- Internal helpers ---------------------------------------------------

    def _display_row_for(self, doc_index: int) -> int:
        """Convert a document layer index (bottom = 0) to a list row index
        (top of stack = 0)."""
        if self._document is None:
            return 0
        return len(self._document.layers) - 1 - doc_index

    def _doc_index_for_row(self, row: int) -> int:
        if self._document is None:
            return 0
        return len(self._document.layers) - 1 - row

    def _update_button_states(self) -> None:
        if self._document is None:
            self._delete_button.setEnabled(False)
            self._up_button.setEnabled(False)
            self._down_button.setEnabled(False)
            return
        layer_count = len(self._document.layers)
        active = self._document.active_layer_index
        self._delete_button.setEnabled(layer_count > 1)
        # "Up" = move toward top of stack = larger doc index. Disabled if
        # already at the top.
        self._up_button.setEnabled(active < layer_count - 1)
        self._down_button.setEnabled(active > 0)

    # --- Event handlers -----------------------------------------------------

    def _on_current_row_changed(self, row: int) -> None:
        if self._suppress_signals or self._document is None or row < 0:
            return
        doc_index = self._doc_index_for_row(row)
        if doc_index == self._document.active_layer_index:
            return
        if self._document.set_active_layer(doc_index):
            self._update_button_states()
            self.layers_changed.emit()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._suppress_signals or self._document is None:
            return
        row = self._list.row(item)
        doc_index = self._doc_index_for_row(row)
        layer = self._document.layers[doc_index]

        new_visible = item.checkState() == Qt.CheckState.Checked
        new_name = item.text().strip()

        changed = False
        if new_visible != layer.visible:
            self._document.set_layer_visibility(doc_index, new_visible)
            changed = True
        if new_name and new_name != layer.name:
            self._document.rename_layer(doc_index, new_name)
            changed = True
        if not new_name:
            # Reject empty names by reverting the displayed text.
            self._suppress_signals = True
            try:
                item.setText(layer.name)
            finally:
                self._suppress_signals = False
        if changed:
            self.layers_changed.emit()

    def _begin_rename(self, row: int) -> None:
        item = self._list.item(row)
        if item is not None:
            self._list.editItem(item)

    def _add_layer(self) -> None:
        if self._document is None:
            return
        self._document.add_layer()
        self.refresh()
        self.layers_changed.emit()

    def _delete_active(self) -> None:
        if self._document is None:
            return
        if self._document.delete_layer(self._document.active_layer_index):
            self.refresh()
            self.layers_changed.emit()

    def _move_active_up(self) -> None:
        # "Up" in the panel = toward top of stack = +1 in doc index.
        if self._document is None:
            return
        new_index = self._document.move_layer(self._document.active_layer_index, +1)
        if new_index is not None:
            self.refresh()
            self.layers_changed.emit()

    def _move_active_down(self) -> None:
        if self._document is None:
            return
        new_index = self._document.move_layer(self._document.active_layer_index, -1)
        if new_index is not None:
            self.refresh()
            self.layers_changed.emit()
