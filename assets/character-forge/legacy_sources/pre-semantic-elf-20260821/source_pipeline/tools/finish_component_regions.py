from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RGBA = tuple[int, int, int, int]
RGB = tuple[int, int, int]

MARKERS: dict[RGBA, str] = {
    (255, 64, 64, 255): "main",
    (64, 255, 128, 255): "lining",
    (255, 216, 64, 255): "trim",
    (122, 64, 168, 255): "hardware",
    (8, 62, 255, 255): "hood",
}

FOREST_WOOL_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": (
        (14, 30, 20),
        (22, 45, 27),
        (33, 63, 35),
        (48, 82, 45),
        (70, 105, 62),
    ),
    "lining": (
        (12, 28, 30),
        (18, 43, 44),
        (27, 59, 58),
        (42, 78, 73),
        (62, 99, 91),
    ),
    "trim": (
        (54, 36, 12),
        (88, 59, 19),
        (126, 87, 29),
        (165, 121, 43),
        (207, 165, 71),
    ),
    "hardware": (
        (45, 25, 14),
        (75, 42, 22),
        (111, 65, 31),
        (150, 96, 48),
        (192, 137, 75),
    ),
}

BURGUNDY_VELVET_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": (
        (43, 14, 25),
        (66, 20, 35),
        (91, 29, 48),
        (121, 42, 63),
        (154, 61, 82),
    ),
    "lining": (
        (25, 20, 30),
        (39, 29, 45),
        (55, 41, 62),
        (76, 57, 82),
        (101, 78, 106),
    ),
    "trim": (
        (59, 39, 13),
        (94, 64, 21),
        (133, 94, 32),
        (174, 132, 49),
        (218, 177, 79),
    ),
    "hardware": (
        (48, 28, 15),
        (78, 46, 24),
        (113, 71, 35),
        (151, 103, 53),
        (194, 146, 82),
    ),
}

STORM_BLUE_SILVER_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": (
        (14, 24, 38),
        (21, 36, 55),
        (31, 51, 75),
        (45, 70, 99),
        (65, 94, 127),
    ),
    "lining": (
        (19, 25, 31),
        (30, 39, 47),
        (43, 54, 64),
        (60, 73, 84),
        (82, 96, 107),
    ),
    "trim": (
        (48, 55, 61),
        (72, 82, 90),
        (101, 113, 122),
        (136, 149, 157),
        (177, 189, 195),
    ),
    "hardware": (
        (36, 42, 47),
        (57, 66, 72),
        (83, 94, 101),
        (115, 127, 134),
        (154, 165, 171),
    ),
}

AUTUMN_RUSSET_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": (
        (48, 24, 13),
        (73, 35, 17),
        (101, 49, 22),
        (134, 68, 31),
        (171, 94, 46),
    ),
    "lining": (
        (26, 31, 18),
        (41, 47, 25),
        (59, 65, 34),
        (80, 86, 46),
        (105, 111, 62),
    ),
    "trim": (
        (64, 47, 24),
        (98, 74, 39),
        (135, 105, 58),
        (174, 142, 83),
        (216, 187, 119),
    ),
    "hardware": (
        (48, 27, 14),
        (79, 45, 22),
        (115, 70, 35),
        (154, 103, 55),
        (198, 147, 87),
    ),
}

POINTED_HOOD_GREEN_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": (
        (15, 31, 17),
        (23, 47, 22),
        (34, 65, 29),
        (50, 85, 39),
        (73, 108, 56),
    ),
    "lining": (
        (12, 28, 30),
        (18, 43, 44),
        (27, 59, 58),
        (42, 78, 73),
        (62, 99, 91),
    ),
    "trim": (
        (25, 34, 13),
        (39, 53, 18),
        (57, 72, 26),
        (78, 94, 39),
        (105, 122, 59),
    ),
    "hardware": (
        (45, 25, 14),
        (75, 42, 22),
        (111, 65, 31),
        (150, 96, 48),
        (192, 137, 75),
    ),
}

WINTER_GRAY_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": (
        (25, 34, 38),
        (38, 49, 54),
        (53, 65, 71),
        (72, 85, 91),
        (96, 111, 117),
    ),
    "lining": (
        (17, 27, 31),
        (26, 40, 45),
        (38, 55, 60),
        (53, 72, 78),
        (71, 92, 98),
    ),
    "trim": (
        (34, 40, 43),
        (51, 59, 63),
        (72, 81, 85),
        (96, 107, 111),
        (125, 137, 141),
    ),
    "hardware": (
        (36, 42, 47),
        (57, 66, 72),
        (83, 94, 101),
        (115, 127, 134),
        (154, 165, 171),
    ),
}

