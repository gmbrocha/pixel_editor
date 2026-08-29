from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from src.core.character_forge import (
    CAMERA_HEIGHT_ORDER,
    CHARACTER_SLOTS,
    CharacterForgeError,
    CharacterRecipe,
    composite_character_animation,
    create_default_catalog,
    create_default_recipe,
    export_character,
    extract_character_frame,
    load_base_animation,
    load_part_animation,
    load_part_render_layer,
    load_recipe,
    randomize_recipe,
    recolor_part_ramp,
    save_recipe,
    validate_catalog,
    validate_recipe,
)
from src.ui.character_forge_window import CharacterForgeWindow
from src.ui.main_window import MainWindow


ROOT = Path(__file__).parents[1]
ASSET_ROOT = ROOT / "assets" / "character-forge"
PART_IDS = {
    "elf-basic-linen-shirt": "torso",
    "elf-simple-work-vest": "outerwear",
    "elf-basic-trousers": "legwear",
    "elf-plain-leather-gloves": "hands",
    "elf-tall-work-boots": "feet",
}


def _pixels(image: Image.Image):
    return (
        image.get_flattened_data()
        if hasattr(image, "get_flattened_data")
        else image.getdata()
    )


def test_catalog_contains_all_approved_motion_bases() -> None:
    catalog = create_default_catalog()
    validate_catalog(catalog)
    assert {base.id for base in catalog.bases} == {
        "elf-01",
        "tiefling-female-01",
        "dwarf-male-01",
        "human-muscular-male-01",
    }
    base = catalog.base("elf-01")
    assert base.name == "Elf Female Base"
    discovered_parts = {part.id: part.slot for part in catalog.parts}
    assert PART_IDS.items() <= discovered_parts.items()
    assert not (ASSET_ROOT / "bases" / "human-01").exists()
    assert not (ASSET_ROOT / "bases" / "human-less-muscular-male-01").exists()
    assert not (ASSET_ROOT / "workbench").exists()
    assert not (ROOT / "art_pipeline").exists()

    expected = {
        "idle": ((1792, 512), 14, 6),
        "walk": ((1024, 512), 8, 10),
        "run": ((1024, 512), 8, 10),
    }
    for character_base in catalog.bases:
        assert character_base.camera_heights == CAMERA_HEIGHT_ORDER
        for animation_id, (sheet_size, frame_count, fps) in expected.items():
            animation = character_base.animations[animation_id]
            assert animation.sheet_size == sheet_size
            assert animation.frame_size == (128, 128)
            assert animation.frames_per_direction == frame_count
            assert animation.fps == fps
            assert animation.direction_rows == {
                "front": 0, "back": 1, "right": 2, "left": 3
            }
            assert all(
                animation.playback_frames(direction) == tuple(range(frame_count))
                for direction in animation.directions
            )
            assert set(animation.camera_variants) == set(CAMERA_HEIGHT_ORDER)
            for camera_height in CAMERA_HEIGHT_ORDER:
                assert character_base.animation_path(
                    animation_id, camera_height
                ).is_file()
        idle = character_base.animations["idle"]
        assert len(idle.frame_durations_ms) == 14
        assert idle.frame_duration_ms(5) == 1500
        assert idle.frame_duration_ms(12) == 1500
        assert all(
            duration == 167
            for index, duration in enumerate(idle.frame_durations_ms)
            if index not in {5, 12}
        )
    assert all(catalog.part(part_id).fit == "elf-01" for part_id in PART_IDS)


def test_components_cannot_be_applied_to_a_different_body_base() -> None:
    catalog = create_default_catalog()
    recipe = create_default_recipe("invalid-fit")
    recipe.base_id = "tiefling-female-01"
    recipe.parts["torso"] = "elf-basic-linen-shirt"
    with pytest.raises(CharacterForgeError, match="fits 'elf-01'"):
        validate_recipe(catalog, recipe)


