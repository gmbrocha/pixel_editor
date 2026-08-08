from __future__ import annotations

from collections import Counter
import colorsys
from dataclasses import dataclass, field
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


Color = tuple[int, int, int, int]
_HEX_COLOR_RE = re.compile(r"#?(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6})")
_FAMILY_ORDER = (
    "neutral_shadow",
    "stone_gray",
    "earth_tan",
    "brown_wood",
    "olive_vegetation",
    "blue_crystal",
    "harmonic_gold",
    "corruption_red",
    "green_nature",
    "other",
)
_POSTERIZE_MODES = {"rgb_levels", "lab_lightness", "perceptual"}
_POSTERIZE_SOURCES = {"preview_only", "sampling_source", "final_quantize_source"}


@dataclass(slots=True)
class PaletteExtractionSettings:
    palette_size: int = 16
    min_cluster_percent: float = 0.001
    min_perceptual_distance: float = 10.0
    neutral_saturation_threshold: float = 0.15
    max_colors_per_family: int = 4
    preserve_accent_colors: bool = True
    apply_family_cap_to_spread: bool = False
    apply_family_cap_to_most_frequent: bool = False
    apply_family_cap_to_balanced: bool = True
    posterize_enabled: bool = False
    posterize_strength: float = 0.35
    posterize_rgb_levels: int = 12
    posterize_lab_lightness_levels: int = 10
    posterize_chroma_levels: int = 8
    posterize_mode: str = "perceptual"
    posterize_source: str = "sampling_source"


@dataclass(slots=True)
class SelectedPaletteColorDebug:
    color: Color
    family: str
    pixel_percent: float
    cluster_weight: int
    lightness: float = 0.0
    saturation: float = 0.0
    chroma: float = 0.0
    hue_degrees: float = 0.0


@dataclass(slots=True)
class FamilyPaletteDebug:
    family: str
    candidate_count: int
    selected_count: int
    pixel_percent: float


@dataclass(slots=True)
class PaletteExtractionDebug:
    total_unique_rgb_colors: int
    perceptual_cluster_count: int
    requested_palette_size: int = 0
    colors_after_posterize: int = 0
    perceptual_clusters_after_posterize: int = 0
    candidate_cluster_count: int = 0
    selected_color_count: int = 0
    rejected_by_family_cap: int = 0
    rejected_by_lab_distance: int = 0
    rejected_by_min_cluster_size: int = 0
    final_min_lab_distance: float = 0.0
    output_limited_by_source_color_count: bool = False
    output_limited_by_posterize_source: bool = False
    output_limited_by_family_cap: bool = False
    output_limited_by_lab_distance: bool = False
    posterize_enabled: bool = False
    posterize_mode: str = "perceptual"
    posterize_source: str = "sampling_source"
    quantize_source_image: Image.Image | None = None
    selected_colors: list[SelectedPaletteColorDebug] = field(default_factory=list)
    family_summaries: list[FamilyPaletteDebug] = field(default_factory=list)
    average_selected_lab_distance: float = 0.0

    def summary_lines(self) -> list[str]:
        lines = [
            f"Requested palette size: {self.requested_palette_size}",
            f"Original unique RGB colors: {self.total_unique_rgb_colors}",
            f"Colors after posterize: {self.colors_after_posterize}",
            f"Perceptual clusters: {self.perceptual_cluster_count}",
            f"Perceptual clusters after posterize: {self.perceptual_clusters_after_posterize}",
            f"Candidate clusters: {self.candidate_cluster_count}",
            f"Selected colors: {self.selected_color_count}",
            f"Rejected by family cap: {self.rejected_by_family_cap}",
            f"Rejected by LAB distance: {self.rejected_by_lab_distance}",
            f"Rejected by min cluster size: {self.rejected_by_min_cluster_size}",
            f"Final min LAB distance: {self.final_min_lab_distance:.1f}",
            f"Average LAB distance: {self.average_selected_lab_distance:.1f}",
            f"Output limited by source color count: {self.output_limited_by_source_color_count}",
            f"Output limited by posterize source: {self.output_limited_by_posterize_source}",
            f"Output limited by family cap: {self.output_limited_by_family_cap}",
            f"Output limited by LAB distance: {self.output_limited_by_lab_distance}",
        ]
        if self.output_limited_by_posterize_source:
            lines.append(
                f"Available colors after posterize: {self.colors_after_posterize}"
            )
            lines.append("Output limited by posterize source")
        for selected in self.selected_colors:
            r, g, b, _a = selected.color
            lines.append(
                f"#{r:02X}{g:02X}{b:02X}  {selected.family}  "
                f"{selected.pixel_percent * 100:.2f}%  "
                f"L {selected.lightness:.1f}  "
                f"S {selected.saturation:.2f}  "
                f"C {selected.chroma:.1f}  "
                f"H {selected.hue_degrees:.1f}"
            )
        if self.family_summaries:
            lines.append("Family summary:")
            for summary in self.family_summaries:
                lines.append(
                    f"{summary.family}: candidates {summary.candidate_count}, "
                    f"selected {summary.selected_count}, "
                    f"{summary.pixel_percent * 100:.2f}%"
                )
        return lines


