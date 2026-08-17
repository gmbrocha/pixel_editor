import hashlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QColorDialog

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
from src.ui.component_review_window import ComponentReviewWindow
from src.ui.main_window import MainWindow


BASE_HASHES = {
    "idle.png": "80326212e8a23301f9d2d5309ae3f2edb269251dbeeee5b6f2325dcfc497eeee",
    "run.png": "89d33142892d0d6d8095875e0aac33448fa1353138db004399ba1f66d7acc947",
    "run-back.png": "0cc0486c27824dc5eb07d68d106d452f8153e2c16355635f1fe4b5c8f89c2e2c",
    "run-front.png": "d642400d860c197e8bdf9f62434275154250c286212693fa8ff018fceeca7e74",
    "run-left.png": "32566d95b52b00a3eb21e2a2db0710f58e1256c042e1f8741a26c75ae4e2f9eb",
    "run-right.png": "f5c4ae57e7cb6ca039a1b7bf52b27ff165d42d2f43bdb74d5f1bde39bd9f1d9b",
    "walk.png": "90f886c15de51a3e6fbdb1a1280b50203aed38bb310016c3edb01fb6f8c76fce",
}


def test_static_catalog_preserves_supplied_sheet_geometry_and_bytes() -> None:
    catalog = create_default_catalog()
    validate_catalog(catalog)
    base = catalog.base("human-01")

    assert base.animations["idle"].sheet_size == (64, 256)
    assert base.animations["idle"].frames_per_direction == 1
    assert base.animations["idle"].direction_rows == {
        "front": 0,
        "left": 1,
        "right": 2,
        "back": 3,
    }
    assert base.animations["walk"].sheet_size == (384, 259)
    assert base.animations["walk"].frames_per_direction == 6
    assert base.animations["walk"].direction_rows == {
        "front": 0,
        "back": 1,
        "right": 2,
        "left": 3,
    }
    assert base.animations["run"].sheet_size == (384, 256)
    assert base.animations["run"].frames_per_direction == 6
    assert base.animations["run"].direction_rows == {
        "front": 0,
        "back": 1,
        "right": 2,
        "left": 3,
    }
    assert all(animation.frame_size == (64, 64) for animation in base.animations.values())

    for filename, expected_hash in BASE_HASHES.items():
        digest = hashlib.sha256((base.directory / filename).read_bytes()).hexdigest()
        assert digest == expected_hash


def test_matte_normalization_only_changes_exact_white_alpha() -> None:
    catalog = create_default_catalog()
    base = catalog.base("human-01")
    with Image.open(base.animation_path("idle")) as source_image:
        source = source_image.convert("RGBA")
    normalized = load_base_animation(catalog, base.id, "idle")

    source_pixels = list(
        source.get_flattened_data()
        if hasattr(source, "get_flattened_data")
        else source.getdata()
    )
    rendered_pixels = list(
        normalized.get_flattened_data()
        if hasattr(normalized, "get_flattened_data")
        else normalized.getdata()
    )
    for original, rendered in zip(source_pixels, rendered_pixels):
        if original[:3] == (255, 255, 255):
            assert rendered == (255, 255, 255, 0)
        else:
            assert rendered == original


def test_corrected_walk_preserves_native_white_eye_pixels() -> None:
    catalog = create_default_catalog()
    base = catalog.base("human-01")
    with Image.open(base.animation_path("walk")) as source_image:
        source = source_image.convert("RGBA")
    loaded = load_base_animation(catalog, base.id, "walk")

    assert loaded.tobytes() == source.tobytes()
    assert sum(
        pixel == (255, 255, 255, 255)
        for pixel in (
            loaded.get_flattened_data()
            if hasattr(loaded, "get_flattened_data")
            else loaded.getdata()
        )
    ) == 48


def test_authoritative_run_rows_are_assembled_pixel_exactly() -> None:
    catalog = create_default_catalog()
    base = catalog.base("human-01")
    run = load_base_animation(catalog, base.id, "run")
    assert run.size == (384, 256)

    for filename, row in (
        ("run-front.png", 0),
        ("run-back.png", 1),
        ("run-right.png", 2),
        ("run-left.png", 3),
    ):
        with Image.open(base.directory / filename) as source_image:
            source = source_image.convert("RGBA")
        assert run.crop((0, row * 64, 384, row * 64 + 64)).tobytes() == source.tobytes()