ROYAL_AMETHYST_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": ((29, 16, 45), (47, 25, 70), (69, 38, 98), (96, 55, 130), (132, 79, 166)),
    "lining": ((22, 18, 35), (35, 29, 52), (50, 42, 72), (70, 59, 96), (94, 81, 124)),
    "trim": ((61, 40, 12), (98, 66, 20), (140, 98, 31), (184, 137, 49), (230, 184, 82)),
    "hardware": ((47, 34, 15), (77, 57, 25), (111, 86, 40), (151, 124, 64), (197, 169, 99)),
}

MIDNIGHT_RAVEN_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": ((9, 11, 17), (16, 20, 29), (25, 31, 43), (37, 45, 59), (54, 64, 80)),
    "lining": ((35, 8, 18), (58, 13, 28), (84, 21, 39), (115, 32, 53), (151, 49, 70)),
    "trim": ((29, 34, 39), (47, 54, 61), (70, 79, 87), (99, 109, 118), (134, 145, 153)),
    "hardware": ((45, 29, 12), (75, 50, 20), (108, 76, 32), (148, 109, 51), (193, 153, 82)),
}

DESERT_SAND_TEAL_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": ((52, 38, 22), (80, 59, 33), (111, 84, 48), (146, 115, 69), (185, 153, 96)),
    "lining": ((8, 37, 38), (13, 58, 58), (21, 82, 79), (33, 109, 102), (51, 140, 127)),
    "trim": ((63, 41, 17), (98, 66, 27), (136, 96, 42), (177, 134, 65), (219, 178, 101)),
    "hardware": ((42, 30, 17), (69, 49, 27), (101, 75, 42), (139, 109, 66), (183, 152, 101)),
}

IVORY_CRIMSON_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": ((66, 61, 50), (98, 91, 75), (132, 123, 103), (169, 160, 137), (211, 203, 179)),
    "lining": ((45, 10, 20), (71, 16, 30), (100, 24, 42), (133, 36, 56), (171, 54, 75)),
    "trim": ((54, 18, 24), (87, 27, 37), (122, 40, 52), (161, 59, 70), (204, 87, 98)),
    "hardware": ((48, 42, 32), (76, 68, 53), (108, 99, 79), (146, 137, 113), (190, 181, 154)),
}

WARLOCK_VOID_AMETHYST_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": ((18, 8, 31), (31, 13, 51), (48, 21, 75), (70, 33, 103), (99, 51, 137)),
    "lining": ((12, 10, 20), (21, 17, 32), (33, 26, 47), (48, 39, 64), (67, 56, 84)),
    "trim": ((65, 42, 10), (103, 69, 17), (145, 101, 27), (190, 144, 45), (235, 193, 79)),
    "hardware": ((48, 31, 13), (77, 51, 21), (111, 78, 33), (150, 112, 53), (194, 157, 84)),
}

WARLOCK_BLOOD_RITUAL_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": ((35, 5, 10), (58, 8, 15), (85, 13, 22), (117, 22, 31), (154, 36, 44)),
    "lining": ((18, 10, 12), (29, 17, 19), (43, 26, 28), (60, 38, 39), (81, 53, 53)),
    "trim": ((67, 20, 5), (107, 35, 8), (151, 55, 13), (199, 82, 23), (242, 121, 43)),
    "hardware": ((45, 27, 11), (73, 45, 18), (106, 69, 29), (145, 101, 47), (190, 142, 76)),
}

WARLOCK_NECROTIC_JADE_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": ((7, 22, 18), (11, 36, 29), (17, 53, 42), (26, 73, 56), (39, 97, 73)),
    "lining": ((14, 18, 13), (23, 29, 21), (35, 43, 31), (50, 59, 43), (69, 79, 58)),
    "trim": ((51, 58, 25), (79, 88, 39), (111, 121, 57), (147, 157, 81), (187, 196, 113)),
    "hardware": ((39, 43, 25), (63, 68, 40), (91, 97, 60), (125, 131, 87), (165, 170, 122)),
}

WARLOCK_ASTRAL_MIDNIGHT_PALETTES: dict[str, tuple[RGB, ...]] = {
    "main": ((6, 14, 32), (10, 25, 52), (16, 38, 76), (24, 55, 104), (36, 77, 136)),
    "lining": ((10, 20, 28), (17, 33, 43), (26, 48, 60), (38, 66, 80), (54, 88, 103)),
    "trim": ((35, 64, 73), (53, 96, 106), (76, 132, 140), (104, 171, 177), (142, 212, 215)),
    "hardware": ((31, 40, 48), (50, 62, 72), (74, 89, 101), (104, 121, 133), (140, 159, 170)),
}


