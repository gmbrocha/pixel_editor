from __future__ import annotations

from PySide6.QtCore import QEvent, QObject


class TooltipEventFilter(QObject):
    """Suppress hover tooltips throughout the application."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            return True
        return super().eventFilter(watched, event)