def test_partial_walking_shirt_is_registered_only_for_its_authored_sheet() -> None:
    catalog = create_default_catalog()
    recipe = create_default_recipe()
    shirt = catalog.part("walking-shirt-test")

    assert shirt.name == "Blue Walking Shirt (Front Test)"
    assert shirt.slot == "torso"
    assert shirt.layer == "torso"
    assert shirt.status == "incomplete"
    assert set(shirt.animations) == {"walk"}
    assert len(shirt.color_ramp) == 9
    assert shirt.ramp_main_color == (44, 66, 103)
    assert recipe.parts["torso"] == shirt.id
    assert all(
        recipe.parts[slot] is None for slot in CHARACTER_SLOTS if slot != "torso"
    )
    assert {part.id for part in catalog.parts_for_slot("torso")} == {
        "walking-shirt-test",
        "walking-shirt-crimson-derived",
        "walking-shirt-cream-indigo-yoke-derived",
    }
    assert {part.id for part in catalog.parts_for_slot("feet")} == {
        "leather-boots-front-test",
        "leather-boots-blackened-iron-derived",
    }
    assert all(
        catalog.parts_for_slot(slot) == ()
        for slot in ("waist", "legwear", "facial_hair", "back")
    )

    with Image.open(shirt.animations["walk"]) as source:
        overlay = source.convert("RGBA")
    assert overlay.size == (384, 259)
    assert overlay.getchannel("A").getextrema() == (0, 255)
    assert all(
        overlay.crop((column * 64, 0, column * 64 + 64, 64)).getbbox()
        is not None
        for column in range(6)
    )
    assert all(
        overlay.crop((0, row * 64, 384, row * 64 + 64)).getbbox() is None
        for row in range(1, 4)
    )


def test_partial_leather_boots_are_front_walk_only_and_fall_back_to_base() -> None:
    catalog = create_default_catalog()
    boots = catalog.part("leather-boots-front-test")
    recipe = CharacterRecipe()
    recipe.parts["feet"] = boots.id

    assert boots.name == "Leather Boots (Front Walk Test)"
    assert boots.slot == "feet"
    assert boots.layer == "footwear"
    assert boots.status == "incomplete"
    assert set(boots.animations) == {"walk"}
    assert boots.coverage == {"walk": ("front",)}

    overlay = load_part_animation(catalog, boots.id, "walk")
    assert overlay.size == (384, 259)
    assert all(
        overlay.crop((column * 64, 0, column * 64 + 64, 64)).getbbox()
        is not None
        for column in range(6)
    )
    assert overlay.crop((0, 64, 384, 259)).getbbox() is None

    walk = catalog.base(recipe.base_id).animations["walk"]
    base_walk = load_base_animation(catalog, recipe.base_id, "walk")
    composed_walk = composite_character_animation(catalog, recipe, "walk")
    for frame_index in range(walk.frames_per_direction):
        assert extract_character_frame(
            composed_walk, walk, "front", frame_index
        ).tobytes() != extract_character_frame(
            base_walk, walk, "front", frame_index
        ).tobytes()
        for direction in ("back", "right", "left"):
            assert extract_character_frame(
                composed_walk, walk, direction, frame_index
            ).tobytes() == extract_character_frame(
                base_walk, walk, direction, frame_index
            ).tobytes()

    for animation_id in ("idle", "run"):
        assert composite_character_animation(
            catalog, recipe, animation_id
        ).tobytes() == load_base_animation(
            catalog, recipe.base_id, animation_id
        ).tobytes()


def test_semantic_pointed_hood_cloak_covers_every_walk_direction() -> None:
    catalog = create_default_catalog()
    cloak = catalog.part("hooded-cloak-semantic-pointed-green")
    recipe = CharacterRecipe()
    recipe.parts["outerwear"] = cloak.id

    assert cloak.name == "Pointed Green Hooded Cloak (Full Walk)"
    assert cloak.slot == "outerwear"
    assert cloak.layer == "outerwear"
    assert cloak.status == "incomplete"
    assert cloak.occupies_slots == ("outerwear",)
    assert cloak.reserved_slots == ("headwear", "neck")
    assert set(cloak.animations) == {"walk"}
    assert cloak.coverage == {"walk": ("front", "back", "right", "left")}

    overlay = load_part_animation(catalog, cloak.id, "walk")
    assert overlay.size == (384, 259)
    assert all(
        overlay.crop(
            (column * 64, row * 64, column * 64 + 64, row * 64 + 64)
        ).getbbox()
        is not None
        for row in range(4)
        for column in range(6)
    )
    assert overlay.crop((0, 256, 384, 259)).getbbox() is None

    walk = catalog.base(recipe.base_id).animations["walk"]
    base_walk = load_base_animation(catalog, recipe.base_id, "walk")
    composed_walk = composite_character_animation(catalog, recipe, "walk")
    for frame_index in range(walk.frames_per_direction):
        for direction in ("front", "back", "right", "left"):
            assert extract_character_frame(
                composed_walk, walk, direction, frame_index
            ).tobytes() != extract_character_frame(
                base_walk, walk, direction, frame_index
            ).tobytes()

    for animation_id in ("idle", "run"):
        assert composite_character_animation(
            catalog, recipe, animation_id
        ).tobytes() == load_base_animation(
            catalog, recipe.base_id, animation_id
        ).tobytes()


