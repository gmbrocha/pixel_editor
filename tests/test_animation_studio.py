from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from src.core.animation_document import (
    AnchorPoint,
    AnimationProjectError,
    FrameSequenceSpec,
    create_animation_project_from_gif,
    create_animation_project_from_sheet,
    export_project_gif,
    export_project_metadata,
    load_animation_project,
    playback_frame_indices,
    project_to_sheet,
    save_animation_project,
    track_to_sheet,
)
from src.ui.animation_editor_window import AnimationEditorWindow
from src.ui.animation_source_canvas import AnimationSourceCanvas
from src.ui.main_window import MainWindow


def _coordinate_sheet(width: int = 16, height: int = 16) -> Image.Image:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for y in range(height):
        for x in range(width):
            image.putpixel((x, y), (x, y, (x + y) % 256, 255))
    return image


def _write_test_gif(path: Path, *, loop: int | None = 0) -> list[Image.Image]:
    frames = [
        Image.new("RGBA", (3, 2), color)
        for color in (
            (220, 20, 30, 255),
            (20, 200, 40, 255),
            (30, 40, 220, 255),
        )
    ]
    save_options = {
        "save_all": True,
        "append_images": frames[1:],
        "duration": [100, 200, 300],
        "disposal": 2,
    }
    if loop is not None:
        save_options["loop"] = loop
    frames[0].save(path, **save_options)
    return frames


def test_gif_import_builds_an_editable_horizontal_sheet_and_preserves_timing(
    tmp_path,
) -> None:
    path = tmp_path / "spell.gif"
    expected_frames = _write_test_gif(path)

    project = create_animation_project_from_gif(path, palette=[(12, 34, 56, 255)])

    assert project.name == "spell"
    assert project.source_path == str(path)
    assert project.sheet_size == (9, 2)
    assert (project.frame_width, project.frame_height) == (3, 2)
    assert project.fps == 10
    assert project.playback_mode == "loop"
    assert project.palette == [(12, 34, 56, 255)]
    assert len(project.tracks) == 1
    track = project.tracks[0]
    assert track.name == "Animation"
    assert track.spec == FrameSequenceSpec(0, 0, 3, 2, 3, 3, 0)
    assert [frame.duration_ticks for frame in track.frames] == [1, 2, 3]
    for index, expected in enumerate(expected_frames):
        assert project.frame_image(track.id, index).tobytes() == expected.tobytes()
    assert project.original_sheet.tobytes() == project.working_sheet.tobytes()

    edited = project.frame_image(track.id, 1)
    edited.putpixel((1, 1), (1, 2, 3, 4))
    project.commit_frame_image(track.id, 1, edited)
    assert project.frame_image(track.id, 1).getpixel((1, 1)) == (1, 2, 3, 4)
    assert project.frame_image(track.id, 1, original=True).getpixel((1, 1)) != (
        1,
        2,
        3,
        4,
    )

    archive = tmp_path / "spell.pfa"
    save_animation_project(project, archive)
    reopened = load_animation_project(archive)
    assert reopened.original_sheet.tobytes() == project.original_sheet.tobytes()
    assert reopened.working_sheet.tobytes() == project.working_sheet.tobytes()
    assert reopened.fps == 10
    assert reopened.playback_mode == "loop"
    assert [frame.duration_ticks for frame in reopened.tracks[0].frames] == [1, 2, 3]


def test_gif_import_without_loop_metadata_uses_once_playback(tmp_path) -> None:
    path = tmp_path / "once.gif"
    _write_test_gif(path, loop=None)

    project = create_animation_project_from_gif(path)

    assert project.playback_mode == "once"


def test_gif_import_fits_long_delays_without_sluggish_timing_distortion(
    tmp_path,
) -> None:
    path = tmp_path / "slow.gif"
    frames = [
        Image.new("RGBA", (2, 2), (180, 30, 20, 255)),
        Image.new("RGBA", (2, 2), (20, 40, 180, 255)),
    ]
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=[1500, 3000],
        loop=0,
    )

    project = create_animation_project_from_gif(path)

    assert project.fps == 2
    assert [frame.duration_ticks for frame in project.tracks[0].frames] == [3, 6]


