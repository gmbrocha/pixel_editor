import os
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

import src.component_pipeline.pipeline as pipeline
import src.ui.component_review_window as review_ui
from src.core.pixel_document import PixelDocument
from src.ui.component_review_window import ComponentReviewWindow
from src.ui.pixel_editor_window import PixelEditorWindow


def test_review_window_lists_a_queued_candidate(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "PIPELINE_ROOT", tmp_path / "art_pipeline")
    monkeypatch.setattr(review_ui, "PIPELINE_ROOT", tmp_path / "art_pipeline")
    catalog_path = tmp_path / "components.yaml"
    shutil.copy2(pipeline.CATALOG_PATH, catalog_path)
    monkeypatch.setattr(pipeline, "CATALOG_PATH", catalog_path)
    jobs = pipeline.queue_component_jobs(
        "weathered_captains_cap_01",
        animation_id="idle",
        candidates=1,
        force_new=True,
    )
    application = QApplication.instance() or QApplication([])
    window = ComponentReviewWindow(jobs[0].name)
    application.processEvents()
    assert window.candidate_list.count() == 1
    assert "weathered_captains_cap_01" in window.heading.text()
    assert window.regenerate_button.isEnabled()
    assert not window.approve_button.isEnabled()
    window.close()


def test_cleanup_restore_source_selection_is_undoable() -> None:
    application = QApplication.instance() or QApplication([])
    reference = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    reference.putpixel((2, 1), (120, 30, 20, 255))
    document = PixelDocument(image=Image.new("RGBA", (4, 4), (0, 0, 0, 0)))
    document.selected_pixels.add((2, 1))
    window = PixelEditorWindow(document, headless=True, restore_reference=reference)
    window._restore_source_selection()
    assert document.image.getpixel((2, 1)) == (120, 30, 20, 255)
    window.undo_last_edit()
    assert document.image.getpixel((2, 1)) == (0, 0, 0, 0)
    window.close()
    application.processEvents()