@dataclass(slots=True)
class _ColorCluster:
    color: Color
    lab: tuple[float, float, float]
    count: int
    unique_count: int
    family: str

    @property
    def saturation(self) -> float:
        return _rgb_to_hsv(self.color)[1]

    @property
    def lightness(self) -> float:
        return self.lab[0]

    @property
    def chroma(self) -> float:
        return math.sqrt(self.lab[1] ** 2 + self.lab[2] ** 2)

    @property
    def hue_degrees(self) -> float:
        return _rgb_to_hsv(self.color)[0] * 360.0


@dataclass(slots=True)
class _SelectionStats:
    candidate_cluster_count: int = 0
    rejected_by_family_cap: int = 0
    rejected_by_lab_distance: int = 0
    rejected_by_min_cluster_size: int = 0
    final_min_lab_distance: float = 0.0


def add_color_to_palette(
    palette: list[Color],
    color: Color,
    max_colors: int | None = None,
) -> list[Color]:
    updated = list(palette)
    if color in updated:
        updated.remove(color)
    updated.append(color)
    if max_colors is not None and len(updated) > max_colors:
        updated = updated[-max_colors:]
    return updated


def palette_from_image(
    image: Image.Image,
    max_colors: int = 16,
    *,
    selection: str = "frequent",
    settings: PaletteExtractionSettings | None = None,
) -> list[Color]:
    """Extract up to `max_colors` colors from `image`.

    `selection` controls which colors win when the image has more distinct
    colors than `max_colors`:

    - "frequent" / "most_frequent": largest perceptual clusters win.
    - "spread": weighted farthest-point sampling over perceptual clusters.
    - "balanced": material/color-family quotas over perceptual clusters.
    """
    colors, _debug = palette_from_image_with_debug(
        image,
        max_colors=max_colors,
        selection=selection,
        settings=settings,
    )
    return colors


def palette_from_image_with_debug(
    image: Image.Image,
    max_colors: int = 16,
    *,
    selection: str = "frequent",
    settings: PaletteExtractionSettings | None = None,
) -> tuple[list[Color], PaletteExtractionDebug]:
    extraction_settings = _normalize_extraction_settings(settings, max_colors)

    rgba = image.convert("RGBA")
    original_rgb_counts = _opaque_rgb_counts(rgba)
    if not original_rgb_counts:
        debug = PaletteExtractionDebug(
            total_unique_rgb_colors=0,
            perceptual_cluster_count=0,
            requested_palette_size=extraction_settings.palette_size,
            colors_after_posterize=0,
            perceptual_clusters_after_posterize=0,
            candidate_cluster_count=0,
            selected_color_count=1,
            final_min_lab_distance=extraction_settings.min_perceptual_distance,
            posterize_enabled=extraction_settings.posterize_enabled,
            posterize_mode=extraction_settings.posterize_mode,
            posterize_source=extraction_settings.posterize_source,
            selected_colors=[
                SelectedPaletteColorDebug(
                    color=(0, 0, 0, 0),
                    family="neutral_shadow",
                    pixel_percent=0.0,
                    cluster_weight=0,
                )
            ],
        )
        return [(0, 0, 0, 0)], debug

    posterized_image = (
        _posterize_image(rgba, extraction_settings)
        if extraction_settings.posterize_enabled
        else rgba
    )
    posterized_rgb_counts = _opaque_rgb_counts(posterized_image)
    posterize_affects_sampling = (
        extraction_settings.posterize_enabled
        and extraction_settings.posterize_source
        in {"sampling_source", "final_quantize_source"}
    )
    sample_image = posterized_image if posterize_affects_sampling else rgba
    rgb_counts = (
        posterized_rgb_counts if posterize_affects_sampling else original_rgb_counts
    )
    total_pixels = sum(rgb_counts.values())
    clusters = _build_perceptual_clusters(
        rgb_counts,
        neutral_saturation_threshold=extraction_settings.neutral_saturation_threshold,
    )
    posterized_clusters = _build_perceptual_clusters(
        posterized_rgb_counts,
        neutral_saturation_threshold=extraction_settings.neutral_saturation_threshold,
    )

    normalized = (selection or "balanced").strip().lower()
    if normalized == "spread":
        selected, stats = _select_spread_clusters(
            clusters,
            total_pixels,
            extraction_settings,
        )
    elif normalized == "balanced":
        selected, stats = _select_balanced_clusters(
            clusters,
            total_pixels,
            extraction_settings,
        )
    else:
        selected, stats = _select_most_frequent_clusters(
            clusters,
            total_pixels,
            extraction_settings,
        )

    colors = [cluster.color for cluster in selected[: extraction_settings.palette_size]]
    if not colors:
        colors.append((0, 0, 0, 0))

    selected_for_debug = selected[: extraction_settings.palette_size]
    selected_color_count = len(selected_for_debug)
    output_limited_by_source = (
        selected_color_count < extraction_settings.palette_size
        and stats.candidate_cluster_count <= selected_color_count
    )
    output_limited_by_posterize = (
        posterize_affects_sampling
        and len(posterized_rgb_counts) < extraction_settings.palette_size
        and selected_color_count < extraction_settings.palette_size
    )
    output_limited_by_family_cap = (
        selected_color_count < extraction_settings.palette_size
        and stats.rejected_by_family_cap > 0
    )
    output_limited_by_lab_distance = (
        selected_color_count < extraction_settings.palette_size
        and stats.rejected_by_lab_distance > 0
        and not output_limited_by_source
        and not output_limited_by_family_cap
    )
    candidate_clusters, _candidate_rejections = _eligible_clusters(
        clusters,
        total_pixels,
        extraction_settings,
    )
    debug = PaletteExtractionDebug(
        total_unique_rgb_colors=len(original_rgb_counts),
        perceptual_cluster_count=len(clusters),
        requested_palette_size=extraction_settings.palette_size,
        colors_after_posterize=len(posterized_rgb_counts),
        perceptual_clusters_after_posterize=len(posterized_clusters),
        candidate_cluster_count=stats.candidate_cluster_count,
        selected_color_count=selected_color_count,
        rejected_by_family_cap=stats.rejected_by_family_cap,
        rejected_by_lab_distance=stats.rejected_by_lab_distance,
        rejected_by_min_cluster_size=stats.rejected_by_min_cluster_size,
        final_min_lab_distance=stats.final_min_lab_distance,
        output_limited_by_source_color_count=output_limited_by_source,
        output_limited_by_posterize_source=output_limited_by_posterize,
        output_limited_by_family_cap=output_limited_by_family_cap,
        output_limited_by_lab_distance=output_limited_by_lab_distance,
        posterize_enabled=extraction_settings.posterize_enabled,
        posterize_mode=extraction_settings.posterize_mode,
        posterize_source=extraction_settings.posterize_source,
        quantize_source_image=(
            sample_image.copy()
            if extraction_settings.posterize_enabled
            and extraction_settings.posterize_source == "final_quantize_source"
            else None
        ),
        selected_colors=[
            SelectedPaletteColorDebug(
                color=cluster.color,
                family=cluster.family,
                pixel_percent=cluster.count / total_pixels,
                cluster_weight=cluster.count,
                lightness=cluster.lightness,
                saturation=cluster.saturation,
                chroma=cluster.chroma,
                hue_degrees=cluster.hue_degrees,
            )
            for cluster in selected_for_debug
        ],
        family_summaries=_family_summaries(
            candidate_clusters,
            selected_for_debug,
            total_pixels,
        ),
        average_selected_lab_distance=_average_lab_distance(
            [cluster.lab for cluster in selected_for_debug]
        ),
    )
    return colors, debug


