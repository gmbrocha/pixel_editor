from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from src.core.character_forge import create_default_catalog, validate_catalog


ROOT = Path(__file__).parents[1]
ASSET_ROOT = ROOT / "assets" / "character-forge"
BASES = (
    "elf-01",
    "tiefling-female-01",
    "dwarf-male-01",
    "human-muscular-male-01",
)
TARGET_BASES = BASES[1:]
SEQUENCES = ("idle", "walk", "run")
DIRECTIONS = ("front", "back", "right", "left")
FRAME_COUNTS = {"idle": 14, "walk": 8, "run": 8}
FAMILY_SLOT_COUNTS = {
    "torso": 4,
    "outerwear": 4,
    "legwear": 6,
    "hands": 3,
    "feet": 4,
    "headwear": 4,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_25_component_families_are_fitted_to_all_four_bases() -> None:
    generated = json.loads(
        (ASSET_ROOT / "component_families_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert generated["family_count"] == 25
    assert generated["variant_count"] == 100
    assert tuple(generated["bases"]) == BASES
    assert len(generated["families"]) == 25
    assert len({family["id"] for family in generated["families"]}) == 25

    catalog = create_default_catalog()
    validate_catalog(catalog)
    generated_parts = [
        part for part in catalog.parts if "generated_family" in part.tags
    ]
    assert len(catalog.parts) == 107
    assert len(generated_parts) == 100
    assert {
        base_id: sum(part.fit == base_id for part in generated_parts)
        for base_id in BASES
    } == {base_id: 25 for base_id in BASES}
    assert {
        slot: sum(
            part.slot == slot and part.fit == "tiefling-female-01"
            for part in generated_parts
        )
        for slot in FAMILY_SLOT_COUNTS
    } == FAMILY_SLOT_COUNTS

    for family in generated["families"]:
        assert len(family["variants"]) == 4
        assert {variant["fit"] for variant in family["variants"]} == set(BASES)
        for variant in family["variants"]:
            part = catalog.part(variant["id"])
            assert part.fit == variant["fit"]
            assert part.status == "approved"
            assert len(part.color_ramp) == 5
            assert part.ramp_main_color in part.color_ramp
            assert not part.camera_variants


def test_generated_components_have_complete_low_camera_pixel_coverage() -> None:
    catalog = create_default_catalog()
    for part in catalog.parts:
        if "generated_family" not in part.tags:
            continue
        base = catalog.base(part.fit)
        manifest = json.loads(part.manifest_path.read_text(encoding="utf-8"))
        provenance = manifest["provenance"]
        assert provenance["generator"] == "tools/build_character_component_families.py"
        assert provenance["outline"]["widthPixels"] == 1
        assert provenance["cleanup"]["kind"] == "canonical_component_preprocessing"
        assert provenance["cleanup"]["settings"]["max_terminal_spur_length"] == 2
        palette = {
            tuple(bytes.fromhex(color.removeprefix("#")))
            for color in manifest["colorRamp"]["colors"]
        }
        for sequence in SEQUENCES:
            path = part.animations[sequence]
            assert _sha256(path) == provenance["animationSha256"][sequence]
            with Image.open(path) as opened:
                image = opened.convert("RGBA")
            assert image.size == base.animations[sequence].sheet_size
            pixels = np.asarray(image, dtype=np.uint8)
            visible = pixels[..., 3] > 0
            assert np.any(visible)
            assert {
                tuple(color) for color in np.unique(pixels[..., :3][visible], axis=0)
            } <= palette
            for row, direction in enumerate(DIRECTIONS):
                row_alpha = pixels[row * 128:(row + 1) * 128, :, 3]
                assert np.any(row_alpha), (part.id, sequence, direction)
            assert part.coverage[sequence] == DIRECTIONS


def test_target_weight_region_sheets_cover_every_opaque_base_pixel() -> None:
    for base_id in TARGET_BASES:
        for sequence in SEQUENCES:
            region_dir = ASSET_ROOT / "base_regions" / base_id / sequence
            manifest = json.loads(
                (region_dir / f"{sequence}_region_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            assert manifest["kind"] == "weight_derived_character_region_sheet"
            assert not Path(manifest["base_sheet"]).is_absolute()
            assert not Path(manifest["paired_manifest"]).is_absolute()
            assert not Path(manifest["source_blend"]).is_absolute()
            assert manifest["region_ids"] == list(range(1, 33))
            assert manifest["direction_order"] == list(DIRECTIONS)
            assert len(manifest["source_frames"]) == FRAME_COUNTS[sequence]
            region_path = region_dir / f"{sequence}_regions.png"
            preview_path = region_dir / f"{sequence}_regions_preview.png"
            assert _sha256(region_path) == manifest["outputs"][region_path.name]
            assert _sha256(preview_path) == manifest["outputs"][preview_path.name]
            with Image.open(region_path) as opened:
                regions = np.asarray(opened.convert("L"), dtype=np.uint8)
            with Image.open(ASSET_ROOT / "bases" / base_id / f"{sequence}.png") as opened:
                alpha = np.asarray(opened.convert("RGBA"), dtype=np.uint8)[..., 3] > 0
            assert np.array_equal(regions > 0, alpha)
            assert set(np.unique(regions)) == set(range(33))


def test_components_are_low_camera_only_and_isolated_by_fit() -> None:
    catalog = create_default_catalog()
    for base_id in BASES:
        expected = 30 if base_id == "elf-01" else 25
        low = sum(
            len(catalog.parts_for_slot(slot, base_id, "low"))
            for slot in FAMILY_SLOT_COUNTS
        )
        assert low == expected
        assert all(
            not catalog.parts_for_slot(slot, base_id, camera_height)
            for slot in FAMILY_SLOT_COUNTS
            for camera_height in ("top_down", "three_quarter")
        )
        assert all(
            part.fit == base_id
            for slot in FAMILY_SLOT_COUNTS
            for part in catalog.parts_for_slot(slot, base_id, "low")
        )


def test_all_component_family_review_boards_are_present() -> None:
    review_root = ASSET_ROOT / "review" / "component-families"
    for base_id in BASES:
        for sequence in SEQUENCES:
            with Image.open(review_root / f"{base_id}-{sequence}.png") as opened:
                assert opened.size == (880, 880)
