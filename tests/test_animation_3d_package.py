from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication, QFileDialog

from src.core.animation_3d_package import (
    Animation3DPackageError,
    create_animation_project_from_3d_package,
    load_animation_3d_package,
    package_summary,
)
from src.ui.animation_editor_window import AnimationEditorWindow
from tools.blender.export_pixel_animation import _sample_frames, _semantic_for_bone


FRAME_SIZE = (4, 4)
BACKGROUND = (0, 0, 0, 0)
TORSO = (255, 0, 0, 255)


def _write_package(root: Path) -> dict:
    directions = []
    for direction_name, frame_count in (("Front", 2), ("Right", 1)):
        direction_id = direction_name.casefold()
        frames = []
        for index in range(frame_count):
            prefix = f"{direction_id}/{index:03d}"
            visible_relative = f"visible/{prefix}.png"
            regions_relative = f"regions/{prefix}.png"
            silhouette_relative = f"silhouettes/{prefix}.png"
            anchors_relative = f"anchors/{prefix}.json"
            visible = Image.new(
                "RGBA", FRAME_SIZE, (20 + index * 40, 80, 120, 255)
            )
            regions = Image.new("RGBA", FRAME_SIZE, BACKGROUND)
            regions.putpixel((1, 1), TORSO)
            silhouette = Image.new("RGBA", FRAME_SIZE, BACKGROUND)
            silhouette.putpixel((1, 1), (255, 255, 255, 255))
            for relative, image in (
                (visible_relative, visible),
                (regions_relative, regions),
                (silhouette_relative, silhouette),
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                image.save(path)
            anchors_path = root / anchors_relative
            anchors_path.parent.mkdir(parents=True, exist_ok=True)
            anchors_path.write_text(
                json.dumps(
                    {
                        "anchors": {
                            "head": [1.5 + index, 0.5],
                            "foot_left": [0.49, 3.49],
                        }
                    }
                ),
                encoding="utf-8",
            )
            frames.append(
                {
                    "index": index,
                    "sourceTime": index / frame_count,
                    "visible": visible_relative,
                    "regions": regions_relative,
                    "silhouette": silhouette_relative,
                    "anchors": anchors_relative,
                }
            )
        directions.append(
            {"id": direction_id, "name": direction_name, "frames": frames}
        )
    manifest = {
        "kind": "pixel-forge-3d-animation",
        "schemaVersion": 1,
        "name": "pilot-human",
        "animation": "run",
        "frameSize": list(FRAME_SIZE),
        "fps": 8,
        "playbackMode": "loop",
        "regions": {
            "background": list(BACKGROUND),
            "torso": list(TORSO),
        },
        "directions": directions,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def test_load_3d_package_validates_structural_passes_and_builds_project(
    tmp_path: Path,
) -> None:
    _write_package(tmp_path)

    package = load_animation_3d_package(tmp_path)
    project = create_animation_project_from_3d_package(
        package, palette=[(1, 2, 3, 255)]
    )

    assert package.name == "pilot-human"
    assert package.animation == "run"
    assert package.frame_size == FRAME_SIZE
    assert package.frame_count == 3
    assert [direction.id for direction in package.directions] == ["front", "right"]
    assert "2 directions, 3 frames" in package_summary(package)
    assert project.sheet_size == (8, 8)
    assert project.name == "pilot-human-run"
    assert project.palette == [(1, 2, 3, 255)]
    assert [track.name for track in project.tracks] == ["Front", "Right"]
    assert [len(track.frames) for track in project.tracks] == [2, 1]
    assert project.frame_image(project.tracks[0].id, 0).getpixel((0, 0)) == (
        20,
        80,
        120,
        255,
    )
    assert project.frame_image(project.tracks[1].id, 0).getpixel((0, 0)) == (
        20,
        80,
        120,
        255,
    )
    assert project.working_sheet.crop((4, 4, 8, 8)).getbbox() is None
    anchors = project.tracks[0].frames[0].anchors
    assert [(anchor.name, anchor.x, anchor.y) for anchor in anchors] == [
        ("foot_left", 0, 3),
        ("head", 2, 1),
    ]


def test_load_3d_package_rejects_unknown_region_pixels(tmp_path: Path) -> None:
    _write_package(tmp_path)
    region_path = tmp_path / "regions/front/000.png"
    with Image.open(region_path) as opened:
        regions = opened.convert("RGBA")
    regions.putpixel((2, 2), (1, 2, 3, 255))
    regions.save(region_path)

    with pytest.raises(Animation3DPackageError, match="unknown RGBA colors"):
        load_animation_3d_package(tmp_path)


def test_load_3d_package_rejects_paths_outside_package(tmp_path: Path) -> None:
    manifest = _write_package(tmp_path)
    manifest["directions"][0]["frames"][0]["visible"] = "../outside.png"
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(Animation3DPackageError, match="escapes the package root"):
        load_animation_3d_package(tmp_path)


def test_animation_studio_imports_validated_3d_package(
    tmp_path: Path, monkeypatch
) -> None:
    _write_package(tmp_path)
    application = QApplication.instance() or QApplication([])
    window = AnimationEditorWindow()
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(tmp_path),
    )

    window._open_3d_package()

    assert window._project.name == "pilot-human-run"
    assert [track.name for track in window._project.tracks] == ["Front", "Right"]
    assert window._project.frame_width == 4
    assert "Imported pilot-human / run" in window.statusBar().currentMessage()
    window._dirty = False
    window.close()
    application.processEvents()


def test_blender_exporter_maps_common_mixamo_bones_and_excludes_loop_endpoint() -> None:
    class Action:
        frame_range = (10.0, 30.0)

    assert _semantic_for_bone("mixamorig:Head") == "head"
    assert _semantic_for_bone("mixamorig:LeftUpLeg") == "thigh_left"
    assert _semantic_for_bone("mixamorig:LeftLeg") == "shin_left"
    assert _semantic_for_bone("mixamorig:LeftFoot") == "foot_left"
    assert _semantic_for_bone("mixamorig:RightForeArm") == "lower_arm_right"
    assert _semantic_for_bone("mixamorig:Spine2") == "torso"
    assert _sample_frames(Action(), 4) == [10.0, 15.0, 20.0, 25.0]