def _add_hood_shadow(palettes: dict[str, tuple[RGB, ...]]) -> None:
    """Give the authored hood panel a stable, same-hue shadow of the main fabric."""
    palettes["hood"] = tuple(
        tuple(max(0, round(channel * 0.78)) for channel in color)
        for color in palettes["main"]
    )


for _palettes in (
    FOREST_WOOL_PALETTES,
    BURGUNDY_VELVET_PALETTES,
    STORM_BLUE_SILVER_PALETTES,
    AUTUMN_RUSSET_PALETTES,
    POINTED_HOOD_GREEN_PALETTES,
    WINTER_GRAY_PALETTES,
    ROYAL_AMETHYST_PALETTES,
    MIDNIGHT_RAVEN_PALETTES,
    DESERT_SAND_TEAL_PALETTES,
    IVORY_CRIMSON_PALETTES,
    WARLOCK_VOID_AMETHYST_PALETTES,
    WARLOCK_BLOOD_RITUAL_PALETTES,
    WARLOCK_NECROTIC_JADE_PALETTES,
    WARLOCK_ASTRAL_MIDNIGHT_PALETTES,
):
    _add_hood_shadow(_palettes)

PALETTE_PRESETS: dict[str, dict[str, tuple[RGB, ...]]] = {
    "forest-wool": FOREST_WOOL_PALETTES,
    "burgundy-velvet": BURGUNDY_VELVET_PALETTES,
    "storm-blue-silver": STORM_BLUE_SILVER_PALETTES,
    "autumn-russet": AUTUMN_RUSSET_PALETTES,
    "pointed-hood-green": POINTED_HOOD_GREEN_PALETTES,
    "winter-gray": WINTER_GRAY_PALETTES,
    "royal-amethyst": ROYAL_AMETHYST_PALETTES,
    "midnight-raven": MIDNIGHT_RAVEN_PALETTES,
    "desert-sand-teal": DESERT_SAND_TEAL_PALETTES,
    "ivory-crimson": IVORY_CRIMSON_PALETTES,
    "warlock-void-amethyst": WARLOCK_VOID_AMETHYST_PALETTES,
    "warlock-blood-ritual": WARLOCK_BLOOD_RITUAL_PALETTES,
    "warlock-necrotic-jade": WARLOCK_NECROTIC_JADE_PALETTES,
    "warlock-astral-midnight": WARLOCK_ASTRAL_MIDNIGHT_PALETTES,
}


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def extract_semantic_regions(source: Image.Image) -> Image.Image:
    """Keep only exact semantic marker pixels and normalize Walk canvas height."""
    rgba = source.convert("RGBA")
    if rgba.width != 384 or rgba.height not in {256, 259}:
        raise ValueError(
            f"Semantic Walk test must be 384x256 or 384x259, got {rgba.size}"
        )
    regions = Image.new("RGBA", (384, 259), (0, 0, 0, 0))
    source_pixels = rgba.load()
    output_pixels = regions.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            pixel = source_pixels[x, y]
            if pixel in MARKERS:
                output_pixels[x, y] = pixel
    if regions.getbbox() is None:
        raise ValueError("Source contains none of the configured semantic marker colors")
    return regions


def _frame_anchor(
    regions: Image.Image,
    direction_row: int,
    frame_index: int,
) -> tuple[float, float]:
    left = frame_index * 64
    top = direction_row * 64
    hardware = MARKERS[(122, 64, 168, 255)]
    points: list[tuple[int, int]] = []
    fallback: list[tuple[int, int]] = []
    for local_y in range(64):
        for local_x in range(64):
            pixel = regions.getpixel((left + local_x, top + local_y))
            region = MARKERS.get(pixel)
            if region is not None:
                fallback.append((local_x, local_y))
            if region == hardware:
                points.append((local_x, local_y))
    selected = points or fallback
    if not selected:
        return 31.5, 31.5
    return (
        sum(point[0] for point in selected) / len(selected),
        sum(point[1] for point in selected) / len(selected),
    )


def _region_at(regions: Image.Image, x: int, y: int) -> str | None:
    if x < 0 or y < 0 or x >= regions.width or y >= regions.height:
        return None
    return MARKERS.get(regions.getpixel((x, y)))


