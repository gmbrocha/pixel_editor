from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication

from src.core.character_forge import (
    CHARACTER_SLOTS,
    CharacterRecipe,
    composite_character_animation,
    create_default_catalog,
    create_default_recipe,
    export_character,
    extract_character_frame,
    load_base_animation,
    load_part_animation,
    load_recipe,
    randomize_recipe,
    recolor_part_ramp,
    save_recipe,
    validate_catalog,
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


def test_catalog_contains_only_the_new_semantic_elf_runtime() -> None:
    catalog = create_default_catalog()
    validate_catalog(catalog)
    assert len(catalog.bases) == 1
    base = catalog.base("elf-01")
    assert base.name == "Semantic Elf Base"
    assert {part.id: part.slot for part in catalog.parts} == PART_IDS
    assert not (ASSET_ROOT / "bases" / "human-01").exists()
    assert not (ASSET_ROOT / "workbench").exists()
    assert not (ROOT / "art_pipeline").exists()

    expected = {
        "idle": ((3328, 512), 26, 12),
        "walk": ((1024, 512), 8, 10),
        "run": ((1024, 512), 8, 10),
    }
    for animation_id, (sheet_size, frame_count, fps) in expected.items():
        animation = base.animations[animation_id]
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
    for part in catalog.parts:
        assert part.status == "approved"
        assert part.fit == "elf-01"
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
    for part in catalog.parts:
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
    for part in catalog.parts:
        recipe.parts[part.slot] = part.id
    recipe.part_colors["elf-basic-linen-shirt"] = "#B43A46"
    path = tmp_path / "recipe.json"
    save_recipe(recipe, path)
    assert load_recipe(path).to_dict() == recipe.to_dict()

    outputs = export_character(catalog, recipe, tmp_path / "export")
    assert set(outputs) == {"idle", "walk", "run", "recipe"}
    for animation_id in ("idle", "walk", "run"):
        with Image.open(outputs[animation_id]) as opened:
            assert opened.size == catalog.base("elf-01").animations[animation_id].sheet_size


def test_character_forge_window_displays_128px_elf_and_new_parts() -> None:
    application = QApplication.instance() or QApplication([])
    window = CharacterForgeWindow()
    assert window.windowTitle() == "Character Forge"
    assert window.base_combo.currentText() == "Semantic Elf Base"
    assert [
        window.animation_combo.itemData(index)
        for index in range(window.animation_combo.count())
    ] == ["idle", "walk", "run"]
    assert window.part_combos["torso"].count() == 2
    assert window.part_combos["outerwear"].count() == 2
    assert window.part_combos["legwear"].count() == 2
    assert window.part_combos["hands"].count() == 2
    assert window.part_combos["feet"].count() == 2
    assert all(
        window.part_combos[slot].count() == 1
        for slot in CHARACTER_SLOTS
        if slot not in {"torso", "outerwear", "legwear", "hands", "feet"}
    )
    window.animation_combo.setCurrentIndex(window.animation_combo.findData("walk"))
    application.processEvents()
    assert "128x128 frame" in window.frame_label.text()
    assert window.preview_label.pixmap().size().toTuple() == (1024, 1024)
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
