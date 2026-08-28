from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

import numpy as np
from PIL import Image

from src.core.image_processing import area_resize, cluster_cleanup
from src.core.palette import (
    PaletteExtractionSettings,
    palette_from_image_with_debug,
    quantize_to_palette,
)


RGBA = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class SpritePixelizationSettings:
    cell_size: int = 64
    palette_size: int = 16
    alpha_threshold: int = 112
    cleanup_threshold: int = 1
    preview_fps: int = 10
    palette_selection: str = "most_frequent"
    min_cluster_percent: float = 0.0005
    min_perceptual_distance: float = 4.0

    def normalized(self) -> "SpritePixelizationSettings":
        return SpritePixelizationSettings(
            cell_size=max(1, int(self.cell_size)),
            palette_size=max(1, min(256, int(self.palette_size))),
            alpha_threshold=max(1, min(255, int(self.alpha_threshold))),
            cleanup_threshold=max(0, int(self.cleanup_threshold)),
            preview_fps=max(1, min(60, int(self.preview_fps))),
            palette_selection=(self.palette_selection or "most_frequent").strip(),
            min_cluster_percent=max(0.0, float(self.min_cluster_percent)),
            min_perceptual_distance=max(0.0, float(self.min_perceptual_distance)),
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGBA").save(path, format="PNG", optimize=False, compress_level=9)


def _resolve_source(manifest_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path.resolve()


def _binary_alpha(image: Image.Image, threshold: int) -> Image.Image:
    pixels = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    visible = pixels[..., 3] >= threshold
    pixels[~visible] = 0
    pixels[visible, 3] = 255
    return Image.fromarray(pixels, mode="RGBA")


def _sampling_atlas(images: list[Image.Image]) -> Image.Image:
    if not images:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    columns = min(8, len(images))
    rows = (len(images) + columns - 1) // columns
    width, height = images[0].size
    atlas = Image.new("RGBA", (columns * width, rows * height), (0, 0, 0, 0))
    for index, image in enumerate(images):
        atlas.alpha_composite(image, ((index % columns) * width, (index // columns) * height))
    return atlas


def _opaque_review(image: Image.Image, scale: int = 4) -> Image.Image:
    scaled = image.convert("RGBA").resize(
        (image.width * scale, image.height * scale),
        Image.Resampling.NEAREST,
    )
    background = Image.new("RGBA", scaled.size, (27, 29, 34, 255))
    background.alpha_composite(scaled)
    return background


def _save_preview_gif(
    frames: list[Image.Image],
    path: Path,
    fps: int,
    scale: int = 4,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = [_opaque_review(frame, scale=scale).convert("RGB") for frame in frames]
    rendered[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=rendered[1:],
        duration=max(1, round(1000 / fps)),
        loop=0,
        optimize=False,
        disposal=2,
    )


def _validated_entries(
    manifest_path: Path,
    manifest: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    directions = [str(item) for item in manifest.get("direction_order", [])]
    if not directions:
        raise ValueError("Sprite render manifest has no direction_order")
    sequences = manifest.get("sequences")
    if not isinstance(sequences, dict) or not sequences:
        raise ValueError("Sprite render manifest has no sequences")

    entries: list[dict[str, Any]] = []
    for sequence_name, sequence in sequences.items():
        if not isinstance(sequence, dict):
            raise ValueError(f"Invalid sequence entry: {sequence_name}")
        source_frames = [int(frame) for frame in sequence.get("source_frames", [])]
        if not source_frames:
            raise ValueError(f"Sequence {sequence_name} has no source frames")
        direction_map = sequence.get("directions")
        if not isinstance(direction_map, dict):
            raise ValueError(f"Sequence {sequence_name} has no direction mapping")
        for direction in directions:
            raw_paths = direction_map.get(direction)
            if not isinstance(raw_paths, list) or len(raw_paths) != len(source_frames):
                actual = len(raw_paths) if isinstance(raw_paths, list) else 0
                raise ValueError(
                    f"{sequence_name}/{direction} has {actual} renders; "
                    f"expected {len(source_frames)}"
                )
            for frame_index, (source_frame, raw_path) in enumerate(
                zip(source_frames, raw_paths, strict=True)
            ):
                resolved = _resolve_source(manifest_path, str(raw_path))
                if not resolved.is_file():
                    raise FileNotFoundError(resolved)
                entries.append(
                    {
                        "sequence": str(sequence_name),
                        "action": str(sequence.get("action", "")),
                        "direction": direction,
                        "frame_index": frame_index,
                        "source_frame": source_frame,
                        "source": resolved,
                    }
                )
    return directions, entries


def generate_pixel_sprite_sheets(
    manifest_path: Path,
    output_dir: Path,
    settings: SpritePixelizationSettings | None = None,
) -> dict[str, Any]:
    """Convert immutable Blender renders into deterministic pixel-art sheets.

    Every frame shares one palette, uses premultiplied area downsampling, and
    receives binary alpha before quantization. Source renders are read only.
    """
    manifest_path = manifest_path.resolve()
    output_dir = output_dir.resolve()
    normalized = (settings or SpritePixelizationSettings()).normalized()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    directions, entries = _validated_entries(manifest_path, manifest)

    reduced: list[Image.Image] = []
    source_hashes: dict[str, str] = {}
    for entry in entries:
        source_path = entry["source"]
        with Image.open(source_path) as opened:
            resized = area_resize(
                opened.convert("RGBA"),
                (normalized.cell_size, normalized.cell_size),
            )
        reduced.append(_binary_alpha(resized, normalized.alpha_threshold))
        source_hashes[str(source_path)] = _sha256(source_path)

    sample = _sampling_atlas(reduced)
    palette_settings = PaletteExtractionSettings(
        palette_size=normalized.palette_size,
        min_cluster_percent=normalized.min_cluster_percent,
        min_perceptual_distance=normalized.min_perceptual_distance,
        preserve_accent_colors=True,
        apply_family_cap_to_most_frequent=False,
    )
    palette, palette_debug = palette_from_image_with_debug(
        sample,
        max_colors=normalized.palette_size,
        selection=normalized.palette_selection,
        settings=palette_settings,
    )
    opaque_palette: list[RGBA] = [(*color[:3], 255) for color in palette if color[3] > 0]
    if not opaque_palette:
        raise ValueError("Visible Blender renders produced no opaque palette colors")

    processed: dict[tuple[str, str, int], Image.Image] = {}
    for entry, image in zip(entries, reduced, strict=True):
        converted = quantize_to_palette(image, opaque_palette, dither=False)
        if normalized.cleanup_threshold > 0:
            converted = cluster_cleanup(
                converted,
                threshold=normalized.cleanup_threshold,
            )
        processed[(entry["sequence"], entry["direction"], entry["frame_index"])] = converted

    output_dir.mkdir(parents=True, exist_ok=True)
    output_sequences: dict[str, Any] = {}
    sequence_names = list(manifest["sequences"])
    for sequence_name in sequence_names:
        sequence = manifest["sequences"][sequence_name]
        source_frames = [int(frame) for frame in sequence["source_frames"]]
        frame_count = len(source_frames)
        sheet = Image.new(
            "RGBA",
            (normalized.cell_size * frame_count, normalized.cell_size * len(directions)),
            (0, 0, 0, 0),
        )
        strips: dict[str, str] = {}
        previews: dict[str, str] = {}
        frame_outputs: dict[str, list[str]] = {}
        for row, direction in enumerate(directions):
            strip = Image.new(
                "RGBA",
                (normalized.cell_size * frame_count, normalized.cell_size),
                (0, 0, 0, 0),
            )
            relative_frames: list[str] = []
            direction_frames: list[Image.Image] = []
            for column in range(frame_count):
                frame = processed[(sequence_name, direction, column)]
                direction_frames.append(frame)
                relative = Path("frames") / sequence_name / direction / f"frame_{column:02d}.png"
                _save_png(frame, output_dir / relative)
                relative_frames.append(relative.as_posix())
                strip.alpha_composite(frame, (column * normalized.cell_size, 0))
                sheet.alpha_composite(
                    frame,
                    (column * normalized.cell_size, row * normalized.cell_size),
                )
            strip_relative = Path("strips") / f"{sequence_name}_{direction}_{normalized.cell_size}px.png"
            _save_png(strip, output_dir / strip_relative)
            strips[direction] = strip_relative.as_posix()
            frame_outputs[direction] = relative_frames
            preview_relative = (
                Path("review")
                / f"{sequence_name}_{direction}_{normalized.preview_fps}fps.gif"
            )
            _save_preview_gif(
                direction_frames,
                output_dir / preview_relative,
                normalized.preview_fps,
            )
            previews[direction] = preview_relative.as_posix()

        sheet_relative = Path("sheets") / f"{sequence_name}_four_direction_{normalized.cell_size}px.png"
        review_relative = Path("review") / f"{sequence_name}_four_direction_{normalized.cell_size}px_4x.png"
        _save_png(sheet, output_dir / sheet_relative)
        _save_png(_opaque_review(sheet), output_dir / review_relative)
        output_sequences[sequence_name] = {
            "action": str(sequence.get("action", "")),
            "source_frames": source_frames,
            "frame_count": frame_count,
            "dimensions": list(sheet.size),
            "frames": frame_outputs,
            "strips": strips,
            "previews": previews,
            "sheet": sheet_relative.as_posix(),
            "review": review_relative.as_posix(),
        }

    palette_image = Image.new(
        "RGBA",
        (len(opaque_palette) * 16, 16),
        (0, 0, 0, 0),
    )
    for index, color in enumerate(opaque_palette):
        palette_image.paste(color, (index * 16, 0, (index + 1) * 16, 16))
    _save_png(palette_image, output_dir / "palette.png")

    output_hashes = {
        path.relative_to(output_dir).as_posix(): _sha256(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".png", ".gif"}
    }
    output_manifest = {
        "schema_version": 1,
        "source_manifest_sha256": _sha256(manifest_path),
        "source_blend": str(manifest.get("blend", "")),
        "direction_order": directions,
        "settings": asdict(normalized),
        "palette": [list(color) for color in opaque_palette],
        "palette_debug": {
            "source_unique_rgb_colors": palette_debug.total_unique_rgb_colors,
            "perceptual_cluster_count": palette_debug.perceptual_cluster_count,
            "selected_color_count": palette_debug.selected_color_count,
        },
        "source_render_sha256": source_hashes,
        "sequences": output_sequences,
        "output_sha256": output_hashes,
    }
    manifest_output = output_dir / "pixel_sprite_manifest.json"
    manifest_output.write_text(
        json.dumps(output_manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output_manifest


def check_pixel_sprite_sheets(
    manifest_path: Path,
    output_dir: Path,
    settings: SpritePixelizationSettings | None = None,
) -> list[str]:
    """Return relative output paths that do not match fresh regeneration."""
    output_dir = output_dir.resolve()
    with tempfile.TemporaryDirectory(prefix="pixel-forge-sprite-check-") as temporary:
        candidate = Path(temporary)
        generate_pixel_sprite_sheets(manifest_path, candidate, settings)
        mismatches: list[str] = []
        for expected in sorted(path for path in candidate.rglob("*") if path.is_file()):
            relative = expected.relative_to(candidate)
            actual = output_dir / relative
            if not actual.is_file() or actual.read_bytes() != expected.read_bytes():
                mismatches.append(relative.as_posix())
        return mismatches