def test_semantic_art_region_previews_and_gifs_are_installed() -> None:
    catalog = create_default_catalog()
    base = catalog.base("elf-01")
    for animation_id, animation in base.animations.items():
        semantic = ASSET_ROOT / "semantic" / "elf-01" / animation_id
        manifest = json.loads(
            (semantic / f"{animation_id}_manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["sequence"] == animation_id
        assert manifest["sheet_dimensions"] == list(animation.sheet_size)
        assert len(manifest["source_frames"]) == animation.frames_per_direction
        assert (semantic / f"{animation_id}.png").read_bytes() == (
            base.animation_path(animation_id).read_bytes()
        )
        with Image.open(semantic / f"{animation_id}_regions.png") as opened:
            regions = np.asarray(opened.convert("L"))
        with Image.open(base.animation_path(animation_id)) as opened:
            alpha = np.asarray(opened.convert("RGBA"))[..., 3] > 0
        assert regions.shape == alpha.shape
        assert np.array_equal(regions > 0, alpha)
        assert set(np.unique(regions)) <= set(range(33))
        assert (semantic / f"{animation_id}_regions_preview.png").is_file()
        for direction in animation.directions:
            gif = semantic / "gifs" / f"{animation_id}_{direction}.gif"
            with Image.open(gif) as opened:
                assert opened.size == (128, 128)
                assert opened.n_frames >= 2


def test_five_region_derived_parts_cover_every_animation_and_direction() -> None:
    catalog = create_default_catalog()
    base = catalog.base("elf-01")
    for part_id in PART_IDS:
        part = catalog.part(part_id)
        assert part.status == "approved"
        assert part.fit == "elf-01"
        manifest = json.loads(part.manifest_path.read_text(encoding="utf-8"))
        assert manifest["provenance"]["outline"]["widthPixels"] == 1
        assert set(part.animations) == set(base.animations)
        assert len(part.color_ramp) == 5
        assert part.ramp_main_color in part.color_ramp
        for animation_id, animation in base.animations.items():
            overlay = load_part_animation(catalog, part.id, animation_id)
            assert overlay.size == animation.sheet_size
            assert overlay.getchannel("A").getbbox() is not None
            assert part.coverage[animation_id] == (
                "front", "back", "right", "left"
            )
            for direction in animation.directions:
                row = animation.direction_rows[direction]
                row_box = (
                    0, row * 128, animation.sheet_size[0], (row + 1) * 128
                )
                assert overlay.crop(row_box).getchannel("A").getbbox() is not None


def test_every_starter_part_changes_idle_walk_and_run() -> None:
    catalog = create_default_catalog()
    base = catalog.base("elf-01")
    for part_id in PART_IDS:
        part = catalog.part(part_id)
        recipe = create_default_recipe(part.id)
        recipe.parts[part.slot] = part.id
        for animation_id, animation in base.animations.items():
            naked = load_base_animation(catalog, base.id, animation_id)
            dressed = composite_character_animation(catalog, recipe, animation_id)
            assert dressed.size == naked.size
            assert dressed.tobytes() != naked.tobytes()
            for direction in animation.directions:
                changed = False
                for frame_index in range(animation.frame_count(direction)):
                    changed |= (
                        extract_character_frame(
                            dressed, animation, direction, frame_index
                        ).tobytes()
                        != extract_character_frame(
                            naked, animation, direction, frame_index
                        ).tobytes()
                    )
                assert changed, (part.id, animation_id, direction)


def test_tiefling_long_hair_prototype_is_front_run_low_only() -> None:
    catalog = create_default_catalog()
    validate_catalog(catalog)
    part_id = "tiefling-long-hair-run-front-prototype"
    part = catalog.part(part_id)
    assert part.status == "incomplete"
    assert part.fit == "tiefling-female-01"
    assert part.slot == "hair"
    assert set(part.render_layers) == {"hair_back", "hair_front"}
    assert part.coverage == {"idle": (), "walk": (), "run": ("front",)}
    assert part in catalog.parts_for_slot("hair", "tiefling-female-01", "low")
    assert part not in catalog.parts_for_slot("hair", "elf-01", "low")
    assert part not in catalog.parts_for_slot(
        "hair", "tiefling-female-01", "three_quarter"
    )

    recipe = create_default_recipe("hair-prototype")
    recipe.base_id = "tiefling-female-01"
    recipe.camera_height = "low"
    recipe.parts["hair"] = part_id
    validate_recipe(catalog, recipe)
    source_path = (
        ROOT / "animation_images_models" / "component_cleanup_v2"
        / "new_hand_authored" / "teifling_long_hair_run_front_only_third_edit.png"
    )
    with Image.open(source_path) as opened:
        approved = opened.convert("RGBA")
    assert load_part_render_layer(
        catalog, part_id, "hair_front", "run"
    ).tobytes() == approved.tobytes()
    for animation_id in ("idle", "walk", "run"):
        assert load_part_render_layer(
            catalog, part_id, "hair_back", animation_id
        ).getchannel("A").getbbox() is None
    for animation_id in ("idle", "walk", "run"):
        base = load_base_animation(catalog, recipe.base_id, animation_id)
        result = composite_character_animation(catalog, recipe, animation_id)
        animation = catalog.base(recipe.base_id).animations[animation_id]
        for direction in animation.directions:
            changed = any(
                extract_character_frame(result, animation, direction, frame).tobytes()
                != extract_character_frame(base, animation, direction, frame).tobytes()
                for frame in range(animation.frame_count(direction))
            )
            assert changed is (animation_id == "run" and direction == "front")


def test_headwear_hair_occlusion_contract() -> None:
    catalog = create_default_catalog()
    hair_id = "tiefling-long-hair-run-front-prototype"

    def rendered(headwear_id: str | None, include_hair: bool) -> Image.Image:
        recipe = create_default_recipe("hair-occlusion")
        recipe.base_id = "tiefling-female-01"
        recipe.camera_height = "low"
        recipe.parts["hair"] = hair_id if include_hair else None
        recipe.parts["headwear"] = headwear_id
        return composite_character_animation(catalog, recipe, "run")

    headband_id = "cloth-headband-tiefling-female-01"
    cap_id = "soft-travel-cap-tiefling-female-01"
    helm_id = "simple-guard-helm-tiefling-female-01"
    assert catalog.part(headband_id).hair_occlusion == "show"
    assert catalog.part(cap_id).hair_occlusion == "clip"
    assert catalog.part(helm_id).hair_occlusion == "hide"

    assert rendered(headband_id, True).tobytes() != rendered(
        headband_id, False
    ).tobytes()
    assert rendered(helm_id, True).tobytes() == rendered(
        helm_id, False
    ).tobytes()

    hair = load_part_render_layer(catalog, hair_id, "hair_front", "run")
    cap = load_part_animation(catalog, cap_id, "run")
    cap_alpha = np.asarray(cap.getchannel("A")) > 0
    assert np.any((np.asarray(hair.getchannel("A")) > 0) & cap_alpha)
    with_cap = rendered(cap_id, True)
    without_hair = rendered(cap_id, False)
    assert np.array_equal(
        np.asarray(with_cap)[cap_alpha],
        np.asarray(without_hair)[cap_alpha],
    )


def test_starter_color_variants_remap_only_declared_ramp() -> None:
    catalog = create_default_catalog()
    shirt = catalog.part("elf-basic-linen-shirt")
    original = load_part_animation(catalog, shirt.id, "walk")
    recolored = recolor_part_ramp(original, shirt, "#B43A46")
    source_pixels = list(_pixels(original))
    output_pixels = list(_pixels(recolored))
    assert recolored.getchannel("A").tobytes() == original.getchannel("A").tobytes()
    assert source_pixels != output_pixels
    for source, output in zip(source_pixels, output_pixels, strict=True):
        if source[:3] not in shirt.color_ramp:
            assert output == source
        else:
            assert output[3] == source[3]
    assert any(
        source[:3] == shirt.ramp_main_color and output[:3] == (180, 58, 70)
        for source, output in zip(source_pixels, output_pixels, strict=True)
    )


def test_recipe_round_trip_randomization_and_export(tmp_path: Path) -> None:
    catalog = create_default_catalog()
    first = randomize_recipe(catalog, "elf-01", 48271, name="seeded")
    second = randomize_recipe(catalog, "elf-01", 48271, name="seeded")
    assert first.to_dict() == second.to_dict()

    recipe = create_default_recipe("all-starters")
    for part_id in PART_IDS:
        part = catalog.part(part_id)
        recipe.parts[part.slot] = part.id
    recipe.part_colors["elf-basic-linen-shirt"] = "#B43A46"
    path = tmp_path / "recipe.json"
    save_recipe(recipe, path)
    assert load_recipe(path).to_dict() == recipe.to_dict()

    elevated = CharacterRecipe(
        base_id="dwarf-male-01", camera_height="three_quarter", name="elevated"
    )
    elevated_path = tmp_path / "elevated.json"
    save_recipe(elevated, elevated_path)
    assert load_recipe(elevated_path).to_dict() == elevated.to_dict()
    validate_recipe(catalog, elevated)

    outputs = export_character(catalog, recipe, tmp_path / "export")
    assert set(outputs) == {"idle", "walk", "run", "recipe"}
    for animation_id in ("idle", "walk", "run"):
        with Image.open(outputs[animation_id]) as opened:
            assert opened.size == catalog.base("elf-01").animations[animation_id].sheet_size


def test_character_forge_window_displays_128px_elf_and_new_parts() -> None:
    application = QApplication.instance() or QApplication([])
    window = CharacterForgeWindow()
    assert window.windowTitle() == "Character Forge"
    assert window.base_combo.currentText() == "Elf Female Base"
    assert window.base_combo.count() == 4
    assert window.base_combo.isEnabled()
    assert [
        window.animation_combo.itemData(index)
        for index in range(window.animation_combo.count())
    ] == ["idle", "walk", "run"]
    assert [
        window.camera_height_combo.itemData(index)
        for index in range(window.camera_height_combo.count())
    ] == ["top_down", "three_quarter", "low"]
    assert window.part_combos["torso"].count() == 6
    assert window.part_combos["outerwear"].count() == 6
    assert window.part_combos["legwear"].count() == 8
    assert window.part_combos["hands"].count() == 5
    assert window.part_combos["feet"].count() == 6
    assert window.part_combos["headwear"].count() == 5
    assert all(
        window.part_combos[slot].count() == 1
        for slot in CHARACTER_SLOTS
        if slot not in {
            "torso", "outerwear", "legwear", "hands", "feet", "headwear"
        }
    )
    window.animation_combo.setCurrentIndex(window.animation_combo.findData("walk"))
    application.processEvents()
    assert "128x128 frame" in window.frame_label.text()
    assert window.preview_label.pixmap().size().toTuple() == (1024, 1024)
    window.camera_height_combo.setCurrentIndex(
        window.camera_height_combo.findData("top_down")
    )
    application.processEvents()
    assert window.recipe.camera_height == "top_down"
    assert all(combo.count() == 1 for combo in window.part_combos.values())
    assert window.preview_label.pixmap().size().toTuple() == (1024, 1024)
    window.camera_height_combo.setCurrentIndex(
        window.camera_height_combo.findData("low")
    )
    application.processEvents()
    assert window.part_combos["torso"].count() == 6
    window.base_combo.setCurrentIndex(
        window.base_combo.findData("tiefling-female-01")
    )
    application.processEvents()
    assert window.part_combos["torso"].count() == 5
    assert window.part_combos["outerwear"].count() == 5
    assert window.part_combos["legwear"].count() == 7
    assert window.part_combos["hands"].count() == 4
    assert window.part_combos["feet"].count() == 5
    assert window.part_combos["headwear"].count() == 5
    assert window.part_combos["hair"].count() == 2
    assert window.catalog.base("tiefling-female-01").animations["idle"].frame_duration_ms(5) == 1500
    window.close()
    application.processEvents()


def test_main_window_keeps_character_forge_and_retires_old_component_factory() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.character_forge_action.text() == "Character Forge"
    assert not hasattr(window, "component_review_action")
    window.character_forge_action.trigger()
    application.processEvents()
    forge_windows = [
        child for child in window._tool_windows
        if isinstance(child, CharacterForgeWindow)
    ]
    assert len(forge_windows) == 1
    forge_windows[0].close()
    window.close()
    application.processEvents()