def test_animation_editor_import_gif_loads_track_source_and_frame_editor(
    tmp_path, monkeypatch
) -> None:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "walk.gif"
    _write_test_gif(path)
    window = AnimationEditorWindow()
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(path), "GIF Images (*.gif)"),
    )

    window._open_gif()

    assert window._project.sheet_size == (9, 2)
    assert len(window._project.tracks[0].frames) == 3
    assert window._current_track_id == window._project.tracks[0].id
    assert window._frame_doc.image.size == (3, 2)
    assert window._frame_count_spin.value() == 3
    assert window._dirty
    assert "Imported 3 GIF frames" in window.statusBar().currentMessage()
    window._dirty = False
    window.close()
    application.processEvents()


def test_sequence_specs_extract_horizontal_vertical_reverse_gapped_and_diagonal() -> (
    None
):
    sheet = _coordinate_sheet()
    specs = {
        "horizontal": FrameSequenceSpec(1, 2, 2, 2, 3, 3, 0),
        "vertical": FrameSequenceSpec(2, 1, 2, 2, 3, 0, 3),
        "reverse": FrameSequenceSpec(8, 2, 2, 2, 3, -3, 0),
        "diagonal": FrameSequenceSpec(1, 1, 2, 2, 3, 3, 3),
    }
    for name, spec in specs.items():
        project = create_animation_project_from_sheet(sheet, frame_size=(2, 2))
        track = project.add_track(name, spec)
        assert len(track.frames) == 3
        for index, rect in enumerate(spec.rectangles()):
            assert (
                project.frame_image(track.id, index).tobytes()
                == sheet.crop(
                    (rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3])
                ).tobytes()
            )


def test_playback_frame_indices_support_ping_pong_without_duplicate_turnarounds() -> (
    None
):
    assert playback_frame_indices(6, "once") == [0, 1, 2, 3, 4, 5]
    assert playback_frame_indices(6, "loop") == [0, 1, 2, 3, 4, 5]
    assert playback_frame_indices(6, "ping_pong") == [
        0,
        1,
        2,
        3,
        4,
        5,
        4,
        3,
        2,
        1,
    ]
    assert playback_frame_indices(1, "ping_pong") == [0]
    assert playback_frame_indices(2, "ping_pong") == [0, 1]
    assert playback_frame_indices(6, "ping_pong", start=1, end=4) == [
        1,
        2,
        3,
        4,
        3,
        2,
    ]


def test_sequence_validation_rejects_out_of_bounds_and_mismatched_track_size() -> None:
    sheet = _coordinate_sheet(8, 8)
    invalid = FrameSequenceSpec(6, 6, 3, 3, 1, 0, 0)
    assert invalid.validation_errors(sheet.size)
    project = create_animation_project_from_sheet(sheet, frame_size=(2, 2))
    project.add_track("Front", FrameSequenceSpec(0, 0, 2, 2, 2, 2, 0))
    try:
        project.add_track("Back", FrameSequenceSpec(0, 2, 3, 2, 2, 3, 0))
    except AnimationProjectError as exc:
        assert "project frame size" in str(exc).lower()
    else:
        raise AssertionError("Mismatched track geometry should be rejected")


def test_linked_edit_updates_working_sheet_overlap_and_global_history() -> None:
    source = _coordinate_sheet(8, 4)
    project = create_animation_project_from_sheet(source, frame_size=(2, 2))
    first = project.add_track("Front", FrameSequenceSpec(0, 0, 2, 2, 2, 2, 0))
    shared = project.add_track("Shared", FrameSequenceSpec(0, 0, 2, 2, 1, 0, 0))
    original_bytes = project.original_sheet.tobytes()
    replacement = Image.new("RGBA", (2, 2), (240, 10, 20, 255))

    changed = project.commit_frame_image(first.id, 0, replacement)

    assert changed == (0, 0, 2, 2)
    assert project.frame_image(first.id, 0).tobytes() == replacement.tobytes()
    assert project.frame_image(shared.id, 0).tobytes() == replacement.tobytes()
    assert project.original_sheet.tobytes() == original_bytes
    assert set(project.intersecting_frames(changed)) == {(first.id, 0), (shared.id, 0)}

    transaction = project.undo()
    assert transaction is not None
    assert (
        project.frame_image(first.id, 0).tobytes()
        == project.frame_image(first.id, 0, original=True).tobytes()
    )
    assert project.redo() is transaction
    assert project.frame_image(shared.id, 0).tobytes() == replacement.tobytes()


