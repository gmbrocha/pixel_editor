import hashlib
import json
from pathlib import Path

from PIL import Image

from src.core.character_forge import (
    CharacterRecipe,
    composite_character_animation,
    create_default_catalog,
    extract_character_frame,
    load_base_animation,
)
from tools.finish_component_regions import (
    MARKERS,
    PALETTE_PRESETS,
    generate_finished_component,
)
from tools.complete_cloak_walk_regions import (
    LEFT_ALIGNMENT_OFFSET,
    SIDE_FRAME_ORDER,
    generate_completed_walk_source,
)
from tools.generate_cloak_walk_variants import generate_all


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FULL_SOURCE_ROOT = (
    PROJECT_ROOT
    / "assets"
    / "character-forge"
    / "semantic_sources"
    / "hooded-cloak-walk"
)
FULL_VARIANTS = {
    "hooded-cloak-semantic-forest-wool": "forest-wool",
    "hooded-cloak-semantic-burgundy-velvet": "burgundy-velvet",
    "hooded-cloak-semantic-storm-blue-silver": "storm-blue-silver",
    "hooded-cloak-semantic-autumn-russet": "autumn-russet",
    "hooded-cloak-semantic-pointed-green": "pointed-hood-green",
    "hooded-cloak-semantic-winter-gray": "winter-gray",
    "hooded-cloak-semantic-royal-amethyst": "royal-amethyst",
    "hooded-cloak-semantic-midnight-raven": "midnight-raven",
    "hooded-cloak-semantic-desert-sand-teal": "desert-sand-teal",
    "hooded-cloak-semantic-ivory-crimson": "ivory-crimson",
}
LEGACY_CLOAK_IDS = {
    "hooded-cloak-pointy-front-test",
    "hooded-cloak-burgundy-gold-derived",
    "hooded-cloak-winter-gray-derived",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pixels(image: Image.Image):
    if hasattr(image, "get_flattened_data"):
        return image.get_flattened_data()
    return image.getdata()


def test_full_semantic_source_preserves_authored_rows_and_mirrors_left_exactly() -> None:
    authored_path = FULL_SOURCE_ROOT / "authored-regions.png"
    regions_path = FULL_SOURCE_ROOT / "semantic-regions.png"
    source_manifest = json.loads(
        (FULL_SOURCE_ROOT / "source.json").read_text(encoding="utf-8")
    )
    with Image.open(authored_path) as opened:
        authored = opened.convert("RGBA")
    with Image.open(regions_path) as opened:
        regions = opened.convert("RGBA")

    assert authored.size == (384, 256)
    assert regions.size == (384, 259)
    assert set(_pixels(regions)) <= {(0, 0, 0, 0), *MARKERS}
    assert sum(pixel in MARKERS for pixel in _pixels(regions)) == 7794
    assert regions.crop((0, 256, 384, 259)).getbbox() is None
    for direction_row in range(4):
        for frame_index in range(6):
            frame = regions.crop(
                (
                    frame_index * 64,
                    direction_row * 64,
                    (frame_index + 1) * 64,
                    (direction_row + 1) * 64,
                )
            )
            assert frame.getbbox() is not None
    for output_index, source_index in enumerate(SIDE_FRAME_ORDER):
        authored_right = authored.crop(
            (source_index * 64, 128, (source_index + 1) * 64, 192)
        )
        right = regions.crop(
            (output_index * 64, 128, (output_index + 1) * 64, 192)
        )
        left = regions.crop(
            (output_index * 64, 192, (output_index + 1) * 64, 256)
        )
        assert right.tobytes() == authored_right.tobytes()
        expected_left = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        expected_left.paste(
            right.transpose(Image.Transpose.FLIP_LEFT_RIGHT),
            LEFT_ALIGNMENT_OFFSET,
        )
        assert left.tobytes() == expected_left.tobytes()
    assert source_manifest["authoredDirections"] == ["front", "back", "right"]
    assert source_manifest["sideFrameOrder"] == [1, 2, 3, 4, 5, 6]
    assert source_manifest["derivedDirections"]["right"]["sourceFrameOrder"] == [
        1,
        2,
        3,
        4,
        5,
        6,
    ]
    assert (
        source_manifest["derivedDirections"]["left"]["sourceDirection"]
        == "right"
    )
    assert source_manifest["derivedDirections"]["left"]["alignmentOffset"] == [
        -1,
        -1,
    ]
    assert source_manifest["authoredSourceSha256"] == _digest(authored_path)
    assert source_manifest["semanticRegionsSha256"] == _digest(regions_path)


def test_completed_source_and_all_cloak_outputs_are_reproducible(tmp_path) -> None:
    authored_path = FULL_SOURCE_ROOT / "authored-regions.png"
    generated_authored = tmp_path / "authored-regions.png"
    generated_regions = tmp_path / "semantic-regions.png"
    expected = (_digest(authored_path), _digest(FULL_SOURCE_ROOT / "semantic-regions.png"))

    assert generate_completed_walk_source(
        authored_path, generated_authored, generated_regions
    ) == expected
    generate_completed_walk_source(
        authored_path, generated_authored, generated_regions, check=True
    )
    generate_all(check=True)


def test_full_semantic_presets_are_distinct_repeatable_and_preserve_source(tmp_path) -> None:
    catalog = create_default_catalog()
    regions_path = FULL_SOURCE_ROOT / "semantic-regions.png"
    with Image.open(regions_path) as opened:
        regions = opened.convert("RGBA")
    output_hashes: set[str] = set()

    for component_id, preset in FULL_VARIANTS.items():
        part = catalog.part(component_id)
        output_path = part.animations["walk"]
        manifest = json.loads(part.manifest_path.read_text(encoding="utf-8"))
        with Image.open(output_path) as opened:
            output = opened.convert("RGBA")

        assert output.getchannel("A").tobytes() == regions.getchannel("A").tobytes()
        assert output.tobytes() != regions.tobytes()
        assert {
            pixel[:3] for pixel in _pixels(output) if pixel[3]
        } <= {
            color for palette in PALETTE_PRESETS[preset].values() for color in palette
        }
        assert manifest["provenance"]["preset"] == preset
        assert manifest["provenance"]["semanticRegionsSha256"] == _digest(
            regions_path
        )
        assert manifest["provenance"]["walkSha256"] == _digest(output_path)
        output_hashes.add(_digest(output_path))

        generated_regions = tmp_path / preset / "semantic-regions.png"
        generated_walk = tmp_path / preset / "walk.png"
        generated_hashes = generate_finished_component(
            regions_path,
            generated_regions,
            generated_walk,
            preset=preset,
        )
        assert generated_hashes == (_digest(regions_path), _digest(output_path))
        generate_finished_component(
            regions_path,
            generated_regions,
            generated_walk,
            preset=preset,
            check=True,
        )

    assert len(output_hashes) == len(FULL_VARIANTS)


def test_full_semantic_variants_cover_every_walk_direction_and_fall_back_elsewhere() -> None:
    catalog = create_default_catalog()
    base_id = "human-01"
    walk = catalog.base(base_id).animations["walk"]
    base_walk = load_base_animation(catalog, base_id, "walk")

    for component_id in FULL_VARIANTS:
        recipe = CharacterRecipe()
        recipe.parts["outerwear"] = component_id
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
                catalog, base_id, animation_id
            ).tobytes()


def test_legacy_cloaks_are_archived_outside_runtime_discovery() -> None:
    catalog = create_default_catalog()
    catalog_ids = {part.id for part in catalog.parts}
    archive_root = (
        PROJECT_ROOT
        / "assets"
        / "character-forge"
        / "legacy_sources"
        / "old-model-cloaks"
    )

    assert LEGACY_CLOAK_IDS.isdisjoint(catalog_ids)
    for component_id in LEGACY_CLOAK_IDS:
        component_root = archive_root / component_id
        assert (component_root / "manifest.json").is_file()
        assert (component_root / "walk.png").is_file()