def _normalize_extraction_settings(
    settings: PaletteExtractionSettings | None,
    max_colors: int,
) -> PaletteExtractionSettings:
    raw = settings or PaletteExtractionSettings(palette_size=max_colors)
    posterize_mode = (
        raw.posterize_mode
        if raw.posterize_mode in _POSTERIZE_MODES
        else "perceptual"
    )
    posterize_source = (
        raw.posterize_source
        if raw.posterize_source in _POSTERIZE_SOURCES
        else "sampling_source"
    )
    return PaletteExtractionSettings(
        palette_size=max(1, int(max_colors or raw.palette_size)),
        min_cluster_percent=max(0.0, raw.min_cluster_percent),
        min_perceptual_distance=max(0.0, raw.min_perceptual_distance),
        neutral_saturation_threshold=max(
            0.0,
            min(1.0, raw.neutral_saturation_threshold),
        ),
        max_colors_per_family=max(1, int(raw.max_colors_per_family)),
        preserve_accent_colors=bool(raw.preserve_accent_colors),
        apply_family_cap_to_spread=bool(raw.apply_family_cap_to_spread),
        apply_family_cap_to_most_frequent=bool(
            raw.apply_family_cap_to_most_frequent
        ),
        apply_family_cap_to_balanced=bool(raw.apply_family_cap_to_balanced),
        posterize_enabled=bool(raw.posterize_enabled),
        posterize_strength=max(0.0, min(1.0, raw.posterize_strength)),
        posterize_rgb_levels=max(2, min(256, int(raw.posterize_rgb_levels))),
        posterize_lab_lightness_levels=max(
            2,
            min(100, int(raw.posterize_lab_lightness_levels)),
        ),
        posterize_chroma_levels=max(2, min(128, int(raw.posterize_chroma_levels))),
        posterize_mode=posterize_mode,
        posterize_source=posterize_source,
    )


def _opaque_rgb_counts(image: Image.Image) -> "Counter[tuple[int, int, int]]":
    return Counter(
        (r, g, b)
        for r, g, b, a in image.convert("RGBA").getdata()
        if a > 0
    )


def _build_perceptual_clusters(
    rgb_counts: "Counter[tuple[int, int, int]]",
    *,
    neutral_saturation_threshold: float,
    bin_size: float = 4.0,
) -> list[_ColorCluster]:
    bins: dict[tuple[int, int, int], dict[str, object]] = {}
    for (red, green, blue), count in rgb_counts.items():
        lab = _rgb_to_lab(red, green, blue)
        key = (
            int(math.floor(lab[0] / bin_size)),
            int(math.floor((lab[1] + 128.0) / bin_size)),
            int(math.floor((lab[2] + 128.0) / bin_size)),
        )
        bucket = bins.setdefault(
            key,
            {
                "count": 0,
                "rgb": [0.0, 0.0, 0.0],
                "lab": [0.0, 0.0, 0.0],
                "unique": 0,
            },
        )
        bucket["count"] = int(bucket["count"]) + count
        bucket["unique"] = int(bucket["unique"]) + 1
        rgb_acc = bucket["rgb"]
        lab_acc = bucket["lab"]
        assert isinstance(rgb_acc, list)
        assert isinstance(lab_acc, list)
        rgb_acc[0] += red * count
        rgb_acc[1] += green * count
        rgb_acc[2] += blue * count
        lab_acc[0] += lab[0] * count
        lab_acc[1] += lab[1] * count
        lab_acc[2] += lab[2] * count

    clusters: list[_ColorCluster] = []
    for bucket in bins.values():
        count = int(bucket["count"])
        rgb_acc = bucket["rgb"]
        lab_acc = bucket["lab"]
        assert isinstance(rgb_acc, list)
        assert isinstance(lab_acc, list)
        color = (
            max(0, min(255, int(round(rgb_acc[0] / count)))),
            max(0, min(255, int(round(rgb_acc[1] / count)))),
            max(0, min(255, int(round(rgb_acc[2] / count)))),
            255,
        )
        lab = (
            lab_acc[0] / count,
            lab_acc[1] / count,
            lab_acc[2] / count,
        )
        clusters.append(
            _ColorCluster(
                color=color,
                lab=lab,
                count=count,
                unique_count=int(bucket["unique"]),
                family=_color_family(color, lab, neutral_saturation_threshold),
            )
        )

    return sorted(clusters, key=lambda cluster: (-cluster.count, cluster.color))


