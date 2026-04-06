from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

Color = tuple[int, int, int, int]


@dataclass(slots=True)
class AnchorPoint:
    name: str
    x: int
    y: int


@dataclass(slots=True)
class AnimationFrame:
    image: Image.Image
    duration_ticks: int = 1
    anchors: list[AnchorPoint] = field(default_factory=list)
    label: str = ""


@dataclass(slots=True)
class AnimationDocument:
    frames: list[AnimationFrame] = field(default_factory=list)
    name: str = "animation"
    palette: list[Color] = field(default_factory=list)
    current_color: Color = (0, 0, 0, 255)
    use_transparent_color: bool = False

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def frame_size(self) -> tuple[int, int]:
        if not self.frames:
            return 0, 0
        return self.frames[0].image.width, self.frames[0].image.height


def create_animation_from_base(
    base: Image.Image,
    count: int,
    palette: list[Color] | None = None,
) -> AnimationDocument:
    frames = [AnimationFrame(image=base.copy()) for _ in range(max(1, count))]
    return AnimationDocument(frames=frames, palette=list(palette or []))


def create_blank_animation(
    width: int,
    height: int,
    count: int,
    palette: list[Color] | None = None,
) -> AnimationDocument:
    blank = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
    return create_animation_from_base(blank, count, palette)


def frames_to_sheet(
    frames: list[AnimationFrame],
    columns: int,
) -> Image.Image:
    if not frames:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    cols = max(1, columns)
    w, h = frames[0].image.width, frames[0].image.height
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGBA", (w * cols, h * rows), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        col = i % cols
        row = i // cols
        sheet.paste(frame.image, (col * w, row * h))
    return sheet


def export_gif(
    frames: list[AnimationFrame],
    path: str | Path,
    fps: int = 10,
    loop: bool = True,
) -> None:
    if not frames:
        return
    base_ms = max(10, int(1000 / max(1, fps)))
    pil_frames = []
    durations = []
    for f in frames:
        rgba = f.image.convert("RGBA")
        pil_frames.append(rgba)
        durations.append(base_ms * f.duration_ticks)

    pil_frames[0].save(
        str(path),
        save_all=True,
        append_images=pil_frames[1:],
        duration=durations,
        loop=0 if loop else 1,
        disposal=2,
    )


def export_animation_metadata(
    doc: AnimationDocument,
    path: str | Path,
    columns: int,
) -> None:
    meta: dict = {
        "name": doc.name,
        "frame_width": doc.frame_size[0],
        "frame_height": doc.frame_size[1],
        "columns": columns,
        "frames": [],
    }
    for i, f in enumerate(doc.frames):
        fdata: dict = {
            "index": i,
            "duration_ticks": f.duration_ticks,
            "label": f.label,
            "anchors": [{"name": a.name, "x": a.x, "y": a.y} for a in f.anchors],
        }
        meta["frames"].append(fdata)
    Path(path).write_text(json.dumps(meta, indent=2), encoding="utf-8")


def rotate_pixels_around_pivot(
    image: Image.Image,
    selected: set[tuple[int, int]],
    pivot: tuple[int, int],
    angle_degrees: float,
) -> Image.Image:
    """Rotate *selected* pixels around *pivot* by *angle_degrees*. Non-selected pixels stay."""
    result = image.copy()
    if not selected:
        return result

    rad = math.radians(angle_degrees)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    px, py = pivot

    for sx, sy in selected:
        result.putpixel((sx, sy), (0, 0, 0, 0))

    for sx, sy in selected:
        color = image.getpixel((sx, sy))
        dx = sx - px
        dy = sy - py
        nx = round(px + dx * cos_a - dy * sin_a)
        ny = round(py + dx * sin_a + dy * cos_a)
        if 0 <= nx < result.width and 0 <= ny < result.height:
            result.putpixel((nx, ny), color)

    return result