def _shade_index(
    regions: Image.Image,
    x: int,
    y: int,
    region: str,
    anchor: tuple[float, float],
) -> int:
    local_x = x % 64
    local_y = y % 64
    anchor_x, anchor_y = anchor
    score = 0.0

    same_left = _region_at(regions, x - 1, y) == region
    same_right = _region_at(regions, x + 1, y) == region
    same_up = _region_at(regions, x, y - 1) == region
    same_down = _region_at(regions, x, y + 1) == region
    occupied_left = _region_at(regions, x - 1, y) is not None
    occupied_right = _region_at(regions, x + 1, y) is not None
    occupied_up = _region_at(regions, x, y - 1) is not None
    occupied_down = _region_at(regions, x, y + 1) is not None

    # Fixed top-left illumination. These rules are geometric and contain no
    # per-frame noise, so highlights remain attached to equivalent boundaries.
    if not same_left:
        score += 0.55
    if not same_up:
        score += 0.8
    if not same_right:
        score -= 0.45
    if not same_down:
        score -= 0.75
    if local_x < anchor_x - 2:
        score += 0.2
    elif local_x > anchor_x + 2:
        score -= 0.2
    if local_y < anchor_y - 3:
        score += 0.15
    elif local_y > anchor_y + 8:
        score -= 0.15

    # External lower/right edges act as a stable colored outline rather than a
    # bright, randomly changing glint.
    if not occupied_down or not occupied_right:
        score -= 0.65
    elif not occupied_up or not occupied_left:
        score += 0.25

    # Two broad folds radiate from the authored clasp anchor. They move with the
    # garment instead of being regenerated from unrelated sheet coordinates.
    if region in {"main", "lining"}:
        dy = local_y - anchor_y
        dx = local_x - anchor_x
        if dy >= 3:
            if abs(dx * 4 + dy) <= 3 or abs(dx * 4 - dy) <= 3:
                score -= 0.8
            elif abs(dx * 4 + dy) <= 7 or abs(dx * 4 - dy) <= 7:
                score += 0.35

    if score <= -0.85:
        return 0
    if score <= -0.25:
        return 1
    if score < 0.45:
        return 2
    if score < 1.05:
        return 3
    return 4


def finish_semantic_regions(
    regions: Image.Image,
    palettes: dict[str, tuple[RGB, ...]] = FOREST_WOOL_PALETTES,
) -> Image.Image:
    source = regions.convert("RGBA")
    if source.size != (384, 259):
        raise ValueError(f"Semantic region sheet must be 384x259, got {source.size}")
    for name in set(MARKERS.values()):
        palette = palettes.get(name)
        if palette is None or len(palette) != 5:
            raise ValueError(f"Region {name!r} requires an exact five-color palette")

    output = Image.new("RGBA", source.size, (0, 0, 0, 0))
    output_pixels = output.load()
    anchors = {
        (direction_row, frame_index): _frame_anchor(
            source, direction_row, frame_index
        )
        for direction_row in range(4)
        for frame_index in range(6)
    }
    for y in range(source.height):
        for x in range(source.width):
            region = _region_at(source, x, y)
            if region is None:
                continue
            shade = _shade_index(
                source,
                x,
                y,
                region,
                anchors[(y // 64, x // 64)],
            )
            output_pixels[x, y] = (*palettes[region][shade], 255)

    if output.getchannel("A").tobytes() != source.getchannel("A").tobytes():
        raise RuntimeError("Finishing changed the supplied semantic silhouette")
    return output


def _write_or_check(path: Path, content: bytes, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"Finished component is stale or missing: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def generate_finished_component(
    source_path: str | Path,
    regions_path: str | Path,
    output_path: str | Path,
    *,
    preset: str = "forest-wool",
    check: bool = False,
) -> tuple[str, str]:
    try:
        palettes = PALETTE_PRESETS[preset]
    except KeyError as exc:
        raise ValueError(f"Unknown semantic finish preset: {preset}") from exc
    source_bytes = Path(source_path).read_bytes()
    with Image.open(BytesIO(source_bytes)) as opened:
        regions = extract_semantic_regions(opened)
    finished = finish_semantic_regions(regions, palettes)
    region_bytes = _png_bytes(regions)
    output_bytes = _png_bytes(finished)
    _write_or_check(Path(regions_path), region_bytes, check)
    _write_or_check(Path(output_path), output_bytes, check)
    return sha256(region_bytes).hexdigest(), sha256(output_bytes).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Finish exact-color semantic component regions deterministically."
    )
    parser.add_argument("source", type=Path, help="Composite or mask containing markers")
    parser.add_argument("--regions-out", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--preset",
        choices=tuple(PALETTE_PRESETS),
        default="forest-wool",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    region_hash, output_hash = generate_finished_component(
        args.source,
        args.regions_out,
        args.output,
        preset=args.preset,
        check=args.check,
    )
    action = "Verified" if args.check else "Generated"
    print(f"{action} semantic regions sha256={region_hash}")
    print(f"{action} finished component sha256={output_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