def _eligible_clusters(
    clusters: list[_ColorCluster],
    total_pixels: int,
    settings: PaletteExtractionSettings,
) -> tuple[list[_ColorCluster], int]:
    min_count = max(1, math.ceil(total_pixels * settings.min_cluster_percent))
    accent_count = max(1, math.ceil(min_count * 0.25))
    eligible: list[_ColorCluster] = []
    rejected_by_min_cluster_size = 0
    for cluster in clusters:
        if cluster.count >= min_count:
            eligible.append(cluster)
            continue
        if (
            settings.preserve_accent_colors
            and cluster.count >= accent_count
            and _is_accent_cluster(cluster)
        ):
            eligible.append(cluster)
            continue
        rejected_by_min_cluster_size += 1
    return (eligible or clusters[:]), rejected_by_min_cluster_size


def _family_cap_allows(
    cluster: _ColorCluster,
    selected: list[_ColorCluster],
    settings: PaletteExtractionSettings,
) -> bool:
    return (
        sum(chosen.family == cluster.family for chosen in selected)
        < settings.max_colors_per_family
    )


def _select_most_frequent_clusters(
    clusters: list[_ColorCluster],
    total_pixels: int,
    settings: PaletteExtractionSettings,
) -> tuple[list[_ColorCluster], _SelectionStats]:
    candidates, rejected_by_min_cluster_size = _eligible_clusters(
        clusters,
        total_pixels,
        settings,
    )
    stats = _SelectionStats(
        candidate_cluster_count=len(candidates),
        rejected_by_min_cluster_size=rejected_by_min_cluster_size,
        final_min_lab_distance=settings.min_perceptual_distance,
    )
    selected: list[_ColorCluster] = []
    for cluster in candidates:
        if (
            settings.apply_family_cap_to_most_frequent
            and not _family_cap_allows(cluster, selected, settings)
        ):
            stats.rejected_by_family_cap += 1
            continue
        if not _far_enough(cluster, selected, settings.min_perceptual_distance):
            stats.rejected_by_lab_distance += 1
            continue
        selected.append(cluster)
        if len(selected) >= settings.palette_size:
            break
    return selected, stats


def _select_spread_clusters(
    clusters: list[_ColorCluster],
    total_pixels: int,
    settings: PaletteExtractionSettings,
) -> tuple[list[_ColorCluster], _SelectionStats]:
    candidates, rejected_by_min_cluster_size = _eligible_clusters(
        clusters,
        total_pixels,
        settings,
    )
    stats = _SelectionStats(
        candidate_cluster_count=len(candidates),
        rejected_by_min_cluster_size=rejected_by_min_cluster_size,
        final_min_lab_distance=settings.min_perceptual_distance,
    )
    if not candidates:
        return [], stats

    selected = [max(candidates, key=lambda c: (c.count, c.saturation, c.color))]
    remaining = [cluster for cluster in candidates if cluster is not selected[0]]
    max_count = max(cluster.count for cluster in candidates)

    while remaining and len(selected) < settings.palette_size:
        scored: list[tuple[float, _ColorCluster]] = []
        distance_rejections_this_pass = 0
        family_rejections_this_pass = 0
        for cluster in remaining:
            if (
                settings.apply_family_cap_to_spread
                and not _family_cap_allows(cluster, selected, settings)
            ):
                family_rejections_this_pass += 1
                continue
            nearest_distance = min(
                _lab_distance(cluster.lab, chosen.lab)
                for chosen in selected
            )
            if nearest_distance < stats.final_min_lab_distance:
                distance_rejections_this_pass += 1
                continue
            weight = 0.35 + 0.65 * math.sqrt(cluster.count / max_count)
            scored.append((nearest_distance * weight, cluster))
        if not scored:
            if family_rejections_this_pass and not distance_rejections_this_pass:
                stats.rejected_by_family_cap += family_rejections_this_pass
                break
            stats.rejected_by_lab_distance += distance_rejections_this_pass
            if stats.final_min_lab_distance <= 0.0:
                break
            stats.final_min_lab_distance = max(0.0, stats.final_min_lab_distance * 0.5)
            if stats.final_min_lab_distance < 1.0:
                stats.final_min_lab_distance = 0.0
            continue
        _score, chosen = max(scored, key=lambda item: (item[0], item[1].count, item[1].color))
        selected.append(chosen)
        remaining.remove(chosen)

    return selected, stats


