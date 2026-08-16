import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QWidget

from src.ui.tooltip_filter import TooltipEventFilter


class TooltipTrackingWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.tooltip_event_count = 0

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            self.tooltip_event_count += 1
        return super().event(event)


def test_application_filter_suppresses_hover_tooltips() -> None:
    application = QApplication.instance() or QApplication([])
    tooltip_filter = TooltipEventFilter(application)
    application.installEventFilter(tooltip_filter)
    widget = TooltipTrackingWidget()

    tooltip_event = QHelpEvent(QEvent.Type.ToolTip, QPoint(1, 1), QPoint(1, 1))
    QApplication.sendEvent(widget, tooltip_event)

    assert widget.tooltip_event_count == 0
    application.removeEventFilter(tooltip_filter)