def test_shirt_main_color_remaps_only_its_authored_ramp() -> None:
    catalog = create_default_catalog()
    shirt = catalog.part("walking-shirt-test")
    original = load_part_animation(catalog, shirt.id, "walk")
    recolored = recolor_part_ramp(original, shirt, "#B43A46")
    source_pixels = list(
        original.get_flattened_data()
        if hasattr(original, "get_flattened_data")
        else original.getdata()
    )
    output_pixels = list(
        recolored.get_flattened_data()
        if hasattr(recolored, "get_flattened_data")
        else recolored.getdata()
    )

    changed = 0
    selected_main_pixels = 0
    for source, output in zip(source_pixels, output_pixels):
        if source[:3] in shirt.color_ramp:
            assert output[3] == source[3]
            changed += output != source
            if source[:3] == shirt.ramp_main_color:
                assert output[:3] == (180, 58, 70)
                selected_main_pixels += 1
        else:
            assert output == source
    assert changed > 0
    assert selected_main_pixels > 0
    assert recolored.getchannel("A").tobytes() == original.getchannel("A").tobytes()


def test_recipe_round_trip_and_seeded_randomization_are_deterministic(tmp_path) -> None:
    catalog = create_default_catalog()
    first = randomize_recipe(catalog, "human-01", 48271, name="seeded")
    second = randomize_recipe(catalog, "human-01", 48271, name="seeded")
    assert first.to_dict() == second.to_dict()

    path = tmp_path / "seeded.json"
    save_recipe(first, path)
    loaded = load_recipe(path)
    assert loaded.to_dict() == first.to_dict()
    assert CharacterRecipe.from_dict(loaded.to_dict()).to_dict() == first.to_dict()

    colored = create_default_recipe("colored")
    colored.part_colors["walking-shirt-test"] = "#B43A46"
    colored_path = tmp_path / "colored.json"
    save_recipe(colored, colored_path)
    assert load_recipe(colored_path).to_dict() == colored.to_dict()


def test_partial_shirt_composition_and_export_preserve_supported_fallbacks(tmp_path) -> None:
    catalog = create_default_catalog()
    recipe = create_default_recipe("forge-test")
    recipe.part_colors["walking-shirt-test"] = "#B43A46"
    outputs = export_character(catalog, recipe, tmp_path)
    base = catalog.base(recipe.base_id)

    assert set(outputs) == {"idle", "walk", "run", "recipe"}
    for animation_id, animation in base.animations.items():
        base_sheet = load_base_animation(catalog, base.id, animation_id)
        composed = composite_character_animation(catalog, recipe, animation_id)
        with Image.open(outputs[animation_id]) as output_image:
            exported = output_image.convert("RGBA")
        assert composed.size == animation.sheet_size
        assert exported.size == animation.sheet_size
        assert exported.tobytes() == composed.tobytes()

        if animation_id == "walk":
            assert composed.tobytes() != base_sheet.tobytes()
            exported_pixels = (
                exported.get_flattened_data()
                if hasattr(exported, "get_flattened_data")
                else exported.getdata()
            )
            assert (180, 58, 70, 255) in set(exported_pixels)
            for frame_index in range(animation.frames_per_direction):
                clothed = extract_character_frame(
                    composed, animation, "front", frame_index
                )
                naked = extract_character_frame(
                    base_sheet, animation, "front", frame_index
                )
                assert clothed.tobytes() != naked.tobytes()
            for direction in ("back", "left", "right"):
                for frame_index in range(animation.frames_per_direction):
                    assert extract_character_frame(
                        composed, animation, direction, frame_index
                    ).tobytes() == extract_character_frame(
                        base_sheet, animation, direction, frame_index
                    ).tobytes()
        else:
            assert composed.tobytes() == base_sheet.tobytes()

        last_frame = extract_character_frame(
            composed,
            animation,
            animation.directions[-1],
            animation.frames_per_direction - 1,
        )
        assert last_frame.size == (64, 64)

    assert load_recipe(outputs["recipe"]).to_dict() == recipe.to_dict()


