import hashlib
import json

from PIL import Image

from src.core.character_forge import (
    CharacterRecipe,
    composite_character_animation,
    create_default_catalog,
    extract_character_frame,
    load_base_animation,
    load_part_animation,
    validate_catalog,
)
from tools.generate_character_component_variants import (
    DEFAULT_ASSET_ROOT,
    VARIANTS,
    generate_variants,
)


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_variant_generator_is_repeatable_and_never_changes_sources(tmp_path) -> None:
    source_paths = {
        DEFAULT_ASSET_ROOT / spec.source_relative_path for spec in VARIANTS
    }
    source_hashes = {path: _digest(path) for path in source_paths}

    first_outputs = generate_variants(DEFAULT_ASSET_ROOT, output_root=tmp_path)
    first_hashes = {path.relative_to(tmp_path): _digest(path) for path in first_outputs}
    second_outputs = generate_variants(DEFAULT_ASSET_ROOT, output_root=tmp_path)
    second_hashes = {path.relative_to(tmp_path): _digest(path) for path in second_outputs}
    generate_variants(DEFAULT_ASSET_ROOT, output_root=tmp_path, check=True)

    assert len(first_outputs) == len(VARIANTS) * 2
    assert first_hashes == second_hashes
    assert source_hashes == {path: _digest(path) for path in source_paths}


def test_committed_variants_preserve_silhouettes_and_manifest_provenance() -> None:
    catalog = create_default_catalog()
    validate_catalog(catalog)

    for spec in VARIANTS:
        source_path = DEFAULT_ASSET_ROOT / spec.source_relative_path
        part = catalog.part(spec.id)
        generated_path = part.animations["walk"]
        manifest = json.loads(part.manifest_path.read_text(encoding="utf-8"))
        with Image.open(source_path) as opened:
            source = opened.convert("RGBA")
        with Image.open(generated_path) as opened:
            generated = opened.convert("RGBA")

        assert generated.size == source.size == (384, 259)
        assert generated.getchannel("A").tobytes() == source.getchannel("A").tobytes()
        assert generated.tobytes() != source.tobytes()
        assert part.coverage == {"walk": ("front",)}
        assert manifest["provenance"]["kind"] == "deterministic_variant"
        assert manifest["provenance"]["sourceComponent"] == spec.source_component
        assert manifest["provenance"]["sourceSha256"] == _digest(source_path)
        assert manifest["provenance"]["walkSha256"] == _digest(generated_path)


def test_all_variants_change_front_walk_only_and_fall_back_everywhere_else() -> None:
    catalog = create_default_catalog()
    base_id = "human-01"
    walk = catalog.base(base_id).animations["walk"]
    base_walk = load_base_animation(catalog, base_id, "walk")

    for spec in VARIANTS:
        recipe = CharacterRecipe()
        recipe.parts[spec.slot] = spec.id
        composed_walk = composite_character_animation(catalog, recipe, "walk")
        overlay = load_part_animation(catalog, spec.id, "walk")

        assert overlay.crop((0, 64, 384, 259)).getbbox() is None
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
                catalog, base_id, animation_id
            ).tobytes()


def test_removed_test_components_are_absent_and_clean_material_variants_do_not_speckle() -> None:
    catalog = create_default_catalog()
    part_ids = {part.id for part in catalog.parts}

    assert "hooded-cloak-semantic-forest-test" not in part_ids
    assert "leather-boots-muddy-field-derived" not in part_ids
    assert "hooded-cloak-pointy-front-test" not in part_ids
    assert "hooded-cloak-burgundy-gold-derived" not in part_ids
    assert "hooded-cloak-winter-gray-derived" not in part_ids

    cleaned = {
        "leather-boots-blackened-iron-derived": (174, 185, 189),
    }
    for component_id, removed_accent in cleaned.items():
        part = catalog.part(component_id)
        manifest = json.loads(part.manifest_path.read_text(encoding="utf-8"))
        with Image.open(part.animations["walk"]) as opened:
            image = opened.convert("RGBA")
            pixels = list(
                image.get_flattened_data()
                if hasattr(image, "get_flattened_data")
                else image.getdata()
            )

        assert all(pixel[:3] != removed_accent for pixel in pixels if pixel[3])
        assert "seed" not in manifest["provenance"]
        assert "stable" in manifest["provenance"]["transformation"]
