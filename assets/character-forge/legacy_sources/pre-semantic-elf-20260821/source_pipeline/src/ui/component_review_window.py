from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMovie, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.component_pipeline.pipeline import (
    PIPELINE_ROOT,
    PipelineError,
    generate_job,
    load_job,
    promote_candidate,
    queue_component_jobs,
    save_cleaned_candidate,
    set_candidate_review,
)
from src.core.palette import all_colors_from_image
from src.core.pixel_document import PixelDocument
from src.ui.pixel_editor_window import PixelEditorWindow


class ComponentReviewWindow(QMainWindow):
    """Developer-facing review conveyor for generated component candidates."""

    component_promoted = Signal(str)

    def __init__(self, initial_job: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pip & Pyre Component Review")
        self.resize(1480, 900)
        self._selection: tuple[Path, str] | None = None
        self._cleanup_windows: list[PixelEditorWindow] = []
        self._movie: QMovie | None = None
        self._build_ui()
        self._connect()
        self.refresh(initial_job)

    def _build_ui(self) -> None:
        root = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        filters = QHBoxLayout()
        self.status_filter = QComboBox()
        self.status_filter.addItems(
            ["All", "queued", "review", "approved", "rejected", "failed", "incomplete"]
        )
        self.refresh_button = QPushButton("Refresh")
        filters.addWidget(self.status_filter, 1)
        filters.addWidget(self.refresh_button)
        left_layout.addLayout(filters)
        self.candidate_list = QListWidget()
        left_layout.addWidget(self.candidate_list, 1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.heading = QLabel("Select a candidate")
        self.heading.setStyleSheet("font-size: 16px; font-weight: bold;")
        right_layout.addWidget(self.heading)
        self.tabs = QTabWidget()
        self.image_labels: dict[str, QLabel] = {}
        for name in ("Raw", "Normalized", "Extracted", "Reconstruction"):
            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumSize(420, 420)
            label.setStyleSheet("background: #252525; border: 1px solid #555;")
            self.tabs.addTab(label, name)
            self.image_labels[name.lower()] = label
        details = QTextEdit()
        details.setReadOnly(True)
        self.details_text = details
        self.tabs.addTab(details, "Metadata / QA")
        self.prompt_text = QTextEdit()
        self.prompt_text.setReadOnly(True)
        self.tabs.addTab(self.prompt_text, "Prompt")
        right_layout.addWidget(self.tabs, 1)

        animation_row = QHBoxLayout()
        animation_row.addWidget(QLabel("Animated direction"))
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["front", "back", "left", "right"])
        animation_row.addWidget(self.direction_combo)
        self.animation_label = QLabel()
        self.animation_label.setFixedSize(192, 192)
        self.animation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        animation_row.addWidget(self.animation_label)
        animation_row.addStretch(1)
        right_layout.addLayout(animation_row)

        actions = QHBoxLayout()
        self.approve_button = QPushButton("APPROVE")
        self.reject_button = QPushButton("REJECT")
        self.regenerate_button = QPushButton("REGENERATE")
        self.edit_button = QPushButton("EDIT / CLEANUP")
        self.promote_button = QPushButton("PROMOTE")
        for button in (
            self.approve_button,
            self.reject_button,
            self.regenerate_button,
            self.edit_button,
            self.promote_button,
        ):
            button.setEnabled(False)
            actions.addWidget(button)
        right_layout.addLayout(actions)
        root.addWidget(left)
        root.addWidget(right)
        root.setStretchFactor(0, 0)
        root.setStretchFactor(1, 1)
        root.setSizes([420, 1060])
        self.setCentralWidget(root)

    def _connect(self) -> None:
        self.refresh_button.clicked.connect(lambda: self.refresh())
        self.status_filter.currentTextChanged.connect(lambda _value: self.refresh())
        self.candidate_list.currentItemChanged.connect(self._select_item)
        self.direction_combo.currentTextChanged.connect(lambda _value: self._update_movie())
        self.approve_button.clicked.connect(self._approve)
        self.reject_button.clicked.connect(self._reject)
        self.regenerate_button.clicked.connect(self._regenerate)
        self.edit_button.clicked.connect(self._edit)
        self.promote_button.clicked.connect(self._promote)

    def refresh(self, initial_job: str | None = None) -> None:
        self.candidate_list.clear()
        jobs_root = PIPELINE_ROOT / "jobs"
        if not jobs_root.is_dir():
            return
        selected_item: QListWidgetItem | None = None
        rows: list[tuple[float, Path, str, dict[str, object], dict[str, object]]] = []
        selected_status = self.status_filter.currentText()
        for job_dir in jobs_root.iterdir():
            metadata_path = job_dir / "metadata.json"
            if not metadata_path.is_file():
                continue
            try:
                _path, metadata = load_job(job_dir)
            except PipelineError:
                continue
            candidates = metadata.get("candidates")
            if not isinstance(candidates, dict):
                continue
            for candidate_id, candidate in candidates.items():
                if not isinstance(candidate, dict):
                    continue
                status = str(candidate.get("status", metadata.get("status", "queued")))
                if selected_status != "All" and status != selected_status:
                    continue
                qa = candidate.get("qa")
                score = float(qa.get("score", -1)) if isinstance(qa, dict) else -1.0
                rows.append((score, job_dir, str(candidate_id), metadata, candidate))
        for score, job_dir, candidate_id, metadata, candidate in sorted(
            rows, key=lambda row: (-row[0], row[1].name, row[2])
        ):
            status = candidate.get("status", metadata.get("status", "queued"))
            label = (
                f"{metadata.get('component_id')} | {metadata.get('animation_id')} | "
                f"{candidate_id} | {status} | {score:.1f}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, (str(job_dir), candidate_id))
            self.candidate_list.addItem(item)
            if initial_job and job_dir.name == Path(initial_job).name and selected_item is None:
                selected_item = item
        if selected_item is not None:
            self.candidate_list.setCurrentItem(selected_item)
        elif self.candidate_list.count():
            self.candidate_list.setCurrentRow(0)

    def _select_item(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None:
            self._selection = None
            return
        job_text, candidate_id = current.data(Qt.ItemDataRole.UserRole)
        job_dir, metadata = load_job(job_text)
        candidate = metadata["candidates"][candidate_id]
        self._selection = (job_dir, candidate_id)
        self.heading.setText(
            f"{metadata['component_id']} — {metadata['animation_id']} — {candidate_id}"
        )
        self.prompt_text.setPlainText((job_dir / "prompt.txt").read_text(encoding="utf-8"))
        self.details_text.setPlainText(
            json.dumps({"job": metadata, "candidate": candidate}, indent=2)
        )
        paths = {
            "raw": job_dir / "raw_candidates" / f"{candidate_id}.png",
            "normalized": job_dir / "normalized" / candidate_id / "dominant.png",
            "extracted": job_dir / "extracted" / f"{candidate_id}.png",
            "reconstruction": job_dir / "previews" / candidate_id / "reconstruction.png",
        }
        for name, label in self.image_labels.items():
            path = paths[name]
            if path.is_file():
                pixmap = QPixmap(str(path)).scaled(
                    640,
                    640,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
                label.setPixmap(pixmap)
            else:
                label.setText("Not available")
                label.setPixmap(QPixmap())
        status = candidate.get("status")
        qa = candidate.get("qa")
        review = candidate.get("review")
        can_review = status == "review"
        self.approve_button.setEnabled(can_review)
        self.reject_button.setEnabled(can_review)
        self.regenerate_button.setEnabled(True)
        self.edit_button.setEnabled(paths["extracted"].is_file())
        self.promote_button.setEnabled(
            isinstance(review, dict)
            and review.get("decision") == "approved"
            and isinstance(qa, dict)
            and qa.get("status") != "fail"
        )
        self._update_movie()

    def _update_movie(self) -> None:
        if self._selection is None:
            return
        job_dir, candidate_id = self._selection
        path = job_dir / "previews" / candidate_id / f"{self.direction_combo.currentText()}.webp"
        if self._movie is not None:
            self._movie.stop()
        if not path.is_file():
            self.animation_label.clear()
            return
        self._movie = QMovie(str(path))
        self._movie.setScaledSize(self.animation_label.size())
        self.animation_label.setMovie(self._movie)
        self._movie.start()

    def _selected(self) -> tuple[Path, str]:
        if self._selection is None:
            raise PipelineError("Select a candidate first")
        return self._selection

    def _approve(self) -> None:
        job_dir, candidate_id = self._selected()
        set_candidate_review(job_dir, candidate_id, "approved")
        self.refresh(job_dir.name)

    def _reject(self) -> None:
        job_dir, candidate_id = self._selected()
        reason, accepted = QInputDialog.getText(
            self,
            "Reject candidate",
            "Reason (stored with the candidate):",
        )
        if not accepted:
            return
        reason = reason.strip()
        if not reason:
            QMessageBox.information(self, "Reason required", "Enter a rejection reason.")
            return
        set_candidate_review(job_dir, candidate_id, "rejected", note=reason)
        self.refresh(job_dir.name)

    def _regenerate(self) -> None:
        job_dir, _candidate_id = self._selected()
        _path, metadata = load_job(job_dir)
        jobs = queue_component_jobs(
            str(metadata["component_id"]),
            animation_id=str(metadata["animation_id"]),
            candidates=1,
            force_new=True,
            design_reference=(
                str(metadata["design_reference"])
                if metadata.get("design_reference")
                else None
            ),
        )
        try:
            generate_job(jobs[0])
        except PipelineError as exc:
            self.statusBar().showMessage(str(exc))
        self.refresh(jobs[0].name)

    def _edit(self) -> None:
        job_dir, candidate_id = self._selected()
        path = job_dir / "extracted" / f"{candidate_id}.png"
        with Image.open(path) as opened:
            source = opened.convert("RGBA")
        document = PixelDocument(
            image=source.copy(),
            name=f"{job_dir.name}-{candidate_id}-cleanup",
            palette=all_colors_from_image(source),
        )
        window = PixelEditorWindow(document, None, restore_reference=source)
        window.asset_save_requested.connect(
            lambda _name, image, selected_job=job_dir, selected_candidate=candidate_id: (
                save_cleaned_candidate(selected_job, selected_candidate, image),
                self.refresh(selected_job.name),
            )
        )
        window.destroyed.connect(
            lambda *_args, target=window: self._remove_cleanup_window(target)
        )
        self._cleanup_windows.append(window)
        window.show()
        self.statusBar().showMessage(
            "Cleanup opened; use To Tray to save the corrected candidate back to its job"
        )

    def _remove_cleanup_window(self, target: PixelEditorWindow) -> None:
        self._cleanup_windows = [window for window in self._cleanup_windows if window is not target]

    def _promote(self) -> None:
        job_dir, candidate_id = self._selected()
        try:
            path = promote_candidate(job_dir, candidate_id)
        except PipelineError as exc:
            QMessageBox.critical(self, "Promotion failed", str(exc))
            return
        self.statusBar().showMessage(f"Promoted {path}")
        self.component_promoted.emit(str(path))
        self.refresh(job_dir.name)


def run_component_review(initial_job: str | None = None) -> int:
    application = QApplication.instance()
    owns_application = application is None
    if application is None:
        application = QApplication([])
    window = ComponentReviewWindow(initial_job)
    window.show()
    if owns_application:
        return application.exec()
    return 0