def test_overlap_detection_checks_proposed_and_existing_rectangles() -> None:
    project = create_animation_project_from_sheet(
        _coordinate_sheet(12, 6), frame_size=(3, 3)
    )
    project.add_track("Front", FrameSequenceSpec(0, 0, 3, 3, 2, 3, 0))
    overlaps = project.overlaps_for_spec(FrameSequenceSpec(2, 0, 3, 3, 2, 2, 0))
    assert overlaps
    assert any(first == (2, 0, 3, 3) for first, _second in overlaps)


def test_project_archive_round_trip_preserves_baseline_working_pixels_and_metadata(
    tmp_path,
) -> None:
    source = _coordinate_sheet(12, 8)
    project = create_animation_project_from_sheet(
        source,
        name="walk",
        frame_size=(3, 4),
        fps=11,
        playback_mode="ping_pong",
        palette=[(1, 2, 3, 255)],
    )
    track = project.add_track("Front", FrameSequenceSpec(0, 0, 3, 4, 3, 3, 0))
    track.frames[0].duration_ticks = 2
    track.frames[0].label = "contact"
    track.frames[0].anchors.append(AnchorPoint("hand", 1, 2))
    track.frames[0].pivot = (1, 3)
    project.commit_frame_image(track.id, 1, Image.new("RGBA", (3, 4), (9, 8, 7, 255)))
    path = tmp_path / "walk.pfa"

    save_animation_project(project, path)
    loaded = load_animation_project(path)

    assert loaded.original_sheet.tobytes() == project.original_sheet.tobytes()
    assert loaded.working_sheet.tobytes() == project.working_sheet.tobytes()
    assert loaded.frame_width == 3
    assert loaded.frame_height == 4
    assert loaded.fps == 11
    assert loaded.playback_mode == "ping_pong"
    assert loaded.palette == [(1, 2, 3, 255)]
    loaded_frame = loaded.tracks[0].frames[0]
    assert loaded_frame.duration_ticks == 2
    assert loaded_frame.label == "contact"
    assert loaded_frame.anchors == [AnchorPoint("hand", 1, 2)]
    assert loaded_frame.pivot == (1, 3)
    with zipfile.ZipFile(path) as archive:
        assert set(archive.namelist()) == {
            "project.json",
            "original.png",
            "working.png",
        }


def test_track_all_sheet_and_metadata_exports_follow_track_order(tmp_path) -> None:
    project = create_animation_project_from_sheet(
        _coordinate_sheet(12, 8), frame_size=(3, 4)
    )
    front = project.add_track("Front", FrameSequenceSpec(0, 0, 3, 4, 3, 3, 0))
    project.add_track("Back", FrameSequenceSpec(0, 4, 3, 4, 2, 3, 0))
    selected = track_to_sheet(project, front.id)
    combined = project_to_sheet(project)
    metadata_path = tmp_path / "animation.json"
    gif_path = tmp_path / "front.gif"
    front.frames[0].duration_ticks = 2
    export_project_metadata(project, metadata_path)
    export_project_gif(project, front.id, gif_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert selected.size == (9, 4)
    assert combined.size == (9, 8)
    assert combined.crop((6, 4, 9, 8)).getbbox() is None
    assert [track["name"] for track in metadata["tracks"]] == ["Front", "Back"]
    assert metadata["sheet_columns"] == 3
    assert metadata["playback_mode"] == "loop"
    with Image.open(gif_path) as animated:
        assert animated.n_frames == 3
        assert animated.info["duration"] == 250


def test_ping_pong_gif_export_expands_the_reverse_leg(tmp_path) -> None:
    sheet = Image.new("RGBA", (5, 1), (0, 0, 0, 0))
    colors = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 0, 255),
        (255, 0, 255, 255),
    ]
    for index, color in enumerate(colors):
        sheet.putpixel((index, 0), color)
    project = create_animation_project_from_sheet(
        sheet, frame_size=(1, 1), playback_mode="ping_pong"
    )
    track = project.add_track("Walk", FrameSequenceSpec(0, 0, 1, 1, 5, 1, 0))
    path = tmp_path / "walk_ping_pong.gif"

    export_project_gif(project, track.id, path)

    with Image.open(path) as animated:
        assert animated.n_frames == 8
        rendered = []
        for frame_index in range(animated.n_frames):
            animated.seek(frame_index)
            rendered.append(animated.convert("RGBA").getpixel((0, 0)))
        assert rendered == [
            colors[0],
            colors[1],
            colors[2],
            colors[3],
            colors[4],
            colors[3],
            colors[2],
            colors[1],
        ]


