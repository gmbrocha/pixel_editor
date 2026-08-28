"""Assemble Blender sprite renders into fixed-cell four-direction PNG sheets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cell-size", type=int, default=64)
    return parser.parse_args()


def main() -> None:
    args = _args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    direction_order = manifest["direction_order"]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    outputs = {}
    for sequence_name, sequence in manifest["sequences"].items():
        frame_count = len(sequence["source_frames"])
        sheet = Image.new(
            "RGBA",
            (args.cell_size * frame_count, args.cell_size * len(direction_order)),
            (0, 0, 0, 0),
        )
        strips = {}
        for row, direction in enumerate(direction_order):
            paths = [Path(path) for path in sequence["directions"][direction]]
            if len(paths) != frame_count:
                raise ValueError(
                    f"{sequence_name}/{direction} has {len(paths)} frames; expected {frame_count}"
                )
            strip = Image.new(
                "RGBA",
                (args.cell_size * frame_count, args.cell_size),
                (0, 0, 0, 0),
            )
            for column, path in enumerate(paths):
                with Image.open(path) as source:
                    frame = source.convert("RGBA").resize(
                        (args.cell_size, args.cell_size),
                        Image.Resampling.LANCZOS,
                    )
                x = column * args.cell_size
                strip.alpha_composite(frame, (x, 0))
                sheet.alpha_composite(frame, (x, row * args.cell_size))
            strip_path = args.output_dir / f"{sequence_name}_{direction}_{args.cell_size}px.png"
            strip.save(strip_path, optimize=False)
            strips[direction] = str(strip_path.resolve())

        sheet_path = args.output_dir / f"{sequence_name}_four_direction_{args.cell_size}px.png"
        sheet.save(sheet_path, optimize=False)
        outputs[sequence_name] = {
            "sheet": str(sheet_path.resolve()),
            "strips": strips,
            "dimensions": list(sheet.size),
            "frame_count": frame_count,
            "source_frames": sequence["source_frames"],
        }

    output_manifest = {
        "schema_version": 1,
        "source_manifest": str(args.manifest.resolve()),
        "cell_size": args.cell_size,
        "direction_order": direction_order,
        "outputs": outputs,
    }
    output_manifest_path = args.output_dir / "sprite_sheet_manifest.json"
    output_manifest_path.write_text(
        json.dumps(output_manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_manifest_path.resolve()}")


if __name__ == "__main__":
    main()
