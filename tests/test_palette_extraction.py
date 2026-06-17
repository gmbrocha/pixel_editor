import colorsys

from PIL import Image

from src.core.palette import (
    PaletteExtractionSettings,
    palette_from_image,
    palette_from_image_with_debug,
)


def _image_from_pixels(pixels: list[tuple[int, int, int, int]]) -> Image.Image:
    image = Image.new("RGBA", (len(pixels), 1))
    image.putdata(pixels)
    return image


def _has_blue(colors: list[tuple[int, int, int, int]]) -> bool:
    return any(color[2] > color[0] * 2 and color[2] > color[1] * 2 for color in colors)


def _two_family_many_cluster_image() -> Image.Image:
    pixels: list[tuple[int, int, int, int]] = []
    for hue in (0.58, 0.09):
        for saturation_index in range(10):
            for value_index in range(12):
                saturation = 0.25 + saturation_index * 0.07
                value = 0.22 + value_index * 0.065
                red, green, blue = [
                    round(channel * 255)
                    for channel in colorsys.hsv_to_rgb(hue, saturation, value)
                ]
                pixels.extend([(red, green, blue, 255)] * 2)
    return _image_from_pixels(pixels)


def _high_color_fixed_hue_image() -> Image.Image:
    pixels: list[tuple[int, int, int, int]] = []
    for saturation_index in range(64):
        for value_index in range(64):
            saturation = 0.20 + saturation_index * 0.012
            value = 0.24 + value_index * 0.011
            red, green, blue = [
                round(channel * 255)
                for channel in colorsys.hsv_to_rgb(0.12, saturation, value)
            ]
            pixels.append((red, green, blue, 255))
    return _image_from_pixels(pixels)


def test_palette_extraction_ignores_transparent_pixels() -> None:
    image = _image_from_pixels(
        [(255, 0, 0, 0)] * 50
        + [(20, 80, 210, 255)] * 10
    )

    palette = palette_from_image(image, max_colors=2, selection="frequent")

    assert palette == [(20, 80, 210, 255)]


def test_most_frequent_uses_perceptual_clusters_not_raw_unique_rgb() -> None:
    stone = [
        (118 + offset, 116 + offset, 110 + offset, 255)
        for offset in range(8)
        for _ in range(20)
    ]
    blue = [(30, 90, 230, 255)] * 24
    image = _image_from_pixels(stone + blue)

    palette, debug = palette_from_image_with_debug(
        image,
        max_colors=2,
        selection="most_frequent",
        settings=PaletteExtractionSettings(
            palette_size=2,
            min_cluster_percent=0.0,
            min_perceptual_distance=8.0,
        ),
    )

    assert debug.total_unique_rgb_colors == 9
    assert debug.perceptual_cluster_count < debug.total_unique_rgb_colors
    assert len(palette) == 2
    assert _has_blue(palette)


def test_spread_uses_cluster_threshold_so_one_pixel_artifacts_do_not_dominate() -> None:
    image = _image_from_pixels(
        [(90, 90, 88, 255)] * 100
        + [(30, 150, 70, 255)] * 80
        + [(255, 0, 0, 255)]
    )

    palette = palette_from_image(
        image,
        max_colors=3,
        selection="spread",
        settings=PaletteExtractionSettings(
            palette_size=3,
            min_cluster_percent=0.05,
            min_perceptual_distance=8.0,
            preserve_accent_colors=False,
        ),
    )

    assert (255, 0, 0, 255) not in palette
    assert len(palette) == 2


def test_balanced_allocates_across_material_families() -> None:
    image = _image_from_pixels(
        [(110 + i % 4, 118 + i % 4, 126 + i % 4, 255) for i in range(500)]
        + [(80, 45, 25, 255)] * 90
        + [(25, 85, 220, 255)] * 60
        + [(210, 170, 35, 255)] * 60
        + [(35, 145, 65, 255)] * 60
    )

    _palette, debug = palette_from_image_with_debug(
        image,
        max_colors=6,
        selection="balanced",
        settings=PaletteExtractionSettings(
            palette_size=6,
            min_cluster_percent=0.01,
            min_perceptual_distance=8.0,
            neutral_saturation_threshold=0.2,
            max_colors_per_family=2,
        ),
    )

    families = [selected.family for selected in debug.selected_colors]
    assert families.count("stone_gray") <= 2
    assert {
        "stone_gray",
        "brown_wood",
        "blue_crystal",
        "harmonic_gold",
        "green_nature",
    }.issubset(families)


