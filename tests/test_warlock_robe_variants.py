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
from tools.finish_component_regions import MARKERS, PALETTE_PRESETS
from tools.generate_warlock_robe_variants import VARIANTS, generate_all


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = (
    PROJECT_ROOT
    / "assets"
    / "character-forge"
    / "semantic_sources"
    / "warlock-robe-front-walk"
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pixels(image: Image.Image):
    if hasattr(image, "get_flattened_data"):
        return image.get_flattened_data()
    return image.getdata()


def test_warlock_robe_source_is_preserved_and_normalized_exactly() -> None:
    authored_path = SOURCE_ROOT / "authored-regions.png"
    regions_path = SOURCE_ROOT / "semantic-regions.png"
    source_manifest = json.loads(
        (SOURCE_ROOT / "source.json").read_text(encoding="utf-8")
    )
    with Image.open(authored_path) as opened:
        authored = opened.convert("RGBA")
    with Image.open(regions_path) as opened:
        regions = opened.convert("RGBA")

    assert authored.size == (384, 256)
    assert regions.size == (384, 259)
    assert authored.tobytes() == regions.crop((0, 0, 384, 256)).tobytes()
    assert regions.crop((0, 256, 384, 259)).getbbox() is None
    assert set(_pixels(regions)) <= {
        (0, 0, 0, 0),
        (255, 64, 64, 255),
        (255, 216, 64, 255),
    }
    assert sum(pixel == (255, 64, 64, 255) for pixel in _pixels(regions)) == 605
    assert sum(pixel == (255, 216, 64, 255) for pixel in _pixels(regions)) == 282
    for frame_index in range(6):
        assert regions.crop(
            (frame_index * 64, 0, (frame_index + 1) * 64, 64)
        ).getbbox() is not None
    assert regions.crop((0, 64, 384, 256)).getbbox() is None
    assert source_manifest["authoredSourceSha256"] == _digest(authored_path)
    assert source_manifest["semanticRegionsSha256"] == _digest(regions_path)


def test_warlock_robe_variants_are_distinct_reproducible_and_preserve_silhouette() -> None:
    generate_all(check=True)
    catalog = create_default_catalog()
    with Image.open(SOURCE_ROOT / "semantic-regions.png") as opened:
        regions = opened.convert("RGBA")
    output_hashes: set[str] = set()

    for variant in VARIANTS:
        part = catalog.part(variant.component_id)
        manifest = json.loads(part.manifest_path.read_text(encoding="utf-8"))
        with Image.open(part.animations["walk"]) as opened:
            output = opened.convert("RGBA")

        assert part.coverage == {"walk": ("front",)}
        assert part.reserved_slots == ()
        assert output.getchannel("A").tobytes() == regions.getchannel("A").tobytes()
        assert output.tobytes() != regions.tobytes()
        assert {
            pixel[:3] for pixel in _pixels(output) if pixel[3]
        } <= {
            color
            for region in ("main", "trim")
            for color in PALETTE_PRESETS[variant.preset][region]
        }
        assert manifest["provenance"]["preset"] == variant.preset
        assert manifest["provenance"]["walkSha256"] == _digest(
            part.animations["walk"]
        )
        output_hashes.add(_digest(part.animations["walk"]))

    assert len(output_hashes) == len(VARIANTS) == 4


def test_warlock_robes_change_front_walk_only_and_fall_back_elsewhere() -> None:
    catalog = create_default_catalog()
    base_id = "human-01"
    walk = catalog.base(base_id).animations["walk"]
    base_walk = load_base_animation(catalog, base_id, "walk")

    for variant in VARIANTS:
        recipe = CharacterRecipe()
        recipe.parts["outerwear"] = variant.component_id
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
                catalog, base_id, animation_id
            ).tobytes()