def _select_balanced_clusters(
    clusters: list[_ColorCluster],
    total_pixels: int,
    settings: PaletteExtractionSettings,
) -> tuple[list[_ColorCluster], _SelectionStats]:
    candidates, rejected_by_min_cluster_size = _eligible_clusters(
        clusters,
        total_pixels,
        settings,
    )
    stats = _SelectionStats(
        candidate_cluster_count=len(candidates),
        rejected_by_min_cluster_size=rejected_by_min_cluster_size,
        final_min_lab_distance=settings.min_perceptual_distance,
    )
    families: dict[str, list[_ColorCluster]] = {family: [] for family in _FAMILY_ORDER}
    for cluster in candidates:
        families.setdefault(cluster.family, []).append(cluster)

    occupied = [
        family
        for family in _FAMILY_ORDER
        if families.get(family)
    ]
    if not occupied:
        return [], stats

    family_limit = (
        settings.max_colors_per_family
        if settings.apply_family_cap_to_balanced
        else settings.palette_size
    )

    allocation = {family: 0 for family in occupied}
    for family in sorted(occupied, key=lambda f: -sum(c.count for c in families[f])):
        if sum(allocation.values()) >= settings.palette_size:
            break
        allocation[family] = 1

    while sum(allocation.values()) < settings.palette_size:
        hungry = [
            family
            for family in occupied
            if allocation[family] < min(family_limit, len(families[family]))
        ]
        if not hungry:
            break
        family = max(
            hungry,
            key=lambda f: (
                sum(c.count for c in families[f]) / (allocation[f] + 1),
                -_FAMILY_ORDER.index(f) if f in _FAMILY_ORDER else -99,
            ),
        )
        allocation[family] += 1

    selected: list[_ColorCluster] = []
    for family in occupied:
        quota = allocation[family]
        if quota <= 0:
            continue
        selected.extend(
            _select_family_lightness_spread(
                families[family],
                quota,
                selected,
                settings.min_perceptual_distance,
            )
        )

    if len(selected) < settings.palette_size:
        for cluster in sorted(candidates, key=lambda c: (-c.count, c.color)):
            if cluster in selected:
                continue
            if (
                settings.apply_family_cap_to_balanced
                and not _family_cap_allows(cluster, selected, settings)
            ):
                stats.rejected_by_family_cap += 1
                continue
            if _far_enough(cluster, selected, settings.min_perceptual_distance):
                selected.append(cluster)
            else:
                stats.rejected_by_lab_distance += 1
            if len(selected) >= settings.palette_size:
                break

    if settings.apply_family_cap_to_balanced:
        max_possible = sum(min(settings.max_colors_per_family, len(families[f])) for f in occupied)
        if settings.palette_size > max_possible:
            stats.rejected_by_family_cap += sum(
                max(0, len(families[f]) - settings.max_colors_per_family)
                for f in occupied
            )

    return selected[: settings.palette_size], stats


def _select_family_lightness_spread(
    clusters: list[_ColorCluster],
    quota: int,
    already_selected: list[_ColorCluster],
    min_distance: float,
) -> list[_ColorCluster]:
    if quota <= 0:
        return []

    ordered = sorted(clusters, key=lambda c: c.lightness)
    selected: list[_ColorCluster] = []
    buckets = min(quota, len(ordered))
    for index in range(buckets):
        start = int(index * len(ordered) / buckets)
        end = int((index + 1) * len(ordered) / buckets)
        bucket = ordered[start:max(start + 1, end)]
        for cluster in sorted(bucket, key=lambda c: (-c.count, c.color)):
            if _far_enough(cluster, already_selected + selected, min_distance):
                selected.append(cluster)
                break
        if len(selected) >= quota:
            return selected

    for cluster in sorted(clusters, key=lambda c: (-c.count, c.color)):
        if cluster in selected:
            continue
        if _far_enough(cluster, already_selected + selected, min_distance):
            selected.append(cluster)
        if len(selected) >= quota:
            break
    return selected


def _family_summaries(
    candidates: list[_ColorCluster],
    selected: list[_ColorCluster],
    total_pixels: int,
) -> list[FamilyPaletteDebug]:
    summaries: list[FamilyPaletteDebug] = []
    selected_counts = Counter(cluster.family for cluster in selected)
    for family in _FAMILY_ORDER:
        family_candidates = [cluster for cluster in candidates if cluster.family == family]
        if not family_candidates and selected_counts.get(family, 0) == 0:
            continue
        summaries.append(
            FamilyPaletteDebug(
                family=family,
                candidate_count=len(family_candidates),
                selected_count=selected_counts.get(family, 0),
                pixel_percent=(
                    sum(cluster.count for cluster in family_candidates) / total_pixels
                    if total_pixels
                    else 0.0
                ),
            )
        )
    return summaries