def test_source_canvas_drag_emits_pixel_aligned_selection() -> None:
    application = QApplication.instance() or QApplication([])
    canvas = AnimationSourceCanvas()
    canvas.set_image(_coordinate_sheet(8, 8))
    canvas.set_zoom(10)
    canvas.resize(canvas.sizeHint())
    canvas.show()
    selections: list[tuple] = []
    canvas.selection_changed.connect(selections.append)
    margin = canvas.MARGIN

    QTest.mousePress(
        canvas,
        Qt.MouseButton.LeftButton,
        pos=QPoint(margin + 1 * 10 + 5, margin + 2 * 10 + 5),
    )
    QTest.mouseMove(canvas, QPoint(margin + 3 * 10 + 5, margin + 4 * 10 + 5))
    QTest.mouseRelease(
        canvas,
        Qt.MouseButton.LeftButton,
        pos=QPoint(margin + 3 * 10 + 5, margin + 4 * 10 + 5),
    )

    assert selections[-1] == (1, 2, 3, 3)
    canvas.close()
    application.processEvents()


def test_animation_editor_constructs_and_syncs_linked_frame_edits() -> None:
    application = QApplication.instance() or QApplication([])
    window = AnimationEditorWindow()
    assert window._left_tabs.tabText(0) == "Source Sheet"
    assert window._left_tabs.tabText(1) == "Frame Editor"
    assert window._track_combo.currentText() == "Track"
    track = window._project.tracks[0]
    baseline = window._project.original_sheet.tobytes()

    window._frame_doc.image.putpixel((0, 0), (255, 0, 0, 255))
    window._on_frame_image_changed()
    window._flush_frame_edit()

    assert window._project.frame_image(track.id, 0).getpixel((0, 0)) == (255, 0, 0, 255)
    assert window._project.original_sheet.tobytes() == baseline
    window._undo()
    assert window._project.frame_image(track.id, 0).getpixel((0, 0)) == (0, 0, 0, 0)
    window._dirty = False
    window.close()
    application.processEvents()


