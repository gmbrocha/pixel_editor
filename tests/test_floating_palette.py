from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QMainWindow

from src.core.pixel_document import PixelDocument
from src.ui import character_forge_window as character_forge_module
from src.ui import component_review_window as component_review_module
from src.ui import main_window as main_window_module
from src.ui.character_forge_window import CharacterForgeWindow
from src.ui.component_review_window import ComponentReviewWindow
from src.ui.main_window import MainWindow
from src.ui.pixel_editor_window import (
    ClickableColorButton,
    FloatingPaletteWindow,
    PixelEditorWindow,
)


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_floating_palette_starts_local_and_is_an_editor_owned_tool() -> None:
    application = _application()
    selected = (28, 84, 176, 255)
    document = PixelDocument(
        image=Image.new("RGBA", (4, 4)),
        palette=[selected, (200, 40, 30, 255), (30, 180, 80, 255)],
    )
    document.current_color = selected
    editor = PixelEditorWindow(document, headless=True)

    editor.show_floating_palette()
    application.processEvents()
    palette = editor._floating_palette

    assert isinstance(palette, FloatingPaletteWindow)
    assert palette.colors() == [selected, FloatingPaletteWindow.TRANSPARENT]
    assert palette.parentWidget() is editor
    assert palette.isWindow()
    assert palette.windowFlags() & Qt.WindowType.Tool
    assert not (palette.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    palette.close()
    editor.close()
    application.processEvents()


def test_transparent_initial_color_is_deduplicated_and_permanent() -> None:
    application = _application()
    document = PixelDocument(image=Image.new("RGBA", (2, 2)))
    document.current_color = (90, 80, 70, 0)
    editor = PixelEditorWindow(document, headless=True)

    editor.show_floating_palette()
    palette = editor._floating_palette

    assert palette is not None
    assert palette.colors() == [FloatingPaletteWindow.TRANSPARENT]
    assert palette.remove_color((90, 80, 70, 0)) is False
    assert palette.remove_color(FloatingPaletteWindow.TRANSPARENT) is False

    palette.close()
    editor.close()
    application.processEvents()


def test_main_palette_context_send_opens_without_changing_current_color() -> None:
    application = _application()
    selected = (10, 20, 30, 255)
    sent = (190, 80, 45, 255)
    document = PixelDocument(
        image=Image.new("RGBA", (3, 3)),
        palette=[selected, sent],
    )
    document.current_color = selected
    editor = PixelEditorWindow(document, headless=True)
    buttons = editor.palette_container.findChildren(ClickableColorButton)
    sent_button = next(button for button in buttons if button._color == sent)

    menu = sent_button._create_context_menu()
    assert [action.text() for action in menu.actions()] == ["Send to Floating Palette"]
    menu.actions()[0].trigger()
    application.processEvents()

    palette = editor._floating_palette
    assert palette is not None
    assert palette.isVisible()
    assert palette.colors() == [selected, FloatingPaletteWindow.TRANSPARENT, sent]
    assert document.current_color == selected

    sent_button.send_to_floating_requested.emit(sent)
    assert palette.colors().count(sent) == 1

    palette.close()
    editor.close()
    application.processEvents()


def test_custom_floating_color_is_selected_but_not_added_to_project_palette(
    monkeypatch,
) -> None:
    application = _application()
    original = (22, 44, 66, 255)
    custom = (211, 103, 47, 180)
    document = PixelDocument(
        image=Image.new("RGBA", (3, 3)),
        palette=[original],
    )
    document.current_color = original
    editor = PixelEditorWindow(document, headless=True)
    editor.show_floating_palette()
    palette = editor._floating_palette
    project_palette = list(document.palette)
    monkeypatch.setattr(
        editor,
        "_choose_rgba_color",
        lambda *_args, **_kwargs: custom,
    )

    editor._add_custom_floating_color()

    assert palette is not None
    assert palette.colors() == [original, FloatingPaletteWindow.TRANSPARENT, custom]
    assert document.current_color == custom
    assert document.palette == project_palette

    custom_button = next(
        button
        for button in palette.findChildren(ClickableColorButton)
        if button._color == custom
    )
    remove_menu = custom_button._create_context_menu()
    assert [action.text() for action in remove_menu.actions()] == [
        "Remove from Floating Palette"
    ]
    remove_menu.actions()[0].trigger()
    application.processEvents()
    assert custom not in palette.colors()

    palette.close()
    editor.close()
    application.processEvents()


def test_floating_palette_retains_colors_and_position_for_editor_session() -> None:
    application = _application()
    initial = (20, 40, 60, 255)
    added = (120, 140, 160, 255)
    document = PixelDocument(image=Image.new("RGBA", (2, 2)))
    document.current_color = initial
    editor = PixelEditorWindow(document, headless=True)
    editor.show_floating_palette()
    palette = editor._floating_palette
    assert palette is not None
    palette.add_color(added)
    palette.move(37, 53)
    saved_position = palette.pos()

    palette.close()
    editor.show_floating_palette()
    application.processEvents()

    assert editor._floating_palette is palette
    assert palette.colors() == [initial, FloatingPaletteWindow.TRANSPARENT, added]
    assert palette.pos() == saved_position

    palette.close()
    editor.close()
    application.processEvents()


def test_each_pixel_editor_has_an_isolated_floating_palette() -> None:
    application = _application()
    first_color = (15, 30, 45, 255)
    second_color = (180, 150, 120, 255)
    extra = (240, 80, 90, 255)
    first_document = PixelDocument(image=Image.new("RGBA", (2, 2)))
    second_document = PixelDocument(image=Image.new("RGBA", (2, 2)))
    first_document.current_color = first_color
    second_document.current_color = second_color
    first = PixelEditorWindow(first_document, headless=True)
    second = PixelEditorWindow(second_document, headless=True)

    first.show_floating_palette(extra)
    second.show_floating_palette()

    assert first._floating_palette is not second._floating_palette
    assert first._floating_palette.colors() == [
        first_color,
        FloatingPaletteWindow.TRANSPARENT,
        extra,
    ]
    assert second._floating_palette.colors() == [
        second_color,
        FloatingPaletteWindow.TRANSPARENT,
    ]

    first._floating_palette.close()
    second._floating_palette.close()
    first.close()
    second.close()
    application.processEvents()


class _FakeToolWindow(QMainWindow):
    component_promoted = Signal(str)

    def __init__(self, parent=None, *_args, **kwargs) -> None:
        if "parent" in kwargs:
            parent = kwargs["parent"]
        super().__init__(parent)


class _FakePixelEditor(QMainWindow):
    asset_save_requested = Signal(str, object)

    def __init__(self, _document, parent=None, *_args, **_kwargs) -> None:
        super().__init__(parent)


def test_main_window_launches_every_persistent_tool_as_independent(
    monkeypatch,
) -> None:
    application = _application()
    main = MainWindow()
    for name in (
        "CharacterForgeWindow",
        "ComponentReviewWindow",
        "AnimationEditorWindow",
        "ReferenceMapperWindow",
        "TileLayoutWindow",
        "TilesetProcessorWindow",
        "TilesetTemplateWindow",
        "TextureGeneratorWindow",
    ):
        monkeypatch.setattr(main_window_module, name, _FakeToolWindow)

    main.open_character_forge()
    main.open_component_review()
    main.open_animation_editor()
    main.open_reference_mapper()
    main.open_tile_layout()
    main.open_tileset_processor()
    main.open_tileset_template()
    main.open_texture_generator()

    assert len(main._tool_windows) == 8
    assert all(window.parentWidget() is None for window in main._tool_windows)
    assert all(window.isWindow() for window in main._tool_windows)

    main.show()
    application.processEvents()
    main.showMinimized()
    application.processEvents()
    assert all(not window.isMinimized() for window in main._tool_windows)

    for window in main._tool_windows:
        window.close()
    main.close()
    application.processEvents()


def test_main_window_pixel_editor_is_independent_and_strongly_referenced() -> None:
    application = _application()
    main = MainWindow()
    document = PixelDocument(image=Image.new("RGBA", (2, 2)), name="independent")

    main._open_pixel_editor(document, headless=True)
    editor = main._pixel_windows[-1]

    assert editor.parentWidget() is None
    assert editor.isWindow()
    main.show()
    application.processEvents()
    main.showMinimized()
    application.processEvents()
    assert not editor.isMinimized()

    editor.close()
    main.close()
    application.processEvents()


def test_nested_pixel_editor_launchers_are_independent(
    monkeypatch,
    tmp_path,
) -> None:
    application = _application()
    monkeypatch.setattr(character_forge_module, "PixelEditorWindow", _FakePixelEditor)
    monkeypatch.setattr(component_review_module, "PixelEditorWindow", _FakePixelEditor)

    forge = CharacterForgeWindow()
    part = forge.catalog.parts[0]
    forge.recipe.parts[part.slot] = part.id
    monkeypatch.setattr(
        character_forge_module,
        "load_part_animation",
        lambda *_args: Image.new("RGBA", (4, 4)),
    )
    forge._edit_part(part.slot)

    assert len(forge._pixel_windows) == 1
    assert forge._pixel_windows[0].parentWidget() is None

    job_dir = tmp_path / "job"
    extracted = job_dir / "extracted"
    extracted.mkdir(parents=True)
    candidate = extracted / "candidate-001.png"
    Image.new("RGBA", (4, 4), (80, 90, 100, 255)).save(candidate)
    review = ComponentReviewWindow()
    monkeypatch.setattr(review, "_selected", lambda: (job_dir, "candidate-001"))
    review._edit()

    assert len(review._cleanup_windows) == 1
    assert review._cleanup_windows[0].parentWidget() is None

    review._cleanup_windows[0].close()
    forge._pixel_windows[0].close()
    review.close()
    forge.close()
    application.processEvents()