def _color_family(
    color: Color,
    lab: tuple[float, float, float],
    neutral_saturation_threshold: float,
) -> str:
    hue, saturation, value = _rgb_to_hsv(color)
    degrees = hue * 360.0
    lightness, lab_a, lab_b = lab
    chroma = math.sqrt(lab_a ** 2 + lab_b ** 2)

    if saturation < neutral_saturation_threshold or chroma < 8.0:
        if lightness < 32.0:
            return "neutral_shadow"
        if lab_b < -1.5 or 175.0 <= degrees < 260.0:
            return "stone_gray"
        return "neutral_shadow"

    if lightness < 24.0 and saturation < 0.45:
        return "neutral_shadow"

    if saturation <= 0.32 and 170.0 <= degrees < 260.0:
        return "stone_gray"
    if saturation <= 0.24 and lightness >= 34.0 and abs(lab_a) < 7.0:
        return "stone_gray" if lab_b < 4.0 else "neutral_shadow"

    if 18.0 <= degrees < 42.0:
        if (
            saturation >= 0.50
            and value >= 0.64
            and lightness >= 48.0
            and chroma >= 38.0
        ):
            return "harmonic_gold"
        if value < 0.52 or lightness < 42.0:
            return "brown_wood"
        return "earth_tan"

    if 42.0 <= degrees < 74.0:
        if degrees >= 58.0 and (
            saturation < 0.55 or value < 0.68 or chroma < 42.0
        ):
            return "olive_vegetation"
        if (
            saturation >= 0.48
            and value >= 0.68
            and lightness >= 52.0
            and chroma >= 42.0
        ):
            return "harmonic_gold"
        return "earth_tan" if value >= 0.36 else "brown_wood"

    if 74.0 <= degrees < 135.0:
        if saturation < 0.45 or value < 0.52 or chroma < 36.0:
            return "olive_vegetation"
        return "green_nature"

    if 135.0 <= degrees < 170.0:
        return "green_nature" if saturation >= 0.30 and chroma >= 22.0 else "stone_gray"

    if 170.0 <= degrees < 250.0:
        if saturation >= 0.25 and chroma >= 18.0 and value >= 0.25:
            return "blue_crystal"
        return "stone_gray"

    if degrees >= 320.0 or degrees < 18.0:
        if (
            saturation >= 0.46
            and chroma >= 40.0
            and value >= 0.38
            and lightness >= 24.0
        ):
            return "corruption_red"
        if value < 0.50 or lightness < 40.0:
            return "brown_wood"
        return "other"

    if 250.0 <= degrees < 320.0:
        return "other"

    return "other"


def _is_accent_cluster(cluster: _ColorCluster) -> bool:
    if cluster.family == "blue_crystal":
        return cluster.saturation >= 0.25 and cluster.chroma >= 18.0
    if cluster.family in {"harmonic_gold", "corruption_red", "green_nature"}:
        return cluster.saturation >= 0.35 and cluster.chroma >= 25.0
    return False


def _posterize_image(image: Image.Image, settings: PaletteExtractionSettings) -> Image.Image:
    source = image.convert("RGBA")
    pixels: list[Color] = []
    for red, green, blue, alpha in source.getdata():
        if alpha == 0:
            pixels.append((0, 0, 0, 0))
            continue
        if settings.posterize_mode == "rgb_levels":
            pixels.append((*_posterize_rgb(red, green, blue, settings), alpha))
        elif settings.posterize_mode == "lab_lightness":
            pixels.append((*_posterize_lab_lightness(red, green, blue, settings), alpha))
        else:
            pixels.append((*_posterize_perceptual(red, green, blue, settings), alpha))
    output = Image.new("RGBA", source.size)
    output.putdata(pixels)
    return output


def _effective_levels(configured_levels: int, strength: float, full_levels: int) -> int:
    eased_remaining = (1.0 - strength) ** 2
    levels = configured_levels + (full_levels - configured_levels) * eased_remaining
    return max(2, min(full_levels, int(round(levels))))


def _quantize_channel(value: float, low: float, high: float, levels: int) -> float:
    if levels <= 1 or high <= low:
        return value
    clamped = max(low, min(high, value))
    step = (high - low) / (levels - 1)
    return low + round((clamped - low) / step) * step


def _posterize_rgb(
    red: int,
    green: int,
    blue: int,
    settings: PaletteExtractionSettings,
) -> tuple[int, int, int]:
    levels = _effective_levels(
        settings.posterize_rgb_levels,
        settings.posterize_strength,
        256,
    )
    return (
        int(round(_quantize_channel(red, 0.0, 255.0, levels))),
        int(round(_quantize_channel(green, 0.0, 255.0, levels))),
        int(round(_quantize_channel(blue, 0.0, 255.0, levels))),
    )


def _posterize_lab_lightness(
    red: int,
    green: int,
    blue: int,
    settings: PaletteExtractionSettings,
) -> tuple[int, int, int]:
    lab_l, lab_a, lab_b = _rgb_to_lab(red, green, blue)
    levels = _effective_levels(
        settings.posterize_lab_lightness_levels,
        settings.posterize_strength,
        101,
    )
    lab_l = _quantize_channel(lab_l, 0.0, 100.0, levels)
    return _lab_to_rgb(lab_l, lab_a, lab_b)


def _posterize_perceptual(
    red: int,
    green: int,
    blue: int,
    settings: PaletteExtractionSettings,
) -> tuple[int, int, int]:
    lab_l, lab_a, lab_b = _rgb_to_lab(red, green, blue)
    lightness_levels = _effective_levels(
        settings.posterize_lab_lightness_levels,
        settings.posterize_strength,
        101,
    )
    chroma_levels = _effective_levels(
        settings.posterize_chroma_levels,
        settings.posterize_strength,
        128,
    )
    chroma = math.sqrt(lab_a ** 2 + lab_b ** 2)
    angle = math.atan2(lab_b, lab_a)
    quantized_l = _quantize_channel(lab_l, 0.0, 100.0, lightness_levels)
    quantized_chroma = _quantize_channel(chroma, 0.0, 150.0, chroma_levels)
    return _lab_to_rgb(
        quantized_l,
        math.cos(angle) * quantized_chroma,
        math.sin(angle) * quantized_chroma,
    )


