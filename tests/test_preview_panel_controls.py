import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGroupBox

from src.ui.preview_panel import PreviewPanel


def test_new_resize_and_cleanup_controls_have_expected_names_and_defaults() -> None:
    application = QApplication.instance() or QApplication([])
    panel = PreviewPanel()

    assert [panel.resample_combo.itemText(index) for index in range(panel.resample_combo.count())] == [
        "Nearest Neighbor",
        "Bilinear",
        "Bicubic",
        "Area (Box Average)",
        "Lanczos 3",
    ]
    assert panel.post_process_combo.findText("Edge-Preserving Denoise") >= 0
    assert panel.post_process_combo.findText("Despeckle") >= 0
    assert panel.denoise_radius_spin.value() == 1
    assert panel.denoise_strength_spin.value() == 35
    assert panel.despeckle_max_size_spin.value() == 1
    assert not hasattr(panel, "quantize_checkbox")
    assert not hasattr(panel, "reference_palette_label")
    assert "Limit Colors" not in [
        group.title() for group in panel.findChildren(QGroupBox)
    ]

    panel.deleteLater()
    application.processEvents()
