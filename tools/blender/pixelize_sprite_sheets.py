"""Create deterministic limited-palette sheets from Blender sprite renders."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.sprite_pixelizer import (
    SpritePixelizationSettings,
    check_pixel_sprite_sheets,
    generate_pixel_sprite_sheets,
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cell-size", type=int, default=64)
    parser.add_argument("--palette-size", type=int, default=16)
    parser.add_argument("--alpha-threshold", type=int, default=112)
    parser.add_argument("--cleanup-threshold", type=int, default=1)
    parser.add_argument("--preview-fps", type=int, default=10)
    parser.add_argument("--preview-scale", type=int, default=4)
    parser.add_argument("--silhouette-outline", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _args()
    settings = SpritePixelizationSettings(
        cell_size=args.cell_size,
        palette_size=args.palette_size,
        alpha_threshold=args.alpha_threshold,
        cleanup_threshold=args.cleanup_threshold,
        preview_fps=args.preview_fps,
        preview_scale=args.preview_scale,
        silhouette_outline=args.silhouette_outline,
    )
    if args.check:
        mismatches = check_pixel_sprite_sheets(
            args.manifest,
            args.output_dir,
            settings,
        )
        if mismatches:
            joined = "\n  ".join(mismatches)
            raise SystemExit(f"Pixel sprite outputs differ:\n  {joined}")
        print(f"Verified deterministic pixel sprite outputs in {args.output_dir.resolve()}")
        return

    manifest = generate_pixel_sprite_sheets(
        args.manifest,
        args.output_dir,
        settings,
    )
    print(
        f"Wrote {args.output_dir.resolve()} with "
        f"{len(manifest['palette'])} shared colors"
    )


if __name__ == "__main__":
    main()