def _far_enough(
    cluster: _ColorCluster,
    selected: list[_ColorCluster],
    min_distance: float,
) -> bool:
    return all(_lab_distance(cluster.lab, chosen.lab) >= min_distance for chosen in selected)


def _lab_distance(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    return math.sqrt(
        (a[0] - b[0]) ** 2
        + (a[1] - b[1]) ** 2
        + (a[2] - b[2]) ** 2
    )


def _average_lab_distance(labs: list[tuple[float, float, float]]) -> float:
    if len(labs) < 2:
        return 0.0
    total = 0.0
    pairs = 0
    for i, lab in enumerate(labs):
        for other in labs[i + 1:]:
            total += _lab_distance(lab, other)
            pairs += 1
    return total / pairs if pairs else 0.0


def _clear_fully_transparent_pixels(image: Image.Image) -> Image.Image:
    output = image.convert("RGBA")
    pixels = output.load()
    for y in range(output.height):
        for x in range(output.width):
            if pixels[x, y][3] == 0:
                pixels[x, y] = (0, 0, 0, 0)
    return output


def _rgb_to_lab(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert an sRGB triplet (0-255) to CIELAB (D65 illuminant).

    LAB separates lightness from chroma and places the red/green axis on `a`
    and the yellow/blue axis on `b`, so perceptually distinct hues (e.g. tan
    vs green) remain far apart even when their RGB values are close.
    """
    def _linearize(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    rl, gl, bl = _linearize(r), _linearize(g), _linearize(b)
    x = 0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl
    y = 0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl
    z = 0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl

    def _f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0

    fx, fy, fz = _f(x / 0.95047), _f(y / 1.00000), _f(z / 1.08883)
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def _lab_to_rgb(lab_l: float, lab_a: float, lab_b: float) -> tuple[int, int, int]:
    fy = (lab_l + 16.0) / 116.0
    fx = lab_a / 500.0 + fy
    fz = fy - lab_b / 200.0

    def _finv(t: float) -> float:
        return t ** 3 if t ** 3 > 0.008856 else (t - 16.0 / 116.0) / 7.787

    x = 0.95047 * _finv(fx)
    y = 1.00000 * _finv(fy)
    z = 1.08883 * _finv(fz)

    red_linear = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    green_linear = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    blue_linear = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z

    def _encode(channel: float) -> int:
        channel = max(0.0, min(1.0, channel))
        if channel <= 0.0031308:
            value = 12.92 * channel
        else:
            value = 1.055 * (channel ** (1.0 / 2.4)) - 0.055
        return max(0, min(255, int(round(value * 255.0))))

    return _encode(red_linear), _encode(green_linear), _encode(blue_linear)


def _nearest_palette_color_lab(
    rgb: tuple[int, int, int],
    palette_lab: list[tuple[float, float, float]],
    palette: list[Color],
) -> Color:
    plab = _rgb_to_lab(rgb[0], rgb[1], rgb[2])
    best = min(
        range(len(palette_lab)),
        key=lambda i: (
            (plab[0] - palette_lab[i][0]) ** 2
            + (plab[1] - palette_lab[i][1]) ** 2
            + (plab[2] - palette_lab[i][2]) ** 2
        ),
    )
    return palette[best]


def quantize_to_palette(
    image: Image.Image,
    palette: list[Color],
    *,
    dither: bool = False,
) -> Image.Image:
    if not palette:
        return image.convert("RGBA")

    source = image.convert("RGBA")

    if dither:
        return _floyd_steinberg_to_palette(source, palette)

    # Perceptual (CIELAB) nearest-neighbor for non-dithered output.
    # Pre-compute LAB for every palette entry, then build a unique-color
    # lookup table so each distinct pixel color is only converted once.
    palette_lab = [_rgb_to_lab(c[0], c[1], c[2]) for c in palette]

    raw_pixels: list[tuple[int, int, int, int]] = list(source.getdata())  # type: ignore[arg-type]
    unique_rgb: set[tuple[int, int, int]] = {p[:3] for p in raw_pixels if p[3] > 0}

    color_map: dict[tuple[int, int, int], Color] = {
        rgb: _nearest_palette_color_lab(rgb, palette_lab, palette)
        for rgb in unique_rgb
    }

    new_pixels: list[Color] = [
        (0, 0, 0, 0) if px[3] == 0 else (*color_map[px[:3]][:3], px[3])  # type: ignore[misc]
        for px in raw_pixels
    ]

    output = Image.new("RGBA", source.size)
    output.putdata(new_pixels)  # type: ignore[arg-type]
    return _clear_fully_transparent_pixels(output)


def _floyd_steinberg_to_palette(
    image: Image.Image,
    palette: list[Color],
) -> Image.Image:
    """Deterministic Floyd-Steinberg without scanline or transparency bleed."""
    source = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    alpha = source[..., 3]
    if np.all(alpha > 0):
        palette_image = _pillow_palette_image(palette)
        output = image.convert("RGB").quantize(
            palette=palette_image,
            dither=Image.Dither.FLOYDSTEINBERG,
        ).convert("RGBA")
        output.putalpha(Image.fromarray(alpha, mode="L"))
        return output

    working = source[..., :3].astype(np.float64)
    output = np.zeros_like(source)
    palette_rgb = np.asarray([color[:3] for color in palette], dtype=np.float64)
    height, width = alpha.shape

    for y in range(height):
        for x in range(width):
            if alpha[y, x] == 0:
                continue
            current = np.clip(working[y, x], 0.0, 255.0)
            distances = np.sum((palette_rgb - current) ** 2, axis=1)
            selected = palette_rgb[int(np.argmin(distances))]
            output[y, x, :3] = selected.astype(np.uint8)
            output[y, x, 3] = alpha[y, x]
            error = current - selected

            # Explicit coordinates prevent right-edge error from wrapping to
            # the next scanline. Transparent pixels neither receive nor pass
            # error, so hidden RGB cannot contaminate sprite boundaries.
            for nx, ny, weight in (
                (x + 1, y, 7.0 / 16.0),
                (x - 1, y + 1, 3.0 / 16.0),
                (x, y + 1, 5.0 / 16.0),
                (x + 1, y + 1, 1.0 / 16.0),
            ):
                if 0 <= nx < width and ny < height and alpha[ny, nx] > 0:
                    working[ny, nx] += error * weight

    return Image.fromarray(output, mode="RGBA")


def _pillow_palette_image(palette: list[Color]) -> Image.Image:
    palette_image = Image.new("P", (1, 1))
    raw: list[int] = []
    for color in palette[:256]:
        raw.extend(color[:3])
    last = list(palette[min(len(palette), 256) - 1][:3])
    while len(raw) < 768:
        raw.extend(last)
    palette_image.putpalette(raw)
    return palette_image


def load_palette_from_hex_list(text: str, max_colors: int = 256) -> list[Color]:
    colors: list[Color] = []
    for match in _HEX_COLOR_RE.finditer(text):
        raw = match.group(0).lstrip("#")
        if len(raw) == 6:
            color = (
                int(raw[0:2], 16),
                int(raw[2:4], 16),
                int(raw[4:6], 16),
                255,
            )
        else:
            color = (
                int(raw[0:2], 16),
                int(raw[2:4], 16),
                int(raw[4:6], 16),
                int(raw[6:8], 16),
            )
        if color not in colors:
            colors.append(color)
        if len(colors) >= max_colors:
            break

    if not colors:
        raise ValueError("No palette colors found in hex list")
    return colors


def load_palette_from_source(
    path_or_text: str | Path,
    max_colors: int = 256,
    *,
    selection: str = "frequent",
    settings: PaletteExtractionSettings | None = None,
) -> list[Color]:
    path = Path(path_or_text)
    if path.exists():
        if path.suffix.lower() in {".txt", ".hex", ".pal"}:
            return load_palette_from_hex_list(
                path.read_text(encoding="utf-8"),
                max_colors=max_colors,
            )
        return load_palette_from_image(
            path,
            max_colors=max_colors,
            selection=selection,
            settings=settings,
        )
    return load_palette_from_hex_list(str(path_or_text), max_colors=max_colors)


def load_palette_from_image(
    path: str | Path,
    max_colors: int = 16,
    *,
    selection: str = "frequent",
    settings: PaletteExtractionSettings | None = None,
) -> list[Color]:
    image = Image.open(path).convert("RGBA")
    return palette_from_image(
        image,
        max_colors=max_colors,
        selection=selection,
        settings=settings,
    )


def export_palette_strip(
    palette: list[Color],
    path: str | Path,
    swatch_size: int = 24,
) -> None:
    width = max(1, len(palette)) * swatch_size
    image = Image.new("RGBA", (width, swatch_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for index, color in enumerate(palette):
        x0 = index * swatch_size
        x1 = x0 + swatch_size - 1
        draw.rectangle((x0, 0, x1, swatch_size - 1), fill=color)
    image.save(path)


def export_palette_grid(
    cells: list[Color | None],
    columns: int,
    rows: int,
    path: str | Path,
    swatch_size: int = 24,
) -> None:
    columns = max(1, int(columns))
    rows = max(1, int(rows))
    image = Image.new("RGBA", (columns * swatch_size, rows * swatch_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    for index, color in enumerate(cells[: columns * rows]):
        if color is None:
            continue
        col = index % columns
        row = index // columns
        x0 = col * swatch_size
        y0 = row * swatch_size
        x1 = x0 + swatch_size - 1
        y1 = y0 + swatch_size - 1
        draw.rectangle((x0, y0, x1, y1), fill=color)

    image.save(path)


def sort_palette(palette: list[Color], mode: str = "brightness") -> list[Color]:
    normalized_mode = mode.strip().lower()
    if normalized_mode == "brightness":
        return sorted(palette, key=_brightness_sort_key)
    if normalized_mode == "hue":
        return sorted(palette, key=_hue_sort_key)
    raise ValueError(f"Unsupported palette sort mode: {mode}")


def _brightness_sort_key(color: Color) -> tuple[bool, float, float, int]:
    red, green, blue, alpha = color
    luma = 0.299 * red + 0.587 * green + 0.114 * blue
    saturation = _rgb_to_hsv(color)[1]
    return (alpha == 0, luma, saturation, alpha)


def _hue_sort_key(color: Color) -> tuple[bool, float, float, float, int]:
    hue, saturation, value = _rgb_to_hsv(color)
    return (color[3] == 0, hue, saturation, value, color[3])


def _rgb_to_hsv(color: Color) -> tuple[float, float, float]:
    red, green, blue, _alpha = color
    hue, saturation, value = colorsys.rgb_to_hsv(red / 255.0, green / 255.0, blue / 255.0)
    return (hue, saturation, value)
