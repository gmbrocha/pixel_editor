from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from src.core.component_cleanup import cleanup_component_frame


PALETTE = ((10, 20, 30), (40, 50, 60), (70, 80, 90))
ROOT = Path(__file__).parents[1]
BUNDLE_ROOT = ROOT / "animation_images_models" / "component_cleanup_v2"


def _image(pixels: np.ndarray) -> Image.Image:
    return Image.fromarray(pixels.astype(np.uint8), "RGBA")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_cleanup_removes_only_small_detached_islands() -> None:
    pixels = np.zeros((16, 16, 4), dtype=np.uint8)
    pixels[4:12, 4:12] = (*PALETTE[1], 255)
    pixels[1, 1] = (*PALETTE[0], 255)
    pixels[1:4, 13:16] = (*PALETTE[0], 255)
    result, report = cleanup_component_frame(
        _image(pixels), outline_rgb=PALETTE[0], palette=PALETTE,
        max_island_area=4, max_island_ratio=0.08,
    )
    output = np.asarray(result)
    assert output[1, 1, 3] == 0
    assert np.count_nonzero(output[1:4, 13:16, 3]) == 5
    assert report.removed_islands == 1
    assert report.removed_island_pixels == 1


def test_cleanup_chamfers_only_declared_outline_convex_corners() -> None:
    pixels = np.zeros((9, 9, 4), dtype=np.uint8)
    pixels[2:7, 2:7] = (*PALETTE[1], 255)
    pixels[2, 2:7] = (*PALETTE[0], 255)
    pixels[6, 2:7] = (*PALETTE[0], 255)
    pixels[2:7, 2] = (*PALETTE[0], 255)
    pixels[2:7, 6] = (*PALETTE[0], 255)
    result, report = cleanup_component_frame(
        _image(pixels), outline_rgb=PALETTE[0], palette=PALETTE,
    )
    output = np.asarray(result)
    assert output[2, 2, 3] == 0
    assert output[2, 6, 3] == 0
    assert output[6, 2, 3] == 0
    assert output[6, 6, 3] == 0
    assert np.all(output[3:6, 3:6, 3] == 255)
    assert report.chamfered_outline_pixels == 4


def test_cleanup_can_preserve_two_intentional_pieces() -> None:
    pixels = np.zeros((20, 20, 4), dtype=np.uint8)
    pixels[4:14, 3:10] = (*PALETTE[1], 255)
    pixels[7:10, 15:18] = (*PALETTE[0], 255)
    pixels[1, 1] = (*PALETTE[0], 255)
    result, report = cleanup_component_frame(
        _image(pixels), outline_rgb=PALETTE[0], palette=PALETTE,
        protected_components=2,
    )
    output = np.asarray(result)
    assert np.count_nonzero(output[7:10, 15:18, 3]) == 5
    assert output[1, 1, 3] == 0
    assert report.removed_islands == 1


def test_cleanup_removes_small_remote_outlier_even_when_ratio_is_not_tiny() -> None:
    pixels = np.zeros((32, 32, 4), dtype=np.uint8)
    pixels[12:20, 12:20] = (*PALETTE[1], 255)
    pixels[1:3, 1:6] = (*PALETTE[0], 255)
    result, report = cleanup_component_frame(
        _image(pixels), outline_rgb=PALETTE[0], palette=PALETTE,
    )
    output = np.asarray(result)
    assert np.count_nonzero(output[1:3, 1:6, 3]) == 0
    assert report.removed_island_pixels == 10


def test_cleanup_preserves_nearby_substantial_split_garment_piece() -> None:
    pixels = np.zeros((32, 32, 4), dtype=np.uint8)
    pixels[10:20, 10:20] = (*PALETTE[1], 255)
    pixels[12:17, 22:26] = (*PALETTE[1], 255)
    result, report = cleanup_component_frame(
        _image(pixels), outline_rgb=PALETTE[0], palette=PALETTE,
        max_island_area=24,
    )
    output = np.asarray(result)
    assert np.count_nonzero(output[12:17, 22:26, 3]) > 0
    assert report.removed_islands == 0


def test_cleanup_island_result_is_stable_after_outline_chamfer() -> None:
    pixels = np.zeros((24, 24, 4), dtype=np.uint8)
    pixels[8:17, 8:17] = (*PALETTE[1], 255)
    pixels[7, 7] = (*PALETTE[0], 255)
    pixels[7, 8] = (*PALETTE[0], 255)
    first, _report = cleanup_component_frame(
        _image(pixels), outline_rgb=PALETTE[0], palette=PALETTE,
    )
    second, second_report = cleanup_component_frame(
        first, outline_rgb=PALETTE[0], palette=PALETTE,
    )
    assert second_report.removed_islands == 0
    assert np.count_nonzero(np.asarray(second)[..., 3]) <= np.count_nonzero(
        np.asarray(first)[..., 3]
    )


def test_cleanup_fills_only_tiny_enclosed_transparency() -> None:
    pixels = np.zeros((12, 12, 4), dtype=np.uint8)
    pixels[1:11, 1:11] = (*PALETTE[1], 255)
    pixels[4, 4] = 0
    pixels[7:9, 7:9] = 0
    result, report = cleanup_component_frame(
        _image(pixels), outline_rgb=PALETTE[0], palette=PALETTE,
        max_hole_area=2,
    )
    output = np.asarray(result)
    assert tuple(output[4, 4]) == (*PALETTE[1], 255)
    assert np.all(output[7:9, 7:9, 3] == 0)
    assert report.filled_holes == 1
    assert report.filled_hole_pixels == 1


