from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
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
    visibility_toggle_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        item = self.itemAt(event.position().toPoint())
        if item is not None:
            rect = self.visualItemRect(item)
            if event.position().x() - rect.x() <= 24:
                # Visibility is deliberately independent from the editing
                # target: clicking a checkbox must never activate that row.
                self.visibility_toggle_requested.emit(self.row(item))
                event.accept()
                return
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
    selection_transfer_requested = Signal(int, bool)
    status_message = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Layers", parent)
        self._document: PixelDocument | None = None
        self._suppress_signals = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        active_heading = QLabel("EDITING LAYER")
        active_heading.setStyleSheet("font-size: 10px; font-weight: 700; color: #8ecdf2;")
        layout.addWidget(active_heading)
        self.active_layer_label = QLabel()
        self.active_layer_label.setObjectName("activeLayerLabel")
        self.active_layer_label.setMinimumHeight(34)
        self.active_layer_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.active_layer_label)
        self.layer_help_label = QLabel(
            "Highlighted row = edit target. Checkbox = visibility only."
        )
        self.layer_help_label.setWordWrap(True)
        self.layer_help_label.setStyleSheet("color: #aeb8c2; font-size: 10px;")
        layout.addWidget(self.layer_help_label)

        self._list = _LayerListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setUniformItemSizes(True)
        self._list.setToolTip(
            "Stack order: top = renders on top.\n"
            "Click the checkbox to toggle visibility.\n"
            "Click the row to make it the editing layer; this clears any old selection.\n"
            "Click an already-selected layer (or press F2) to rename inline."
        )
        layout.addWidget(self._list, 1)

        button_row = QGridLayout()
        button_row.setSpacing(2)
        self._add_button = QPushButton("New Layer")
        self._add_button.setToolTip("Add a new transparent layer above the active layer")
        self._delete_button = QPushButton("Delete Active")
        self._delete_button.setToolTip("Confirm and delete the explicitly named editing layer")
        self._up_button = QPushButton("Raise")
        self._up_button.setToolTip("Move the active layer up in the stack (toward the top)")
        self._down_button = QPushButton("Lower")
        self._down_button.setToolTip("Move the active layer down in the stack (toward the bottom)")
        button_row.addWidget(self._add_button, 0, 0)
        button_row.addWidget(self._delete_button, 0, 1)
        button_row.addWidget(self._up_button, 1, 0)
        button_row.addWidget(self._down_button, 1, 1)
        button_row.setColumnStretch(0, 1)
        button_row.setColumnStretch(1, 1)
        layout.addLayout(button_row)

        transfer_heading = QLabel("SEND CURRENT SELECTION TO EXISTING LAYER")
        transfer_heading.setStyleSheet("font-size: 10px; font-weight: 700; color: #8ecdf2;")
        layout.addWidget(transfer_heading)
        transfer_row = QHBoxLayout()
        transfer_row.setSpacing(3)
        self.selection_target_combo = QComboBox()
        self.selection_target_combo.setToolTip(
            "Destination layer. The current editing layer remains the source until you click Move or Copy."
        )
        self.move_selection_button = QPushButton("Move")
        self.move_selection_button.setToolTip(
            "Move selected non-transparent pixels from the editing layer to this existing layer"
        )
        self.copy_selection_button = QPushButton("Copy")
        self.copy_selection_button.setToolTip(
            "Copy selected non-transparent pixels from the editing layer to this existing layer"
        )
        transfer_row.addWidget(self.selection_target_combo, 1)
        transfer_row.addWidget(self.move_selection_button)
        transfer_row.addWidget(self.copy_selection_button)
        layout.addLayout(transfer_row)
        self.selection_transfer_summary = QLabel("Select pixels to enable layer transfer.")
        self.selection_transfer_summary.setWordWrap(True)
        self.selection_transfer_summary.setStyleSheet("color: #aeb8c2; font-size: 10px;")
        layout.addWidget(self.selection_transfer_summary)

        self._selection_count = 0

        self._list.currentRowChanged.connect(self._on_current_row_changed)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.rename_requested.connect(self._begin_rename)
        self._list.visibility_toggle_requested.connect(self._toggle_visibility)
        self._add_button.clicked.connect(self._add_layer)
        self._delete_button.clicked.connect(self._delete_active)
        self._up_button.clicked.connect(self._move_active_up)
        self._down_button.clicked.connect(self._move_active_down)
        self.move_selection_button.clicked.connect(lambda: self._request_selection_transfer(True))
        self.copy_selection_button.clicked.connect(lambda: self._request_selection_transfer(False))

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
            active_display_row = self._display_row_for(self._document.active_layer_index)
            for display_row, layer in enumerate(reversed(self._document.layers)):
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
                item.setToolTip(
                    f"{'ACTIVE EDITING LAYER' if display_row == active_display_row else 'Click row to edit'}: "
                    f"{layer.name}\nVisibility: {'shown' if layer.visible else 'hidden'}"
                )
                if display_row == active_display_row:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setBackground(QBrush(QColor("#245777")))
                    item.setForeground(QBrush(QColor("#ffffff")))
                self._list.addItem(item)
            self._list.setCurrentRow(active_display_row)
        finally:
            self._suppress_signals = False
        self._refresh_active_layer_banner()
        self._refresh_transfer_targets()
        self._update_button_states()

    def set_selection_count(self, count: int) -> None:
        self._selection_count = max(0, int(count))
        self._update_transfer_state()

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
        self._delete_button.setText("Delete Active")
        self._delete_button.setToolTip(
            f"Delete editing layer '{self._document.active_layer.name}' after confirmation"
        )

    def _refresh_active_layer_banner(self) -> None:
        if self._document is None:
            self.active_layer_label.setText("No document")
            return
        layer = self._document.active_layer
        visibility = "VISIBLE" if layer.visible else "HIDDEN - edits will not be visible"
        self.active_layer_label.setText(f"  {layer.name}   |   {visibility}")
        if layer.visible:
            self.active_layer_label.setStyleSheet(
                "QLabel { background: #16384d; color: white; border: 2px solid #4fb3e8; "
                "border-radius: 4px; padding: 5px; font-weight: 700; }"
            )
        else:
            self.active_layer_label.setStyleSheet(
                "QLabel { background: #4b2d16; color: #ffe0a3; border: 2px solid #e6a23c; "
                "border-radius: 4px; padding: 5px; font-weight: 700; }"
            )

    def _refresh_transfer_targets(self) -> None:
        if self._document is None:
            return
        previous_target = self.selection_target_combo.currentData()
        blocked = self.selection_target_combo.blockSignals(True)
        self.selection_target_combo.clear()
        for doc_index in range(len(self._document.layers) - 1, -1, -1):
            if doc_index == self._document.active_layer_index:
                continue
            layer = self._document.layers[doc_index]
            self.selection_target_combo.addItem(layer.name, doc_index)
        if previous_target is not None:
            previous_row = self.selection_target_combo.findData(previous_target)
            if previous_row >= 0:
                self.selection_target_combo.setCurrentIndex(previous_row)
        self.selection_target_combo.blockSignals(blocked)
        self._update_transfer_state()

    def _update_transfer_state(self) -> None:
        has_target = self.selection_target_combo.count() > 0
        enabled = self._selection_count > 0 and has_target
        self.selection_target_combo.setEnabled(has_target)
        self.move_selection_button.setEnabled(enabled)
        self.copy_selection_button.setEnabled(enabled)
        if not has_target:
            self.selection_transfer_summary.setText("Create another layer to enable transfer.")
        elif self._selection_count == 0:
            self.selection_transfer_summary.setText("Select pixels to enable layer transfer.")
        else:
            source = self._document.active_layer.name if self._document is not None else "active layer"
            self.selection_transfer_summary.setText(
                f"{self._selection_count} selected from '{source}'. Choose the destination above."
            )

    # --- Event handlers -----------------------------------------------------

    def _on_current_row_changed(self, row: int) -> None:
        if self._suppress_signals or self._document is None or row < 0:
            return
        doc_index = self._doc_index_for_row(row)
        if doc_index == self._document.active_layer_index:
            return
        had_selection = bool(self._document.selected_points())
        if self._document.set_active_layer(doc_index):
            self._selection_count = 0
            self.refresh()
            self._update_button_states()
            self.layers_changed.emit()
            suffix = " Previous selection cleared." if had_selection else ""
            self.status_message.emit(
                f"Editing layer: '{self._document.active_layer.name}'.{suffix}"
            )

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._suppress_signals or self._document is None:
            return
        row = self._list.row(item)
        doc_index = self._doc_index_for_row(row)
        layer = self._document.layers[doc_index]

        new_visible = item.checkState() == Qt.CheckState.Checked
        new_name = item.text().strip()

        changed = False
        visibility_changed = False
        renamed = False
        if new_visible != layer.visible:
            self._document.set_layer_visibility(doc_index, new_visible)
            changed = True
            visibility_changed = True
        if new_name and new_name != layer.name:
            self._document.rename_layer(doc_index, new_name)
            changed = True
            renamed = True
        if not new_name:
            # Reject empty names by reverting the displayed text.
            self._suppress_signals = True
            try:
                item.setText(layer.name)
            finally:
                self._suppress_signals = False
        if changed:
            self._refresh_active_layer_banner()
            self.layers_changed.emit()
            if visibility_changed:
                self.status_message.emit(
                    f"Layer '{layer.name}' is now {'visible' if layer.visible else 'hidden'}"
                )
            elif renamed:
                self.status_message.emit(f"Renamed editing layer to '{layer.name}'")

    def _toggle_visibility(self, row: int) -> None:
        if self._document is None or row < 0:
            return
        item = self._list.item(row)
        if item is None:
            return
        doc_index = self._doc_index_for_row(row)
        layer = self._document.layers[doc_index]
        new_visible = not layer.visible
        self._document.set_layer_visibility(doc_index, new_visible)
        self._suppress_signals = True
        try:
            item.setCheckState(
                Qt.CheckState.Checked if new_visible else Qt.CheckState.Unchecked
            )
            item.setToolTip(
                f"{'ACTIVE EDITING LAYER' if doc_index == self._document.active_layer_index else 'Click row to edit'}: "
                f"{layer.name}\nVisibility: {'shown' if new_visible else 'hidden'}"
            )
        finally:
            self._suppress_signals = False
        self._refresh_active_layer_banner()
        self.layers_changed.emit()
        self.status_message.emit(
            f"Layer '{layer.name}' is now {'visible' if new_visible else 'hidden'}; "
            f"editing layer remains '{self._document.active_layer.name}'."
        )

    def _begin_rename(self, row: int) -> None:
        item = self._list.item(row)
        if item is not None:
            self._list.editItem(item)

    def _add_layer(self) -> None:
        if self._document is None:
            return
        self._document.add_layer()
        self._selection_count = 0
        self.refresh()
        self.layers_changed.emit()
        self.status_message.emit(f"Created and activated layer '{self._document.active_layer.name}'")

    def _delete_active(self) -> None:
        if self._document is None:
            return
        index = self._document.active_layer_index
        layer_name = self._document.active_layer.name
        answer = QMessageBox.question(
            self,
            "Delete active layer?",
            f"Delete the active editing layer '{layer_name}'?\n\n"
            "Its pixels and undo history will be removed. This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self._document.delete_layer(index):
            self._selection_count = 0
            self.refresh()
            self.layers_changed.emit()
            self.status_message.emit(
                f"Deleted layer '{layer_name}'. Now editing '{self._document.active_layer.name}'."
            )

    def _move_active_up(self) -> None:
        # "Up" in the panel = toward top of stack = +1 in doc index.
        if self._document is None:
            return
        new_index = self._document.move_layer(self._document.active_layer_index, +1)
        if new_index is not None:
            self.refresh()
            self.layers_changed.emit()
            self.status_message.emit(f"Raised layer '{self._document.active_layer.name}'")

    def _move_active_down(self) -> None:
        if self._document is None:
            return
        new_index = self._document.move_layer(self._document.active_layer_index, -1)
        if new_index is not None:
            self.refresh()
            self.layers_changed.emit()
            self.status_message.emit(f"Lowered layer '{self._document.active_layer.name}'")

    def _request_selection_transfer(self, move: bool) -> None:
        target_index = self.selection_target_combo.currentData()
        if target_index is None or self._selection_count <= 0:
            return
        self.selection_transfer_requested.emit(int(target_index), move)
