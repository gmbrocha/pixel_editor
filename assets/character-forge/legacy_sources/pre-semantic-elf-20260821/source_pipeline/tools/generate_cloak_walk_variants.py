from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from PIL import Image

try:
    from tools.complete_cloak_walk_regions import (
        LEFT_ALIGNMENT_OFFSET,
        SIDE_FRAME_ORDER,
        generate_completed_walk_source,
    )
    from tools.finish_component_regions import MARKERS, generate_finished_component
except ModuleNotFoundError:  # Direct `python tools/...py` execution.
    from complete_cloak_walk_regions import (
        LEFT_ALIGNMENT_OFFSET,
        SIDE_FRAME_ORDER,
        generate_completed_walk_source,
    )
    from finish_component_regions import MARKERS, generate_finished_component


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = PROJECT_ROOT / "assets" / "character-forge"
SOURCE_ROOT = ASSET_ROOT / "semantic_sources" / "hooded-cloak-walk"
AUTHORED_SOURCE = SOURCE_ROOT / "authored-regions.png"
SEMANTIC_SOURCE = SOURCE_ROOT / "semantic-regions.png"
PARTS_ROOT = ASSET_ROOT / "parts" / "outerwear"
FULL_DIRECTIONS = ["front", "back", "right", "left"]


@dataclass(frozen=True, slots=True)
class CloakVariant:
    component_id: str
    display_name: str
    preset: str
    tags: tuple[str, ...]
    replaces_legacy: str | None = None


VARIANTS = (
    CloakVariant(
        "hooded-cloak-semantic-forest-wool",
        "Forest Wool Hooded Cloak (Full Walk)",
        "forest-wool",
        ("forest_wool", "green"),
    ),
    CloakVariant(
        "hooded-cloak-semantic-burgundy-velvet",
        "Burgundy Cloak + Gold Trim (Full Walk)",
        "burgundy-velvet",
        ("burgundy_velvet", "gold_trim"),
        "hooded-cloak-burgundy-gold-derived",
    ),
    CloakVariant(
        "hooded-cloak-semantic-storm-blue-silver",
        "Storm Blue + Silver Hooded Cloak (Full Walk)",
        "storm-blue-silver",
        ("storm_blue", "silver"),
    ),
    CloakVariant(
        "hooded-cloak-semantic-autumn-russet",
        "Autumn Russet Hooded Cloak (Full Walk)",
        "autumn-russet",
        ("autumn", "russet"),
    ),
    CloakVariant(
        "hooded-cloak-semantic-pointed-green",
        "Pointed Green Hooded Cloak (Full Walk)",
        "pointed-hood-green",
        ("pointed_hood", "green"),
        "hooded-cloak-pointy-front-test",
    ),
    CloakVariant(
        "hooded-cloak-semantic-winter-gray",
        "Winter Gray Hooded Cloak (Full Walk)",
        "winter-gray",
        ("winter_gray", "gray"),
        "hooded-cloak-winter-gray-derived",
    ),
    CloakVariant(
        "hooded-cloak-semantic-royal-amethyst",
        "Royal Amethyst + Gold Hooded Cloak (Full Walk)",
        "royal-amethyst",
        ("royal", "amethyst", "gold_trim"),
    ),
    CloakVariant(
        "hooded-cloak-semantic-midnight-raven",
        "Midnight Raven Hooded Cloak (Full Walk)",
        "midnight-raven",
        ("midnight", "raven", "crimson_lining"),
    ),
    CloakVariant(
        "hooded-cloak-semantic-desert-sand-teal",
        "Desert Sand + Teal Hooded Cloak (Full Walk)",
        "desert-sand-teal",
        ("desert", "sand", "teal_lining"),
    ),
    CloakVariant(
        "hooded-cloak-semantic-ivory-crimson",
        "Ivory + Crimson Hooded Cloak (Full Walk)",
        "ivory-crimson",
        ("ivory", "crimson"),
    ),
)


