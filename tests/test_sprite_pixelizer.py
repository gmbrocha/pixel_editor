from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image
import pytest

from src.core.sprite_pixelizer import (
    SpritePixelizationSettings,
    check_pixel_sprite_sheets,
    generate_pixel_sprite_sheets,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: Path, color: tuple[int, int, int, int], accent: tuple[int, int, int, int]) -> None:
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for y in range(1, 7):
        for x in range(2, 6):
            image.putpixel((x, y), color)
    image.putpixel((3, 2), accent)
    image.putpixel((1, 1), (255, 0, 255, 40))
    image.save(path)


def _manifest(tmp_path: Path) -> tuple[Path, list[Path]]:
    paths = [tmp_path / f"source_{index}.png" for index in range(4)]
    colors = [
        ((210, 170, 150, 255), (90, 70, 65, 255)),
        ((195, 150, 130, 255), (70, 65, 68, 255)),
        ((130, 130, 135, 255), (225, 205, 190, 255)),
        ((105, 105, 110, 255), (180, 135, 120, 255)),
    ]
    for path, (color, accent) in zip(paths, colors, strict=True):
        _source(path, color, accent)
    manifest = {
        "schema_version": 1,
        "blend": "fixture.blend",
        "direction_order": ["front", "back"],
        "sequences": {
            "run": {
                "action": "PF_Run_Test",
                "source_frames": [1, 2],
                "directions": {
                    "front": [str(paths[0].resolve()), str(paths[1].resolve())],
                    "back": [str(paths[2].resolve()), str(paths[3].resolve())],
                },
            }
        },
    }
    manifest_path = tmp_path / "sprite_render_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, paths


def test_pixelizer_uses_shared_palette_binary_alpha_and_fixed_layout(tmp_path: Path) -> None:
    manifest_path, source_paths = _manifest(tmp_path)
    source_hashes = [_digest(path) for path in source_paths]
    output_dir = tmp_path / "pixel"
    settings = SpritePixelizationSettings(
        cell_size=4,
        palette_size=4,
        alpha_threshold=112,
        cleanup_threshold=0,
        min_cluster_percent=0.0,
        min_perceptual_distance=0.0,
    )

    manifest = generate_pixel_sprite_sheets(manifest_path, output_dir, settings)

    assert [_digest(path) for path in source_paths] == source_hashes
    assert manifest["direction_order"] == ["front", "back"]
    assert manifest["sequences"]["run"]["action"] == "PF_Run_Test"
    assert manifest["sequences"]["run"]["dimensions"] == [8, 8]
    assert len(manifest["palette"]) == 4

    palette = {tuple(color) for color in manifest["palette"]}
    sheet_path = output_dir / manifest["sequences"]["run"]["sheet"]
    with Image.open(sheet_path) as opened:
        sheet = opened.convert("RGBA")
    assert sheet.size == (8, 8)
    assert {pixel[3] for pixel in sheet.getdata()} <= {0, 255}
    assert {pixel for pixel in sheet.getdata() if pixel[3] > 0} <= palette
    assert (255, 0, 255, 255) not in palette
    preview_path = output_dir / manifest["sequences"]["run"]["previews"]["front"]
    with Image.open(preview_path) as preview:
        assert preview.n_frames == 2
        assert preview.info["duration"] == 100


def test_pixelizer_check_detects_output_changes(tmp_path: Path) -> None:
    manifest_path, _source_paths = _manifest(tmp_path)
    output_dir = tmp_path / "pixel"
    settings = SpritePixelizationSettings(
        cell_size=4,
        palette_size=4,
        cleanup_threshold=0,
        min_cluster_percent=0.0,
        min_perceptual_distance=0.0,
    )
    manifest = generate_pixel_sprite_sheets(manifest_path, output_dir, settings)

    assert check_pixel_sprite_sheets(manifest_path, output_dir, settings) == []

    sheet_path = output_dir / manifest["sequences"]["run"]["sheet"]
    with Image.open(sheet_path) as opened:
        changed = opened.convert("RGBA")
    changed.putpixel((0, 0), (255, 0, 0, 255))
    changed.save(sheet_path)

    mismatches = check_pixel_sprite_sheets(manifest_path, output_dir, settings)
    assert manifest["sequences"]["run"]["sheet"] in mismatches


def test_pixelizer_rejects_incomplete_direction_rows(tmp_path: Path) -> None:
    manifest_path, _source_paths = _manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sequences"]["run"]["directions"]["back"].pop()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="run/back has 1 renders; expected 2"):
        generate_pixel_sprite_sheets(manifest_path, tmp_path / "pixel")
