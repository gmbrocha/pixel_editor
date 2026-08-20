from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from src.core.animation_document import (
    AnchorPoint,
    AnimationProject,
    FrameSequenceSpec,
    create_animation_project_from_sheet,
)

PACKAGE_KIND = "pixel-forge-3d-animation"
PACKAGE_SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_DIRECTIONS = 16
MAX_FRAMES_PER_DIRECTION = 1024
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class Animation3DPackageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PackageAnchor:
    name: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class PackageFrame:
    index: int
    source_time: float
    visible_path: Path
    regions_path: Path
    silhouette_path: Path
    anchors_path: Path
    depth_path: Path | None
    anchors: tuple[PackageAnchor, ...]


@dataclass(frozen=True, slots=True)
class PackageDirection:
    id: str
    name: str
    frames: tuple[PackageFrame, ...]


@dataclass(frozen=True, slots=True)
class Animation3DPackage:
    root: Path
    name: str
    animation: str
    frame_size: tuple[int, int]
    fps: int
    playback_mode: str
    region_colors: dict[str, tuple[int, int, int, int]]
    directions: tuple[PackageDirection, ...]
    manifest: dict

    @property
    def frame_count(self) -> int:
        return sum(len(direction.frames) for direction in self.directions)


def load_animation_3d_package(path: str | Path) -> Animation3DPackage:
    """Load and strictly validate a Blender/3D animation interchange directory."""

    selected = Path(path).expanduser()
    root = selected.parent if selected.is_file() else selected
    manifest_path = selected if selected.is_file() else root / "manifest.json"
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    if manifest_path.parent != root:
        raise Animation3DPackageError("Package manifest must be at the package root.")
    if not manifest_path.is_file():
        raise Animation3DPackageError(
            f"3D animation package is missing {manifest_path.name}."
        )
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise Animation3DPackageError("3D animation package manifest is too large.")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Animation3DPackageError(f"Could not read package manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise Animation3DPackageError("Package manifest must be a JSON object.")
    if data.get("kind") != PACKAGE_KIND:
        raise Animation3DPackageError(
            f"Unsupported package kind: {data.get('kind')!r}."
        )
    if data.get("schemaVersion") != PACKAGE_SCHEMA_VERSION:
        raise Animation3DPackageError(
            f"Unsupported 3D package schema: {data.get('schemaVersion')!r}."
        )

    name = _required_text(data, "name")
    animation = _required_identifier(data, "animation")
    frame_size = _size(data.get("frameSize"), "frameSize")
    fps = _bounded_int(data.get("fps", 8), "fps", 1, 60)
    playback_mode = str(data.get("playbackMode", "loop"))
    if playback_mode not in {"once", "loop", "ping_pong"}:
        raise Animation3DPackageError(
            f"Invalid package playbackMode: {playback_mode!r}."
        )
    region_colors = _region_palette(data.get("regions"))
    checksums = _checksums(data.get("checksums", {}))

    raw_directions = data.get("directions")
    if not isinstance(raw_directions, list) or not raw_directions:
        raise Animation3DPackageError("Package directions must be a non-empty list.")
    if len(raw_directions) > MAX_DIRECTIONS:
        raise Animation3DPackageError(
            f"Package supports at most {MAX_DIRECTIONS} directions."
        )

    directions: list[PackageDirection] = []
    direction_ids: set[str] = set()
    direction_names: set[str] = set()
    referenced_paths: set[str] = set()
    for raw_direction in raw_directions:
        if not isinstance(raw_direction, dict):
            raise Animation3DPackageError("Each package direction must be an object.")
        direction_id = _required_identifier(raw_direction, "id")
        direction_name = _required_text(raw_direction, "name")
        if direction_id in direction_ids:
            raise Animation3DPackageError(
                f"Duplicate package direction ID: {direction_id}."
            )
        if direction_name.casefold() in direction_names:
            raise Animation3DPackageError(
                f"Duplicate package direction name: {direction_name}."
            )
        direction_ids.add(direction_id)
        direction_names.add(direction_name.casefold())

        raw_frames = raw_direction.get("frames")
        if not isinstance(raw_frames, list) or not raw_frames:
            raise Animation3DPackageError(
                f"Direction {direction_id!r} must contain frames."
            )
        if len(raw_frames) > MAX_FRAMES_PER_DIRECTION:
            raise Animation3DPackageError(
                f"Direction {direction_id!r} exceeds the frame limit."
            )
        frames: list[PackageFrame] = []
        for expected_index, raw_frame in enumerate(raw_frames):
            if not isinstance(raw_frame, dict):
                raise Animation3DPackageError(
                    f"Direction {direction_id!r} contains an invalid frame."
                )
            index = _bounded_int(
                raw_frame.get("index"), "frame index", 0, MAX_FRAMES_PER_DIRECTION - 1
            )
            if index != expected_index:
                raise Animation3DPackageError(
                    f"Direction {direction_id!r} frame indexes must be consecutive "
                    f"from zero; expected {expected_index}, found {index}."
                )
            source_time = _finite_number(
                raw_frame.get("sourceTime", index / len(raw_frames)), "sourceTime"
            )
            if source_time < 0:
                raise Animation3DPackageError("Frame sourceTime cannot be negative.")

            visible_path, visible_relative = _asset_path(
                root, raw_frame.get("visible"), "visible"
            )
            regions_path, regions_relative = _asset_path(
                root, raw_frame.get("regions"), "regions"
            )
            silhouette_path, silhouette_relative = _asset_path(
                root, raw_frame.get("silhouette"), "silhouette"
            )
            anchors_path, anchors_relative = _asset_path(
                root, raw_frame.get("anchors"), "anchors"
            )
            depth_value = raw_frame.get("depth")
            depth_path: Path | None = None
            depth_relative: str | None = None
            if depth_value is not None:
                depth_path, depth_relative = _asset_path(root, depth_value, "depth")

            relative_assets = [
                visible_relative,
                regions_relative,
                silhouette_relative,
                anchors_relative,
            ]
            if depth_relative is not None:
                relative_assets.append(depth_relative)
            duplicates = referenced_paths.intersection(relative_assets)
            if duplicates:
                raise Animation3DPackageError(
                    "Package assets may not be reused between frames: "
                    + ", ".join(sorted(duplicates))
                )
            referenced_paths.update(relative_assets)

            for relative, asset_path in zip(
                relative_assets,
                [
                    visible_path,
                    regions_path,
                    silhouette_path,
                    anchors_path,
                    *([depth_path] if depth_path is not None else []),
                ],
                strict=True,
            ):
                expected_digest = checksums.get(relative)
                if expected_digest is not None:
                    actual_digest = _sha256(asset_path)
                    if actual_digest != expected_digest:
                        raise Animation3DPackageError(
                            f"Checksum mismatch for package asset {relative}."
                        )

            visible = _load_rgba(visible_path, frame_size, "visible")
            region_image = _load_rgba(regions_path, frame_size, "region")
            silhouette = _load_rgba(silhouette_path, frame_size, "silhouette")
            if depth_path is not None:
                _validate_image_size(depth_path, frame_size, "depth")
            _validate_region_image(region_image, region_colors, regions_relative)
            _validate_silhouette(region_image, silhouette, region_colors)
            anchors = _load_anchors(anchors_path, frame_size)
            # Force image decoding before the context-free package object is returned.
            visible.load()
            frames.append(
                PackageFrame(
                    index=index,
                    source_time=source_time,
                    visible_path=visible_path,
                    regions_path=regions_path,
                    silhouette_path=silhouette_path,
                    anchors_path=anchors_path,
                    depth_path=depth_path,
                    anchors=anchors,
                )
            )
        directions.append(
            PackageDirection(direction_id, direction_name, tuple(frames))
        )

    unknown_checksums = set(checksums) - referenced_paths
    if unknown_checksums:
        raise Animation3DPackageError(
            "Checksums reference assets that are not used by any frame: "
            + ", ".join(sorted(unknown_checksums))
        )

    return Animation3DPackage(
        root=root,
        name=name,
        animation=animation,
        frame_size=frame_size,
        fps=fps,
        playback_mode=playback_mode,
        region_colors=region_colors,
        directions=tuple(directions),
        manifest=data,
    )


def create_animation_project_from_3d_package(
    package: Animation3DPackage,
    *,
    palette: list[tuple[int, int, int, int]] | None = None,
) -> AnimationProject:
    """Create an editable linked-sheet project from validated visible frames."""

    frame_width, frame_height = package.frame_size
    max_frames = max(len(direction.frames) for direction in package.directions)
    sheet = Image.new(
        "RGBA",
        (frame_width * max_frames, frame_height * len(package.directions)),
        (0, 0, 0, 0),
    )
    loaded_frames: dict[tuple[int, int], Image.Image] = {}
    for row, direction in enumerate(package.directions):
        for column, frame in enumerate(direction.frames):
            image = _load_rgba(frame.visible_path, package.frame_size, "visible")
            loaded_frames[(row, column)] = image
            sheet.paste(image, (column * frame_width, row * frame_height))

    project = create_animation_project_from_sheet(
        sheet,
        name=f"{package.name}-{package.animation}",
        frame_size=package.frame_size,
        fps=package.fps,
        playback_mode=package.playback_mode,
        palette=palette,
        source_path=str(package.root),
    )
    for row, direction in enumerate(package.directions):
        track = project.add_track(
            direction.name,
            FrameSequenceSpec(
                origin_x=0,
                origin_y=row * frame_height,
                frame_width=frame_width,
                frame_height=frame_height,
                count=len(direction.frames),
                step_x=frame_width,
                step_y=0,
            ),
        )
        for project_frame, package_frame in zip(
            track.frames, direction.frames, strict=True
        ):
            project_frame.label = f"3D phase {package_frame.source_time:g}"
            project_frame.anchors = [
                AnchorPoint(anchor.name, _round_pixel(anchor.x), _round_pixel(anchor.y))
                for anchor in package_frame.anchors
            ]
    return project


def package_summary(package: Animation3DPackage) -> str:
    depth_count = sum(
        frame.depth_path is not None
        for direction in package.directions
        for frame in direction.frames
    )
    return (
        f"{package.name} / {package.animation}: {len(package.directions)} directions, "
        f"{package.frame_count} frames at {package.frame_size[0]}x{package.frame_size[1]}, "
        f"{len(package.region_colors)} regions, {depth_count} depth passes"
    )


def _required_text(data: dict, field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise Animation3DPackageError(f"Package {field} must be non-empty text.")
    return value.strip()


def _required_identifier(data: dict, field: str) -> str:
    value = _required_text(data, field).casefold()
    if not _IDENTIFIER.fullmatch(value):
        raise Animation3DPackageError(
            f"Package {field} must be a lowercase identifier; found {value!r}."
        )
    return value


def _bounded_int(value: object, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise Animation3DPackageError(f"Package {field} must be an integer.")
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise Animation3DPackageError(f"Package {field} must be an integer.") from exc
    if result < minimum or result > maximum:
        raise Animation3DPackageError(
            f"Package {field} must be between {minimum} and {maximum}."
        )
    return result


def _size(value: object, field: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise Animation3DPackageError(f"Package {field} must be [width, height].")
    return (
        _bounded_int(value[0], f"{field} width", 1, 4096),
        _bounded_int(value[1], f"{field} height", 1, 4096),
    )


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise Animation3DPackageError(f"Package {field} must be numeric.")
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise Animation3DPackageError(f"Package {field} must be numeric.") from exc
    if not math.isfinite(result):
        raise Animation3DPackageError(f"Package {field} must be finite.")
    return result


def _region_palette(value: object) -> dict[str, tuple[int, int, int, int]]:
    if not isinstance(value, dict) or not value:
        raise Animation3DPackageError("Package regions must be a non-empty object.")
    result: dict[str, tuple[int, int, int, int]] = {}
    used_colors: set[tuple[int, int, int, int]] = set()
    for raw_name, raw_color in value.items():
        name = str(raw_name).casefold()
        if not _IDENTIFIER.fullmatch(name):
            raise Animation3DPackageError(f"Invalid package region name: {raw_name!r}.")
        if not isinstance(raw_color, list) or len(raw_color) != 4:
            raise Animation3DPackageError(
                f"Region {name!r} must use an [R, G, B, A] color."
            )
        color = tuple(
            _bounded_int(channel, f"region {name} channel", 0, 255)
            for channel in raw_color
        )
        if color in used_colors:
            raise Animation3DPackageError("Package region colors must be unique.")
        result[name] = color  # type: ignore[assignment]
        used_colors.add(color)  # type: ignore[arg-type]
    background = result.get("background")
    if background is None or background[3] != 0:
        raise Animation3DPackageError(
            "Package regions must define a fully transparent background color."
        )
    return result


def _checksums(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise Animation3DPackageError("Package checksums must be an object.")
    result: dict[str, str] = {}
    for raw_path, raw_digest in value.items():
        path = str(raw_path).replace("\\", "/")
        digest = str(raw_digest).casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise Animation3DPackageError(f"Invalid checksum for {path!r}.")
        result[path] = digest
    return result


def _asset_path(root: Path, value: object, field: str) -> tuple[Path, str]:
    if not isinstance(value, str) or not value.strip():
        raise Animation3DPackageError(f"Frame {field} path must be non-empty text.")
    relative = value.replace("\\", "/")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise Animation3DPackageError(
            f"Frame {field} path escapes the package root: {value!r}."
        ) from exc
    normalized = candidate.relative_to(root).as_posix()
    if normalized != relative.lstrip("./"):
        raise Animation3DPackageError(
            f"Frame {field} path is not canonical: {value!r}."
        )
    if not candidate.is_file():
        raise Animation3DPackageError(f"Package asset does not exist: {normalized}.")
    return candidate, normalized


def _load_rgba(path: Path, size: tuple[int, int], role: str) -> Image.Image:
    try:
        with Image.open(path) as opened:
            if opened.size != size:
                raise Animation3DPackageError(
                    f"Package {role} image {path.name} is {opened.width}x{opened.height}; "
                    f"expected {size[0]}x{size[1]}."
                )
            return opened.convert("RGBA").copy()
    except Animation3DPackageError:
        raise
    except (OSError, ValueError) as exc:
        raise Animation3DPackageError(
            f"Could not open package {role} image {path.name}: {exc}"
        ) from exc


def _validate_image_size(path: Path, size: tuple[int, int], role: str) -> None:
    try:
        with Image.open(path) as opened:
            if opened.size != size:
                raise Animation3DPackageError(
                    f"Package {role} image {path.name} is {opened.width}x{opened.height}; "
                    f"expected {size[0]}x{size[1]}."
                )
            opened.load()
    except Animation3DPackageError:
        raise
    except (OSError, ValueError) as exc:
        raise Animation3DPackageError(
            f"Could not open package {role} image {path.name}: {exc}"
        ) from exc


def _validate_region_image(
    image: Image.Image,
    region_colors: dict[str, tuple[int, int, int, int]],
    relative_path: str,
) -> None:
    allowed = set(region_colors.values())
    unknown = set(image.get_flattened_data()) - allowed
    if unknown:
        sample = sorted(unknown)[:4]
        raise Animation3DPackageError(
            f"Region map {relative_path} contains unknown RGBA colors: {sample}."
        )


def _validate_silhouette(
    regions: Image.Image,
    silhouette: Image.Image,
    region_colors: dict[str, tuple[int, int, int, int]],
) -> None:
    background = region_colors["background"]
    for region_pixel, silhouette_pixel in zip(
        regions.get_flattened_data(),
        silhouette.get_flattened_data(),
        strict=True,
    ):
        occupied = region_pixel != background
        silhouette_occupied = silhouette_pixel[3] > 0
        if occupied != silhouette_occupied:
            raise Animation3DPackageError(
                "Package silhouette occupancy does not match its region map."
            )


def _load_anchors(
    path: Path, frame_size: tuple[int, int]
) -> tuple[PackageAnchor, ...]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Animation3DPackageError(f"Could not read anchors {path.name}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("anchors"), dict):
        raise Animation3DPackageError(
            f"Anchor file {path.name} must contain an anchors object."
        )
    anchors: list[PackageAnchor] = []
    width, height = frame_size
    for raw_name, raw_point in data["anchors"].items():
        name = str(raw_name).casefold()
        if not _IDENTIFIER.fullmatch(name):
            raise Animation3DPackageError(f"Invalid anchor name: {raw_name!r}.")
        if not isinstance(raw_point, list) or len(raw_point) != 2:
            raise Animation3DPackageError(
                f"Anchor {name!r} must contain [x, y] coordinates."
            )
        x = _finite_number(raw_point[0], f"anchor {name} x")
        y = _finite_number(raw_point[1], f"anchor {name} y")
        if not (-width <= x <= width * 2 and -height <= y <= height * 2):
            raise Animation3DPackageError(
                f"Anchor {name!r} is implausibly far outside the frame."
            )
        anchors.append(PackageAnchor(name, x, y))
    anchors.sort(key=lambda anchor: anchor.name)
    return tuple(anchors)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _round_pixel(value: float) -> int:
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)