def test_preserve_accent_colors_keeps_small_saturated_clusters() -> None:
    image = _image_from_pixels(
        [(100, 100, 98, 255)] * 1000
        + [(35, 90, 245, 255)] * 3
    )
    settings = PaletteExtractionSettings(
        palette_size=2,
        min_cluster_percent=0.01,
        min_perceptual_distance=8.0,
        preserve_accent_colors=True,
    )

    palette = palette_from_image(
        image,
        max_colors=2,
        selection="frequent",
        settings=settings,
    )

    assert _has_blue(palette)


def test_palette_debug_reports_selected_family_percent_and_average_distance() -> None:
    image = _image_from_pixels(
        [(100, 100, 98, 255)] * 40
        + [(25, 85, 220, 255)] * 40
        + [(210, 170, 35, 255)] * 20
    )

    _palette, debug = palette_from_image_with_debug(
        image,
        max_colors=3,
        selection="balanced",
    )

    assert debug.total_unique_rgb_colors == 3
    assert debug.perceptual_cluster_count == 3
    assert debug.average_selected_lab_distance > 0
    assert [selected.pixel_percent for selected in debug.selected_colors]
    assert {selected.family for selected in debug.selected_colors} >= {
        "neutral_shadow",
        "blue_crystal",
    }
    assert all(selected.chroma >= 0.0 for selected in debug.selected_colors)
    assert all(0.0 <= selected.hue_degrees <= 360.0 for selected in debug.selected_colors)


def test_spread_relaxes_lab_distance_to_fill_requested_palette_without_family_cap() -> None:
    image = _two_family_many_cluster_image()

    palette, debug = palette_from_image_with_debug(
        image,
        max_colors=128,
        selection="spread",
        settings=PaletteExtractionSettings(
            palette_size=128,
            min_cluster_percent=0.0,
            min_perceptual_distance=80.0,
            max_colors_per_family=4,
        ),
    )

    assert debug.candidate_cluster_count >= 128
    assert len(palette) == 128
    assert debug.selected_color_count == 128
    assert debug.final_min_lab_distance < 80.0
    assert debug.rejected_by_lab_distance > 0
    assert debug.rejected_by_family_cap == 0


def test_spread_family_cap_is_only_applied_when_enabled() -> None:
    image = _two_family_many_cluster_image()

    _palette, debug = palette_from_image_with_debug(
        image,
        max_colors=128,
        selection="spread",
        settings=PaletteExtractionSettings(
            palette_size=128,
            min_cluster_percent=0.0,
            min_perceptual_distance=0.0,
            max_colors_per_family=4,
            apply_family_cap_to_spread=True,
        ),
    )

    assert debug.selected_color_count < 128
    assert debug.rejected_by_family_cap > 0


def test_most_frequent_ignores_family_cap_by_default() -> None:
    image = _two_family_many_cluster_image()

    palette, debug = palette_from_image_with_debug(
        image,
        max_colors=16,
        selection="frequent",
        settings=PaletteExtractionSettings(
            palette_size=16,
            min_cluster_percent=0.0,
            min_perceptual_distance=0.0,
            max_colors_per_family=2,
        ),
    )

    assert len(palette) == 16
    assert debug.rejected_by_family_cap == 0


def test_debug_reports_min_cluster_rejections_and_requested_size() -> None:
    image = _image_from_pixels(
        [(90, 90, 88, 255)] * 100
        + [(30, 150, 70, 255)] * 80
        + [(255, 0, 0, 255)]
    )

    _palette, debug = palette_from_image_with_debug(
        image,
        max_colors=3,
        selection="spread",
        settings=PaletteExtractionSettings(
            palette_size=3,
            min_cluster_percent=0.05,
            preserve_accent_colors=False,
        ),
    )

    assert debug.requested_palette_size == 3
    assert debug.candidate_cluster_count == 2
    assert debug.rejected_by_min_cluster_size == 1


