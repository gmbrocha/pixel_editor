from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np
from PIL import Image

from src.core.image_processing import area_resize
from src.core.mannequin_semantics import (
    CHARACTER_SLOTS,
    REGIONS,
    REGION_BY_NAME,
    SLOT_HIDE_REGIONS,
    SLOT_SURFACE_REGIONS,
)
from src.core.sprite_pixelizer import (
    SpritePixelizationSettings,
    generate_pixel_sprite_sheets,
)


@dataclass(frozen=True, slots=True)
class SemanticSpriteSettings:
    cell_size: int = 128
    palette_size: int = 16
    alpha_threshold: int = 112
    cleanup_threshold: int = 1
    fps: int = 10
    thin_region_source_pixels: int = 8

    def normalized(self) -> "SemanticSpriteSettings":
        return SemanticSpriteSettings(
            cell_size=max(1, int(self.cell_size)),
            palette_size=max(1, min(256, int(self.palette_size))),
            alpha_threshold=max(1, min(255, int(self.alpha_threshold))),
            cleanup_threshold=max(0, int(self.cleanup_threshold)),
            fps=max(1, min(60, int(self.fps))),
            thin_region_source_pixels=max(1, int(self.thin_region_source_pixels)),
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _save(image: Image.Image, path: Path, mode: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode:
        image = image.convert(mode)
    image.save(path, format="PNG", optimize=False, compress_level=9)


def _resolve(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    return (manifest_path.parent / path).resolve() if not path.is_absolute() else path.resolve()


def _nearest_region_ids(rgb: np.ndarray) -> np.ndarray:
    colors = np.asarray([region.color[:3] for region in REGIONS], dtype=np.int16)
    flat = rgb.reshape(-1, 3)
    unique, inverse = np.unique(flat, axis=0, return_inverse=True)
    delta = unique[:, None, :].astype(np.int32) - colors[None, :, :].astype(np.int32)
    nearest = np.argmin(np.sum(delta * delta, axis=2), axis=1).astype(np.uint8) + 1
    return nearest[inverse].reshape(rgb.shape[:2])


def _downsample_regions(
    semantic: Image.Image,
    art: Image.Image,
    cell_size: int,
    alpha_threshold: int,
    rescue_threshold: int,
) -> tuple[np.ndarray, list[int]]:
    source = np.asarray(semantic.convert("RGBA"), dtype=np.uint8)
    if source.shape[0] % cell_size or source.shape[1] % cell_size:
        raise ValueError(f"Semantic render {semantic.size} is not divisible by {cell_size}")
    if source.shape[0] != source.shape[1]:
        raise ValueError(f"Semantic render must be square, found {semantic.size}")
    factor = source.shape[0] // cell_size
    if factor < 1:
        raise ValueError("Semantic render is smaller than the requested cell")

    high_ids = _nearest_region_ids(source[..., :3])
    visible = source[..., 3] >= alpha_threshold
    high_ids[~visible] = 0
    blocks = high_ids.reshape(cell_size, factor, cell_size, factor).transpose(0, 2, 1, 3)
    counts = np.stack([(blocks == region.id).sum(axis=(2, 3)) for region in REGIONS], axis=2)
    result = np.argmax(counts, axis=2).astype(np.uint8) + 1
    result[np.max(counts, axis=2) == 0] = 0

    art_alpha = np.asarray(art.convert("RGBA"), dtype=np.uint8)[..., 3] > 0
    result[~art_alpha] = 0
    rescued: list[int] = []
    for region in REGIONS:
        if np.count_nonzero(high_ids == region.id) < rescue_threshold:
            continue
        if np.any(result == region.id):
            continue
        coverage = counts[..., region.id - 1].copy()
        coverage[~art_alpha] = 0
        index = int(np.argmax(coverage))
        if coverage.flat[index] > 0:
            result.flat[index] = region.id
            rescued.append(region.id)

    missing = art_alpha & (result == 0)
    for _ in range(cell_size * 2):
        if not np.any(missing):
            break
        candidates = np.zeros((*result.shape, 4), dtype=np.uint8)
        candidates[1:, :, 0] = result[:-1, :]
        candidates[:-1, :, 1] = result[1:, :]
        candidates[:, 1:, 2] = result[:, :-1]
        candidates[:, :-1, 3] = result[:, 1:]
        fill = np.max(candidates, axis=2)
        can_fill = missing & (fill > 0)
        result[can_fill] = fill[can_fill]
        missing = art_alpha & (result == 0)
    if np.any(missing):
        raise ValueError("Opaque art pixels could not be assigned an anatomical region")
    return result, rescued


def _preview(ids: np.ndarray) -> Image.Image:
    lookup = np.zeros((33, 4), dtype=np.uint8)
    for region in REGIONS:
        lookup[region.id] = region.color
    return Image.fromarray(lookup[ids], "RGBA")


def _mask(ids: np.ndarray, region_names: tuple[str, ...]) -> Image.Image:
    allowed = np.asarray([REGION_BY_NAME[name].id for name in region_names], dtype=np.uint8)
    return Image.fromarray(np.where(np.isin(ids, allowed), 255, 0).astype(np.uint8), "L")


def _native_gif(frames: list[Image.Image], output: Path, fps: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    prepared = [frame.convert("RGBA") for frame in frames]
    prepared[0].save(
        output,
        save_all=True,
        append_images=prepared[1:],
        duration=max(1, round(1000 / fps)),
        loop=0,
        disposal=2,
        optimize=False,
    )


def generate_semantic_sprite_package(
    paired_manifest_path: Path,
    output_dir: Path,
    settings: SemanticSpriteSettings | None = None,
    sequence_name: str = "walk",
) -> dict[str, Any]:
    paired_manifest_path = paired_manifest_path.resolve()
    output_dir = output_dir.resolve()
    normalized = (settings or SemanticSpriteSettings()).normalized()
    paired = json.loads(paired_manifest_path.read_text(encoding="utf-8"))
    directions = [str(value) for value in paired.get("direction_order", [])]
    sequence_name = sequence_name.strip().lower()
    sequence = paired.get("sequences", {}).get(sequence_name)
    if not directions or not isinstance(sequence, dict):
        raise ValueError(
            f"Paired manifest must contain the {sequence_name} sequence and direction order"
        )
    source_frames = [int(value) for value in sequence.get("source_frames", [])]
    frame_count = len(source_frames)
    if frame_count < 1:
        raise ValueError(f"{sequence_name.title()} must have at least one frame")

    with tempfile.TemporaryDirectory(prefix="pixel-forge-art-") as temporary:
        art_dir = Path(temporary)
        art_manifest = generate_pixel_sprite_sheets(
            paired_manifest_path,
            art_dir,
            SpritePixelizationSettings(
                cell_size=normalized.cell_size,
                palette_size=normalized.palette_size,
                alpha_threshold=normalized.alpha_threshold,
                cleanup_threshold=normalized.cleanup_threshold,
                preview_fps=normalized.fps,
            ),
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        art_sequence = art_manifest["sequences"][sequence_name]
        shutil.copy2(
            art_dir / art_sequence["sheet"], output_dir / f"{sequence_name}.png"
        )
        shutil.copy2(art_dir / "palette.png", output_dir / "palette.png")

        region_sheet = Image.new(
            "L", (normalized.cell_size * frame_count, normalized.cell_size * len(directions))
        )
        preview_sheet = Image.new("RGBA", region_sheet.size, (0, 0, 0, 0))
        frame_records: list[dict[str, Any]] = []
        art_frames_by_direction: dict[str, list[Image.Image]] = {}
        for row, direction in enumerate(directions):
            art_frames_by_direction[direction] = []
            strip = Image.new(
                "RGBA", (normalized.cell_size * frame_count, normalized.cell_size),
                (0, 0, 0, 0),
            )
            semantic_paths = sequence.get("semantic_directions", {}).get(direction)
            if not isinstance(semantic_paths, list) or len(semantic_paths) != frame_count:
                raise ValueError(
                    f"{sequence_name}/{direction} must contain {frame_count} semantic renders"
                )
            for column, source_frame in enumerate(source_frames):
                art_source = art_dir / art_sequence["frames"][direction][column]
                with Image.open(art_source) as opened:
                    art = opened.convert("RGBA")
                art_frames_by_direction[direction].append(art.copy())
                art_path = output_dir / "frames" / "art" / direction / f"frame_{column:02d}.png"
                _save(art, art_path, "RGBA")
                strip.alpha_composite(art, (column * normalized.cell_size, 0))
                semantic_source = _resolve(paired_manifest_path, str(semantic_paths[column]))
                with Image.open(semantic_source) as opened:
                    ids, rescued = _downsample_regions(
                        opened, art, normalized.cell_size,
                        normalized.alpha_threshold, normalized.thin_region_source_pixels,
                    )
                region_image = Image.fromarray(ids, "L")
                preview_image = _preview(ids)
                region_path = output_dir / "frames" / "regions" / direction / f"frame_{column:02d}.png"
                preview_path = output_dir / "frames" / "regions_preview" / direction / f"frame_{column:02d}.png"
                _save(region_image, region_path, "L")
                _save(preview_image, preview_path, "RGBA")
                region_sheet.paste(region_image, (column * normalized.cell_size, row * normalized.cell_size))
                preview_sheet.alpha_composite(preview_image, (column * normalized.cell_size, row * normalized.cell_size))
                counts = np.bincount(ids.ravel(), minlength=33)
                frame_records.append({
                    "direction": direction,
                    "frame_index": column,
                    "source_frame": source_frame,
                    "rect": [column * normalized.cell_size, row * normalized.cell_size, normalized.cell_size, normalized.cell_size],
                    "art": art_path.relative_to(output_dir).as_posix(),
                    "regions": region_path.relative_to(output_dir).as_posix(),
                    "regions_preview": preview_path.relative_to(output_dir).as_posix(),
                    "region_pixel_counts": {str(i): int(counts[i]) for i in range(1, 33) if counts[i]},
                    "rescued_region_ids": rescued,
                    "semantic_source_sha256": _sha256(semantic_source),
                })
            _save(
                strip, output_dir / "strips" / f"{sequence_name}_{direction}.png", "RGBA"
            )
            _native_gif(
                art_frames_by_direction[direction],
                output_dir / "gifs" / f"{sequence_name}_{direction}.gif",
                normalized.fps,
            )

        _save(region_sheet, output_dir / f"{sequence_name}_regions.png", "L")
        _save(
            preview_sheet, output_dir / f"{sequence_name}_regions_preview.png", "RGBA"
        )
        region_array = np.asarray(region_sheet, dtype=np.uint8)
        for slot in CHARACTER_SLOTS:
            _save(
                _mask(region_array, SLOT_SURFACE_REGIONS[slot]),
                output_dir / "slots" / f"{sequence_name}_slot_{slot}.png", "L",
            )
            _save(
                _mask(region_array, SLOT_HIDE_REGIONS[slot]),
                output_dir / "hide" / f"{sequence_name}_hide_{slot}.png", "L",
            )

        source_hashes = {
            "paired_manifest": _sha256(paired_manifest_path),
            "blend": str(paired.get("blend", "")),
            "blend_sha256": str(paired.get("blend_sha256", "")),
        }
        outputs = {
            path.relative_to(output_dir).as_posix(): _sha256(path)
            for path in sorted(output_dir.rglob("*"))
            if path.is_file() and path.name != f"{sequence_name}_manifest.json"
        }
        manifest = {
            "schema_version": 1,
            "kind": "pixel_forge_semantic_sprite_package",
            "sequence": sequence_name,
            "action": str(sequence.get("action", "")),
            "staged": True,
            "source": source_hashes,
            "direction_order": directions,
            "source_frames": source_frames,
            "sheet_dimensions": [
                normalized.cell_size * frame_count,
                normalized.cell_size * len(directions),
            ],
            "settings": asdict(normalized),
            "art_palette": art_manifest["palette"],
            "regions": [asdict(region) for region in REGIONS],
            "slots": {slot: list(SLOT_SURFACE_REGIONS[slot]) for slot in CHARACTER_SLOTS},
            "hide_regions": {slot: list(SLOT_HIDE_REGIONS[slot]) for slot in CHARACTER_SLOTS},
            "frames": frame_records,
            "output_sha256": outputs,
        }
        (output_dir / f"{sequence_name}_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        return manifest


def check_semantic_sprite_package(
    paired_manifest_path: Path,
    output_dir: Path,
    settings: SemanticSpriteSettings | None = None,
    sequence_name: str = "walk",
) -> list[str]:
    output_dir = output_dir.resolve()
    with tempfile.TemporaryDirectory(prefix="pixel-forge-semantic-check-") as temporary:
        candidate = Path(temporary)
        generate_semantic_sprite_package(
            paired_manifest_path, candidate, settings, sequence_name=sequence_name
        )
        expected_files = {path.relative_to(candidate) for path in candidate.rglob("*") if path.is_file()}
        actual_files = {path.relative_to(output_dir) for path in output_dir.rglob("*") if path.is_file()}
        mismatches = []
        for relative in sorted(expected_files | actual_files):
            expected = candidate / relative
            actual = output_dir / relative
            if not expected.is_file() or not actual.is_file() or expected.read_bytes() != actual.read_bytes():
                mismatches.append(relative.as_posix())
        return mismatches
