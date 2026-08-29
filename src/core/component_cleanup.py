"""Conservative preprocessing for editable Character Forge component sheets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
from PIL import Image


CARDINAL = ((-1, 0), (1, 0), (0, -1), (0, 1))
NEIGHBORS = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1), (0, 1),
    (1, -1), (1, 0), (1, 1),
)


@dataclass(frozen=True, slots=True)
class FrameCleanupReport:
    removed_islands: int = 0
    removed_island_pixels: int = 0
    chamfered_outline_pixels: int = 0
    removed_spurs: int = 0
    removed_spur_pixels: int = 0
    filled_holes: int = 0
    filled_hole_pixels: int = 0

    @property
    def changed_pixels(self) -> int:
        return (
            self.removed_island_pixels
            + self.chamfered_outline_pixels
            + self.removed_spur_pixels
            + self.filled_hole_pixels
        )

    def to_dict(self) -> dict[str, int]:
        result = asdict(self)
        result["changed_pixels"] = self.changed_pixels
        return result


@dataclass(frozen=True, slots=True)
class SheetCleanupReport:
    frame_size: tuple[int, int]
    frame_columns: int
    direction_rows: int
    frames_changed: int
    removed_islands: int
    removed_island_pixels: int
    chamfered_outline_pixels: int
    removed_spurs: int
    removed_spur_pixels: int
    filled_holes: int
    filled_hole_pixels: int
    frame_reports: tuple[dict[str, object], ...]

    @property
    def changed_pixels(self) -> int:
        return (
            self.removed_island_pixels
            + self.chamfered_outline_pixels
            + self.removed_spur_pixels
            + self.filled_hole_pixels
        )

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["frame_size"] = list(self.frame_size)
        result["changed_pixels"] = self.changed_pixels
        return result


def _components(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    height, width = mask.shape
    seen = np.zeros(mask.shape, dtype=bool)
    result: list[list[tuple[int, int]]] = []
    for start_y, start_x in zip(*np.nonzero(mask), strict=True):
        if seen[start_y, start_x]:
            continue
        seen[start_y, start_x] = True
        pending = [(int(start_y), int(start_x))]
        component: list[tuple[int, int]] = []
        while pending:
            y, x = pending.pop()
            component.append((y, x))
            for dy, dx in CARDINAL:
                next_y, next_x = y + dy, x + dx
                if (
                    0 <= next_y < height
                    and 0 <= next_x < width
                    and mask[next_y, next_x]
                    and not seen[next_y, next_x]
                ):
                    seen[next_y, next_x] = True
                    pending.append((next_y, next_x))
        result.append(component)
    return result


def _remove_detached_islands(
    pixels: np.ndarray,
    *,
    max_area: int,
    max_largest_ratio: float,
    max_nearby_gap: int,
    protected_components: int,
) -> tuple[int, int]:
    components = _components(pixels[..., 3] > 0)
    if len(components) <= protected_components:
        return 0, 0
    components.sort(key=len, reverse=True)
    largest = len(components[0])
    largest_y = [point[0] for point in components[0]]
    largest_x = [point[1] for point in components[0]]
    largest_bounds = (
        min(largest_x), max(largest_x), min(largest_y), max(largest_y)
    )
    removed = 0
    removed_pixels = 0
    for index, component in enumerate(components):
        if index < protected_components:
            continue
        area = len(component)
        ys = [point[0] for point in component]
        xs = [point[1] for point in component]
        bounds = (min(xs), max(xs), min(ys), max(ys))
        horizontal_gap = max(
            0,
            largest_bounds[0] - bounds[1] - 1,
            bounds[0] - largest_bounds[1] - 1,
        )
        vertical_gap = max(
            0,
            largest_bounds[2] - bounds[3] - 1,
            bounds[2] - largest_bounds[3] - 1,
        )
        nearby = max(horizontal_gap, vertical_gap) <= max_nearby_gap
        if area > max_area or (area >= largest * max_largest_ratio and nearby):
            continue
        for y, x in component:
            pixels[y, x] = 0
        removed += 1
        removed_pixels += area
    return removed, removed_pixels


def _convex_outline_corners(
    pixels: np.ndarray,
    outline_rgb: tuple[int, int, int],
) -> np.ndarray:
    alpha = pixels[..., 3] > 0
    outline = alpha & np.all(
        pixels[..., :3] == np.asarray(outline_rgb, dtype=np.uint8), axis=2
    )
    padded = np.pad(alpha, 1)
    north = padded[:-2, 1:-1]
    south = padded[2:, 1:-1]
    west = padded[1:-1, :-2]
    east = padded[1:-1, 2:]
    northwest = padded[:-2, :-2]
    northeast = padded[:-2, 2:]
    southwest = padded[2:, :-2]
    southeast = padded[2:, 2:]
    return outline & (
        (north & east & northeast & ~south & ~west)
        | (east & south & southeast & ~north & ~west)
        | (south & west & southwest & ~north & ~east)
        | (west & north & northwest & ~south & ~east)
    )


def _remove_terminal_spurs(
    pixels: np.ndarray,
    *,
    max_length: int,
) -> tuple[int, int]:
    """Remove short one-pixel-wide stems attached to a broad silhouette edge."""

    if max_length not in {1, 2}:
        raise ValueError("Terminal-spur removal supports a length of one or two pixels")
    alpha = pixels[..., 3] > 0
    height, width = alpha.shape
    remove = np.zeros(alpha.shape, dtype=bool)
    spurs: set[tuple[tuple[int, int], ...]] = set()

    def opaque(y: int, x: int) -> bool:
        return 0 <= y < height and 0 <= x < width and bool(alpha[y, x])

    for tip_y, tip_x in zip(*np.nonzero(alpha), strict=True):
        tip_y, tip_x = int(tip_y), int(tip_x)
        for inward_y, inward_x in CARDINAL:
            side_y, side_x = -inward_x, inward_y
            for length in range(1, max_length + 1):
                chain = tuple(
                    (tip_y + step * inward_y, tip_x + step * inward_x)
                    for step in range(length)
                )
                base_y = tip_y + length * inward_y
                base_x = tip_x + length * inward_x
                if not all(opaque(y, x) for y, x in chain):
                    continue
                if not opaque(base_y, base_x):
                    continue
                if opaque(tip_y - inward_y, tip_x - inward_x):
                    continue
                if any(
                    opaque(y + side_y, x + side_x)
                    or opaque(y - side_y, x - side_x)
                    for y, x in chain
                ):
                    continue
                if not (
                    opaque(base_y + side_y, base_x + side_x)
                    and opaque(base_y - side_y, base_x - side_x)
                ):
                    continue
                if not (
                    opaque(base_y + 2 * side_y, base_x + 2 * side_x)
                    or opaque(base_y - 2 * side_y, base_x - 2 * side_x)
                ):
                    continue
                spurs.add(chain)

    for chain in spurs:
        for y, x in chain:
            remove[y, x] = True
    removed_pixels = int(np.count_nonzero(remove))
    pixels[remove] = 0
    return len(spurs), removed_pixels


def _fill_color(
    pixels: np.ndarray,
    component: Iterable[tuple[int, int]],
    palette: tuple[tuple[int, int, int], ...],
) -> tuple[int, int, int]:
    height, width = pixels.shape[:2]
    counts: dict[tuple[int, int, int], int] = {}
    for y, x in component:
        for dy, dx in NEIGHBORS:
            next_y, next_x = y + dy, x + dx
            if not (0 <= next_y < height and 0 <= next_x < width):
                continue
            if pixels[next_y, next_x, 3] == 0:
                continue
            color = tuple(int(value) for value in pixels[next_y, next_x, :3])
            counts[color] = counts.get(color, 0) + 1
    if not counts:
        return palette[0]
    palette_order = {color: index for index, color in enumerate(palette)}
    return min(
        counts,
        key=lambda color: (-counts[color], palette_order.get(color, len(palette)), color),
    )


def _fill_tiny_holes(
    pixels: np.ndarray,
    *,
    palette: tuple[tuple[int, int, int], ...],
    max_area: int,
) -> tuple[int, int]:
    if max_area not in {1, 2}:
        raise ValueError("Tiny-hole filling supports an area of one or two pixels")
    transparent = pixels[..., 3] == 0
    height, width = transparent.shape
    holes: list[list[tuple[int, int]]] = []
    padded = np.pad(transparent, 1)
    north = padded[:-2, 1:-1]
    south = padded[2:, 1:-1]
    west = padded[1:-1, :-2]
    east = padded[1:-1, 2:]
    neighbor_count = (
        north.astype(np.uint8)
        + south.astype(np.uint8)
        + west.astype(np.uint8)
        + east.astype(np.uint8)
    )
    interior = np.zeros(transparent.shape, dtype=bool)
    interior[1:-1, 1:-1] = True
    singles = transparent & interior & (neighbor_count == 0)
    holes.extend(
        [[(int(y), int(x))] for y, x in zip(*np.nonzero(singles), strict=True)]
    )
    if max_area == 2:
        horizontal = (
            transparent[:, :-1]
            & transparent[:, 1:]
            & interior[:, :-1]
            & interior[:, 1:]
            & (neighbor_count[:, :-1] == 1)
            & (neighbor_count[:, 1:] == 1)
        )
        holes.extend(
            [[(int(y), int(x)), (int(y), int(x + 1))]
             for y, x in zip(*np.nonzero(horizontal), strict=True)]
        )
        vertical = (
            transparent[:-1, :]
            & transparent[1:, :]
            & interior[:-1, :]
            & interior[1:, :]
            & (neighbor_count[:-1, :] == 1)
            & (neighbor_count[1:, :] == 1)
        )
        holes.extend(
            [[(int(y), int(x)), (int(y + 1), int(x))]
             for y, x in zip(*np.nonzero(vertical), strict=True)]
        )

    filled = 0
    filled_pixels = 0
    for component in holes:
        color = _fill_color(pixels, component, palette)
        for y, x in component:
            pixels[y, x, :3] = color
            pixels[y, x, 3] = 255
        filled += 1
        filled_pixels += len(component)
    return filled, filled_pixels


def cleanup_component_frame(
    frame: Image.Image,
    *,
    outline_rgb: tuple[int, int, int],
    palette: tuple[tuple[int, int, int], ...],
    max_island_area: int = 16,
    max_island_ratio: float = 0.20,
    max_nearby_island_gap: int = 6,
    max_hole_area: int = 2,
    max_spur_length: int = 2,
    protected_components: int = 1,
) -> tuple[Image.Image, FrameCleanupReport]:
    """Clean one component-only frame without inventing new silhouette art."""

    pixels = np.array(frame.convert("RGBA"), dtype=np.uint8)
    removed, removed_pixels = _remove_detached_islands(
        pixels,
        max_area=max_island_area,
        max_largest_ratio=max_island_ratio,
        max_nearby_gap=max_nearby_island_gap,
        protected_components=protected_components,
    )
    corners = _convex_outline_corners(pixels, outline_rgb)
    chamfered = int(np.count_nonzero(corners))
    pixels[corners] = 0
    # Chamfering can expose a speck that was cardinally attached only through a
    # removable corner. Sweep islands once more without applying another
    # outline pass, so the cleanup is strict without thinning borders twice.
    post_removed, post_removed_pixels = _remove_detached_islands(
        pixels,
        max_area=max_island_area,
        max_largest_ratio=max_island_ratio,
        max_nearby_gap=max_nearby_island_gap,
        protected_components=protected_components,
    )
    removed += post_removed
    removed_pixels += post_removed_pixels
    removed_spurs, removed_spur_pixels = _remove_terminal_spurs(
        pixels, max_length=max_spur_length
    )
    filled, filled_pixels = _fill_tiny_holes(
        pixels, palette=palette, max_area=max_hole_area
    )
    pixels[pixels[..., 3] == 0] = 0
    return Image.fromarray(pixels, "RGBA"), FrameCleanupReport(
        removed_islands=removed,
        removed_island_pixels=removed_pixels,
        chamfered_outline_pixels=chamfered,
        removed_spurs=removed_spurs,
        removed_spur_pixels=removed_spur_pixels,
        filled_holes=filled,
        filled_hole_pixels=filled_pixels,
    )


def cleanup_component_sheet(
    sheet: Image.Image,
    *,
    outline_rgb: tuple[int, int, int],
    palette: tuple[tuple[int, int, int], ...],
    frame_size: tuple[int, int] = (128, 128),
    direction_rows: int = 4,
    max_island_area: int = 16,
    max_island_ratio: float = 0.20,
    max_nearby_island_gap: int = 6,
    max_hole_area: int = 2,
    max_spur_length: int = 2,
    protected_components: int = 1,
) -> tuple[Image.Image, SheetCleanupReport]:
    source = sheet.convert("RGBA")
    frame_width, frame_height = frame_size
    if source.width % frame_width or source.height != frame_height * direction_rows:
        raise ValueError(
            f"Component sheet {source.size} does not match {frame_size} cells "
            f"and {direction_rows} direction rows"
        )
    columns = source.width // frame_width
    output = Image.new("RGBA", source.size, (0, 0, 0, 0))
    reports: list[dict[str, object]] = []
    totals = {
        "removed_islands": 0,
        "removed_island_pixels": 0,
        "chamfered_outline_pixels": 0,
        "removed_spurs": 0,
        "removed_spur_pixels": 0,
        "filled_holes": 0,
        "filled_hole_pixels": 0,
    }
    for row in range(direction_rows):
        for column in range(columns):
            box = (
                column * frame_width,
                row * frame_height,
                (column + 1) * frame_width,
                (row + 1) * frame_height,
            )
            cleaned, report = cleanup_component_frame(
                source.crop(box),
                outline_rgb=outline_rgb,
                palette=palette,
                max_island_area=max_island_area,
                max_island_ratio=max_island_ratio,
                max_nearby_island_gap=max_nearby_island_gap,
                max_hole_area=max_hole_area,
                max_spur_length=max_spur_length,
                protected_components=protected_components,
            )
            output.paste(cleaned, box[:2])
            report_data = report.to_dict()
            if report.changed_pixels:
                reports.append({"row": row, "column": column, **report_data})
            for key in totals:
                totals[key] += int(report_data[key])
    return output, SheetCleanupReport(
        frame_size=frame_size,
        frame_columns=columns,
        direction_rows=direction_rows,
        frames_changed=len(reports),
        frame_reports=tuple(reports),
        **totals,
    )
