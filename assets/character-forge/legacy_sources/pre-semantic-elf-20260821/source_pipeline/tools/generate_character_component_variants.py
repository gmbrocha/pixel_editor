from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from typing import Callable

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_ROOT = PROJECT_ROOT / "assets" / "character-forge"
RGB = tuple[int, int, int]
ImageTransform = Callable[[Image.Image], Image.Image]


SHIRT_RAMP: tuple[RGB, ...] = (
    (13, 29, 56),
    (19, 39, 77),
    (23, 43, 79),
    (35, 53, 83),
    (44, 66, 103),
    (75, 106, 139),
    (87, 121, 159),
    (143, 174, 198),
    (158, 192, 218),
)
CRIMSON_RAMP: tuple[RGB, ...] = (
    (53, 16, 25),
    (77, 23, 35),
    (99, 32, 44),
    (122, 41, 53),
    (148, 54, 69),
    (185, 81, 95),
    (207, 107, 120),
    (232, 155, 164),
    (244, 185, 191),
)
CREAM_RAMP: tuple[RGB, ...] = (
    (70, 53, 36),
    (90, 70, 48),
    (110, 88, 60),
    (135, 113, 79),
    (163, 138, 99),
    (192, 167, 126),
    (210, 187, 148),
    (229, 210, 175),
    (242, 227, 198),
)
INDIGO_RAMP: tuple[RGB, ...] = (
    (23, 24, 48),
    (31, 34, 68),
    (40, 44, 88),
    (50, 56, 108),
    (63, 70, 130),
    (79, 89, 153),
    (99, 110, 174),
    (126, 137, 194),
    (153, 163, 211),
)

BOOT_RAMP: tuple[RGB, ...] = (
    (35, 18, 2),
    (60, 20, 1),
    (85, 41, 5),
    (119, 69, 20),
    (156, 97, 35),
    (160, 116, 59),
    (198, 132, 56),
)
IRON_RAMP: tuple[RGB, ...] = (
    (17, 21, 27),
    (27, 34, 43),
    (39, 49, 59),
    (53, 67, 78),
    (74, 90, 99),
    (102, 116, 122),
    (135, 147, 152),
)
@dataclass(frozen=True, slots=True)
class VariantSpec:
    id: str
    display_name: str
    source_component: str
    source_relative_path: str
    slot: str
    layer: str
    tags: tuple[str, ...]
    description: str
    transform: ImageTransform
    reserved_slots: tuple[str, ...] = ()
    color_ramp: tuple[RGB, ...] = ()
    ramp_main_index: int | None = None
    seed: int | None = None


def _palette_map(source: tuple[RGB, ...], target: tuple[RGB, ...]) -> dict[RGB, RGB]:
    if len(source) != len(target):
        raise ValueError("Palette ramps must have matching lengths")
    return dict(zip(source, target))


def _replace_palette(image: Image.Image, mapping: dict[RGB, RGB]) -> Image.Image:
    output = image.convert("RGBA").copy()
    pixels = output.load()
    for y in range(output.height):
        for x in range(output.width):
            red, green, blue, alpha = pixels[x, y]
            replacement = mapping.get((red, green, blue))
            if replacement is not None:
                pixels[x, y] = (*replacement, alpha)
    return output


def _two_tone_yoke(image: Image.Image) -> Image.Image:
    cream = _palette_map(SHIRT_RAMP, CREAM_RAMP)
    indigo = _palette_map(SHIRT_RAMP, INDIGO_RAMP)
    output = image.convert("RGBA").copy()
    pixels = output.load()
    for y in range(output.height):
        for x in range(output.width):
            red, green, blue, alpha = pixels[x, y]
            source = (red, green, blue)
            replacement = indigo.get(source) if y <= 32 else cream.get(source)
            if replacement is not None:
                pixels[x, y] = (*replacement, alpha)
    return output


def _blackened_iron_boots(image: Image.Image) -> Image.Image:
    return _replace_palette(image, _palette_map(BOOT_RAMP, IRON_RAMP))


