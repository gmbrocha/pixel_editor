from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from src.core.mannequin_semantics import REGION_BY_NAME
from src.core.semantic_sprite_package import (
    SemanticSpriteSettings,
    check_semantic_sprite_package,
    generate_semantic_sprite_package,
)


def _paired_fixture(
    root: Path,
    *,
    frame_count: int = 8,
    sequence_name: str = "walk",
) -> Path:
    beauty_paths: list[str] = []
    semantic_paths: list[str] = []
    torso = REGION_BY_NAME["chest_front"]
    hand = REGION_BY_NAME["left_hand"]
    for index in range(frame_count):
        beauty = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        draw = ImageDraw.Draw(beauty)
        draw.rectangle((4, 2, 11, 13), fill=(190, 140 + index, 120, 255))
        # Encode the frame index into four aligned 2x2 silhouette notches so
        # GIF encoders cannot legally coalesce a long fixture into repeats.
        for bit in range(4):
            if index & (1 << bit):
                x = 4 + (bit * 2)
                draw.rectangle((x, 4, x + 1, 5), fill=(0, 0, 0, 0))
        beauty_path = root / "beauty" / f"frame_{index:02d}.png"
        beauty_path.parent.mkdir(parents=True, exist_ok=True)
        beauty.save(beauty_path)
        beauty_paths.append(str(beauty_path))

        semantic = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        pixels = np.asarray(semantic).copy()
        pixels[2:14, 4:12] = torso.color
        # A small but intentional second region exercises deterministic rescue.
        pixels[8:12, 10:12] = hand.color
        for bit in range(4):
            if index & (1 << bit):
                x = 4 + (bit * 2)
                pixels[4:6, x : x + 2] = (0, 0, 0, 0)
        semantic = Image.fromarray(pixels, "RGBA")
        semantic_path = root / "semantic" / f"frame_{index:02d}.png"
        semantic_path.parent.mkdir(parents=True, exist_ok=True)
        semantic.save(semantic_path)
        semantic_paths.append(str(semantic_path))

    manifest = {
        "schema_version": 1,
        "kind": "paired_semantic_sprite_render",
        "blend": "fixture.blend",
        "blend_sha256": "fixture",
        "direction_order": ["front"],
        "sequences": {
            sequence_name: {
                "action": "PF_Walk_Test",
                "source_frames": list(range(1, frame_count + 1)),
                "directions": {"front": beauty_paths},
                "semantic_directions": {"front": semantic_paths},
            }
        },
    }
    path = root / "paired.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_semantic_package_builds_exact_id_and_slot_maps(tmp_path: Path) -> None:
    source = tmp_path / "source"
    manifest_path = _paired_fixture(source)
    output = tmp_path / "package"
    settings = SemanticSpriteSettings(
        cell_size=8,
        palette_size=4,
        cleanup_threshold=0,
        thin_region_source_pixels=2,
    )
    manifest = generate_semantic_sprite_package(manifest_path, output, settings)

    assert Image.open(output / "walk.png").size == (64, 8)
    regions = Image.open(output / "walk_regions.png")
    assert regions.mode == "L"
    assert set(regions.getdata()) <= {0, 7, 21}
    assert 7 in set(regions.getdata())
    assert 21 in set(regions.getdata())
    assert Image.open(output / "walk_regions_preview.png").size == (64, 8)
    torso = np.asarray(Image.open(output / "slots" / "walk_slot_torso.png"))
    hands = np.asarray(Image.open(output / "slots" / "walk_slot_hands.png"))
    assert torso.max() == 255
    assert hands.max() == 255
    assert Image.open(output / "gifs" / "walk_front.gif").size == (8, 8)
    assert len(manifest["frames"]) == 8
    assert manifest["sheet_dimensions"] == [64, 8]
    assert manifest["staged"] is True
    assert check_semantic_sprite_package(manifest_path, output, settings) == []


def test_semantic_package_rejects_incomplete_semantic_frames(tmp_path: Path) -> None:
    manifest_path = _paired_fixture(tmp_path / "source")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["sequences"]["walk"]["semantic_directions"]["front"].pop()
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    try:
        generate_semantic_sprite_package(manifest_path, tmp_path / "output")
    except ValueError as error:
        assert "8 semantic renders" in str(error)
    else:
        raise AssertionError("Incomplete semantic frames were accepted")


def test_semantic_package_supports_thirteen_frame_idle(tmp_path: Path) -> None:
    manifest_path = _paired_fixture(
        tmp_path / "source", frame_count=13, sequence_name="idle"
    )
    output = tmp_path / "package"
    manifest = generate_semantic_sprite_package(
        manifest_path,
        output,
        SemanticSpriteSettings(cell_size=8, palette_size=4, cleanup_threshold=0),
        sequence_name="idle",
    )

    assert Image.open(output / "idle.png").size == (104, 8)
    assert Image.open(output / "idle_regions.png").size == (104, 8)
    assert Image.open(output / "gifs" / "idle_front.gif").n_frames == 13
    assert manifest["sequence"] == "idle"
    assert manifest["source_frames"] == list(range(1, 14))
    assert manifest["sheet_dimensions"] == [104, 8]


def test_semantic_package_preserves_exact_idle_hold_durations(tmp_path: Path) -> None:
    manifest_path = _paired_fixture(
        tmp_path / "source", frame_count=26, sequence_name="idle"
    )
    output = tmp_path / "package"
    manifest = generate_semantic_sprite_package(
        manifest_path,
        output,
        SemanticSpriteSettings(
            cell_size=8,
            palette_size=4,
            cleanup_threshold=0,
            fps=12,
            frame_duration_overrides=((11, 1500), (24, 1500)),
        ),
        sequence_name="idle",
    )
    assert manifest["frame_durations_ms"][10] == 1500
    assert manifest["frame_durations_ms"][23] == 1500
    with Image.open(output / "gifs" / "idle_front.gif") as opened:
        durations = []
        for index in range(opened.n_frames):
            opened.seek(index)
            durations.append(opened.info["duration"])
    assert durations[10] == 1500
    assert durations[23] == 1500
    assert set(durations[:10]) == {80}
