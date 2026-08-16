from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from src.core.pixel_document import PixelDocument
from src.core.shade_ramp import (
    COOL_SHADOW_HUE_DEG,
    WARM_HIGHLIGHT_HUE_DEG,
    rgb_to_hsb,
    shade_ramp,
)
from src.ui.pixel_editor_window import PixelEditorWindow


def _hue_distance(left: float, right: float) -> float:
    return abs(((left - right + 180.0) % 360.0) - 180.0)


@pytest.mark.parametrize(
    "base",
    [
        (151, 82, 48, 255),
        (57, 130, 74, 210),
        (58, 96, 168, 128),
        (132, 67, 153, 255),
    ],
)
def test_shade_ramp_has_three_shadows_exact_base_and_two_lights(base) -> None:
    ramp = shade_ramp(base)

    assert [label for label, _color in ramp] == [
        "Deep",
        "Shadow",
        "Soft",
        "Base",
        "Light",
        "Highlight",
    ]
    assert ramp[3][1] == base
    assert all(color[3] == base[3] for _label, color in ramp)

    values = [rgb_to_hsb(*color[:3])[2] for _label, color in ramp]
    assert values == sorted(values)
    assert len({color for _label, color in ramp}) == 6


def test_chromatic_ramp_moves_shadows_cool_and_lights_warm() -> None:
    base = (151, 82, 48, 255)
    ramp = shade_ramp(base)
    hues = [rgb_to_hsb(*color[:3])[0] for _label, color in ramp]

    assert _hue_distance(hues[0], COOL_SHADOW_HUE_DEG) < _hue_distance(
        hues[3], COOL_SHADOW_HUE_DEG
    )
    assert _hue_distance(hues[1], COOL_SHADOW_HUE_DEG) < _hue_distance(
        hues[2], COOL_SHADOW_HUE_DEG
    )
    assert _hue_distance(hues[5], WARM_HIGHLIGHT_HUE_DEG) < _hue_distance(
        hues[3], WARM_HIGHLIGHT_HUE_DEG
    )
    assert _hue_distance(hues[4], WARM_HIGHLIGHT_HUE_DEG) < _hue_distance(
        hues[3], WARM_HIGHLIGHT_HUE_DEG
    )


def test_neutral_ramp_gains_restrained_temperature_contrast() -> None:
    ramp = shade_ramp((128, 128, 128, 255))
    hsb = [rgb_to_hsb(*color[:3]) for _label, color in ramp]

    assert _hue_distance(hsb[0][0], COOL_SHADOW_HUE_DEG) < 3.0
    assert hsb[0][1] == pytest.approx(28.0, abs=1.0)
    assert _hue_distance(hsb[-1][0], WARM_HIGHLIGHT_HUE_DEG) < 3.0
    assert 8.0 <= hsb[-1][1] <= 12.0


@pytest.mark.parametrize(
    "base",
    [
        (0, 0, 0, 0),
        (1, 1, 1, 255),
        (255, 255, 255, 255),
        (255, 0, 0, 64),
        (0, 255, 255, 192),
    ],
)
def test_shade_ramp_extreme_inputs_remain_valid_rgba(base) -> None:
    ramp = shade_ramp(base)

    assert len(ramp) == 6
    assert ramp[3][1] == base
    for _label, color in ramp:
        assert len(color) == 4
        assert all(0 <= channel <= 255 for channel in color)
        assert color[3] == base[3]


def test_pixel_editor_displays_complete_six_stop_ramp() -> None:
    application = QApplication.instance() or QApplication([])
    document = PixelDocument(image=Image.new("RGBA", (4, 4), (0, 0, 0, 0)))
    document.current_color = (151, 82, 48, 255)
    window = PixelEditorWindow(document, headless=True)

    window._generate_shade_ramp()

    assert [label for label, _color in window._current_ramp] == [
        "Deep",
        "Shadow",
        "Soft",
        "Base",
        "Light",
        "Highlight",
    ]
    assert window.shade_ramp_layout.count() == 6
    assert window.shade_add_all_button.isEnabled()
    assert window.apply_shading_button.isEnabled()
    assert "three cool shadows" in window.statusBar().currentMessage()

    window.close()
    application.processEvents()