def test_character_forge_window_exposes_animation_direction_zoom_parts_and_color(
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    window = CharacterForgeWindow()

    assert window.windowTitle() == "Character Forge"
    assert window.base_combo.currentText() == "Human Base 01"
    assert [
        window.animation_combo.itemData(index)
        for index in range(window.animation_combo.count())
    ] == ["idle", "walk", "run"]
    assert window.preview_label.pixmap().size().toTuple() == (512, 512)
    assert set(window.part_combos) == set(CHARACTER_SLOTS)
    assert window.part_combos["torso"].count() == 4
    assert window.part_combos["torso"].isEnabled()
    assert window.part_combos["torso"].currentData() == "walking-shirt-test"
    assert window.part_combos["feet"].count() == 3
    assert window.part_combos["feet"].isEnabled()
    assert window.part_combos["feet"].findData("leather-boots-front-test") >= 1
    assert window.part_combos["feet"].currentData() is None
    assert window.part_combos["outerwear"].count() == 18
    assert window.part_combos["outerwear"].isEnabled()
    assert (
        window.part_combos["outerwear"].findData("hooded-cloak-semantic-pointed-green")
        >= 1
    )
    assert (
        window.part_combos["outerwear"].findData(
            "warlock-robe-semantic-void-amethyst"
        )
        >= 1
    )
    assert window.part_combos["outerwear"].currentData() is None
    assert window.part_combos["hair"].count() == 2
    assert window.part_combos["hair"].isEnabled()
    assert window.part_combos["face"].count() == 3
    assert window.part_combos["face"].isEnabled()
    assert window.part_combos["headwear"].count() == 2
    assert window.part_combos["headwear"].isEnabled()
    assert window.part_combos["neck"].count() == 2
    assert window.part_combos["neck"].isEnabled()
    assert window.part_combos["hands"].count() == 2
    assert window.part_combos["hands"].isEnabled()
    assert window.part_combos["shoulder_chest"].count() == 3
    assert window.part_combos["shoulder_chest"].isEnabled()
    assert not window.edit_part_buttons["torso"].isEnabled()
    assert window.part_color_button.isEnabled()
    assert window.part_color_button.text() == "#2C4267"
    assert not window.reset_part_color_button.isEnabled()
    assert all(
        combo.count() == 1 and combo.itemText(0) == "None" and not combo.isEnabled()
        for slot, combo in window.part_combos.items()
        if slot
        not in {
            "torso",
            "outerwear",
            "feet",
            "hair",
            "face",
            "headwear",
            "neck",
            "hands",
            "shoulder_chest",
        }
    )

    window.animation_combo.setCurrentIndex(window.animation_combo.findData("walk"))
    assert [
        window.direction_combo.itemData(index)
        for index in range(window.direction_combo.count())
    ] == ["front", "back", "left", "right"]
    assert "Frame 1/6" in window.frame_label.text()
    assert "384x259 sheet" in window.frame_label.text()
    assert window.edit_part_buttons["torso"].isEnabled()
    window.part_combos["feet"].setCurrentIndex(
        window.part_combos["feet"].findData("leather-boots-front-test")
    )
    assert window.recipe.parts["feet"] == "leather-boots-front-test"
    assert window.edit_part_buttons["feet"].isEnabled()

    monkeypatch.setattr(
        QColorDialog,
        "getColor",
        lambda *_args, **_kwargs: QColor("#B43A46"),
    )
    window.part_color_button.click()
    assert window.recipe.part_colors == {"walking-shirt-test": "#B43A46"}
    assert window.part_color_button.text() == "#B43A46"
    assert window.reset_part_color_button.isEnabled()
    window.reset_part_color_button.click()
    assert window.recipe.part_colors == {}
    assert window.part_color_button.text() == "#2C4267"

    window.animation_combo.setCurrentIndex(window.animation_combo.findData("run"))
    assert "Frame 1/6" in window.frame_label.text()
    assert "384x256 sheet" in window.frame_label.text()

    window.seed_spin.setValue(17)
    window.randomize_button.click()
    randomized = dict(window.recipe.parts)
    window.randomize_button.click()
    assert window.recipe.parts == randomized
    assert window.recipe.random_seed == 17

    window.close()
    application.processEvents()


def test_main_window_has_character_tools_and_refreshes_forge_after_promotion(
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert window.character_forge_action.text() == "Character Forge"
    assert window.character_forge_action.isVisible()
    window.character_forge_action.trigger()
    application.processEvents()

    forge_windows = [
        tool for tool in window._tool_windows if isinstance(tool, CharacterForgeWindow)
    ]
    assert len(forge_windows) == 1
    assert forge_windows[0].isVisible()

    assert window.component_review_action.text() == "Component Factory"
    assert window.component_review_action.isVisible()
    window.component_review_action.trigger()
    application.processEvents()
    review_windows = [
        tool for tool in window._tool_windows if isinstance(tool, ComponentReviewWindow)
    ]
    assert len(review_windows) == 1

    reloads = []
    monkeypatch.setattr(forge_windows[0], "_reload_catalog", lambda: reloads.append(True))
    review_windows[0].component_promoted.emit("test-component")
    assert reloads == [True]

    review_windows[0].close()
    forge_windows[0].close()
    window.close()
    application.processEvents()
