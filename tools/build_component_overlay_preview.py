"""Composite one aligned component direction over a Character Forge base."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


DIRECTION_ROWS = {"front": 0, "back": 1, "right": 2, "left": 3}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--direction", choices=DIRECTION_ROWS, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    parser.add_argument("--frame-duration-ms", type=int, default=100)
    args = parser.parse_args()

    with Image.open(args.base) as opened:
        base = opened.convert("RGBA")
    with Image.open(args.overlay) as opened:
        overlay = opened.convert("RGBA")
    if base.size != overlay.size:
        raise ValueError(f"Base {base.size} and overlay {overlay.size} must align")
    if base.height != 512 or base.width % 128:
        raise ValueError(f"Expected a four-row 128px sheet, got {base.size}")

    row = DIRECTION_ROWS[args.direction]
    frame_count = base.width // 128
    frames: list[Image.Image] = []
    for column in range(frame_count):
        box = (column * 128, row * 128, (column + 1) * 128, (row + 1) * 128)
        frames.append(Image.alpha_composite(base.crop(box), overlay.crop(box)))

    prefix = args.output_prefix
    prefix.parent.mkdir(parents=True, exist_ok=True)
    strip = Image.new("RGBA", (frame_count * 128, 128), (0, 0, 0, 0))
    for column, frame in enumerate(frames):
        strip.paste(frame, (column * 128, 0))
    strip.save(prefix.with_name(prefix.name + "_strip.png"), format="PNG")

    native = prefix.with_name(prefix.name + "_native.gif")
    frames[0].save(
        native,
        save_all=True,
        append_images=frames[1:],
        duration=args.frame_duration_ms,
        loop=0,
        disposal=2,
        optimize=False,
    )
    scaled = [frame.resize((512, 512), Image.Resampling.NEAREST) for frame in frames]
    review = prefix.with_name(prefix.name + "_4x.gif")
    scaled[0].save(
        review,
        save_all=True,
        append_images=scaled[1:],
        duration=args.frame_duration_ms,
        loop=0,
        disposal=2,
        optimize=False,
    )
    print(f"Wrote {strip.size} strip and {len(frames)}-frame previews")


if __name__ == "__main__":
    main()
