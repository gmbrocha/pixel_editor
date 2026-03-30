from __future__ import annotations

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def main() -> int:
    application = QApplication([])
    application.setApplicationName("Pixels Tile Editor")
    window = MainWindow()
    window.show()
    return application.exec()
