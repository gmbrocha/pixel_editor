from __future__ import annotations

import io
import json
import math
import os
import uuid
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

Color = tuple[int, int, int, int]
FrameRect = tuple[int, int, int, int]  # x, y, width, height
PROJECT_SCHEMA_VERSION = 1
PLAYBACK_MODES = frozenset({"once", "loop", "ping_pong"})


class AnimationProjectError(ValueError):
    pass


@dataclass(slots=True)
class AnchorPoint:
    name: str
    x: int
    y: int


@dataclass(slots=True)
class AnimationFrame:
    """Frame metadata.

    Project frames use ``source_rect`` and read their pixels from the project's
    linked working sheet. ``image`` remains available for the small legacy
    helpers and standalone GIF export.
    """

    image: Image.Image | None = None
    source_rect: FrameRect | None = None
    duration_ticks: int = 1
    anchors: list[AnchorPoint] = field(default_factory=list)
    pivot: tuple[int, int] | None = None
    label: str = ""


@dataclass(frozen=True, slots=True)
class FrameSequenceSpec:
    origin_x: int
    origin_y: int
    frame_width: int
    frame_height: int
    count: int
    step_x: int
    step_y: int

    def rectangles(self) -> list[FrameRect]:
        return [
            (
                self.origin_x + index * self.step_x,
                self.origin_y + index * self.step_y,
                self.frame_width,
                self.frame_height,
            )
            for index in range(max(0, self.count))
        ]

    def validation_errors(self, sheet_size: tuple[int, int]) -> list[str]:
        errors: list[str] = []
        if self.frame_width < 1 or self.frame_height < 1:
            errors.append("Frame width and height must be positive.")
        if self.count < 1:
            errors.append("Frame count must be positive.")
        sheet_width, sheet_height = sheet_size
        for index, rect in enumerate(self.rectangles()):
            x, y, width, height = rect
            if x < 0 or y < 0 or x + width > sheet_width or y + height > sheet_height:
                errors.append(
                    f"Frame {index + 1} at ({x}, {y}, {width}, {height}) is outside "
                    f"the {sheet_width}x{sheet_height} sheet."
                )
        return errors

    def to_dict(self) -> dict[str, int]:
        return {
            "origin_x": self.origin_x,
            "origin_y": self.origin_y,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "count": self.count,
            "step_x": self.step_x,
            "step_y": self.step_y,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FrameSequenceSpec:
        try:
            return cls(
                origin_x=int(data["origin_x"]),
                origin_y=int(data["origin_y"]),
                frame_width=int(data["frame_width"]),
                frame_height=int(data["frame_height"]),
                count=int(data["count"]),
                step_x=int(data["step_x"]),
                step_y=int(data["step_y"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AnimationProjectError("Invalid frame sequence specification") from exc


@dataclass(slots=True)
class AnimationTrack:
    name: str
    spec: FrameSequenceSpec
    frames: list[AnimationFrame]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @classmethod
    def from_spec(cls, name: str, spec: FrameSequenceSpec) -> AnimationTrack:
        return cls(
            name=name,
            spec=spec,
            frames=[AnimationFrame(source_rect=rect) for rect in spec.rectangles()],
        )


@dataclass(slots=True)
class SheetTransaction:
    rect: FrameRect
    before: Image.Image
    after: Image.Image
    description: str


@dataclass(slots=True)
class AnimationProject:
    original_sheet: Image.Image
    working_sheet: Image.Image
    name: str = "animation"
    frame_width: int = 32
    frame_height: int = 32
    fps: int = 8
    playback_mode: str = "loop"
    palette: list[Color] = field(default_factory=list)
    tracks: list[AnimationTrack] = field(default_factory=list)
    source_path: str | None = None
    _undo: list[SheetTransaction] = field(default_factory=list, repr=False)
    _redo: list[SheetTransaction] = field(default_factory=list, repr=False)
    _history_limit: int = field(default=30, repr=False)

    def __post_init__(self) -> None:
        self.original_sheet = self.original_sheet.convert("RGBA").copy()
        self.working_sheet = self.working_sheet.convert("RGBA").copy()
        if self.original_sheet.size != self.working_sheet.size:
            raise AnimationProjectError(
                "Original and working sheets must have the same size"
            )
        self.frame_width = max(1, int(self.frame_width))
        self.frame_height = max(1, int(self.frame_height))
        self.fps = max(1, min(60, int(self.fps)))
        if self.playback_mode not in PLAYBACK_MODES:
            raise AnimationProjectError(
                f"Unknown playback mode: {self.playback_mode!r}"
            )

    @property
    def sheet_size(self) -> tuple[int, int]:
        return self.working_sheet.size

    def unique_track_name(
        self, requested: str, *, excluding_id: str | None = None
    ) -> str:
        base = requested.strip() or "Track"
        used = {
            track.name.casefold() for track in self.tracks if track.id != excluding_id
        }
        if base.casefold() not in used:
            return base
        suffix = 2
        while f"{base} {suffix}".casefold() in used:
            suffix += 1
        return f"{base} {suffix}"

    def add_track(self, name: str, spec: FrameSequenceSpec) -> AnimationTrack:
        self._validate_spec(spec)
        if not self.tracks:
            self.frame_width = spec.frame_width
            self.frame_height = spec.frame_height
        track = AnimationTrack.from_spec(self.unique_track_name(name), spec)
        self.tracks.append(track)
        return track

    def replace_track(
        self, track_id: str, name: str, spec: FrameSequenceSpec
    ) -> AnimationTrack:
        self._validate_spec(spec)
        index = self.track_index(track_id)
        replacement = AnimationTrack.from_spec(
            self.unique_track_name(name, excluding_id=track_id), spec
        )
        replacement.id = track_id
        self.tracks[index] = replacement
        return replacement

    def delete_track(self, track_id: str) -> AnimationTrack:
        return self.tracks.pop(self.track_index(track_id))

    def move_track(self, track_id: str, delta: int) -> int:
        index = self.track_index(track_id)
        target = max(0, min(len(self.tracks) - 1, index + delta))
        if target != index:
            track = self.tracks.pop(index)
            self.tracks.insert(target, track)
        return target

    def track_index(self, track_id: str) -> int:
        for index, track in enumerate(self.tracks):
            if track.id == track_id:
                return index
        raise AnimationProjectError(f"Unknown animation track: {track_id}")

    def track(self, track_id: str) -> AnimationTrack:
        return self.tracks[self.track_index(track_id)]

    def frame_image(
        self, track_id: str, frame_index: int, *, original: bool = False
    ) -> Image.Image:
        frame = self.track(track_id).frames[frame_index]
        if frame.source_rect is None:
            if frame.image is None:
                raise AnimationProjectError("Frame has no source rectangle or image")
            return frame.image.convert("RGBA").copy()
        source = self.original_sheet if original else self.working_sheet
        return source.crop(_rect_to_box(frame.source_rect)).copy()

    def commit_frame_image(
        self,
        track_id: str,
        frame_index: int,
        image: Image.Image,
        description: str = "Edit frame",
    ) -> FrameRect | None:
        frame = self.track(track_id).frames[frame_index]
        if frame.source_rect is None:
            raise AnimationProjectError("Linked frame is missing its source rectangle")
        if image.size != (frame.source_rect[2], frame.source_rect[3]):
            raise AnimationProjectError(
                "Edited frame size does not match its source rectangle"
            )
        return self._replace_region(frame.source_rect, image, description)

    def reset_frame(self, track_id: str, frame_index: int) -> FrameRect | None:
        frame = self.track(track_id).frames[frame_index]
        if frame.source_rect is None:
            return None
        original = self.original_sheet.crop(_rect_to_box(frame.source_rect))
        return self._replace_region(
            frame.source_rect, original, "Reset frame from original"
        )

    def reset_track(self, track_id: str) -> FrameRect | None:
        rects = [
            frame.source_rect
            for frame in self.track(track_id).frames
            if frame.source_rect is not None
        ]
        if not rects:
            return None
        union = bounding_rect(rects)
        before = self.working_sheet.crop(_rect_to_box(union)).copy()
        after = before.copy()
        ux, uy, _uw, _uh = union
        for rect in rects:
            x, y, _width, _height = rect
            original = self.original_sheet.crop(_rect_to_box(rect))
            after.paste(original, (x - ux, y - uy))
        return self._replace_region(union, after, "Reset track from original")

    def undo(self) -> SheetTransaction | None:
        if not self._undo:
            return None
        transaction = self._undo.pop()
        self.working_sheet.paste(transaction.before, transaction.rect[:2])
        self._redo.append(transaction)
        return transaction

    def redo(self) -> SheetTransaction | None:
        if not self._redo:
            return None
        transaction = self._redo.pop()
        self.working_sheet.paste(transaction.after, transaction.rect[:2])
        self._undo.append(transaction)
        return transaction

    def clear_history(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def intersecting_frames(self, changed_rect: FrameRect) -> list[tuple[str, int]]:
        hits: list[tuple[str, int]] = []
        for track in self.tracks:
            for index, frame in enumerate(track.frames):
                if frame.source_rect is not None and rects_overlap(
                    changed_rect, frame.source_rect
                ):
                    hits.append((track.id, index))
        return hits

    def overlaps_for_spec(
        self,
        spec: FrameSequenceSpec,
        *,
        excluding_track_id: str | None = None,
    ) -> list[tuple[FrameRect, FrameRect]]:
        proposed = spec.rectangles()
        existing = [
            frame.source_rect
            for track in self.tracks
            if track.id != excluding_track_id
            for frame in track.frames
            if frame.source_rect is not None
        ]
        overlaps: list[tuple[FrameRect, FrameRect]] = []
        for index, first in enumerate(proposed):
            for second in proposed[index + 1 :]:
                if rects_overlap(first, second):
                    overlaps.append((first, second))
            for second in existing:
                if rects_overlap(first, second):
                    overlaps.append((first, second))
        return overlaps

    def _validate_spec(self, spec: FrameSequenceSpec) -> None:
        errors = spec.validation_errors(self.sheet_size)
        if errors:
            raise AnimationProjectError(errors[0])
        if self.tracks and (
            spec.frame_width != self.frame_width
            or spec.frame_height != self.frame_height
        ):
            raise AnimationProjectError(
                f"All tracks must use the project frame size "
                f"{self.frame_width}x{self.frame_height}"
            )

    def _replace_region(
        self,
        rect: FrameRect,
        replacement: Image.Image,
        description: str,
    ) -> FrameRect | None:
        x, y, width, height = rect
        if replacement.size != (width, height):
            raise AnimationProjectError("Replacement image does not match region size")
        before = self.working_sheet.crop(_rect_to_box(rect)).copy()
        after = replacement.convert("RGBA").copy()
        if before.tobytes() == after.tobytes():
            return None
        self.working_sheet.paste(after, (x, y))
        self._undo.append(SheetTransaction(rect, before, after, description))
        if len(self._undo) > self._history_limit:
            del self._undo[0]
        self._redo.clear()
        return rect


def create_animation_project_from_sheet(
    sheet: Image.Image,
    *,
    name: str = "animation",
    frame_size: tuple[int, int] = (32, 32),
    fps: int = 8,
    playback_mode: str = "loop",
    palette: list[Color] | None = None,
    source_path: str | None = None,
) -> AnimationProject:
    rgba = sheet.convert("RGBA")
    return AnimationProject(
        original_sheet=rgba,
        working_sheet=rgba,
        name=name,
        frame_width=frame_size[0],
        frame_height=frame_size[1],
        fps=fps,
        playback_mode=playback_mode,
        palette=list(palette or []),
        source_path=source_path,
    )


def create_blank_project(
    sheet_width: int,
    sheet_height: int,
    *,
    frame_size: tuple[int, int] = (32, 32),
    name: str = "animation",
    fps: int = 8,
    playback_mode: str = "loop",
    palette: list[Color] | None = None,
) -> AnimationProject:
    sheet = Image.new("RGBA", (max(1, sheet_width), max(1, sheet_height)), (0, 0, 0, 0))
    return create_animation_project_from_sheet(
        sheet,
        name=name,
        frame_size=frame_size,
        fps=fps,
        playback_mode=playback_mode,
        palette=palette,
    )


def rects_overlap(first: FrameRect, second: FrameRect) -> bool:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def bounding_rect(rects: Iterable[FrameRect]) -> FrameRect:
    values = list(rects)
    if not values:
        raise AnimationProjectError("Cannot calculate bounds for no rectangles")
    left = min(rect[0] for rect in values)
    top = min(rect[1] for rect in values)
    right = max(rect[0] + rect[2] for rect in values)
    bottom = max(rect[1] + rect[3] for rect in values)
    return left, top, right - left, bottom - top


def _rect_to_box(rect: FrameRect) -> tuple[int, int, int, int]:
    x, y, width, height = rect
    return x, y, x + width, y + height


def track_to_sheet(project: AnimationProject, track_id: str) -> Image.Image:
    track = project.track(track_id)
    width = max(1, len(track.frames)) * project.frame_width
    result = Image.new("RGBA", (width, project.frame_height), (0, 0, 0, 0))
    for index in range(len(track.frames)):
        result.paste(
            project.frame_image(track_id, index), (index * project.frame_width, 0)
        )
    return result


def project_to_sheet(project: AnimationProject) -> Image.Image:
    max_frames = max((len(track.frames) for track in project.tracks), default=1)
    rows = max(1, len(project.tracks))
    result = Image.new(
        "RGBA",
        (max_frames * project.frame_width, rows * project.frame_height),
        (0, 0, 0, 0),
    )
    for row, track in enumerate(project.tracks):
        for column in range(len(track.frames)):
            result.paste(
                project.frame_image(track.id, column),
                (column * project.frame_width, row * project.frame_height),
            )
    return result


def playback_frame_indices(
    frame_count: int,
    playback_mode: str,
    *,
    start: int = 0,
    end: int | None = None,
) -> list[int]:
    """Return one forward or ping-pong cycle for an inclusive frame range.

    Ping-pong excludes duplicated turnaround frames. For five frames the cycle
    is ``0, 1, 2, 3, 4, 3, 2, 1``; looping supplies the transition back to 0.
    """
    if playback_mode not in PLAYBACK_MODES:
        raise AnimationProjectError(f"Unknown playback mode: {playback_mode!r}")
    if frame_count < 1:
        return []
    last = frame_count - 1 if end is None else end
    if start < 0 or start >= frame_count or last < start or last >= frame_count:
        raise AnimationProjectError("Playback range is outside the track")
    forward = list(range(start, last + 1))
    if playback_mode != "ping_pong" or len(forward) < 3:
        return forward
    return forward + list(range(last - 1, start, -1))


def export_project_gif(
    project: AnimationProject,
    track_id: str,
    path: str | Path,
) -> None:
    track = project.track(track_id)
    frame_indices = playback_frame_indices(len(track.frames), project.playback_mode)
    frames = [
        AnimationFrame(
            image=project.frame_image(track_id, index),
            duration_ticks=track.frames[index].duration_ticks,
            anchors=list(track.frames[index].anchors),
            pivot=track.frames[index].pivot,
            label=track.frames[index].label,
        )
        for index in frame_indices
    ]
    export_gif(
        frames,
        path,
        fps=project.fps,
        loop=project.playback_mode != "once",
    )


def project_metadata(project: AnimationProject) -> dict:
    max_frames = max((len(track.frames) for track in project.tracks), default=0)
    return {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "name": project.name,
        "frame_width": project.frame_width,
        "frame_height": project.frame_height,
        "fps": project.fps,
        "playback_mode": project.playback_mode,
        "sheet_columns": max_frames,
        "source_size": list(project.sheet_size),
        "palette": [list(color) for color in project.palette],
        "tracks": [
            {
                "id": track.id,
                "name": track.name,
                "row": row,
                "spec": track.spec.to_dict(),
                "frames": [
                    {
                        "index": index,
                        "source_rect": list(frame.source_rect)
                        if frame.source_rect
                        else None,
                        "duration_ticks": frame.duration_ticks,
                        "label": frame.label,
                        "anchors": [
                            {"name": anchor.name, "x": anchor.x, "y": anchor.y}
                            for anchor in frame.anchors
                        ],
                        "pivot": list(frame.pivot) if frame.pivot is not None else None,
                    }
                    for index, frame in enumerate(track.frames)
                ],
            }
            for row, track in enumerate(project.tracks)
        ],
    }


def export_project_metadata(project: AnimationProject, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(project_metadata(project), indent=2) + "\n", encoding="utf-8"
    )


def save_animation_project(project: AnimationProject, path: str | Path) -> None:
    destination = Path(path)
    temporary = destination.with_name(destination.name + ".tmp")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr(
                "project.json",
                json.dumps(project_metadata(project), indent=2) + "\n",
            )
            archive.writestr("original.png", _png_bytes(project.original_sheet))
            archive.writestr("working.png", _png_bytes(project.working_sheet))
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_animation_project(path: str | Path) -> AnimationProject:
    source = Path(path)
    try:
        with zipfile.ZipFile(source, "r") as archive:
            data = json.loads(archive.read("project.json").decode("utf-8"))
            original = _image_from_bytes(archive.read("original.png"))
            working = _image_from_bytes(archive.read("working.png"))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise AnimationProjectError(f"Could not open animation project: {exc}") from exc

    if not isinstance(data, dict):
        raise AnimationProjectError("Animation project manifest must be an object")
    if data.get("schema_version") != PROJECT_SCHEMA_VERSION:
        raise AnimationProjectError(
            f"Unsupported animation project schema: {data.get('schema_version')!r}"
        )
    try:
        palette: list[Color] = []
        for raw_color in data.get("palette", []):
            color = tuple(int(channel) for channel in raw_color)
            if len(color) != 4 or any(
                channel < 0 or channel > 255 for channel in color
            ):
                raise AnimationProjectError("Invalid project palette color")
            palette.append(color)  # type: ignore[arg-type]
        project = AnimationProject(
            original_sheet=original,
            working_sheet=working,
            name=str(data["name"]),
            frame_width=int(data["frame_width"]),
            frame_height=int(data["frame_height"]),
            fps=int(data["fps"]),
            playback_mode=str(data.get("playback_mode", "loop")),
            palette=palette,
        )
        seen_track_ids: set[str] = set()
        seen_track_names: set[str] = set()
        raw_tracks = data.get("tracks", [])
        if not isinstance(raw_tracks, list):
            raise AnimationProjectError("Animation tracks must be a list")
        for track_data in raw_tracks:
            if not isinstance(track_data, dict):
                raise AnimationProjectError("Animation track must be an object")
            spec = FrameSequenceSpec.from_dict(track_data["spec"])
            project._validate_spec(spec)
            if (spec.frame_width, spec.frame_height) != (
                project.frame_width,
                project.frame_height,
            ):
                raise AnimationProjectError(
                    "Track specification does not match project frame size"
                )
            track_id = str(track_data["id"])
            track_name = str(track_data["name"])
            if not track_id or track_id in seen_track_ids:
                raise AnimationProjectError("Animation track IDs must be unique")
            if not track_name.strip() or track_name.casefold() in seen_track_names:
                raise AnimationProjectError("Animation track names must be unique")
            seen_track_ids.add(track_id)
            seen_track_names.add(track_name.casefold())
            track = AnimationTrack(
                id=track_id,
                name=track_name,
                spec=spec,
                frames=[],
            )
            raw_frames = track_data.get("frames", [])
            if not isinstance(raw_frames, list):
                raise AnimationProjectError("Animation frames must be a list")
            if len(raw_frames) != spec.count:
                raise AnimationProjectError(
                    "Track frame count does not match its specification"
                )
            for frame_data in raw_frames:
                if not isinstance(frame_data, dict):
                    raise AnimationProjectError("Animation frame must be an object")
                raw_rect = frame_data.get("source_rect")
                rect = (
                    tuple(int(value) for value in raw_rect)
                    if raw_rect is not None
                    else None
                )
                if rect is not None and len(rect) != 4:
                    raise AnimationProjectError("Invalid frame source rectangle")
                frame = AnimationFrame(
                    source_rect=rect,  # type: ignore[arg-type]
                    duration_ticks=max(1, int(frame_data.get("duration_ticks", 1))),
                    label=str(frame_data.get("label", "")),
                    anchors=[
                        AnchorPoint(
                            str(anchor["name"]), int(anchor["x"]), int(anchor["y"])
                        )
                        for anchor in frame_data.get("anchors", [])
                    ],
                    pivot=(
                        tuple(int(value) for value in frame_data["pivot"])
                        if frame_data.get("pivot") is not None
                        else None
                    ),
                )
                if frame.source_rect is not None:
                    if frame.source_rect[2:] != (
                        project.frame_width,
                        project.frame_height,
                    ):
                        raise AnimationProjectError(
                            "Frame rectangle does not match project frame size"
                        )
                    validation = FrameSequenceSpec(
                        frame.source_rect[0],
                        frame.source_rect[1],
                        frame.source_rect[2],
                        frame.source_rect[3],
                        1,
                        0,
                        0,
                    ).validation_errors(project.sheet_size)
                    if validation:
                        raise AnimationProjectError(validation[0])
                if frame.pivot is not None and len(frame.pivot) != 2:
                    raise AnimationProjectError("Invalid frame pivot")
                track.frames.append(frame)
            project.tracks.append(track)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, AnimationProjectError):
            raise
        raise AnimationProjectError("Invalid animation project manifest") from exc
    project.clear_history()
    return project


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


def _image_from_bytes(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as opened:
        return opened.convert("RGBA").copy()


# ---------------------------------------------------------------------------
# Legacy standalone-frame helpers retained for callers outside Animation Studio.


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
        if not self.frames or self.frames[0].image is None:
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


def frames_to_sheet(frames: list[AnimationFrame], columns: int) -> Image.Image:
    available = [frame for frame in frames if frame.image is not None]
    if not available:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    cols = max(1, columns)
    width, height = available[0].image.size  # type: ignore[union-attr]
    rows = math.ceil(len(available) / cols)
    sheet = Image.new("RGBA", (width * cols, height * rows), (0, 0, 0, 0))
    for index, frame in enumerate(available):
        sheet.paste(frame.image, ((index % cols) * width, (index // cols) * height))
    return sheet


def export_gif(
    frames: list[AnimationFrame],
    path: str | Path,
    fps: int = 10,
    loop: bool = True,
) -> None:
    available = [frame for frame in frames if frame.image is not None]
    if not available:
        return
    base_ms = max(10, int(1000 / max(1, fps)))
    pil_frames = [frame.image.convert("RGBA") for frame in available]  # type: ignore[union-attr]
    durations = [base_ms * max(1, frame.duration_ticks) for frame in available]
    save_options = {
        "save_all": True,
        "append_images": pil_frames[1:],
        "duration": durations,
        "disposal": 2,
    }
    if loop:
        save_options["loop"] = 0
    pil_frames[0].save(str(path), **save_options)


def export_animation_metadata(
    doc: AnimationDocument,
    path: str | Path,
    columns: int,
) -> None:
    metadata = {
        "name": doc.name,
        "frame_width": doc.frame_size[0],
        "frame_height": doc.frame_size[1],
        "columns": columns,
        "frames": [
            {
                "index": index,
                "duration_ticks": frame.duration_ticks,
                "label": frame.label,
                "anchors": [
                    {"name": anchor.name, "x": anchor.x, "y": anchor.y}
                    for anchor in frame.anchors
                ],
                "pivot": list(frame.pivot) if frame.pivot is not None else None,
            }
            for index, frame in enumerate(doc.frames)
        ],
    }
    Path(path).write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def rotate_pixels_around_pivot(
    image: Image.Image,
    selected: set[tuple[int, int]],
    pivot: tuple[int, int],
    angle_degrees: float,
) -> Image.Image:
    result = image.copy()
    if not selected:
        return result
    radians = math.radians(angle_degrees)
    cos_angle = math.cos(radians)
    sin_angle = math.sin(radians)
    pivot_x, pivot_y = pivot
    for source_x, source_y in selected:
        result.putpixel((source_x, source_y), (0, 0, 0, 0))
    for source_x, source_y in selected:
        color = image.getpixel((source_x, source_y))
        delta_x = source_x - pivot_x
        delta_y = source_y - pivot_y
        target_x = round(pivot_x + delta_x * cos_angle - delta_y * sin_angle)
        target_y = round(pivot_y + delta_x * sin_angle + delta_y * cos_angle)
        if 0 <= target_x < result.width and 0 <= target_y < result.height:
            result.putpixel((target_x, target_y), color)
    return result
