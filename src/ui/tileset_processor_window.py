from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from tileset_processor import detect_grid, process_tileset


class _WorkerSignals(QObject):
    progress = Signal(int, int)
    finished = Signal(int)
    error = Signal(str)


class TilesetProcessorWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tileset Grid Remover")
        self.resize(720, 560)
        self._files: list[str] = []

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        # --- File list ---
        file_group = QGroupBox("Input Files")
        file_layout = QHBoxLayout(file_group)
        self._file_list = QListWidget()
        self._file_list.setMinimumHeight(120)
        file_layout.addWidget(self._file_list, 1)

        btn_col = QVBoxLayout()
        add_btn = QPushButton("Add Files")
        add_btn.clicked.connect(self._add_files)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._clear_all)
        btn_col.addWidget(add_btn)
        btn_col.addWidget(remove_btn)
        btn_col.addWidget(clear_btn)
        btn_col.addStretch(1)
        file_layout.addLayout(btn_col)
        layout.addWidget(file_group)

        # --- Output ---
        out_group = QGroupBox("Output")
        out_layout = QHBoxLayout(out_group)
        self._out_label = QLabel("(not set)")
        self._out_label.setMinimumWidth(200)
        out_layout.addWidget(self._out_label, 1)
        browse_btn = QPushButton("Save As")
        browse_btn.clicked.connect(self._browse_output)
        open_btn = QPushButton("Open Folder")
        open_btn.clicked.connect(self._open_output)
        out_layout.addWidget(browse_btn)
        out_layout.addWidget(open_btn)
        layout.addWidget(out_group)

        # --- Settings ---
        settings_group = QGroupBox("Settings")
        settings_inner = QVBoxLayout(settings_group)

        self._spins: dict[str, QSpinBox] = {}
        fields = [
            ("Grid", 1, 100, 10),
            ("Top Border", 0, 500, 5),
            ("Bottom Border", 0, 500, 5),
            ("Left Border", 0, 500, 5),
            ("Right Border", 0, 500, 5),
            ("Inside Border", 0, 500, 5),
            ("Trim", 0, 50, 1),
            ("Max Colors", 0, 256, 32),
            ("Joint Thresh", 0, 100, 30),
            ("Joint Darken %", 0, 100, 20),
            ("BG Cutoff", 0, 255, 0),
            ("BG Min Area", 0, 10000, 50),
        ]

        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        row3 = QHBoxLayout()
        rows = [row1, row2, row3]

        for i, (label, lo, hi, default) in enumerate(fields):
            spin = QSpinBox()
            spin.setRange(lo, hi)
            spin.setValue(default)
            spin.setMinimumWidth(55)
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            self._spins[label] = spin
            pair = QHBoxLayout()
            pair.setSpacing(4)
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            pair.addWidget(lbl)
            pair.addWidget(spin)
            rows[i // 4].addLayout(pair)

        for r in rows:
            r.addStretch(1)

        hint = QLabel("(0 = disabled for Max Colors, Joint, and BG fields)")
        hint.setStyleSheet("color: #888;")

        settings_inner.addLayout(row1)
        settings_inner.addLayout(row2)
        settings_inner.addLayout(row3)

        settings_bottom = QHBoxLayout()
        settings_bottom.addWidget(hint, 1)
        export_btn = QPushButton("Export")
        export_btn.setFixedWidth(54)
        export_btn.setToolTip("Save current settings to a file")
        export_btn.clicked.connect(self._export_settings)
        import_btn = QPushButton("Import")
        import_btn.setFixedWidth(54)
        import_btn.setToolTip("Load settings from a file")
        import_btn.clicked.connect(self._import_settings)
        settings_bottom.addWidget(import_btn, 0)
        settings_bottom.addWidget(export_btn, 0)
        settings_inner.addLayout(settings_bottom)
        layout.addWidget(settings_group)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        detect_btn = QPushButton("Auto Detect Grid")
        detect_btn.clicked.connect(self._auto_detect)
        self._process_btn = QPushButton("Process All")
        self._process_btn.clicked.connect(self._run)
        btn_row.addWidget(detect_btn, 0)
        btn_row.addWidget(self._process_btn, 0)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addStretch(1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Add files and select an output folder")

        self._output_dir = ""
        self._output_prefix = ""
        self._signals = _WorkerSignals()
        self._signals.progress.connect(self._on_progress)
        self._signals.finished.connect(self._on_finished)
        self._signals.error.connect(self._on_error)

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Tileset Images", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        for p in paths:
            if p not in self._files:
                self._files.append(p)
                self._file_list.addItem(p)

    def _remove_selected(self) -> None:
        for item in reversed(self._file_list.selectedItems()):
            row = self._file_list.row(item)
            self._files.pop(row)
            self._file_list.takeItem(row)

    def _clear_all(self) -> None:
        self._files.clear()
        self._file_list.clear()

    def _browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Output As (pick prefix)",
            self._output_prefix or "tileset",
            "PNG Image (*.png)",
        )
        if not path:
            return
        folder = os.path.dirname(path)
        prefix = os.path.splitext(os.path.basename(path))[0]
        self._output_dir = folder
        self._output_prefix = prefix
        self._out_label.setText(os.path.join(folder, prefix + "_*.png"))

    def _open_output(self) -> None:
        if not self._output_dir or not os.path.isdir(self._output_dir):
            QMessageBox.warning(self, "No folder", "Set an output location first.")
            return
        if sys.platform == "win32":
            os.startfile(self._output_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self._output_dir])
        else:
            subprocess.Popen(["xdg-open", self._output_dir])

    def _export_settings(self) -> None:
        data = {label: spin.value() for label, spin in self._spins.items()}
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Settings", "tileset_settings.json", "JSON (*.json)",
        )
        if not path:
            return
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self.statusBar().showMessage(f"Settings exported to {os.path.basename(path)}")

    def _import_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", "", "JSON (*.json)",
        )
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))
            return
        for label, value in data.items():
            if label in self._spins:
                self._spins[label].setValue(int(value))
        self.statusBar().showMessage(f"Settings imported from {os.path.basename(path)}")

    def _auto_detect(self) -> None:
        if self._files:
            path = self._files[0]
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Tileset to Analyze", "",
                "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
            )
            if not path:
                return

        self.statusBar().showMessage("Detecting grid...")
        try:
            result = detect_grid(path)
        except Exception as e:
            QMessageBox.critical(self, "Detection failed", str(e))
            self.statusBar().showMessage("Detection failed")
            return

        if result is None:
            QMessageBox.warning(self, "Detection failed", "Could not detect grid lines in this image.")
            self.statusBar().showMessage("Detection failed")
            return

        self._spins["Grid"].setValue(result["grid"])
        self._spins["Top Border"].setValue(result["top"])
        self._spins["Bottom Border"].setValue(result["bottom"])
        self._spins["Left Border"].setValue(result["left"])
        self._spins["Right Border"].setValue(result["right"])
        self._spins["Inside Border"].setValue(result["inside"])

        name = os.path.basename(path)
        self.statusBar().showMessage(
            f"Detected from {name}: {result['grid']}x{result['grid']} grid, "
            f"borders T={result['top']} B={result['bottom']} L={result['left']} R={result['right']}, "
            f"inside={result['inside']}"
        )

    def _run(self) -> None:
        if not self._files:
            QMessageBox.warning(self, "No files", "Add at least one input file.")
            return
        if not self._output_dir or not os.path.isdir(self._output_dir):
            QMessageBox.warning(self, "No output", "Set an output location via Save As.")
            return

        s = self._spins
        grid = s["Grid"].value()
        top = s["Top Border"].value()
        bottom = s["Bottom Border"].value()
        left = s["Left Border"].value()
        right = s["Right Border"].value()
        inside = s["Inside Border"].value()
        trim = s["Trim"].value()
        max_colors = s["Max Colors"].value()
        jt = s["Joint Thresh"].value()
        jd = s["Joint Darken %"].value()
        bg_cut = s["BG Cutoff"].value()
        bg_area = s["BG Min Area"].value()

        out = self._output_dir
        prefix = self._output_prefix or None
        files = list(self._files)
        total = len(files)
        self._process_btn.setEnabled(False)
        self.statusBar().showMessage(f"Processing 0/{total} ...")

        def work():
            for idx, f in enumerate(files, 1):
                if total == 1:
                    file_prefix = prefix
                else:
                    input_stem = os.path.splitext(os.path.basename(f))[0]
                    file_prefix = f"{prefix}_{input_stem}" if prefix else None
                try:
                    process_tileset(f, out, grid, top, bottom, left, right, inside, trim,
                                    max_colors, jt, jd, bg_cut, bg_area, file_prefix)
                except Exception as e:
                    self._signals.error.emit(f"{os.path.basename(f)}: {e}")
                self._signals.progress.emit(idx, total)
            self._signals.finished.emit(total)

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, idx: int, total: int) -> None:
        self.statusBar().showMessage(f"Processing {idx}/{total} ...")

    def _on_finished(self, total: int) -> None:
        self._process_btn.setEnabled(True)
        self.statusBar().showMessage(f"Done — processed {total} file(s)")
        QMessageBox.information(self, "Done", f"Processed {total} file(s) to:\n{self._output_dir}")

    def _on_error(self, msg: str) -> None:
        self.statusBar().showMessage(f"Error: {msg}")
