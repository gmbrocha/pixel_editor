from __future__ import annotations

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow
from src.ui.tooltip_filter import TooltipEventFilter


def main() -> int:
    application = QApplication([])
    application.setApplicationName("PixelForge")
    tooltip_filter = TooltipEventFilter(application)
    application.installEventFilter(tooltip_filter)
    window = MainWindow()
    window.show()
    return application.exec()
