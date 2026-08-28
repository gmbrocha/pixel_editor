from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.semantic_sprite_package import (
    SemanticSpriteSettings,
    check_semantic_sprite_package,
    generate_semantic_sprite_package,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a staged 128px semantic sprite package")
    parser.add_argument("manifest", type=Path, help="Paired beauty/semantic render manifest")
    parser.add_argument("output", type=Path)
    parser.add_argument("--cell-size", type=int, default=128)
    parser.add_argument("--palette-size", type=int, default=16)
    parser.add_argument("--alpha-threshold", type=int, default=112)
    parser.add_argument("--cleanup-threshold", type=int, default=1)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--sequence", default="walk")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    settings = SemanticSpriteSettings(
        cell_size=args.cell_size,
        palette_size=args.palette_size,
        alpha_threshold=args.alpha_threshold,
        cleanup_threshold=args.cleanup_threshold,
        fps=args.fps,
    )
    if args.check:
        mismatches = check_semantic_sprite_package(
            args.manifest, args.output, settings, sequence_name=args.sequence
        )
        if mismatches:
            print("Semantic sprite package differs:")
            for mismatch in mismatches:
                print(f"  {mismatch}")
            return 1
        print("Semantic sprite package is current.")
        return 0
    result = generate_semantic_sprite_package(
        args.manifest, args.output, settings, sequence_name=args.sequence
    )
    print(f"Wrote {len(result['output_sha256']) + 1} files to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
