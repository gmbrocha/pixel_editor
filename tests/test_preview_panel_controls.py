import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel

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
    assert panel.post_process_combo.findText("Cluster Cleanup") >= 0
    assert panel.denoise_radius_spin.value() == 1
    assert panel.denoise_strength_spin.value() == 35
    assert panel.despeckle_max_size_spin.value() == 1
    assert panel.cluster_cleanup_threshold_spin.value() == 3
    assert not hasattr(panel, "quantize_checkbox")
    assert not hasattr(panel, "reference_palette_label")
    assert not hasattr(panel, "size_label")
    assert panel.width_pair_layout.spacing() == 0
    assert panel.height_pair_layout.spacing() == 0
    assert panel.output_controls_layout.indexOf(panel.resample_combo) >= 0
    assert panel.output_controls_layout.indexOf(panel.post_process_combo) >= 0
    assert panel.downscale_combo.isEnabled() is False
    assert "Limit Colors" not in [
        group.title() for group in panel.findChildren(QGroupBox)
    ]

    panel.set_preview_image(Image.new("RGBA", (151, 63)))
    assert not any(
        label.text().startswith("Preview:")
        for label in panel.findChildren(QLabel)
    )

    panel.deleteLater()
    application.processEvents()


def test_integer_downscale_preset_sets_both_dimensions_from_source() -> None:
    application = QApplication.instance() or QApplication([])
    panel = PreviewPanel()
    panel.set_source_size((151, 63))

    panel.downscale_combo.setCurrentIndex(panel.downscale_combo.findData(2))

    assert panel.width_spin.value() == 75
    assert panel.height_spin.value() == 31
    assert panel.fit_combo.currentText() == "Fit"

    panel.width_spin.setValue(74)
    assert panel.downscale_combo.currentData() is None

    panel.set_source_size((5000, 3000))
    panel.downscale_combo.setCurrentIndex(panel.downscale_combo.findData(2))
    assert panel.width_spin.value() == 2500
    assert panel.height_spin.value() == 1500
    assert panel.width_spin.maximum() >= 2500

    panel.deleteLater()
    application.processEvents()


def test_large_source_dimensions_are_available_for_processing_without_resize() -> None:
    application = QApplication.instance() or QApplication([])
    panel = PreviewPanel()

    panel.set_source_size((5000, 3000))
    panel.width_spin.setValue(5000)
    panel.height_spin.setValue(3000)
    panel.post_process_combo.setCurrentText("Small Gaussian Blur")

    settings = panel.settings()
    assert panel.width_spin.maximum() >= 5000
    assert panel.height_spin.maximum() >= 3000
    assert settings.width == 5000
    assert settings.height == 3000
    assert settings.post_process_mode == "Small Gaussian Blur"

    panel.deleteLater()
    application.processEvents()


def test_cluster_cleanup_control_is_live_visible_and_resettable() -> None:
    application = QApplication.instance() or QApplication([])
    panel = PreviewPanel()
    emitted = []
    panel.settings_changed.connect(emitted.append)

    panel.post_process_combo.setCurrentText("Cluster Cleanup")

    assert panel.cluster_cleanup_threshold_label.isVisible() is False
    panel.show()
    application.processEvents()
    assert panel.cluster_cleanup_threshold_label.isVisible() is True
    assert panel.cluster_cleanup_threshold_spin.isVisible() is True
    assert panel.denoise_radius_spin.isVisible() is False
    assert panel.despeckle_max_size_spin.isVisible() is False

    panel.cluster_cleanup_threshold_spin.setValue(7)
    assert emitted[-1].post_process_mode == "Cluster Cleanup"
    assert emitted[-1].cluster_cleanup_threshold == 7

    panel.reset_processing_button.click()
    assert panel.post_process_combo.currentText() == "None"
    assert panel.cluster_cleanup_threshold_spin.value() == 3
    assert panel.cluster_cleanup_threshold_spin.isVisible() is False

    panel.close()
    panel.deleteLater()
    application.processEvents()
