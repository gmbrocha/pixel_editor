from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

try:
    from tools.finish_component_regions import MARKERS, finish_semantic_regions
except ModuleNotFoundError:  # Direct `python tools/...py` execution.
    from finish_component_regions import MARKERS, finish_semantic_regions


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = PROJECT_ROOT / "assets" / "character-forge"
BASE_WALK = ASSET_ROOT / "bases" / "human-01" / "walk.png"
PARTS_ROOT = ASSET_ROOT / "parts"
WORKBENCH_ROOT = ASSET_ROOT / "workbench"
CONCEPT_BOARD = WORKBENCH_ROOT / "starter-component-concept-board.png"
FRAME_SIZE = 64
FRAMES = 6

TRANSPARENT = (0, 0, 0, 0)
MAIN = (255, 64, 64, 255)
LINING = (64, 255, 128, 255)
TRIM = (255, 216, 64, 255)
HARDWARE = (122, 64, 168, 255)
SPECIAL = (8, 62, 255, 255)


@dataclass(frozen=True, slots=True)
class FrameAnchors:
    center_x: int
    eye_left_x: int
    eye_right_x: int
    eye_y: int
    head_top: int


DrawFunction = Callable[[Image.Image, Image.Image, FrameAnchors], None]


@dataclass(frozen=True, slots=True)
class Starter:
    component_id: str
    display_name: str
    slot: str
    layer: str
    draw: DrawFunction
    colors: dict[str, tuple[int, int, int]]
    tags: tuple[str, ...]
    reserved_slots: tuple[str, ...] = ()
    authored_walk: str | None = None
    alpha_occluded_by_tags: tuple[str, ...] = ()


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def _json_bytes(data: object) -> bytes:
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def _write_or_check(path: Path, content: bytes, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"Silhouette starter is stale or missing: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _digest_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def _pixels(image: Image.Image):
    if hasattr(image, "get_flattened_data"):
        return image.get_flattened_data()
    return image.getdata()


def _anchors(base: Image.Image) -> FrameAnchors:
    whites = [
        (x, y)
        for y in range(32)
        for x in range(64)
        if base.getpixel((x, y)) == (255, 255, 255, 255)
    ]
    if not whites:
        raise ValueError("Front Walk frame has no authoritative eye pixels")
    eye_xs = sorted({x for x, _y in whites})
    eye_y = min(y for _x, y in whites)
    head_pixels = [
        (x, y)
        for y in range(32)
        for x in range(64)
        if base.getpixel((x, y))[3]
    ]
    return FrameAnchors(
        center_x=round((eye_xs[0] + eye_xs[-1]) / 2),
        eye_left_x=eye_xs[0],
        eye_right_x=eye_xs[-1],
        eye_y=eye_y,
        head_top=min(y for _x, y in head_pixels),
    )


def _draw_hair(image: Image.Image, _base: Image.Image, a: FrameAnchors) -> None:
    d = ImageDraw.Draw(image)
    cx, top, ey = a.center_x, a.head_top, a.eye_y
    crown = [
        (cx - 8, ey - 1), (cx - 9, top + 2), (cx - 7, top + 2),
        (cx - 8, top - 1), (cx - 5, top), (cx - 5, top - 3),
        (cx - 2, top - 1), (cx, top - 4), (cx + 2, top - 1),
        (cx + 5, top - 3), (cx + 5, top), (cx + 8, top - 1),
        (cx + 7, top + 3), (cx + 9, top + 4), (cx + 7, ey + 1),
        (cx + 5, ey + 3), (cx + 3, ey), (cx + 1, ey + 2),
        (cx - 1, ey - 1), (cx - 3, ey + 2), (cx - 5, ey),
        (cx - 6, ey + 3),
    ]
    d.polygon(crown, fill=MAIN)
    d.line((cx - 6, top + 1, cx - 2, top - 2), fill=TRIM, width=1)
    d.line((cx - 1, top - 2, cx + 3, top), fill=TRIM, width=1)
    d.point((cx + 5, top + 2), fill=LINING)


def _pauldron_polygon(cx: int, side: int) -> list[tuple[int, int]]:
    inner = cx + side * 4
    outer = cx + side * 12
    return [
        (inner, 29), (cx + side * 7, 27), (cx + side * 10, 28),
        (outer, 31), (cx + side * 11, 35), (cx + side * 8, 37),
        (cx + side * 5, 35),
    ]


def _draw_one_pauldron(image: Image.Image, _base: Image.Image, a: FrameAnchors) -> None:
    d = ImageDraw.Draw(image)
    cx = a.center_x
    d.polygon(_pauldron_polygon(cx, -1), fill=MAIN)
    d.line((cx - 5, 29, cx - 10, 31, cx - 9, 34), fill=TRIM, width=1)
    d.rectangle((cx - 10, 32, cx - 8, 33), fill=LINING)
    d.line((cx - 6, 31, cx + 5, 39), fill=MAIN, width=2)
    d.point((cx, 35), fill=HARDWARE)


def _draw_gloves(image: Image.Image, base: Image.Image, a: FrameAnchors) -> None:
    pixels = image.load()
    cx = a.center_x
    for y in range(32, 42):
        for x in range(64):
            if base.getpixel((x, y))[3] and abs(x - cx) >= 5:
                pixels[x, y] = MAIN
    d = ImageDraw.Draw(image)
    d.line((cx - 10, 33, cx - 6, 33), fill=TRIM, width=1)
    d.line((cx + 6, 33, cx + 10, 33), fill=TRIM, width=1)


def _draw_eye_patch(image: Image.Image, _base: Image.Image, a: FrameAnchors) -> None:
    d = ImageDraw.Draw(image)
    x, y = a.eye_right_x, a.eye_y
    d.line((x - 5, y - 6, x + 5, y + 1), fill=MAIN, width=1)
    d.rectangle((x - 1, y - 1, x + 2, y + 2), fill=MAIN)
    d.point((x, y), fill=HARDWARE)


def _draw_double_pauldrons(image: Image.Image, _base: Image.Image, a: FrameAnchors) -> None:
    d = ImageDraw.Draw(image)
    cx = a.center_x
    for side in (-1, 1):
        d.polygon(_pauldron_polygon(cx, side), fill=MAIN)
        d.line(
            (cx + side * 5, 29, cx + side * 10, 31, cx + side * 9, 35),
            fill=TRIM,
            width=1,
        )
        d.rectangle(
            (min(cx + side * 10, cx + side * 7), 32, max(cx + side * 10, cx + side * 7), 33),
            fill=LINING,
        )
        d.point((cx + side * 11, 30), fill=HARDWARE)


def _draw_mage_vestments(image: Image.Image, _base: Image.Image, a: FrameAnchors) -> None:
    d = ImageDraw.Draw(image)
    cx, top = a.center_x, a.head_top
    d.polygon(
        [
            (cx - 13, top), (cx - 6, top - 2), (cx - 3, top - 8),
            (cx, top - 14), (cx + 3, top - 9), (cx + 8, top - 11),
            (cx + 7, top - 5), (cx + 12, top - 3), (cx + 10, top),
        ],
        fill=SPECIAL,
    )
    d.polygon([(cx - 15, top), (cx + 14, top), (cx + 10, top + 3), (cx - 12, top + 3)], fill=MAIN)
    d.line((cx - 11, top, cx + 10, top), fill=TRIM, width=1)
    d.polygon([(cx - 9, 29), (cx, 34), (cx + 9, 29), (cx + 7, 40), (cx, 45), (cx - 7, 40)], fill=MAIN)
    d.polygon([(cx - 5, 30), (cx, 35), (cx + 5, 30), (cx, 39)], fill=LINING)
    d.line((cx, 34, cx, 43), fill=TRIM, width=1)
    d.point((cx, 35), fill=HARDWARE)


def _draw_leather_armor(image: Image.Image, _base: Image.Image, a: FrameAnchors) -> None:
    d = ImageDraw.Draw(image)
    cx = a.center_x
    d.polygon([(cx - 7, 29), (cx - 4, 28), (cx, 31), (cx + 4, 28), (cx + 7, 30), (cx + 6, 40), (cx - 6, 40)], fill=MAIN)
    d.line((cx - 5, 29, cx + 5, 39), fill=LINING, width=2)
    d.line((cx + 5, 29, cx - 4, 39), fill=LINING, width=1)
    d.rectangle((cx - 7, 38, cx + 7, 40), fill=TRIM)
    d.rectangle((cx - 1, 38, cx + 1, 40), fill=HARDWARE)
    d.polygon([(cx - 6, 41), (cx - 2, 41), (cx - 3, 45), (cx - 7, 43)], fill=MAIN)
    d.polygon([(cx + 2, 41), (cx + 6, 41), (cx + 7, 43), (cx + 3, 45)], fill=MAIN)


def _draw_ratty_shawl(image: Image.Image, _base: Image.Image, a: FrameAnchors) -> None:
    d = ImageDraw.Draw(image)
    cx = a.center_x
    d.polygon(
        [
            (cx - 11, 28), (cx - 7, 26), (cx - 3, 29), (cx, 27),
            (cx + 4, 29), (cx + 8, 26), (cx + 12, 29), (cx + 11, 36),
            (cx + 9, 39), (cx + 7, 37), (cx + 5, 42), (cx + 2, 39),
            (cx, 43), (cx - 3, 39), (cx - 6, 42), (cx - 7, 37),
            (cx - 10, 40),
        ],
        fill=MAIN,
    )
    d.line((cx - 8, 29, cx, 34, cx + 8, 29), fill=LINING, width=2)
    d.line((cx - 6, 34, cx + 6, 34), fill=TRIM, width=1)
    d.point((cx - 8, 37), fill=TRANSPARENT)
    d.point((cx + 5, 39), fill=TRANSPARENT)


def _draw_headband(image: Image.Image, _base: Image.Image, a: FrameAnchors) -> None:
    d = ImageDraw.Draw(image)
    y = a.eye_y - 4
    d.rectangle((a.center_x - 7, y, a.center_x + 7, y + 2), fill=MAIN)
    d.line((a.center_x - 5, y, a.center_x + 4, y), fill=TRIM, width=1)
    d.point((a.center_x + 7, y + 1), fill=HARDWARE)
    d.line((a.center_x + 8, y + 1, a.center_x + 11, y + 4), fill=MAIN, width=2)
    d.line((a.center_x + 9, y + 3, a.center_x + 11, y + 7), fill=LINING, width=1)


def _draw_orcish_armor(image: Image.Image, _base: Image.Image, a: FrameAnchors) -> None:
    d = ImageDraw.Draw(image)
    cx = a.center_x
    for side in (-1, 1):
        d.polygon(
            [
                (cx + side * 3, 29), (cx + side * 7, 26),
                (cx + side * 9, 23), (cx + side * 10, 28),
                (cx + side * 14, 26), (cx + side * 12, 31),
                (cx + side * 14, 34), (cx + side * 10, 36),
                (cx + side * 6, 34),
            ],
            fill=MAIN,
        )
        d.line((cx + side * 6, 29, cx + side * 11, 32), fill=TRIM, width=1)
        d.point((cx + side * 10, 30), fill=HARDWARE)
    d.polygon([(cx - 6, 29), (cx, 32), (cx + 6, 29), (cx + 5, 41), (cx - 5, 41)], fill=LINING)
    d.line((cx - 5, 31, cx + 5, 39), fill=MAIN, width=2)
    d.rectangle((cx - 6, 39, cx + 6, 41), fill=TRIM)
    d.rectangle((cx - 1, 39, cx + 1, 41), fill=HARDWARE)
    d.polygon([(cx - 3, 42), (cx + 3, 42), (cx, 47)], fill=MAIN)


def _draw_cult_mask(image: Image.Image, _base: Image.Image, a: FrameAnchors) -> None:
    d = ImageDraw.Draw(image)
    cx, top = a.center_x, a.head_top
    d.polygon([(cx - 6, top), (cx - 10, top - 7), (cx - 9, top - 11), (cx - 6, top - 5), (cx - 4, top - 2)], fill=MAIN)
    d.polygon([(cx + 6, top), (cx + 10, top - 7), (cx + 9, top - 11), (cx + 6, top - 5), (cx + 4, top - 2)], fill=MAIN)
    d.polygon([(cx - 7, top), (cx, top - 3), (cx + 7, top), (cx + 6, a.eye_y + 3), (cx + 2, a.eye_y + 8), (cx, a.eye_y + 10), (cx - 2, a.eye_y + 8), (cx - 6, a.eye_y + 3)], fill=MAIN)
    d.polygon([(a.eye_left_x - 1, a.eye_y - 1), (a.eye_left_x + 2, a.eye_y), (a.eye_left_x, a.eye_y + 2)], fill=SPECIAL)
    d.polygon([(a.eye_right_x + 1, a.eye_y - 1), (a.eye_right_x - 2, a.eye_y), (a.eye_right_x, a.eye_y + 2)], fill=SPECIAL)
    d.line((cx, top, cx, a.eye_y + 6), fill=TRIM, width=1)
    d.point((cx, a.eye_y - 2), fill=HARDWARE)


def _color_set(
    main: tuple[int, int, int],
    lining: tuple[int, int, int],
    trim: tuple[int, int, int],
    hardware: tuple[int, int, int],
    special: tuple[int, int, int],
) -> dict[str, tuple[int, int, int]]:
    return {"main": main, "lining": lining, "trim": trim, "hardware": hardware, "hood": special}


STARTERS = (
    Starter("workbench-messy-frost-hair", "Workbench — Messy Frost Hair", "hair", "hair_front", _draw_hair, _color_set((92, 168, 196), (52, 102, 139), (189, 232, 236), (34, 58, 82), (104, 192, 215)), ("hair", "messy", "male", "frost"), authored_walk="walk_frost_blue_hair.png", alpha_occluded_by_tags=("hooded_cloak",)),
    Starter("workbench-one-shoulder-pauldron", "Workbench — One-Shoulder Pauldron", "shoulder_chest", "foreground_accessory", _draw_one_pauldron, _color_set((91, 57, 36), (48, 61, 48), (151, 118, 65), (173, 181, 177), (60, 45, 36)), ("pauldron", "asymmetric", "leather")),
    Starter("workbench-leather-gloves", "Workbench — Leather Gloves", "hands", "handwear", _draw_gloves, _color_set((89, 50, 30), (54, 32, 23), (142, 99, 55), (164, 151, 122), (66, 39, 29)), ("gloves", "leather")),
    Starter("workbench-eye-patch", "Workbench — Eye Patch", "face", "face_accessory", _draw_eye_patch, _color_set((37, 28, 26), (63, 42, 33), (119, 80, 44), (156, 151, 137), (28, 24, 27)), ("eyepatch", "leather")),
    Starter("workbench-double-leaf-pauldrons", "Workbench — Double Leaf Pauldrons", "shoulder_chest", "foreground_accessory", _draw_double_pauldrons, _color_set((48, 91, 54), (31, 61, 39), (188, 151, 57), (127, 91, 39), (70, 119, 69)), ("pauldrons", "double", "leaf", "armor"), authored_walk="../walk_double_pauldrons.png"),
    Starter("workbench-crooked-mage-vestments", "Workbench — Crooked Mage Hat + Vestments", "outerwear", "outerwear", _draw_mage_vestments, _color_set((89, 46, 111), (53, 31, 75), (207, 155, 53), (149, 92, 41), (39, 27, 64)), ("mage", "hat", "vestments"), ("headwear", "neck")),
    Starter("workbench-rugged-leather-armor", "Workbench — Rugged Leather Armor", "outerwear", "outerwear", _draw_leather_armor, _color_set((100, 59, 35), (59, 38, 29), (157, 112, 63), (178, 166, 137), (66, 45, 35)), ("armor", "leather", "body")),
    Starter("workbench-ratty-shawl", "Workbench — Ratty Shawl", "neck", "neck", _draw_ratty_shawl, _color_set((78, 78, 48), (46, 51, 36), (123, 111, 69), (81, 61, 39), (55, 61, 42)), ("shawl", "ratty", "cloth")),
    Starter("workbench-cloth-headband", "Workbench — Cloth Headband", "headwear", "headwear", _draw_headband, _color_set((139, 48, 45), (83, 34, 35), (216, 142, 55), (119, 82, 51), (172, 59, 53)), ("headband", "cloth")),
    Starter("workbench-orcish-spiked-armor", "Workbench — Orcish Spiked Armor", "outerwear", "outerwear", _draw_orcish_armor, _color_set((55, 68, 55), (91, 74, 45), (141, 126, 77), (169, 176, 157), (42, 53, 45)), ("orcish", "armor", "spiked"), ("shoulder_chest",)),
    Starter("workbench-horned-cult-mask", "Workbench — Horned Cult Mask", "face", "face_accessory", _draw_cult_mask, _color_set((181, 174, 143), (112, 105, 85), (139, 45, 55), (91, 50, 83), (35, 27, 42)), ("mask", "cult", "animal", "horned"), ("headwear",)),
)


def _ramp(color: tuple[int, int, int]) -> tuple[tuple[int, int, int], ...]:
    multipliers = (0.42, 0.62, 0.80, 1.0, 1.16)
    return tuple(
        tuple(min(255, max(0, round(channel * multiplier))) for channel in color)
        for multiplier in multipliers
    )


def _palettes(starter: Starter) -> dict[str, tuple[tuple[int, int, int], ...]]:
    return {name: _ramp(starter.colors[name]) for name in set(MARKERS.values())}


def _regions_for(starter: Starter, base_walk: Image.Image) -> Image.Image:
    regions = Image.new("RGBA", (384, 259), TRANSPARENT)
    for frame_index in range(FRAMES):
        base = base_walk.crop((frame_index * 64, 0, (frame_index + 1) * 64, 64))
        frame = Image.new("RGBA", (64, 64), TRANSPARENT)
        starter.draw(frame, base, _anchors(base))
        if frame.getbbox() is None:
            raise RuntimeError(f"{starter.component_id} frame {frame_index + 1} is empty")
        unknown = {pixel for pixel in _pixels(frame) if pixel[3] and pixel not in MARKERS}
        if unknown:
            raise RuntimeError(f"{starter.component_id} contains non-semantic colors")
        regions.paste(frame, (frame_index * 64, 0))
    return regions


def _authored_walk_for(starter: Starter, root: Path) -> tuple[Image.Image, bytes]:
    if starter.authored_walk is None:
        raise ValueError(f"{starter.component_id} has no authored Walk source")
    path = root / starter.authored_walk
    if not path.is_file():
        raise FileNotFoundError(f"Authored Walk source is missing: {path}")
    content = path.read_bytes()
    with Image.open(path) as opened:
        walk = opened.convert("RGBA")
    if walk.size != (384, 259):
        raise ValueError(
            f"{starter.component_id} authored Walk must be 384x259, got {walk.size}"
        )
    if walk.crop((0, FRAME_SIZE, walk.width, walk.height)).getbbox() is not None:
        raise ValueError(
            f"{starter.component_id} authored Walk must contain Front-row pixels only"
        )
    for frame_index in range(FRAMES):
        frame = walk.crop(
            (frame_index * FRAME_SIZE, 0, (frame_index + 1) * FRAME_SIZE, FRAME_SIZE)
        )
        if frame.getbbox() is None:
            raise ValueError(
                f"{starter.component_id} authored Walk frame {frame_index + 1} is empty"
            )
    return walk, content


def _manifest(
    starter: Starter,
    regions_hash: str | None,
    walk_hash: str,
    base_hash: str,
    authored_hash: str | None = None,
) -> dict[str, object]:
    authored = starter.authored_walk is not None
    provenance: dict[str, object] = {
        "kind": (
            "human_authored_front_walk_overlay"
            if authored
            else "deterministic_semantic_silhouette_starter"
        ),
        "generator": "tools/generate_component_silhouette_starters.py",
        "generatorVersion": 2 if authored else 1,
        "baseWalkSha256": base_hash,
    }
    if authored:
        provenance["authoredSource"] = starter.authored_walk
        provenance["authoredSourceSha256"] = authored_hash
    else:
        provenance["regionsSha256"] = regions_hash
    provenance.update(
        {
            "walkSha256": walk_hash,
            "authoredDirections": ["front"],
            "authoredFrameIndices": [0, 1, 2, 3, 4, 5],
            "conceptBoard": "workbench/starter-component-concept-board.png",
            "readiness": (
                "authored-front-walk" if authored else "rough-editable-silhouette"
            ),
        }
    )

    manifest: dict[str, object] = {
        "schemaVersion": 1,
        "id": starter.component_id,
        "displayName": starter.display_name,
        "slot": starter.slot,
        "occupiesSlots": [starter.slot],
        "reservedSlots": list(starter.reserved_slots),
        "layer": starter.layer,
        "tags": [
            "workbench",
            "authored_pixels" if authored else "silhouette_starter",
            *([] if authored else ["semantic_regions"]),
            *starter.tags,
        ],
        "fit": "standard",
        "version": 2 if authored else 1,
        "status": "incomplete",
        "developmentVisible": True,
        "animations": {"walk": "walk.png"},
        "coverage": {"walk": ["front"]},
    }
    if starter.alpha_occluded_by_tags:
        manifest["alphaOccludedByTags"] = list(starter.alpha_occluded_by_tags)
    if not authored:
        manifest["semanticRegions"] = {"walk": "regions.png"}
    manifest["provenance"] = provenance
    return manifest


def _contact_sheet(
    generated: list[tuple[Starter, Image.Image]],
    base_walk: Image.Image,
) -> Image.Image:
    scale = 4
    tile_width, tile_height = 256, 286
    sheet = Image.new("RGBA", (tile_width * 4, tile_height * 3), (29, 29, 34, 255))
    draw = ImageDraw.Draw(sheet)
    base_frame = base_walk.crop((0, 0, 64, 64))
    for index, (starter, walk) in enumerate(generated):
        x = (index % 4) * tile_width
        y = (index // 4) * tile_height
        overlay = walk.crop((0, 0, 64, 64))
        composed = Image.alpha_composite(base_frame, overlay).resize(
            (64 * scale, 64 * scale), Image.Resampling.NEAREST
        )
        sheet.alpha_composite(composed, (x, y + 22))
        draw.text((x + 4, y + 5), f"{index + 1}. {starter.display_name.removeprefix('Workbench — ')}", fill=(240, 240, 240, 255))
    return sheet


def _all_frames_contact_sheet(
    generated: list[tuple[Starter, Image.Image]],
    base_walk: Image.Image,
) -> Image.Image:
    scale = 2
    tile_width, tile_height = 768, 150
    sheet = Image.new("RGBA", (tile_width * 2, tile_height * 6), (29, 29, 34, 255))
    draw = ImageDraw.Draw(sheet)
    base_front = base_walk.crop((0, 0, 384, 64))
    for index, (starter, walk) in enumerate(generated):
        x = (index % 2) * tile_width
        y = (index // 2) * tile_height
        overlay = walk.crop((0, 0, 384, 64))
        composed = Image.alpha_composite(base_front, overlay).resize(
            (384 * scale, 64 * scale), Image.Resampling.NEAREST
        )
        sheet.alpha_composite(composed, (x, y + 22))
        draw.text(
            (x + 4, y + 5),
            f"{index + 1}. {starter.display_name.removeprefix('Workbench — ')} — all six Front Walk frames",
            fill=(240, 240, 240, 255),
        )
    return sheet


def generate_all(*, check: bool = False) -> None:
    with Image.open(BASE_WALK) as opened:
        base_walk = opened.convert("RGBA")
    base_hash = sha256(BASE_WALK.read_bytes()).hexdigest()
    generated: list[tuple[Starter, Image.Image]] = []
    index_entries: list[dict[str, object]] = []

    for starter in STARTERS:
        root = PARTS_ROOT / starter.slot / starter.component_id
        authored_hash: str | None = None
        if starter.authored_walk is not None:
            walk, walk_bytes = _authored_walk_for(starter, root)
            regions_bytes = None
            authored_hash = _digest_bytes(walk_bytes)
        else:
            regions = _regions_for(starter, base_walk)
            walk = finish_semantic_regions(regions, _palettes(starter))
            regions_bytes = _png_bytes(regions)
            walk_bytes = _png_bytes(walk)
            _write_or_check(root / "regions.png", regions_bytes, check)
        _write_or_check(root / "walk.png", walk_bytes, check)
        _write_or_check(
            root / "manifest.json",
            _json_bytes(
                _manifest(
                    starter,
                    _digest_bytes(regions_bytes) if regions_bytes is not None else None,
                    _digest_bytes(walk_bytes),
                    base_hash,
                    authored_hash,
                )
            ),
            check,
        )
        generated.append((starter, walk))
        entry = {
            "id": starter.component_id,
            "displayName": starter.display_name,
            "slot": starter.slot,
        }
        if starter.authored_walk is not None:
            entry["source"] = str(
                (root / starter.authored_walk)
                .resolve()
                .relative_to(ASSET_ROOT.resolve())
            ).replace("\\", "/")
        else:
            entry["regions"] = str(
                (root / "regions.png").relative_to(ASSET_ROOT)
            ).replace("\\", "/")
        entry["preview"] = str((root / "walk.png").relative_to(ASSET_ROOT)).replace(
            "\\", "/"
        )
        entry["status"] = (
            "authored-front-walk"
            if starter.authored_walk is not None
            else "rough-editable-silhouette"
        )
        index_entries.append(entry)

    _write_or_check(
        WORKBENCH_ROOT / "component-silhouette-starters.json",
        _json_bytes(
            {
                "schemaVersion": 1,
                "generator": "tools/generate_component_silhouette_starters.py",
                "generatorVersion": 1,
                "baseWalkSha256": base_hash,
                "conceptBoard": "starter-component-concept-board.png",
                "starters": index_entries,
            }
        ),
        check,
    )
    _write_or_check(
        WORKBENCH_ROOT / "component-silhouette-starters.png",
        _png_bytes(_contact_sheet(generated, base_walk)),
        check,
    )
    _write_or_check(
        WORKBENCH_ROOT / "component-silhouette-starters-all-frames.png",
        _png_bytes(_all_frames_contact_sheet(generated, base_walk)),
        check,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate editable Front Walk component starters."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not CONCEPT_BOARD.is_file():
        raise FileNotFoundError(f"Workbench concept board is missing: {CONCEPT_BOARD}")
    generate_all(check=args.check)
    action = "Verified" if args.check else "Generated"
    print(f"{action} {len(STARTERS)} component starters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