VARIANTS: tuple[VariantSpec, ...] = (
    VariantSpec(
        id="walking-shirt-crimson-derived",
        display_name="Crimson Walking Shirt (Derived)",
        source_component="walking-shirt-test",
        source_relative_path="parts/torso/walking-shirt-test/walk.png",
        slot="torso",
        layer="torso",
        tags=("shirt", "crimson", "palette_variant", "deterministic"),
        description="Exact silhouette with a nine-step crimson palette remap.",
        transform=lambda image: _replace_palette(
            image, _palette_map(SHIRT_RAMP, CRIMSON_RAMP)
        ),
        color_ramp=CRIMSON_RAMP,
        ramp_main_index=4,
    ),
    VariantSpec(
        id="walking-shirt-cream-indigo-yoke-derived",
        display_name="Cream Shirt + Indigo Yoke (Derived)",
        source_component="walking-shirt-test",
        source_relative_path="parts/torso/walking-shirt-test/walk.png",
        slot="torso",
        layer="torso",
        tags=("shirt", "linen", "two_tone", "deterministic"),
        description="Exact silhouette with a coordinate-masked indigo yoke over cream linen.",
        transform=_two_tone_yoke,
    ),
    VariantSpec(
        id="leather-boots-blackened-iron-derived",
        display_name="Blackened Iron Boots (Derived)",
        source_component="leather-boots-front-test",
        source_relative_path="parts/feet/leather-boots-front-test/walk.png",
        slot="feet",
        layer="footwear",
        tags=("boots", "iron", "palette_variant", "deterministic"),
        description="Exact silhouette with a stable seven-step iron material ramp.",
        transform=_blackened_iron_boots,
    ),
)


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def _manifest(spec: VariantSpec, source_hash: str, walk_hash: str) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schemaVersion": 1,
        "id": spec.id,
        "displayName": spec.display_name,
        "slot": spec.slot,
        "occupiesSlots": [spec.slot],
        "reservedSlots": list(spec.reserved_slots),
        "layer": spec.layer,
        "tags": list(spec.tags),
        "fit": "standard",
        "version": 1,
        "status": "incomplete",
        "developmentVisible": True,
        "animations": {"walk": "walk.png"},
        "coverage": {"walk": ["front"]},
        "provenance": {
            "kind": "deterministic_variant",
            "generator": "tools/generate_character_component_variants.py",
            "generatorVersion": 1,
            "sourceComponent": spec.source_component,
            "sourceSha256": source_hash,
            "walkSha256": walk_hash,
            "transformation": spec.description,
            **({"seed": spec.seed} if spec.seed is not None else {}),
        },
    }
    if spec.color_ramp and spec.ramp_main_index is not None:
        manifest["colorRamp"] = {
            "main": "#{:02X}{:02X}{:02X}".format(
                *spec.color_ramp[spec.ramp_main_index]
            ),
            "colors": ["#{:02X}{:02X}{:02X}".format(*color) for color in spec.color_ramp],
        }
    return manifest


def generate_variants(
    asset_root: str | Path = DEFAULT_ASSET_ROOT,
    *,
    output_root: str | Path | None = None,
    check: bool = False,
) -> tuple[Path, ...]:
    root = Path(asset_root)
    destination_root = Path(output_root) if output_root is not None else root / "parts"
    outputs: list[Path] = []
    for spec in VARIANTS:
        source_path = root / spec.source_relative_path
        source_bytes = source_path.read_bytes()
        source_hash = sha256(source_bytes).hexdigest()
        with Image.open(BytesIO(source_bytes)) as opened:
            source = opened.convert("RGBA")
        generated = spec.transform(source)
        if generated.size != source.size:
            raise ValueError(f"Variant {spec.id} changed sheet geometry")
        if generated.getchannel("A").tobytes() != source.getchannel("A").tobytes():
            raise ValueError(f"Variant {spec.id} changed the source silhouette")
        walk_bytes = _png_bytes(generated)
        walk_hash = sha256(walk_bytes).hexdigest()
        manifest_bytes = (
            json.dumps(_manifest(spec, source_hash, walk_hash), indent=2) + "\n"
        ).encode("utf-8")
        component_root = destination_root / spec.slot / spec.id
        expected = {
            component_root / "walk.png": walk_bytes,
            component_root / "manifest.json": manifest_bytes,
        }
        for path, content in expected.items():
            if check:
                if not path.is_file() or path.read_bytes() != content:
                    raise ValueError(f"Generated variant is stale or missing: {path}")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            outputs.append(path)
        if sha256(source_path.read_bytes()).hexdigest() != source_hash:
            raise RuntimeError(f"Source component changed while generating {spec.id}")
    return tuple(outputs)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic Character Forge variants without editing sources."
    )
    parser.add_argument(
        "--asset-root",
        type=Path,
        default=DEFAULT_ASSET_ROOT,
        help="Character Forge asset root",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed variants do not match deterministic output",
    )
    args = parser.parse_args()
    outputs = generate_variants(args.asset_root, check=args.check)
    action = "Verified" if args.check else "Generated"
    print(f"{action} {len(VARIANTS)} variants ({len(outputs)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