def _pixels(image: Image.Image):
    if hasattr(image, "get_flattened_data"):
        return image.get_flattened_data()
    return image.getdata()


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _json_bytes(data: dict[str, object]) -> bytes:
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def _write_or_check(path: Path, content: bytes, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"Generated metadata is stale or missing: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _region_counts(path: Path) -> dict[str, int]:
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    counts = {name: 0 for name in MARKERS.values()}
    for pixel in _pixels(image):
        name = MARKERS.get(pixel)
        if name is not None:
            counts[name] += 1
    return counts


def _source_manifest(authored_hash: str, semantic_hash: str) -> dict[str, object]:
    counts = _region_counts(SEMANTIC_SOURCE)
    colors = {name: pixel for pixel, name in MARKERS.items()}
    return {
        "schemaVersion": 1,
        "id": "hooded-cloak-walk-semantic-regions",
        "sourceName": "walk_hooded_cloak.png",
        "authoredSource": "authored-regions.png",
        "authoredSourceSha256": authored_hash,
        "semanticRegionsSha256": semantic_hash,
        "sheetSize": [384, 259],
        "logicalExtent": [384, 256],
        "animation": "walk",
        "directionRows": {"front": 0, "back": 1, "right": 2, "left": 3},
        "authoredDirections": ["front", "back", "right"],
        "sideFrameOrder": [index + 1 for index in SIDE_FRAME_ORDER],
        "derivedDirections": {
            "right": {
                "operation": "preserved-authored-row",
                "sourceDirection": "right",
                "sourceFrameOrder": [index + 1 for index in SIDE_FRAME_ORDER],
                "generator": "tools/complete_cloak_walk_regions.py",
                "generatorVersion": 3,
            },
            "left": {
                "operation": "horizontal-frame-mirror",
                "sourceDirection": "right",
                "alignmentOffset": list(LEFT_ALIGNMENT_OFFSET),
                "generator": "tools/complete_cloak_walk_regions.py",
                "generatorVersion": 3,
            }
        },
        "framesPerDirection": 6,
        "regions": {
            name: {
                "color": f"#{red:02X}{green:02X}{blue:02X}",
                "pixels": counts[name],
            }
            for name, (red, green, blue, _alpha) in colors.items()
        },
        "extraction": (
            "Exact opaque semantic marker pixels and authored Front, Back, and Right "
            "frame order are preserved. Left Walk frames are deterministic per-frame "
            "horizontal mirrors of the authored Right row."
        ),
    }


def _component_manifest(
    variant: CloakVariant,
    authored_hash: str,
    semantic_hash: str,
    walk_hash: str,
) -> dict[str, object]:
    provenance: dict[str, object] = {
        "kind": "deterministic_semantic_finish",
        "generator": "tools/generate_cloak_walk_variants.py",
        "generatorVersion": 2,
        "finisher": "tools/finish_component_regions.py",
        "preset": variant.preset,
        "authoredSource": "semantic_sources/hooded-cloak-walk/authored-regions.png",
        "authoredSourceSha256": authored_hash,
        "semanticSource": "semantic_sources/hooded-cloak-walk/semantic-regions.png",
        "semanticRegionsSha256": semantic_hash,
        "walkSha256": walk_hash,
        "authoredDirections": ["front", "back", "right"],
        "sideFrameOrder": [index + 1 for index in SIDE_FRAME_ORDER],
        "derivedDirections": {
            "left": {
                "operation": "horizontal-frame-mirror-of-right",
                "alignmentOffset": list(LEFT_ALIGNMENT_OFFSET),
            }
        },
        "framesPerDirection": 6,
    }
    if variant.replaces_legacy is not None:
        provenance["replacesLegacyComponent"] = variant.replaces_legacy
    return {
        "schemaVersion": 1,
        "id": variant.component_id,
        "displayName": variant.display_name,
        "slot": "outerwear",
        "occupiesSlots": ["outerwear"],
        "reservedSlots": ["headwear", "neck"],
        "layer": "outerwear",
        "tags": ["cloak", "hooded_cloak", "semantic_regions", "deterministic", *variant.tags],
        "fit": "standard",
        "version": 2,
        "status": "incomplete",
        "developmentVisible": True,
        "animations": {"walk": "walk.png"},
        "coverage": {"walk": FULL_DIRECTIONS},
        "provenance": provenance,
    }


def generate_all(*, check: bool = False) -> None:
    authored_hash, semantic_hash = generate_completed_walk_source(
        AUTHORED_SOURCE,
        AUTHORED_SOURCE,
        SEMANTIC_SOURCE,
        check=check,
    )
    _write_or_check(
        SOURCE_ROOT / "source.json",
        _json_bytes(_source_manifest(authored_hash, semantic_hash)),
        check,
    )
    for variant in VARIANTS:
        component_root = PARTS_ROOT / variant.component_id
        walk_path = component_root / "walk.png"
        generated_semantic_hash, walk_hash = generate_finished_component(
            SEMANTIC_SOURCE,
            SEMANTIC_SOURCE,
            walk_path,
            preset=variant.preset,
            check=check,
        )
        if generated_semantic_hash != semantic_hash:
            raise RuntimeError("Semantic finisher changed the canonical region source")
        _write_or_check(
            component_root / "manifest.json",
            _json_bytes(
                _component_manifest(
                    variant,
                    authored_hash,
                    semantic_hash,
                    walk_hash,
                )
            ),
            check,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate every full-direction semantic hooded-cloak variant."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generate_all(check=args.check)
    action = "Verified" if args.check else "Generated"
    print(f"{action} {len(VARIANTS)} full-direction cloak variants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