def test_road_tile_colors_use_art_direction_families() -> None:
    image = _image_from_pixels(
        [(180, 150, 95, 255)] * 120
        + [(150, 120, 76, 255)] * 110
        + [(86, 50, 30, 255)] * 90
        + [(105, 112, 54, 255)] * 80
        + [(38, 35, 31, 255)] * 70
        + [(94, 104, 116, 255)] * 60
    )

    _palette, debug = palette_from_image_with_debug(
        image,
        max_colors=8,
        selection="balanced",
        settings=PaletteExtractionSettings(
            palette_size=8,
            min_cluster_percent=0.0,
            min_perceptual_distance=0.0,
        ),
    )

    families = {selected.family for selected in debug.selected_colors}
    assert {
        "earth_tan",
        "brown_wood",
        "olive_vegetation",
        "neutral_shadow",
        "stone_gray",
    }.issubset(families)
    assert "harmonic_gold" not in families
    assert "corruption_red" not in families


def test_harmonic_wall_keeps_gold_as_accent_family() -> None:
    image = _image_from_pixels(
        [(100, 110, 124, 255)] * 200
        + [(38, 39, 43, 255)] * 120
        + [(224, 178, 34, 255)] * 18
    )

    _palette, debug = palette_from_image_with_debug(
        image,
        max_colors=4,
        selection="balanced",
        settings=PaletteExtractionSettings(
            palette_size=4,
            min_cluster_percent=0.01,
            min_perceptual_distance=0.0,
            preserve_accent_colors=True,
        ),
    )

    families = {selected.family for selected in debug.selected_colors}
    assert {"stone_gray", "neutral_shadow", "harmonic_gold"}.issubset(families)


def test_crystal_wall_preserves_small_blue_crystal_accent() -> None:
    image = _image_from_pixels(
        [(105, 112, 122, 255)] * 700
        + [(34, 36, 40, 255)] * 300
        + [(35, 100, 240, 255)] * 4
    )

    palette = palette_from_image(
        image,
        max_colors=3,
        selection="frequent",
        settings=PaletteExtractionSettings(
            palette_size=3,
            min_cluster_percent=0.01,
            min_perceptual_distance=0.0,
            preserve_accent_colors=True,
        ),
    )

    assert _has_blue(palette)


def test_posterize_disabled_reports_original_color_count() -> None:
    image = _high_color_fixed_hue_image()

    _palette, debug = palette_from_image_with_debug(
        image,
        max_colors=16,
        selection="frequent",
        settings=PaletteExtractionSettings(
            palette_size=16,
            min_cluster_percent=0.0,
            min_perceptual_distance=0.0,
        ),
    )

    assert debug.total_unique_rgb_colors > 1000
    assert debug.colors_after_posterize == debug.total_unique_rgb_colors


def test_posterize_cleanup_presets_are_progressively_stronger() -> None:
    image = _high_color_fixed_hue_image()

    def _debug_for(strength: float, lightness: int, chroma: int):
        return palette_from_image_with_debug(
            image,
            max_colors=256,
            selection="frequent",
            settings=PaletteExtractionSettings(
                palette_size=256,
                min_cluster_percent=0.0,
                min_perceptual_distance=0.0,
                posterize_enabled=True,
                posterize_strength=strength,
                posterize_lab_lightness_levels=lightness,
                posterize_chroma_levels=chroma,
                posterize_mode="perceptual",
                posterize_source="sampling_source",
            ),
        )[1]

    light = _debug_for(0.20, 14, 12)
    medium = _debug_for(0.35, 10, 8)
    strong = _debug_for(0.85, 6, 4)

    assert light.colors_after_posterize > 100
    assert medium.colors_after_posterize > 49
    assert strong.colors_after_posterize < medium.colors_after_posterize


def test_debug_reports_when_posterize_limits_requested_palette() -> None:
    image = _high_color_fixed_hue_image()

    _palette, debug = palette_from_image_with_debug(
        image,
        max_colors=128,
        selection="frequent",
        settings=PaletteExtractionSettings(
            palette_size=128,
            min_cluster_percent=0.0,
            min_perceptual_distance=0.0,
            posterize_enabled=True,
            posterize_strength=1.0,
            posterize_rgb_levels=3,
            posterize_mode="rgb_levels",
            posterize_source="sampling_source",
        ),
    )

    assert debug.colors_after_posterize < debug.requested_palette_size
    assert debug.output_limited_by_source_color_count is True
    assert debug.output_limited_by_posterize_source is True
    assert any("Output limited by posterize source" in line for line in debug.summary_lines())
    assert debug.family_summaries
