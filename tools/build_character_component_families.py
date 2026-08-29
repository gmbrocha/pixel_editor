"""Build 25 fitted low-camera component families for every approved base."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.mannequin_semantics import REGION_BY_NAME
from src.core.component_cleanup import cleanup_component_sheet


ASSET_ROOT = ROOT / "assets" / "character-forge"
SEQUENCES = ("idle", "walk", "run")
DIRECTIONS = ("front", "back", "right", "left")
FRAME_COUNTS = {"idle": 14, "walk": 8, "run": 8}
CLEANUP_SETTINGS = {
    "max_island_area": 16,
    "max_island_to_largest_ratio": 0.20,
    "max_nearby_island_gap": 6,
    "max_enclosed_hole_area": 2,
    "max_terminal_spur_length": 2,
    "protected_largest_components": 1,
    "outline_corner_passes": 1,
}
BASES = {
    "elf-01": "Elf Female",
    "tiefling-female-01": "Tiefling Female",
    "dwarf-male-01": "Dwarf Male",
    "human-muscular-male-01": "Muscular Human Male",
}
SLOT_LAYERS = {
    "torso": "torso",
    "outerwear": "outerwear",
    "legwear": "legwear",
    "hands": "handwear",
    "feet": "footwear",
    "headwear": "headwear",
}
HEADWEAR_HAIR_OCCLUSION = {
    "cloth-headband": "show",
    "soft-travel-cap": "clip",
    "padded-coif": "clip",
    "simple-guard-helm": "hide",
}

TORSO = ("chest_front", "upper_back", "abdomen_front", "lower_back")
PELVIS = ("pelvis_front", "pelvis_back")
SHOULDERS = ("left_shoulder", "right_shoulder")
UPPER_ARMS = ("left_upper_arm", "right_upper_arm")
FOREARMS = ("left_forearm", "right_forearm")
HANDS = ("left_hand", "right_hand")
THIGHS = ("left_thigh", "right_thigh")
KNEES = ("left_knee", "right_knee")
SHINS = ("left_shin", "right_shin")
ANKLES = ("left_ankle", "right_ankle")
FEET = ("left_foot", "right_foot")
HEAD = ("face", "scalp", "rear_head", "left_ear", "right_ear")
HEAD_COVER = ("scalp", "rear_head", "left_ear", "right_ear")


@dataclass(frozen=True, slots=True)
class Family:
    id: str
    name: str
    slot: str
    regions: tuple[str, ...]
    palette: tuple[str, ...]
    main: str
    style: str = "standard"
    dilation: int = 1
    reserved_slots: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


FAMILIES = (
    Family("sleeveless-travel-tunic", "Sleeveless Travel Tunic", "torso", TORSO + PELVIS,
           ("#102B2B", "#1E4B48", "#36706A", "#62958B", "#A3C2B7"), "#36706A"),
    Family("cap-sleeve-field-shirt", "Cap-Sleeve Field Shirt", "torso", TORSO + SHOULDERS + UPPER_ARMS,
           ("#17233A", "#294364", "#3D6590", "#6E91B2", "#ABC0D2"), "#3D6590", "cap_sleeve"),
    Family("long-sleeve-linen-shirt", "Long-Sleeve Linen Shirt", "torso", TORSO + SHOULDERS + UPPER_ARMS + FOREARMS,
           ("#3A1718", "#642C2E", "#91474A", "#BA7372", "#D7AAA5"), "#91474A"),
    Family("cropped-training-top", "Cropped Training Top", "torso", ("chest_front", "upper_back") + SHOULDERS,
           ("#183019", "#2E5530", "#4C784E", "#7AA079", "#B0C5A9"), "#4C784E"),
    Family("padded-gambeson", "Padded Gambeson", "outerwear", TORSO + PELVIS + SHOULDERS + UPPER_ARMS,
           ("#332513", "#5A4421", "#806535", "#AE8C55", "#D1B785"), "#806535", "cap_sleeve", tags=("padded",)),
    Family("leather-jerkin", "Leather Jerkin", "outerwear", TORSO + PELVIS,
           ("#27170E", "#4A2C18", "#714728", "#9B6C43", "#C39A70"), "#714728", tags=("leather",)),
    Family("open-front-work-vest", "Open-Front Work Vest", "outerwear", TORSO,
           ("#171D26", "#2B3948", "#465B6D", "#748797", "#ABB5BD"), "#465B6D", "open_front", dilation=0),
    Family("hooded-surcoat", "Hooded Surcoat", "outerwear", TORSO + PELVIS + SHOULDERS + HEAD_COVER + ("neck",),
           ("#21152F", "#3D2854", "#5D4277", "#856B9D", "#B5A5C3"), "#5D4277", reserved_slots=("headwear", "neck"), tags=("hooded",)),
    Family("travel-shorts", "Travel Shorts", "legwear", PELVIS + THIGHS,
           ("#202318", "#39402A", "#58613E", "#7C865E", "#A9B18C"), "#58613E", "shorts"),
    Family("knee-breeches", "Knee Breeches", "legwear", PELVIS + THIGHS + KNEES,
           ("#292016", "#4A3926", "#6C563A", "#947A58", "#BBA889"), "#6C563A"),
    Family("fitted-trousers", "Fitted Trousers", "legwear", PELVIS + THIGHS + KNEES + SHINS + ANKLES,
           ("#171B1F", "#2B343C", "#46525D", "#71808A", "#A8B1B7"), "#46525D"),
    Family("high-waist-pants", "High-Waist Pants", "legwear", ("abdomen_front", "lower_back") + PELVIS + THIGHS + KNEES + SHINS + ANKLES,
           ("#25182B", "#432C4B", "#64466B", "#8C6D91", "#BAA7BD"), "#64466B"),
    Family("low-waist-pants", "Low-Waist Pants", "legwear", PELVIS + THIGHS + KNEES + SHINS + ANKLES,
           ("#182326", "#2D4145", "#496166", "#75878A", "#AAB5B5"), "#496166", "low_waist"),
    Family("reinforced-leggings", "Reinforced Leggings", "legwear", PELVIS + THIGHS + KNEES + SHINS + ANKLES,
           ("#161C17", "#29352B", "#425445", "#687A69", "#9EAA9A"), "#425445", "reinforced_knees"),
    Family("fingerless-gloves", "Fingerless Gloves", "hands", HANDS + FOREARMS,
           ("#261711", "#472C1E", "#6A472F", "#936B4C", "#BE9978"), "#6A472F", "fingerless"),
    Family("leather-gauntlets", "Leather Gauntlets", "hands", HANDS + FOREARMS,
           ("#21140E", "#3E291B", "#61432D", "#896448", "#B48D6D"), "#61432D"),
    Family("wrist-bracers", "Wrist Bracers", "hands", FOREARMS,
           ("#262119", "#463B2B", "#685A42", "#8E7C60", "#B9AB91"), "#685A42", "bracers"),
    Family("low-travel-shoes", "Low Travel Shoes", "feet", FEET,
           ("#17130F", "#30261C", "#4E3C2B", "#725A43", "#9A8066"), "#4E3C2B"),
    Family("ankle-boots", "Ankle Boots", "feet", FEET + ANKLES,
           ("#1C130E", "#35251A", "#533A29", "#79563E", "#A17D61"), "#533A29"),
    Family("mid-calf-boots", "Mid-Calf Boots", "feet", FEET + ANKLES + SHINS,
           ("#18110D", "#312219", "#4D3829", "#70533E", "#98765D"), "#4D3829", "mid_boots"),
    Family("tall-riding-boots", "Tall Riding Boots", "feet", FEET + ANKLES + SHINS + KNEES,
           ("#15100D", "#2A211A", "#46372B", "#675343", "#8D7662"), "#46372B"),
    Family("cloth-headband", "Cloth Headband", "headwear", HEAD,
           ("#2E1416", "#57272B", "#834047", "#AF6970", "#D49DA0"), "#834047", "headband", dilation=0),
    Family("soft-travel-cap", "Soft Travel Cap", "headwear", HEAD,
           ("#17251B", "#2D4532", "#49684D", "#739074", "#A8B7A2"), "#49684D", "cap"),
    Family("padded-coif", "Padded Coif", "headwear", HEAD_COVER + ("neck",),
           ("#25201A", "#44392D", "#655745", "#897760", "#B0A08B"), "#655745", tags=("padded",)),
    Family("simple-guard-helm", "Simple Guard Helm", "headwear", HEAD,
           ("#202427", "#3B4449", "#5B686D", "#879297", "#B5BDC0"), "#5B686D", "helm", tags=("metal",)),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.removeprefix("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _region_mask(ids: np.ndarray, names: tuple[str, ...]) -> np.ndarray:
    allowed = np.asarray([REGION_BY_NAME[name].id for name in names], dtype=np.uint8)
    return np.isin(ids, allowed)


def _dilate(mask: np.ndarray, pixels: int) -> np.ndarray:
    if pixels <= 0:
        return mask.copy()
    return np.asarray(
        Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), "L").filter(
            ImageFilter.MaxFilter((pixels * 2) + 1)
        ),
        dtype=np.uint8,
    ) > 0


def _erode(mask: np.ndarray) -> np.ndarray:
    return np.asarray(
        Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), "L").filter(
            ImageFilter.MinFilter(3)
        ),
        dtype=np.uint8,
    ) > 0


def _styled_frame(ids: np.ndarray, family: Family, direction: str) -> np.ndarray:
    mask = _region_mask(ids, family.regions)
    if not np.any(mask):
        return mask
    style = family.style
    if style == "cap_sleeve":
        core = _region_mask(ids, TORSO + PELVIS + SHOULDERS)
        arms = _region_mask(ids, UPPER_ARMS)
        mask = core | (arms & _dilate(_region_mask(ids, SHOULDERS), 5))
    elif style == "open_front" and direction == "front":
        ys, xs = np.nonzero(mask)
        center = int(round((xs.min() + xs.max()) / 2))
        mask[:, max(0, center - 1): center + 1] = False
    elif style == "shorts":
        pelvis = _region_mask(ids, PELVIS)
        thighs = _region_mask(ids, THIGHS)
        mask = pelvis | (thighs & _dilate(pelvis, 7))
    elif style == "low_waist":
        pelvis = _region_mask(ids, PELVIS)
        ys, _ = np.nonzero(pelvis)
        if len(ys):
            cutoff = int(np.quantile(ys, 0.28))
            pelvis[:cutoff] = False
        mask = pelvis | _region_mask(ids, THIGHS + KNEES + SHINS + ANKLES)
    elif style == "fingerless":
        hands = _region_mask(ids, HANDS)
        forearms = _region_mask(ids, FOREARMS)
        mask = (hands & _dilate(forearms, 4)) | (forearms & _dilate(hands, 2))
    elif style == "bracers":
        forearms = _region_mask(ids, FOREARMS)
        hands = _region_mask(ids, HANDS)
        mask = forearms & _dilate(hands, 5)
    elif style == "mid_boots":
        ankles = _region_mask(ids, ANKLES)
        mask = _region_mask(ids, FEET + ANKLES) | (
            _region_mask(ids, SHINS) & _dilate(ankles, 6)
        )
    elif style in {"headband", "cap", "helm"}:
        head = _region_mask(ids, HEAD)
        ys, xs = np.nonzero(head)
        if not len(ys):
            return head
        top, bottom = ys.min(), ys.max() + 1
        height = max(1, bottom - top)
        if style == "headband":
            low = top + round(height * 0.28)
            high = max(low + 1, top + round(height * 0.50))
            band = np.zeros_like(head)
            band[low:high] = True
            mask = head & band
        elif style == "cap":
            cutoff = top + round(height * 0.58)
            cap = np.zeros_like(head)
            cap[:cutoff] = True
            mask = head & cap
            brim_y = min(ids.shape[0] - 1, cutoff)
            left, right = xs.min(), xs.max() + 1
            mask[brim_y:brim_y + 1, max(0, left - 1):min(ids.shape[1], right + 2)] = True
        else:
            cutoff = top + round(height * 0.78)
            helmet = np.zeros_like(head)
            helmet[:cutoff] = True
            mask = head & helmet
    return mask


def _component_sheet(
    art_path: Path,
    regions_path: Path,
    family: Family,
    sequence: str,
) -> Image.Image:
    with Image.open(art_path) as opened:
        art = opened.convert("RGBA")
    with Image.open(regions_path) as opened:
        regions = np.asarray(opened.convert("L"), dtype=np.uint8)
    source = np.asarray(art, dtype=np.uint8)
    frame_count = FRAME_COUNTS[sequence]
    output = np.zeros_like(source)
    palette = np.asarray([_rgb(color) for color in family.palette], dtype=np.uint8)
    luminance = (
        source[..., 0].astype(np.uint16) * 54
        + source[..., 1].astype(np.uint16) * 183
        + source[..., 2].astype(np.uint16) * 19
    ) // 256
    shade_indices = np.clip(
        (luminance.astype(np.uint16) * len(palette)) // 256,
        0,
        len(palette) - 1,
    )
    output[..., :3] = palette[shade_indices]

    for row, direction in enumerate(DIRECTIONS):
        for column in range(frame_count):
            box = (
                column * 128,
                row * 128,
                (column + 1) * 128,
                (row + 1) * 128,
            )
            ids = regions[box[1]:box[3], box[0]:box[2]]
            exact = _styled_frame(ids, family, direction)
            expanded = _dilate(exact, family.dilation)
            edge = expanded & ~exact if family.dilation else exact & ~_erode(exact)
            target = output[box[1]:box[3], box[0]:box[2]]
            target[..., 3] = np.where(expanded, 255, 0).astype(np.uint8)
            target[edge, :3] = palette[0]
            if family.style == "reinforced_knees":
                knees = _region_mask(ids, KNEES) & expanded
                target[knees, :3] = palette[1]
    return Image.fromarray(output, "RGBA")


def _region_path(asset_root: Path, base_id: str, sequence: str) -> Path:
    if base_id == "elf-01":
        return asset_root / "semantic" / base_id / sequence / f"{sequence}_regions.png"
    return asset_root / "base_regions" / base_id / sequence / f"{sequence}_regions.png"


def _component_id(family: Family, base_id: str) -> str:
    return f"{family.id}-{base_id}"


def _build_variant(
    asset_root: Path,
    output_root: Path,
    family: Family,
    base_id: str,
) -> dict[str, object]:
    component_id = _component_id(family, base_id)
    part_dir = output_root / family.slot / component_id
    part_dir.mkdir(parents=True, exist_ok=True)
    animation_hashes: dict[str, str] = {}
    cleanup_reports: dict[str, object] = {}
    for sequence in SEQUENCES:
        art = asset_root / "bases" / base_id / f"{sequence}.png"
        regions = _region_path(asset_root, base_id, sequence)
        if not art.is_file() or not regions.is_file():
            raise FileNotFoundError(f"Missing {base_id}/{sequence} art or regions")
        raw_image = _component_sheet(art, regions, family, sequence)
        image, cleanup_report = cleanup_component_sheet(
            raw_image,
            outline_rgb=_rgb(family.palette[0]),
            palette=tuple(_rgb(color) for color in family.palette),
            protected_components=1,
        )
        output = part_dir / f"{sequence}.png"
        image.save(output, format="PNG", optimize=False, compress_level=9)
        animation_hashes[sequence] = _sha256(output)
        cleanup_reports[sequence] = cleanup_report.to_dict()
    manifest = {
        "schemaVersion": 1,
        "id": component_id,
        "familyId": family.id,
        "displayName": family.name,
        "slot": family.slot,
        "occupiesSlots": [family.slot],
        "reservedSlots": list(family.reserved_slots),
        "layer": SLOT_LAYERS[family.slot],
        "hairOcclusion": HEADWEAR_HAIR_OCCLUSION.get(family.id, "show"),
        "tags": ["generated_family", "cross_model", "recolorable", *family.tags],
        "fit": base_id,
        "version": 1,
        "status": "approved",
        "animations": {sequence: f"{sequence}.png" for sequence in SEQUENCES},
        "coverage": {sequence: list(DIRECTIONS) for sequence in SEQUENCES},
        "colorRamp": {"main": family.main, "colors": list(family.palette)},
        "suggestedColors": [family.main],
        "provenance": {
            "kind": "weight_region_fitted_component_family",
            "generator": "tools/build_character_component_families.py",
            "style": family.style,
            "sourceRegions": list(family.regions),
            "outline": {"widthPixels": 1, "color": family.palette[0]},
            "cleanup": {
                "kind": "canonical_component_preprocessing",
                "generator": "src/core/component_cleanup.py",
                "settings": CLEANUP_SETTINGS,
                "reports": cleanup_reports,
            },
            "animationSha256": animation_hashes,
        },
    }
    manifest_path = part_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return {
        "id": component_id,
        "fit": base_id,
        "slot": family.slot,
        "manifest": (Path("parts") / family.slot / component_id / "manifest.json").as_posix(),
        "manifest_sha256": _sha256(manifest_path),
        "animation_sha256": animation_hashes,
    }


def _review_board(asset_root: Path, base_id: str, sequence: str) -> Image.Image:
    cell = 176
    board = Image.new("RGBA", (cell * 5, cell * 5), (27, 29, 34, 255))
    draw = ImageDraw.Draw(board)
    base_sheet_path = asset_root / "bases" / base_id / f"{sequence}.png"
    with Image.open(base_sheet_path) as opened:
        base_sheet = opened.convert("RGBA")
    for index, family in enumerate(FAMILIES):
        component = (
            asset_root
            / "parts"
            / family.slot
            / _component_id(family, base_id)
            / f"{sequence}.png"
        )
        with Image.open(component) as opened:
            overlay = opened.convert("RGBA")
        frame = base_sheet.crop((0, 0, 128, 128))
        frame = Image.alpha_composite(frame, overlay.crop((0, 0, 128, 128)))
        x = (index % 5) * cell
        y = (index // 5) * cell
        board.alpha_composite(frame, (x + 24, y + 8))
        label = family.name
        if len(label) > 23:
            label = label[:20] + "..."
        draw.text((x + 5, y + 143), label, fill=(235, 238, 242, 255))
    return board


def _owned_directories(parts_root: Path) -> list[Path]:
    owned: list[Path] = []
    if not parts_root.is_dir():
        return owned
    for manifest_path in parts_root.rglob("manifest.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("provenance", {}).get("generator") == "tools/build_character_component_families.py":
            owned.append(manifest_path.parent)
    return owned


def _build_all(asset_root: Path, output_root: Path) -> dict[str, object]:
    variants = []
    for family in FAMILIES:
        for base_id in BASES:
            variants.append(_build_variant(asset_root, output_root, family, base_id))
    return {
        "schema_version": 1,
        "status": "generated_component_families",
        "family_count": len(FAMILIES),
        "variant_count": len(variants),
        "bases": BASES,
        "families": [
            {
                "id": family.id,
                "name": family.name,
                "slot": family.slot,
                "style": family.style,
                "variants": [
                    variant for variant in variants if variant["id"].startswith(family.id + "-")
                ],
            }
            for family in FAMILIES
        ],
    }


def _write_review_boards(asset_root: Path, output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for base_id in BASES:
        for sequence in SEQUENCES:
            _review_board(asset_root, base_id, sequence).save(
                output_root / f"{base_id}-{sequence}.png",
                format="PNG",
                optimize=False,
                compress_level=9,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-root", type=Path, default=ASSET_ROOT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.force and args.check:
        parser.error("--force and --check are mutually exclusive")
    asset_root = args.asset_root.resolve()
    parts_root = asset_root / "parts"
    manifest_path = asset_root / "component_families_manifest.json"
    if args.check:
        with tempfile.TemporaryDirectory(prefix="pf-component-families-") as temporary:
            candidate_root = Path(temporary)
            candidate_parts = candidate_root / "parts"
            candidate_review = candidate_root / "review"
            manifest = _build_all(asset_root, candidate_parts)
            _write_review_boards(asset_root, candidate_review)
            expected_manifest = (json.dumps(manifest, indent=2) + "\n").encode()
            mismatches = []
            for expected in candidate_parts.rglob("*"):
                if not expected.is_file():
                    continue
                relative = expected.relative_to(candidate_parts)
                actual = parts_root / relative
                if not actual.is_file() or actual.read_bytes() != expected.read_bytes():
                    mismatches.append(relative.as_posix())
            review_root = asset_root / "review" / "component-families"
            for expected in candidate_review.rglob("*"):
                if not expected.is_file():
                    continue
                relative = expected.relative_to(candidate_review)
                actual = review_root / relative
                if not actual.is_file() or actual.read_bytes() != expected.read_bytes():
                    mismatches.append(f"review/{relative.as_posix()}")
            if not manifest_path.is_file() or manifest_path.read_bytes() != expected_manifest:
                mismatches.append(manifest_path.name)
        if mismatches:
            raise SystemExit("Component family outputs differ: " + ", ".join(mismatches[:20]))
        print(f"Verified {len(FAMILIES)} families and {len(FAMILIES) * len(BASES)} fitted variants")
        return 0

    owned = _owned_directories(parts_root)
    if owned and not args.force:
        raise FileExistsError("Generated component families already exist; use --force")
    for directory in owned:
        resolved = directory.resolve()
        if parts_root.resolve() not in resolved.parents:
            raise RuntimeError(f"Refusing to remove component outside {parts_root}: {resolved}")
        shutil.rmtree(directory)
    manifest = _build_all(asset_root, parts_root)
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    review_root = asset_root / "review" / "component-families"
    _write_review_boards(asset_root, review_root)
    print(f"Built {len(FAMILIES)} families and {len(FAMILIES) * len(BASES)} fitted variants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
