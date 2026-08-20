from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np
from PIL import Image
from skimage.measure import label as connected_component_labels

from src.core.palette import lab_distance, rgb_to_lab


_PIL_RESAMPLING = {
    "Nearest": Image.Resampling.NEAREST,
    "Nearest Neighbor": Image.Resampling.NEAREST,
    "Bilinear": Image.Resampling.BILINEAR,
    "Bicubic": Image.Resampling.BICUBIC,
}


def resize_image(
    image: Image.Image,
    size: tuple[int, int],
    method: str,
) -> Image.Image:
    """Resize an image with one of PixelForge's supported sampling methods.

    The established Pillow paths are intentionally retained for the original
    three methods. The custom filters operate on premultiplied RGBA data so
    RGB hidden beneath transparent pixels cannot bleed into visible edges.
    """
    width, height = (int(size[0]), int(size[1]))
    if width < 1 or height < 1:
        raise ValueError("Resize dimensions must be positive")
    if method in _PIL_RESAMPLING:
        return image.resize((width, height), _PIL_RESAMPLING[method])
    if method == "Area (Box Average)":
        return area_resize(image, (width, height))
    if method == "Lanczos 3":
        return lanczos3_resize(image, (width, height))
    raise ValueError(f"Unknown resize sampling method: {method}")


def area_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """True area-overlap resampling, including fractional source coverage."""
    rgba = image.convert("RGBA")
    if rgba.size == size:
        return rgba.copy()
    samples = _to_premultiplied(rgba)
    x_contributions = _area_contributions(rgba.width, size[0])
    y_contributions = _area_contributions(rgba.height, size[1])
    resized = _resample_separable(samples, x_contributions, y_contributions)
    return _from_premultiplied(resized)


