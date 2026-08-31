from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from src.core.character_forge import (
    CAMERA_HEIGHT_ORDER,
    CharacterRecipe,
    composite_character_animation,
    create_default_catalog,
    validate_catalog,
    validate_recipe,
)

ROOT = Path(__file__).parents[1]
ASSET_ROOT = ROOT / "assets" / "character-forge"
MANIFEST = ASSET_ROOT / "heroic_manifest.json"
STYLE = ROOT / "animation_images_models" / "heroic_style.json"
CHARACTERS = {
    "elf_bald_female": "elf-01",
    "tiefling_bald_female": "tiefling-female-01",
    "dwarf_bald_male": "dwarf-male-01",
    "human_bald_male": "human-muscular-male-01",
}
SEQUENCES = {"idle": 14, "walk": 8, "run": 8}
DIRECTIONS = {"front", "back", "right", "left"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_heroic_manifest_covers_the_complete_forge_matrix() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["kind"] == "canonical_character_forge_sprite_style"
    assert manifest["status"] == "canonical"
    assert manifest["style_id"] == "heroic"
    assert manifest["display_name"] == "Heroic"
    assert _sha256(STYLE) == manifest["style_config_sha256"]
    assert tuple(manifest["camera_heights"]) == CAMERA_HEIGHT_ORDER
    assert set(manifest["characters"]) == set(CHARACTERS)
    assert set(manifest["models"]) == set(CHARACTERS)

    for character_id, model in manifest["models"].items():
        assert model["kind"] == "heroic_authored_character_model"
        assert model["character_id"] == character_id
        assert model["method"] == "rest_pose_lbs_rebind"
        assert 3.5 <= model["heads_tall"] <= 7.0

    for character_id, cameras in manifest["characters"].items():
        assert character_id in CHARACTERS
        assert set(cameras) == set(CAMERA_HEIGHT_ORDER)
        for camera in cameras.values():
            palette_path = ASSET_ROOT / camera["palette"]["file"]
            assert _sha256(palette_path) == camera["palette"]["sha256"]
            with Image.open(palette_path) as palette:
                assert palette.size == (16 * 16, 16)
            assert set(camera["sequences"]) == set(SEQUENCES)
            for sequence_name, frame_count in SEQUENCES.items():
                sequence = camera["sequences"][sequence_name]
                assert sequence["frame_count"] == frame_count
                assert sequence["minimum_alpha_margin"] >= 8
                sheet_path = ASSET_ROOT / sequence["sheet"]
                regions_path = ASSET_ROOT / sequence["regions"]
                assert _sha256(sheet_path) == sequence["sheet_sha256"]
                assert _sha256(regions_path) == sequence["regions_sha256"]
                with Image.open(sheet_path) as opened:
                    sheet = np.asarray(opened.convert("RGBA"), dtype=np.uint8)
                with Image.open(regions_path) as opened:
                    regions = np.asarray(opened.convert("L"), dtype=np.uint8)
                assert sheet.shape == (512, frame_count * 128, 4)
                assert regions.shape == sheet.shape[:2]
                assert set(np.unique(sheet[..., 3])) <= {0, 255}
                assert np.array_equal(regions > 0, sheet[..., 3] > 0)
                assert set(np.unique(regions)) == set(range(33))
                assert set(sequence["gifs"]) == DIRECTIONS
                for gif_record in sequence["gifs"].values():
                    gif_path = ASSET_ROOT / gif_record["file"]
                    assert _sha256(gif_path) == gif_record["sha256"]
                    with Image.open(gif_path) as opened:
                        assert opened.size == (128, 128)
                        assert opened.n_frames == frame_count
                        assert opened.info["loop"] == 0


def test_heroic_style_is_additive_and_base_only() -> None:
    catalog = create_default_catalog()
    validate_catalog(catalog)
    assert catalog.sprite_styles["standard"] == "Standard Pixel"
    assert catalog.sprite_styles["jrpg_chibi"] == "JRPG"
    assert catalog.sprite_styles["heroic"] == "Heroic"

    for base_id in CHARACTERS.values():
        base = catalog.base(base_id)
        assert base.camera_heights_for_style("heroic") == CAMERA_HEIGHT_ORDER
        recipe = CharacterRecipe(
            base_id=base_id,
            sprite_style="heroic",
            camera_height="three_quarter",
        )
        validate_recipe(catalog, recipe)
        assert all(
            not catalog.parts_for_slot(slot, base_id, "three_quarter", "heroic")
            for slot in recipe.parts
        )
        for animation_id, animation in base.animations.items():
            assert base.animation_path(
                animation_id, "three_quarter", "heroic"
            ).is_file()
            assert composite_character_animation(
                catalog, recipe, animation_id
            ).size == animation.sheet_size


def test_heroic_profile_preserves_authored_relative_stature() -> None:
    style = json.loads(STYLE.read_text(encoding="utf-8"))
    assert style["schema_version"] == 2
    assert style["id"] == "heroic"
    assert style["display_name"] == "Heroic"
    assert style["actions"] == {
        "idle": "PF_Idle_HeroicJRPG",
        "walk": "PF_Walk_HeroicJRPG",
        "run": "PF_Run_HeroicJRPG",
    }
    assert style["silhouette_outline"] is False
    assert style["palette_size"] == 16
    assert style["framing_scales"]["dwarf_bald_male"] > 1.3
    assert style["framing_scales"]["elf_bald_female"] == 1.0
