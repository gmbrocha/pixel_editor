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
    validate_catalog,
)
from tools.finish_component_regions import MARKERS
from tools.generate_component_silhouette_starters import (
    ASSET_ROOT,
    BASE_WALK,
    CONCEPT_BOARD,
    STARTERS,
    WORKBENCH_ROOT,
    generate_all,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pixels(image: Image.Image):
    if hasattr(image, "get_flattened_data"):
        return image.get_flattened_data()
    return image.getdata()


def test_silhouette_starters_are_reproducible_catalogued_and_indexed() -> None:
    generate_all(check=True)
    catalog = create_default_catalog()
    validate_catalog(catalog)
    index = json.loads(
        (WORKBENCH_ROOT / "component-silhouette-starters.json").read_text(
            encoding="utf-8"
        )
    )

    assert len(STARTERS) == 11
    assert {starter.component_id for starter in STARTERS} <= {
        part.id for part in catalog.parts
    }
    assert {entry["id"] for entry in index["starters"]} == {
        starter.component_id for starter in STARTERS
    }
    assert index["baseWalkSha256"] == _digest(BASE_WALK)
    assert CONCEPT_BOARD.is_file()
    assert (WORKBENCH_ROOT / "component-silhouette-starters.png").is_file()
    assert (WORKBENCH_ROOT / "component-silhouette-starters-all-frames.png").is_file()


def test_silhouette_starter_regions_are_exact_and_preserved_by_previews() -> None:
    catalog = create_default_catalog()
    walk = catalog.base("human-01").animations["walk"]
    for starter in STARTERS:
        part = catalog.part(starter.component_id)
        root = part.manifest_path.parent
        manifest = json.loads(part.manifest_path.read_text(encoding="utf-8"))
        with Image.open(root / "walk.png") as opened:
            preview = opened.convert("RGBA")

        assert preview.size == (384, 259)
        supported_directions = (
            starter.authored_directions
            if starter.authored_walk is not None
            else ("front",)
        )
        for direction, row in walk.direction_rows.items():
            row_image = preview.crop((0, row * 64, 384, row * 64 + 64))
            if direction in supported_directions:
                assert all(
                    row_image.crop((index * 64, 0, (index + 1) * 64, 64)).getbbox()
                    is not None
                    for index in range(6)
                )
            else:
                assert row_image.getbbox() is None
        assert preview.crop((0, 256, 384, 259)).getbbox() is None
        assert part.coverage == {"walk": supported_directions}
        assert manifest["provenance"]["walkSha256"] == _digest(root / "walk.png")
        if starter.authored_walk is not None:
            source = root / starter.authored_walk
            assert "semanticRegions" not in manifest
            assert (root / "walk.png").read_bytes() == source.read_bytes()
            assert part.alpha_occluded_by_tags == starter.alpha_occluded_by_tags
            if starter.alpha_occluded_by_tags:
                assert manifest["alphaOccludedByTags"] == list(
                    starter.alpha_occluded_by_tags
                )
            else:
                assert "alphaOccludedByTags" not in manifest
            assert manifest["provenance"]["authoredSource"] == starter.authored_walk
            assert manifest["provenance"]["authoredSourceSha256"] == _digest(source)
        else:
            with Image.open(root / "regions.png") as opened:
                regions = opened.convert("RGBA")
            assert regions.size == preview.size
            assert set(_pixels(regions)) <= {(0, 0, 0, 0), *MARKERS}
            assert regions.getchannel("A").tobytes() == preview.getchannel("A").tobytes()
            assert regions.crop((0, 64, 384, 259)).getbbox() is None
            assert manifest["semanticRegions"] == {"walk": "regions.png"}
            assert manifest["provenance"]["regionsSha256"] == _digest(
                root / "regions.png"
            )


def test_silhouette_starters_change_only_their_authored_walk_directions() -> None:
    catalog = create_default_catalog()
    base_id = "human-01"
    walk = catalog.base(base_id).animations["walk"]
    base_walk = load_base_animation(catalog, base_id, "walk")

    for starter in STARTERS:
        supported_directions = (
            starter.authored_directions
            if starter.authored_walk is not None
            else ("front",)
        )
        recipe = CharacterRecipe()
        recipe.parts[starter.slot] = starter.component_id
        composed = composite_character_animation(catalog, recipe, "walk")
        for frame_index in range(6):
            for direction in ("front", "back", "right", "left"):
                composed_frame = extract_character_frame(
                    composed, walk, direction, frame_index
                ).tobytes()
                base_frame = extract_character_frame(
                    base_walk, walk, direction, frame_index
                ).tobytes()
                if direction in supported_directions:
                    assert composed_frame != base_frame
                else:
                    assert composed_frame == base_frame
        for animation_id in ("idle", "run"):
            assert composite_character_animation(
                catalog, recipe, animation_id
            ).tobytes() == load_base_animation(catalog, base_id, animation_id).tobytes()