def test_cleanup_removes_one_and_two_pixel_terminal_spurs() -> None:
    pixels = np.zeros((24, 24, 4), dtype=np.uint8)
    pixels[6:12, 3:8] = (*PALETTE[1], 255)
    pixels[5, 5] = (*PALETTE[0], 255)
    pixels[13:19, 14:19] = (*PALETTE[1], 255)
    pixels[11:13, 16] = (*PALETTE[0], 255)
    result, report = cleanup_component_frame(
        _image(pixels), outline_rgb=PALETTE[2], palette=PALETTE,
    )
    output = np.asarray(result)
    assert output[5, 5, 3] == 0
    assert np.count_nonzero(output[11:13, 16, 3]) == 0
    assert np.all(output[6:12, 3:8, 3] == 255)
    assert np.all(output[13:19, 14:19, 3] == 255)
    assert report.removed_spurs == 2
    assert report.removed_spur_pixels == 3


def test_cleanup_preserves_narrow_terminal_shape_without_broad_attachment() -> None:
    pixels = np.zeros((16, 16, 4), dtype=np.uint8)
    pixels[4:12, 8] = (*PALETTE[1], 255)
    pixels[10:12, 7:10] = (*PALETTE[1], 255)
    result, report = cleanup_component_frame(
        _image(pixels), outline_rgb=PALETTE[2], palette=PALETTE,
    )
    output = np.asarray(result)
    assert np.all(output[4:10, 8, 3] == 255)
    assert report.removed_spur_pixels == 0


def test_cleanup_clears_hidden_rgb_and_preserves_palette() -> None:
    pixels = np.zeros((8, 8, 4), dtype=np.uint8)
    pixels[..., :3] = (255, 0, 255)
    pixels[2:6, 2:6] = (*PALETTE[1], 255)
    result, _report = cleanup_component_frame(
        _image(pixels), outline_rgb=PALETTE[0], palette=PALETTE,
    )
    output = np.asarray(result)
    assert np.all(output[output[..., 3] == 0, :3] == 0)
    assert {
        tuple(color)
        for color in np.unique(output[output[..., 3] > 0, :3], axis=0)
    } <= set(PALETTE)


def test_cleanup_review_bundle_contains_300_editable_sheets() -> None:
    bundle = json.loads(
        (BUNDLE_ROOT / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    assert bundle["kind"] == "component_cleanup_review_bundle"
    assert bundle["status"] == "editable_mirror_of_promoted_baseline"
    assert bundle["family_count"] == 25
    assert bundle["variant_count"] == 100
    assert bundle["sheet_count"] == 300
    assert len(bundle["variants"]) == 100
    assert len(bundle["review_boards"]) == 12
    assert bundle["base_sprites"]["base_count"] == 4
    assert bundle["base_sprites"]["sheet_count"] == 12
    assert bundle["cleanup_totals"]["removed_islands"] > 0
    assert bundle["cleanup_totals"]["chamfered_outline_pixels"] > 0
    assert bundle["cleanup_totals"]["removed_spur_pixels"] > 0
    assert bundle["cleanup_totals"]["filled_holes"] > 0

    expected_sizes = {
        "idle": (1792, 512),
        "walk": (1024, 512),
        "run": (1024, 512),
    }
    base_manifest_path = BUNDLE_ROOT / bundle["base_sprites"]["manifest"]
    assert _sha256(base_manifest_path) == bundle["base_sprites"]["manifest_sha256"]
    base_manifest = json.loads(base_manifest_path.read_text(encoding="utf-8"))
    assert base_manifest["camera_height"] == "low"
    assert len(base_manifest["bases"]) == 4
    for base_id, base in base_manifest["bases"].items():
        for sequence, expected_size in expected_sizes.items():
            record = base["animations"][sequence]
            copied = BUNDLE_ROOT / record["file"]
            source = ROOT / record["source"]
            assert copied.read_bytes() == source.read_bytes()
            assert _sha256(copied) == record["sha256"] == record["source_sha256"]
            with Image.open(copied) as opened:
                assert opened.size == expected_size
    for variant in bundle["variants"]:
        manifest_path = BUNDLE_ROOT / variant["manifest"]
        assert _sha256(manifest_path) == variant["manifest_sha256"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["cleanup_settings"]["protected_largest_components"] == 1
        assert manifest["cleanup_settings"]["max_terminal_spur_length"] == 2
        assert manifest["cleanup_settings"]["source_already_preprocessed"] is True
        palette = {
            tuple(bytes.fromhex(color.removeprefix("#")))
            for color in manifest["palette"]["colors"]
        }
        source_manifest = ROOT / "assets" / "character-forge" / manifest["source_manifest"]
        source = json.loads(source_manifest.read_text(encoding="utf-8"))
        for sequence, expected_size in expected_sizes.items():
            output_path = manifest_path.parent / f"{sequence}.png"
            assert _sha256(output_path) == manifest["output_sha256"][sequence]
            source_path = source_manifest.parent / source["animations"][sequence]
            assert _sha256(source_path) == manifest["source_sha256"][sequence]
            assert output_path.read_bytes() == source_path.read_bytes()
            with Image.open(output_path) as opened:
                assert opened.size == expected_size
                pixels = np.asarray(opened.convert("RGBA"), dtype=np.uint8)
            assert set(np.unique(pixels[..., 3])) <= {0, 255}
            assert np.all(pixels[pixels[..., 3] == 0, :3] == 0)
            assert {
                tuple(color)
                for color in np.unique(pixels[pixels[..., 3] > 0, :3], axis=0)
            } <= palette
