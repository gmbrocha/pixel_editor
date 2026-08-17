from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from PIL import Image

try:
    from tools.finish_component_regions import MARKERS, generate_finished_component
except ModuleNotFoundError:  # Direct `python tools/...py` execution.
    from finish_component_regions import MARKERS, generate_finished_component


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = PROJECT_ROOT / "assets" / "character-forge"
SOURCE_ROOT = ASSET_ROOT / "semantic_sources" / "warlock-robe-front-walk"
AUTHORED_SOURCE = SOURCE_ROOT / "authored-regions.png"
SEMANTIC_SOURCE = SOURCE_ROOT / "semantic-regions.png"
PARTS_ROOT = ASSET_ROOT / "parts" / "outerwear"


@dataclass(frozen=True, slots=True)
class RobeVariant:
    component_id: str
    display_name: str
    preset: str
    tags: tuple[str, ...]


VARIANTS = (
    RobeVariant(
        "warlock-robe-semantic-void-amethyst",
        "Warlock Robe — Void Amethyst (Front Walk)",
        "warlock-void-amethyst",
        ("void", "amethyst", "gold_trim"),
    ),
    RobeVariant(
        "warlock-robe-semantic-blood-ritual",
        "Warlock Robe — Blood Ritual (Front Walk)",
        "warlock-blood-ritual",
        ("blood", "ritual", "ember_trim"),
    ),
    RobeVariant(
        "warlock-robe-semantic-necrotic-jade",
        "Warlock Robe — Necrotic Jade (Front Walk)",
        "warlock-necrotic-jade",
        ("necrotic", "jade", "bone_trim"),
    ),
    RobeVariant(
        "warlock-robe-semantic-astral-midnight",
        "Warlock Robe — Astral Midnight (Front Walk)",
        "warlock-astral-midnight",
        ("astral", "midnight", "cyan_trim"),
    ),
)


def _pixels(image: Image.Image):
    if hasattr(image, "get_flattened_data"):
        return image.get_flattened_data()
    return image.getdata()


def _json_bytes(data: dict[str, object]) -> bytes:
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def _write_or_check(path: Path, content: bytes, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"Generated Warlock Robe asset is stale or missing: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _source_manifest(authored_hash: str, semantic_hash: str) -> dict[str, object]:
    with Image.open(SEMANTIC_SOURCE) as opened:
        regions = opened.convert("RGBA")
    counts = {"main": 0, "trim": 0}
    for pixel in _pixels(regions):
        name = MARKERS.get(pixel)
        if name in counts:
            counts[name] += 1
    return {
        "schemaVersion": 1,
        "id": "warlock-robe-front-walk-semantic-regions",
        "sourceName": "walk_warlock_robe.png",
        "authoredSource": "authored-regions.png",
        "authoredSourceSha256": authored_hash,
        "semanticRegionsSha256": semantic_hash,
        "sheetSize": [384, 259],
        "logicalExtent": [384, 256],
        "animation": "walk",
        "direction": "front",
        "authoredFrameIndices": [0, 1, 2, 3, 4, 5],
        "regions": {
            "main": {"color": "#FF4040", "pixels": counts["main"]},
            "trim": {"color": "#FFD840", "pixels": counts["trim"]},
        },
        "extraction": (
            "Only exact opaque main and trim markers are retained; the supplied "
            "384x256 source is normalized to the canonical 384x259 Walk canvas."
        ),
    }


def _component_manifest(
    variant: RobeVariant,
    authored_hash: str,
    semantic_hash: str,
    walk_hash: str,
) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "id": variant.component_id,
        "displayName": variant.display_name,
        "slot": "outerwear",
        "occupiesSlots": ["outerwear"],
        "reservedSlots": [],
        "layer": "outerwear",
        "tags": [
            "warlock_robe",
            "robe",
            "semantic_regions",
            "deterministic",
            *variant.tags,
        ],
        "fit": "standard",
        "version": 1,
        "status": "incomplete",
        "developmentVisible": True,
        "animations": {"walk": "walk.png"},
        "coverage": {"walk": ["front"]},
        "provenance": {
            "kind": "deterministic_semantic_finish",
            "generator": "tools/generate_warlock_robe_variants.py",
            "generatorVersion": 1,
            "finisher": "tools/finish_component_regions.py",
            "preset": variant.preset,
            "authoredSource": (
                "semantic_sources/warlock-robe-front-walk/authored-regions.png"
            ),
            "authoredSourceSha256": authored_hash,
            "semanticSource": (
                "semantic_sources/warlock-robe-front-walk/semantic-regions.png"
            ),
            "semanticRegionsSha256": semantic_hash,
            "walkSha256": walk_hash,
            "authoredDirections": ["front"],
            "authoredFrameIndices": [0, 1, 2, 3, 4, 5],
        },
    }


def generate_all(*, check: bool = False) -> None:
    authored_hash = _digest(AUTHORED_SOURCE)
    semantic_hash: str | None = None
    for variant in VARIANTS:
        root = PARTS_ROOT / variant.component_id
        generated_semantic_hash, walk_hash = generate_finished_component(
            AUTHORED_SOURCE,
            SEMANTIC_SOURCE,
            root / "walk.png",
            preset=variant.preset,
            check=check,
        )
        if semantic_hash is None:
            semantic_hash = generated_semantic_hash
        elif semantic_hash != generated_semantic_hash:
            raise RuntimeError("Warlock Robe semantic extraction changed between variants")
        _write_or_check(
            root / "manifest.json",
            _json_bytes(
                _component_manifest(
                    variant,
                    authored_hash,
                    generated_semantic_hash,
                    walk_hash,
                )
            ),
            check,
        )
    if semantic_hash is None:
        raise RuntimeError("No Warlock Robe variants are configured")
    _write_or_check(
        SOURCE_ROOT / "source.json",
        _json_bytes(_source_manifest(authored_hash, semantic_hash)),
        check,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate four deterministic semantic Warlock Robe variants."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generate_all(check=args.check)
    action = "Verified" if args.check else "Generated"
    print(f"{action} {len(VARIANTS)} Warlock Robe variants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