def lanczos3_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Separable radius-three Lanczos with a scale-aware downsample kernel."""
    rgba = image.convert("RGBA")
    if rgba.size == size:
        return rgba.copy()
    samples = _to_premultiplied(rgba)
    x_contributions = _lanczos_contributions(rgba.width, size[0])
    y_contributions = _lanczos_contributions(rgba.height, size[1])
    resized = _resample_separable(samples, x_contributions, y_contributions)
    return _from_premultiplied(resized)


def edge_preserving_denoise(
    image: Image.Image,
    *,
    radius: int = 1,
    strength: int | float = 35,
) -> Image.Image:
    """Apply a mild bilateral filter and blend it with the source image."""
    radius = max(1, min(3, int(radius)))
    blend = max(0.0, min(1.0, float(strength) / 100.0))
    source = image.convert("RGBA")
    if blend <= 0.0:
        return source.copy()

    premultiplied = _to_premultiplied(source)
    alpha = premultiplied[..., 3:4]
    straight = np.zeros_like(premultiplied[..., :3])
    np.divide(
        premultiplied[..., :3],
        alpha,
        out=straight,
        where=alpha > 1e-12,
    )
    features = np.concatenate((straight * 255.0, alpha * 255.0), axis=2)

    pad = radius
    padded_values = np.pad(premultiplied, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
    padded_features = np.pad(features, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
    height, width = source.height, source.width
    weighted = np.zeros_like(premultiplied)
    weight_sum = np.zeros((height, width, 1), dtype=np.float64)
    spatial_sigma = max(0.8, radius * 0.8)
    color_sigma = 32.0

    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            neighbor = padded_values[
                pad + dy : pad + dy + height,
                pad + dx : pad + dx + width,
            ]
            neighbor_features = padded_features[
                pad + dy : pad + dy + height,
                pad + dx : pad + dx + width,
            ]
            spatial_weight = math.exp(
                -(dx * dx + dy * dy) / (2.0 * spatial_sigma * spatial_sigma)
            )
            feature_delta = neighbor_features - features
            range_weight = np.exp(
                -np.sum(feature_delta * feature_delta, axis=2, keepdims=True)
                / (2.0 * color_sigma * color_sigma)
            )
            weight = spatial_weight * range_weight
            weighted += neighbor * weight
            weight_sum += weight

    filtered = weighted / np.maximum(weight_sum, 1e-12)
    result = premultiplied * (1.0 - blend) + filtered * blend
    return _from_premultiplied(result)


@dataclass(slots=True)
class _ComponentGraph:
    labels: np.ndarray
    colors: np.ndarray
    areas: np.ndarray
    bounds: np.ndarray
    boundary_pairs: np.ndarray
    boundary_counts: np.ndarray


def cluster_cleanup(image: Image.Image, *, threshold: int = 3) -> Image.Image:
    """Merge tiny exact-color components into structurally adjacent regions.

    Components use four-way connectivity. All merge choices are derived from
    the original component graph and rendered together, so output does not
    depend on component traversal or mutation order.
    """
    source = image.convert("RGBA")
    width, height = source.size
    if width == 0 or height == 0:
        return source.copy()
    threshold = max(1, int(threshold))
    raw = np.asarray(source, dtype=np.uint8)
    graph = _build_component_graph(raw)
    resolved_colors = graph.colors.copy()
    lab_cache: dict[tuple[int, int, int], tuple[float, float, float]] = {}

    def color_lab(color: tuple[int, int, int, int]) -> tuple[float, float, float]:
        rgb = color[:3]
        if rgb not in lab_cache:
            lab_cache[rgb] = rgb_to_lab(*rgb)
        return lab_cache[rgb]

    best_targets = np.full(len(graph.colors), -1, dtype=np.int32)
    best_scores: list[tuple[int, float, int, int] | None] = [None] * len(
        graph.colors
    )

    def consider_target(
        component_id: int, neighbor_id: int, shared_boundary: int
    ) -> None:
        color = tuple(int(value) for value in graph.colors[component_id])
        neighbor_color = tuple(int(value) for value in graph.colors[neighbor_id])
        if graph.areas[component_id] > threshold or color[3] == 0:
            return
        if neighbor_color[3] == 0 or neighbor_color[3] != color[3]:
            return
        score = (
            -shared_boundary,
            lab_distance(color_lab(color), color_lab(neighbor_color)),
            -int(graph.areas[neighbor_id]),
            neighbor_id,
        )
        current = best_scores[component_id]
        if current is None or score < current:
            best_scores[component_id] = score
            best_targets[component_id] = neighbor_id

    for pair, boundary_count in zip(
        graph.boundary_pairs, graph.boundary_counts, strict=True
    ):
        first, second = int(pair[0]), int(pair[1])
        count = int(boundary_count)
        consider_target(first, second, count)
        consider_target(second, first, count)

    selected = np.flatnonzero(best_targets >= 0)
    resolved_colors[selected] = graph.colors[best_targets[selected]]
    output = resolved_colors[graph.labels]
    return Image.fromarray(output.astype(np.uint8, copy=False), mode="RGBA")


def macro_pixels_2x2(image: Image.Image) -> Image.Image:
    """Render every complete two-by-two cell as one indivisible macro pixel.

    The most frequent exact RGBA value in each cell wins. Ties use the first
    value in row-major order. An unmatched final row or column is preserved so
    processing never crops, pads, or resizes the image.
    """
    source = image.convert("RGBA")
    width, height = source.size
    full_width = width - width % 2
    full_height = height - height % 2
    if full_width == 0 or full_height == 0:
        return source.copy()

    raw = np.asarray(source, dtype=np.uint8)
    output = raw.copy()
    block_rows = full_height // 2
    block_columns = full_width // 2
    blocks = (
        raw[:full_height, :full_width]
        .reshape(block_rows, 2, block_columns, 2, 4)
        .transpose(0, 2, 1, 3, 4)
        .reshape(-1, 4, 4)
    )
    matches = np.all(blocks[:, :, None, :] == blocks[:, None, :, :], axis=3)
    winner_indices = np.argmax(matches.sum(axis=2), axis=1)
    winners = blocks[np.arange(len(blocks)), winner_indices]
    macro_pixels = winners.reshape(block_rows, block_columns, 4)
    output[:full_height, :full_width] = macro_pixels.repeat(2, axis=0).repeat(
        2, axis=1
    )
    return Image.fromarray(output, mode="RGBA")


def _build_component_graph(raw: np.ndarray) -> _ComponentGraph:
    height, width = raw.shape[:2]
    encoded = (
        (raw[..., 0].astype(np.uint32) << 24)
        | (raw[..., 1].astype(np.uint32) << 16)
        | (raw[..., 2].astype(np.uint32) << 8)
        | raw[..., 3].astype(np.uint32)
    )
    labels = connected_component_labels(
        encoded, background=-1, connectivity=1
    ).astype(np.int32) - 1
    flat_labels = labels.reshape(-1)
    component_count = int(flat_labels.max()) + 1
    areas = np.bincount(flat_labels, minlength=component_count)

    pixel_indices = np.arange(flat_labels.size, dtype=np.int64)
    first_indices = np.full(component_count, flat_labels.size, dtype=np.int64)
    np.minimum.at(first_indices, flat_labels, pixel_indices)
    colors = raw.reshape(-1, 4)[first_indices].copy()

    x_coordinates = np.tile(np.arange(width, dtype=np.int32), height)
    y_coordinates = np.repeat(np.arange(height, dtype=np.int32), width)
    left = np.full(component_count, width, dtype=np.int32)
    top = np.full(component_count, height, dtype=np.int32)
    right = np.full(component_count, -1, dtype=np.int32)
    bottom = np.full(component_count, -1, dtype=np.int32)
    np.minimum.at(left, flat_labels, x_coordinates)
    np.minimum.at(top, flat_labels, y_coordinates)
    np.maximum.at(right, flat_labels, x_coordinates)
    np.maximum.at(bottom, flat_labels, y_coordinates)
    bounds = np.column_stack((left, top, right + 1, bottom + 1))

    boundaries: list[np.ndarray] = []
    for first, second in (
        (labels[:, :-1], labels[:, 1:]),
        (labels[:-1, :], labels[1:, :]),
    ):
        different = first != second
        if np.any(different):
            pairs = np.column_stack((first[different], second[different]))
            pairs.sort(axis=1)
            boundaries.append(pairs)
    if boundaries:
        boundary_pairs, boundary_counts = np.unique(
            np.concatenate(boundaries), axis=0, return_counts=True
        )
    else:
        boundary_pairs = np.empty((0, 2), dtype=np.int32)
        boundary_counts = np.empty(0, dtype=np.int64)

    return _ComponentGraph(
        labels=labels,
        colors=colors,
        areas=areas,
        bounds=bounds,
        boundary_pairs=boundary_pairs,
        boundary_counts=boundary_counts,
    )


def despeckle(
    image: Image.Image,
    *,
    max_speck_size: int = 1,
    color_tolerance: int | float = 24,
) -> Image.Image:
    """Conservatively replace small, coherently surrounded color clusters."""
    max_speck_size = max(1, min(8, int(max_speck_size)))
    tolerance = max(0.0, min(441.0, float(color_tolerance)))
    source = image.convert("RGBA")
    raw = np.asarray(source, dtype=np.uint8)
    working = raw.copy()
    # Fully transparent RGB is deliberately ignored and cleared.
    working[working[..., 3] == 0, :3] = 0
    features = working.astype(np.float64)
    height, width = source.height, source.width

    if max_speck_size == 1:
        components = _isolated_components(features, tolerance)
    else:
        components = _small_color_components(features, tolerance, max_speck_size)

    replacements: list[tuple[list[tuple[int, int]], np.ndarray]] = []
    for component in components:
        replacement = _coherent_boundary_replacement(
            features,
            component,
            tolerance,
        )
        if replacement is not None:
            replacements.append((component, replacement))

    for component, replacement in replacements:
        value = np.clip(np.floor(replacement + 0.5), 0, 255).astype(np.uint8)
        if value[3] == 0:
            value[:3] = 0
        for x, y in component:
            working[y, x] = value
    return Image.fromarray(working, mode="RGBA")


def _to_premultiplied(image: Image.Image) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float64) / 255.0
    alpha = rgba[..., 3:4]
    rgba[..., :3] *= alpha
    return rgba


def _from_premultiplied(values: np.ndarray) -> Image.Image:
    alpha = np.clip(values[..., 3:4], 0.0, 1.0)
    premultiplied_rgb = np.clip(values[..., :3], 0.0, alpha)
    rgb = np.zeros_like(premultiplied_rgb)
    np.divide(premultiplied_rgb, alpha, out=rgb, where=alpha > 1e-12)
    rgba = np.concatenate((rgb, alpha), axis=2)
    output = np.clip(np.floor(rgba * 255.0 + 0.5), 0, 255).astype(np.uint8)
    output[output[..., 3] == 0, :3] = 0
    return Image.fromarray(output, mode="RGBA")


def _area_contributions(
    source_size: int,
    destination_size: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    scale = source_size / destination_size
    contributions: list[tuple[np.ndarray, np.ndarray]] = []
    for destination_index in range(destination_size):
        start = destination_index * scale
        end = (destination_index + 1) * scale
        first = max(0, int(math.floor(start)))
        last = min(source_size - 1, int(math.ceil(end) - 1))
        indices = np.arange(first, last + 1, dtype=np.intp)
        weights = np.minimum(end, indices + 1.0) - np.maximum(start, indices)
        weights = np.maximum(weights, 0.0)
        weights /= weights.sum()
        contributions.append((indices, weights))
    return contributions


def _lanczos_contributions(
    source_size: int,
    destination_size: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    scale = source_size / destination_size
    filter_scale = max(1.0, scale)
    support = 3.0 * filter_scale
    contributions: list[tuple[np.ndarray, np.ndarray]] = []
    for destination_index in range(destination_size):
        center = (destination_index + 0.5) * scale - 0.5
        first = max(0, int(math.floor(center - support + 1.0)))
        last = min(source_size - 1, int(math.ceil(center + support - 1.0)))
        indices = np.arange(first, last + 1, dtype=np.intp)
        distances = center - indices.astype(np.float64)
        scaled = distances / filter_scale
        weights = np.sinc(scaled) * np.sinc(scaled / 3.0)
        weights[np.abs(scaled) >= 3.0] = 0.0
        total = weights.sum()
        if abs(total) < 1e-12:
            nearest = max(0, min(source_size - 1, int(round(center))))
            indices = np.array([nearest], dtype=np.intp)
            weights = np.array([1.0], dtype=np.float64)
        else:
            weights /= total
        contributions.append((indices, weights))
    return contributions


def _resample_separable(
    values: np.ndarray,
    x_contributions: list[tuple[np.ndarray, np.ndarray]],
    y_contributions: list[tuple[np.ndarray, np.ndarray]],
) -> np.ndarray:
    temporary = np.empty(
        (values.shape[0], len(x_contributions), values.shape[2]),
        dtype=np.float64,
    )
    for x, (indices, weights) in enumerate(x_contributions):
        temporary[:, x, :] = np.tensordot(values[:, indices, :], weights, axes=([1], [0]))

    output = np.empty(
        (len(y_contributions), len(x_contributions), values.shape[2]),
        dtype=np.float64,
    )
    for y, (indices, weights) in enumerate(y_contributions):
        output[y, :, :] = np.tensordot(weights, temporary[indices, :, :], axes=([0], [0]))
    return output


def _distance(left: np.ndarray, right: np.ndarray) -> float:
    delta = left - right
    return float(np.sqrt(np.dot(delta, delta)))


def _neighbors(x: int, y: int, width: int, height: int):
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                yield nx, ny


def _isolated_components(
    features: np.ndarray,
    tolerance: float,
) -> list[list[tuple[int, int]]]:
    height, width = features.shape[:2]
    has_similar_neighbor = np.zeros((height, width), dtype=bool)
    tolerance_squared = tolerance * tolerance
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            x_start, x_end = max(0, -dx), min(width, width - dx)
            y_start, y_end = max(0, -dy), min(height, height - dy)
            if x_start >= x_end or y_start >= y_end:
                continue
            current = features[y_start:y_end, x_start:x_end]
            neighbor = features[
                y_start + dy : y_end + dy,
                x_start + dx : x_end + dx,
            ]
            delta = current - neighbor
            squared_distance = np.einsum("...i,...i->...", delta, delta)
            has_similar_neighbor[y_start:y_end, x_start:x_end] |= (
                squared_distance <= tolerance_squared
            )
    return [[(int(x), int(y))] for y, x in np.argwhere(~has_similar_neighbor)]


def _small_color_components(
    features: np.ndarray,
    tolerance: float,
    max_size: int,
) -> list[list[tuple[int, int]]]:
    height, width = features.shape[:2]
    visited = np.zeros((height, width), dtype=bool)
    small: list[list[tuple[int, int]]] = []
    for y in range(height):
        for x in range(width):
            if visited[y, x]:
                continue
            seed = features[y, x]
            queue: deque[tuple[int, int]] = deque([(x, y)])
            visited[y, x] = True
            component: list[tuple[int, int]] = []
            while queue:
                px, py = queue.popleft()
                component.append((px, py))
                for nx, ny in _neighbors(px, py, width, height):
                    if visited[ny, nx]:
                        continue
                    if _distance(seed, features[ny, nx]) <= tolerance:
                        visited[ny, nx] = True
                        queue.append((nx, ny))
            if len(component) <= max_size:
                small.append(component)
    return small


def _coherent_boundary_replacement(
    features: np.ndarray,
    component: list[tuple[int, int]],
    tolerance: float,
) -> np.ndarray | None:
    height, width = features.shape[:2]
    component_set = set(component)
    boundary_positions = sorted(
        {
            (nx, ny)
            for x, y in component
            for nx, ny in _neighbors(x, y, width, height)
            if (nx, ny) not in component_set
        },
        key=lambda point: (point[1], point[0]),
    )
    if len(boundary_positions) < 2:
        return None
    boundary = np.array([features[y, x] for x, y in boundary_positions])
    threshold = max(1.0, tolerance)
    supports = np.array(
        [
            np.count_nonzero(np.linalg.norm(boundary - candidate, axis=1) <= threshold)
            for candidate in boundary
        ]
    )
    best_index = int(np.argmax(supports))
    family_mask = np.linalg.norm(boundary - boundary[best_index], axis=1) <= threshold
    if int(family_mask.sum()) / len(boundary) < 0.60:
        return None
    replacement = np.median(boundary[family_mask], axis=0)
    component_median = np.median(
        np.array([features[y, x] for x, y in component]),
        axis=0,
    )
    if _distance(component_median, replacement) <= threshold:
        return None
    return replacement
