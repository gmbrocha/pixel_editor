"""Install semantic elf animations and region-derived starter clothes."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.mannequin_semantics import REGION_BY_NAME


DIRECTION_ROWS = {"front": 0, "back": 1, "right": 2, "left": 3}
LAYERS = [
    "body_back", "hair_back", "body", "legwear", "footwear", "torso",
    "outerwear", "handwear", "waist", "neck", "hair_front",
    "face_accessory", "headwear", "foreground_accessory",
]
SLOTS = {
    "headwear": ("Headwear", "headwear"),
    "face": ("Face", "face_accessory"),
    "neck": ("Neck", "neck"),
    "torso": ("Tops", "torso"),
    "waist": ("Waist", "waist"),
    "outerwear": ("Outerwear", "outerwear"),
    "hands": ("Hands", "handwear"),
    "feet": ("Feet", "footwear"),
    "legwear": ("Legwear", "legwear"),
    "hair": ("Hair", "hair_front"),
    "facial_hair": ("Facial Hair", "face_accessory"),
    "shoulder_chest": ("Shoulder / Chest", "foreground_accessory"),
    "back": ("Back", "body_back"),
}


@dataclass(frozen=True, slots=True)
class StarterPart:
    id: str
    name: str
    slot: str
    layer: str
    regions: tuple[str, ...]
    palette: tuple[str, ...]
    main: str
    suggested: tuple[str, ...]
    dilation: int = 1


PARTS = (
    StarterPart(
        "elf-basic-linen-shirt", "Basic Linen Shirt", "torso", "torso",
        (
            "chest_front", "upper_back", "abdomen_front", "lower_back",
            "left_shoulder", "right_shoulder", "left_upper_arm", "right_upper_arm",
        ),
        ("#17243A", "#294463", "#3F668A", "#7194B2", "#AEC4D4"),
        "#3F668A", ("#3F668A", "#8D3D3D", "#536B3E", "#B28B54"),
    ),
    StarterPart(
        "elf-simple-work-vest", "Simple Work Vest", "outerwear", "outerwear",
        ("chest_front", "upper_back", "abdomen_front", "lower_back"),
        ("#24170F", "#4B3020", "#765038", "#A57956", "#C7A17E"),
        "#765038", ("#765038", "#4C586B", "#526B43", "#7B4250"),
        dilation=0,
    ),
    StarterPart(
        "elf-basic-trousers", "Basic Trousers", "legwear", "legwear",
        (
            "pelvis_front", "pelvis_back", "left_thigh", "right_thigh",
            "left_knee", "right_knee", "left_shin", "right_shin",
            "left_ankle", "right_ankle",
        ),
        ("#171B18", "#29332C", "#465445", "#6B7861", "#9AA58C"),
        "#465445", ("#465445", "#3D485D", "#5E4737", "#6A3F47"),
    ),
    StarterPart(
        "elf-plain-leather-gloves", "Plain Leather Gloves", "hands", "handwear",
        ("left_hand", "right_hand"),
        ("#24150E", "#4C2D1C", "#71472D", "#9A6A48", "#C49A73"),
        "#71472D", ("#71472D", "#343A42", "#6A352F", "#79623B"),
    ),
    StarterPart(
        "elf-tall-work-boots", "Tall Work Boots", "feet", "footwear",
        (
            "left_shin", "right_shin", "left_ankle", "right_ankle",
            "left_foot", "right_foot",
        ),
        ("#18110D", "#32231A", "#503828", "#74543D", "#9C795B"),
        "#503828", ("#503828", "#303337", "#67362E", "#5C5137"),
    ),
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-root", required=True, type=Path)
    parser.add_argument("--idle-package", required=True, type=Path)
    parser.add_argument("--walk-package", required=True, type=Path)
    parser.add_argument("--run-package", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.removeprefix("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _load_package(path: Path, sequence: str) -> tuple[dict[str, object], Path, Path]:
    manifest_path = path / f"{sequence}_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("sequence") != sequence:
        raise ValueError(f"{manifest_path} is not a {sequence} package")
    if manifest.get("direction_order") != list(DIRECTION_ROWS):
        raise ValueError(f"{sequence} direction order is not Front, Back, Right, Left")
    dimensions = manifest.get("sheet_dimensions")
    if not isinstance(dimensions, list) or dimensions[1] != 512:
        raise ValueError(f"{sequence} is not a four-row 128px package")
    art = path / f"{sequence}.png"
    regions = path / f"{sequence}_regions.png"
    if not art.is_file() or not regions.is_file():
        raise FileNotFoundError(f"{sequence} package is incomplete")
    return manifest, art, regions


def _expand_mask(mask: Image.Image, pixels: int) -> Image.Image:
    if pixels <= 0:
        return mask
    return mask.filter(ImageFilter.MaxFilter((pixels * 2) + 1))


def _component_image(
    art_path: Path,
    regions_path: Path,
    part: StarterPart,
) -> Image.Image:
    with Image.open(art_path) as opened:
        art = opened.convert("RGBA")
    with Image.open(regions_path) as opened:
        regions = np.asarray(opened.convert("L"), dtype=np.uint8)
    allowed = np.asarray(
        [REGION_BY_NAME[name].id for name in part.regions], dtype=np.uint8
    )
    exact = np.isin(regions, allowed)
    mask = Image.fromarray(np.where(exact, 255, 0).astype(np.uint8), "L")
    expanded = np.asarray(_expand_mask(mask, part.dilation), dtype=np.uint8) > 0
    source = np.asarray(art, dtype=np.uint8)
    luminance = (
        source[..., 0].astype(np.uint16) * 54
        + source[..., 1].astype(np.uint16) * 183
        + source[..., 2].astype(np.uint16) * 19
    ) // 256
    palette = np.asarray([_rgb(color) for color in part.palette], dtype=np.uint8)
    indices = np.clip((luminance.astype(np.uint16) * len(palette)) // 256, 0, len(palette) - 1)
    output = np.zeros((*regions.shape, 4), dtype=np.uint8)
    output[..., :3] = palette[indices]
    output[..., 3] = np.where(expanded, 255, 0).astype(np.uint8)

    # Keep the sewn edge at the one-pixel pixel-art minimum. Dilated parts use
    # only their new outside contour; the previous expanded-through-eroded band
    # was roughly three pixels thick and obscured otherwise-correct shading.
    if part.dilation > 0:
        edge = expanded & ~exact
    else:
        eroded = np.asarray(
            mask.filter(ImageFilter.MinFilter(3)), dtype=np.uint8
        ) > 0
        edge = exact & ~eroded
    output[edge, :3] = palette[0]
    return Image.fromarray(output, "RGBA")


def _copy_semantic_package(source: Path, destination: Path, force: bool) -> None:
    if destination.exists():
        if not force:
            raise FileExistsError(destination)
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _review_contact_sheet(
    asset_root: Path, parts: tuple[StarterPart, ...], sequence: str
) -> None:
    with Image.open(asset_root / "bases" / "elf-01" / f"{sequence}.png") as opened:
        base = opened.convert("RGBA")
    rows = (None, *parts)
    review = Image.new("RGBA", (128 * 4, 128 * len(rows)), (34, 36, 42, 255))
    for row_index, part in enumerate(rows):
        overlay = None
        if part is not None:
            with Image.open(
                asset_root / "parts" / part.slot / part.id / f"{sequence}.png"
            ) as opened:
                overlay = opened.convert("RGBA")
        for column, direction in enumerate(DIRECTION_ROWS):
            source_row = DIRECTION_ROWS[direction]
            box = (0, source_row * 128, 128, (source_row + 1) * 128)
            frame = base.crop(box)
            if overlay is not None:
                frame = Image.alpha_composite(frame, overlay.crop(box))
            review.alpha_composite(frame, (column * 128, row_index * 128))
    review_dir = asset_root / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    review.save(review_dir / f"elf-01-starter-components-{sequence}.png")
    (review_dir / f"elf-01-starter-components-{sequence}.json").write_text(
        json.dumps(
            {
                "columns": list(DIRECTION_ROWS),
                "rows": ["base", *[part.id for part in parts]],
                "animation": sequence,
                "frame_size": [128, 128],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    args = _args()
    package_paths = {
        "idle": args.idle_package.resolve(),
        "walk": args.walk_package.resolve(),
        "run": args.run_package.resolve(),
    }
    packages = {
        name: _load_package(path, name)
        for name, path in package_paths.items()
    }
    asset_root = args.asset_root.resolve()
    specs_path = asset_root / "sheet_specs.json"
    preserved_bases: dict[str, object] = {}
    preserved_camera_heights: dict[str, object] = {}
    previous_elf_animations: dict[str, object] = {}
    if specs_path.is_file():
        previous_specs = json.loads(specs_path.read_text(encoding="utf-8"))
        if previous_specs.get("schema_version") == 2:
            preserved_camera_heights = previous_specs.get("camera_heights", {})
            previous_elf_animations = (
                previous_specs.get("bases", {})
                .get("elf-01", {})
                .get("animations", {})
            )
            preserved_bases = {
                str(base_id): value
                for base_id, value in previous_specs.get("bases", {}).items()
                if base_id != "elf-01"
            }
    base_dir = asset_root / "bases" / "elf-01"
    semantic_root = asset_root / "semantic" / "elf-01"
    parts_root = asset_root / "parts"
    for target in (base_dir, semantic_root, parts_root):
        if target.exists() and not args.force:
            raise FileExistsError(target)
    base_dir.mkdir(parents=True, exist_ok=True)

    animations: dict[str, object] = {}
    for sequence, (manifest, art_path, _regions_path) in packages.items():
        runtime = base_dir / f"{sequence}.png"
        shutil.copy2(art_path, runtime)
        semantic_destination = semantic_root / sequence
        _copy_semantic_package(package_paths[sequence], semantic_destination, args.force)
        frame_count = len(manifest["source_frames"])
        fps = int(manifest["settings"]["fps"])
        frame_durations_ms = [
            int(value)
            for value in manifest.get(
                "frame_durations_ms", [round(1000 / fps)] * frame_count
            )
        ]
        sheet_size = list(manifest["sheet_dimensions"])
        animations[sequence] = {
            "name": sequence.title(),
            "runtime_file": runtime.relative_to(asset_root).as_posix(),
            "runtime_sha256": _sha256(runtime),
            "sheet_size": sheet_size,
            "logical_extent": sheet_size,
            "frames_per_direction": frame_count,
            "direction_rows": DIRECTION_ROWS,
            "direction_playback": {
                direction: list(range(frame_count)) for direction in DIRECTION_ROWS
            },
            "fps": fps,
            "frame_durations_ms": frame_durations_ms,
            "source_matte": None,
            "pivot": None,
            "sources": [{
                "file": (
                    semantic_destination / f"{sequence}_manifest.json"
                ).relative_to(asset_root).as_posix(),
                "sha256": _sha256(semantic_destination / f"{sequence}_manifest.json"),
                "action": manifest["action"],
                "source_frames": manifest["source_frames"],
            }],
        }
        old_variants = previous_elf_animations.get(sequence, {}).get(
            "camera_variants", {}
        )
        if old_variants:
            animations[sequence]["camera_variants"] = {
                **old_variants,
                "low": {
                    "runtime_file": runtime.relative_to(asset_root).as_posix(),
                    "runtime_sha256": _sha256(runtime),
                },
            }

    if args.force:
        # The semantic builder owns only these original starter components.
        # Preserve independently generated fitted families under the shared
        # parts root when the elf semantic package is rebuilt.
        for part in PARTS:
            starter_dir = parts_root / part.slot / part.id
            if starter_dir.exists():
                shutil.rmtree(starter_dir)
    for part in PARTS:
        part_dir = parts_root / part.slot / part.id
        part_dir.mkdir(parents=True, exist_ok=True)
        animation_hashes: dict[str, str] = {}
        for sequence, (_manifest, art_path, regions_path) in packages.items():
            output = part_dir / f"{sequence}.png"
            _component_image(art_path, regions_path, part).save(output)
            animation_hashes[sequence] = _sha256(output)
        manifest = {
            "schemaVersion": 1,
            "id": part.id,
            "displayName": part.name,
            "slot": part.slot,
            "occupiesSlots": [part.slot],
            "reservedSlots": [],
            "layer": part.layer,
            "tags": ["semantic_regions", "starter", "recolorable"],
            "fit": "elf-01",
            "version": 1,
            "status": "approved",
            "animations": {name: f"{name}.png" for name in packages},
            "coverage": {name: list(DIRECTION_ROWS) for name in packages},
            "colorRamp": {"main": part.main, "colors": list(part.palette)},
            "suggestedColors": list(part.suggested),
            "provenance": {
                "kind": "deterministic_anatomical_region_overlay",
                "generator": "tools/build_semantic_character_forge.py",
                "outline": {
                    "widthPixels": 1,
                    "color": part.palette[0],
                    "placement": "outside" if part.dilation > 0 else "inside",
                },
                "sourceRegions": list(part.regions),
                "animationSha256": animation_hashes,
            },
        }
        (part_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
        )

    specs = {
        "schema_version": 2,
        "default_base_id": "elf-01",
        "frame_size": [128, 128],
        "layers": LAYERS,
        "slots": {
            slot: {"label": label, "layer": layer, "generation": False}
            for slot, (label, layer) in SLOTS.items()
        },
        "generation": {
            "enabled": False,
            "note": "The retired 64px component-generation pipeline has been removed.",
        },
        **(
            {"camera_heights": preserved_camera_heights}
            if preserved_camera_heights
            else {}
        ),
        "bases": {
            "elf-01": {
                "name": "Elf Female Base",
                "semantic": True,
                "animations": animations,
            },
            **preserved_bases,
        },
    }
    specs_path.write_text(
        json.dumps(specs, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    for sequence in packages:
        _review_contact_sheet(asset_root, PARTS, sequence)
    print(
        f"Installed elf-01 with {len(animations)} animations and "
        f"{len(PARTS)} region-derived components under {asset_root}"
    )


if __name__ == "__main__":
    main()