def test_animation_editor_drag_select_colors_is_one_shot_and_restores_tool() -> None:
    application = QApplication.instance() or QApplication([])
    window = AnimationEditorWindow()
    red = (220, 20, 30, 255)
    green = (20, 200, 40, 255)
    blue = (30, 40, 220, 180)
    window._frame_doc.image.putpixel((0, 0), red)
    window._frame_doc.image.putpixel((1, 0), green)
    window._frame_doc.image.putpixel((0, 1), (0, 0, 0, 0))
    window._frame_doc.image.putpixel((1, 1), blue)
    window._project.palette = [(1, 2, 3, 255)]
    window._line_radio.setChecked(True)
    window._draw_selection_check.setChecked(True)
    window._frame_canvas.show()
    application.processEvents()

    assert window._color_button.text() == "Pick Color"
    assert window._drag_palette_button.text() == "Drag Select Colors"
    window._drag_palette_button.click()

    assert window._drag_palette_active is True
    assert window._drag_palette_button.isEnabled() is False
    assert window._select_radio.isChecked() is True
    assert window._draw_selection_check.isChecked() is False

    margin = window._frame_canvas._view_margin
    zoom = window._frame_canvas._zoom

    def pixel_center(x: int, y: int) -> QPoint:
        return QPoint(margin + x * zoom + zoom // 2, margin + y * zoom + zoom // 2)

    QTest.mousePress(
        window._frame_canvas, Qt.MouseButton.LeftButton, pos=pixel_center(0, 0)
    )
    QTest.mouseMove(window._frame_canvas, pixel_center(1, 1))
    QTest.mouseRelease(
        window._frame_canvas, Qt.MouseButton.LeftButton, pos=pixel_center(1, 1)
    )
    application.processEvents()

    assert window._project.palette == [red, green, blue]
    assert window._frame_doc.palette == [red, green, blue]
    assert window._drag_palette_active is False
    assert window._drag_palette_button.isEnabled() is True
    assert window._line_radio.isChecked() is True
    assert window._draw_selection_check.isChecked() is True
    assert window._frame_doc.selection_rect is None
    assert "Loaded 3 colors" in window.statusBar().currentMessage()
    window._dirty = False
    window.close()
    application.processEvents()


def test_animation_frame_editor_undoes_one_completed_brush_action_at_a_time() -> None:
    application = QApplication.instance() or QApplication([])
    window = AnimationEditorWindow()
    red = (240, 30, 50, 255)
    transparent = (0, 0, 0, 0)
    window._set_color(red)
    window._frame_canvas.show()
    application.processEvents()
    margin = window._frame_canvas._view_margin
    zoom = window._frame_canvas._zoom

    def pixel_center(x: int, y: int) -> QPoint:
        return QPoint(margin + x * zoom + zoom // 2, margin + y * zoom + zoom // 2)

    QTest.mouseClick(
        window._frame_canvas, Qt.MouseButton.LeftButton, pos=pixel_center(0, 0)
    )
    QTest.mouseClick(
        window._frame_canvas, Qt.MouseButton.LeftButton, pos=pixel_center(1, 0)
    )
    track = window._project.tracks[0]
    assert window._project.frame_image(track.id, 0).getpixel((0, 0)) == red
    assert window._project.frame_image(track.id, 0).getpixel((1, 0)) == red
    assert window._undo_last_action_button.text() == "Undo Last Action"

    window._undo_last_action_button.click()
    assert window._project.frame_image(track.id, 0).getpixel((0, 0)) == red
    assert window._project.frame_image(track.id, 0).getpixel((1, 0)) == transparent

    window._undo_action.trigger()
    assert window._project.frame_image(track.id, 0).getpixel((0, 0)) == transparent
    window._redo_action.trigger()
    assert window._project.frame_image(track.id, 0).getpixel((0, 0)) == red

    window._dirty = False
    window.close()
    application.processEvents()


def test_animation_editor_playback_steps_and_preserves_custom_range() -> None:
    application = QApplication.instance() or QApplication([])
    window = AnimationEditorWindow()
    window._range_start_spin.setValue(2)
    window._range_end_spin.setValue(3)
    window._load_frame(1)
    assert window._range_start_spin.value() == 2
    assert window._range_end_spin.value() == 3
    window._advance_playback()
    assert window._current_frame_index == 2
    window._advance_playback()
    assert window._current_frame_index == 1
    window._pause_playback()
    window._dirty = False
    window.close()
    application.processEvents()


def test_animation_editor_ping_pong_playback_bounces_inside_selected_range() -> None:
    application = QApplication.instance() or QApplication([])
    window = AnimationEditorWindow()
    window._playback_mode_combo.setCurrentIndex(
        window._playback_mode_combo.findData("ping_pong")
    )
    window._range_start_spin.setValue(1)
    window._range_end_spin.setValue(4)
    window._load_frame(0)

    visited = []
    for _ in range(7):
        window._advance_playback()
        visited.append(window._current_frame_index)

    assert visited == [1, 2, 3, 2, 1, 0, 1]
    assert window._project.playback_mode == "ping_pong"
    window._pause_playback()
    window._dirty = False
    window.close()
    application.processEvents()


def test_semantic_elf_walk_sheet_builds_four_complete_tracks(
    tmp_path,
) -> None:
    source_path = (
        Path(__file__).parents[1]
        / "assets"
        / "character-forge"
        / "bases"
        / "elf-01"
        / "walk.png"
    )
    with Image.open(source_path) as opened:
        source = opened.convert("RGBA").copy()
    project = create_animation_project_from_sheet(
        source, name="walk", frame_size=(128, 128), fps=10
    )
    for name, y in (("Front", 0), ("Back", 128), ("Right", 256), ("Left", 384)):
        project.add_track(name, FrameSequenceSpec(0, y, 128, 128, 8, 128, 0))
    edited = project.frame_image(project.tracks[0].id, 0)
    edited.putpixel((0, 0), (255, 0, 0, 255))
    project.commit_frame_image(project.tracks[0].id, 0, edited)

    assert project.sheet_size == (1024, 512)
    assert project_to_sheet(project).size == (1024, 512)
    archive = tmp_path / "walk.pfa"
    save_animation_project(project, archive)
    assert (
        load_animation_project(archive).working_sheet.tobytes()
        == project.working_sheet.tobytes()
    )


def test_main_window_animation_route_opens_the_studio() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.open_animation_editor()
    animation_windows = [
        child
        for child in window._tool_windows
        if isinstance(child, AnimationEditorWindow)
    ]
    assert len(animation_windows) == 1
    assert "Opened animation editor" in window.statusBar().currentMessage()
    for child in animation_windows:
        child._dirty = False
        child.close()
    window.close()
    application.processEvents()
