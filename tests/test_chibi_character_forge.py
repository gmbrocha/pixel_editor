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
MANIFEST = ASSET_ROOT / "chibi_manifest.json"
STYLE = ROOT / "animation_images_models" / "chibi_style.json"
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


def test_chibi_manifest_covers_the_complete_forge_matrix() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["kind"] == "canonical_character_forge_sprite_style"
    assert manifest["status"] == "canonical"
    assert manifest["style_id"] == "jrpg_chibi"
    assert manifest["display_name"] == "JRPG"
    assert _sha256(STYLE) == manifest["style_config_sha256"]
    assert tuple(manifest["camera_heights"]) == CAMERA_HEIGHT_ORDER
    assert set(manifest["characters"]) == set(CHARACTERS)
    assert set(manifest["models"]) == set(CHARACTERS)

    for character_id, model in manifest["models"].items():
        assert model["kind"] == "jrpg_rest_retargeted_character_model"
        assert model["character_id"] == character_id
        assert model["method"] == "rest_pose_lbs_rebind"
        assert model["runtime_source_rotation_sha256"] == model[
            "runtime_jrpg_rotation_sha256"
        ]
        assert 2.8 <= model["heads_tall"] <= 4.6

    for character_id, cameras in manifest["characters"].items():
        base_id = CHARACTERS[character_id]
        assert set(cameras) == set(CAMERA_HEIGHT_ORDER)
        for camera_height, camera in cameras.items():
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


def test_jrpg_profile_is_a_rest_retargeted_proportion_contract() -> None:
    style = json.loads(STYLE.read_text(encoding="utf-8"))
    assert style["schema_version"] == 2
    assert style["display_name"] == "JRPG"
    assert style["method"] == "rest_pose_lbs_rebind"
    scales = style["rest_retarget"]["bones"]
    assert scales["Head"] == [1.6, 1.6]
    assert scales["LeftUpLeg"][0] == 0.66
    assert scales["LeftLeg"][0] == 0.64
    assert scales["LeftArm"][0] == 0.74
    assert style["rest_retarget"]["motion_scale"] == 0.68
    assert style["silhouette_outline"] is False
    assert style["palette_size"] == 16
    assert style["framing_scales"]["dwarf_bald_male"] > style["framing_scales"]["elf_bald_female"]


def test_chibi_recipe_composites_generated_parts_and_legacy_defaults_standard() -> None:
    catalog = create_default_catalog()
    validate_catalog(catalog)
    migrated = CharacterRecipe.from_dict(
        {"schema_version": 3, "name": "legacy", "base": "elf-01"}
    )
    assert migrated.sprite_style == "standard"

    for base_id in CHARACTERS.values():
        base = catalog.base(base_id)
        assert base.camera_heights_for_style("jrpg_chibi") == CAMERA_HEIGHT_ORDER
        torso = catalog.parts_for_slot(
            "torso", base_id, "three_quarter", "jrpg_chibi"
        )[0]
        recipe = CharacterRecipe(
            base_id=base_id,
            sprite_style="jrpg_chibi",
            camera_height="three_quarter",
        )
        recipe.parts["torso"] = torso.id
        validate_recipe(catalog, recipe)
        assert recipe.to_dict()["schema_version"] == 4
        assert recipe.to_dict()["sprite_style"] == "jrpg_chibi"
        for animation_id, animation in base.animations.items():
            assert composite_character_animation(
                catalog, recipe, animation_id
            ).size == animation.sheet_size


def test_hand_authored_standard_parts_are_not_offered_as_fake_chibi_fits() -> None:
    catalog = create_default_catalog()
    assert catalog.parts_for_slot(
        "hair", "tiefling-female-01", "low", "standard"
    )
    assert not catalog.parts_for_slot(
        "hair", "tiefling-female-01", "low", "jrpg_chibi"
    )
    assert catalog.parts_for_slot(
        "face", "tiefling-female-01", "low", "standard"
    )
    assert not catalog.parts_for_slot(
        "face", "tiefling-female-01", "low", "jrpg_chibi"
    )
