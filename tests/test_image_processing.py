import numpy as np
from PIL import Image

from src.core.image_processing import (
    area_resize,
    cluster_cleanup,
    despeckle,
    edge_preserving_denoise,
    lanczos3_resize,
    macro_pixels_2x2,
    resize_image,
)
from src.core.pixel_document import (
    PixelDocument,
    push_image_history,
    redo_image_history,
    undo_image_history,
)


def test_area_exact_two_x_reduction_averages_each_block() -> None:
    image = Image.new("RGBA", (4, 2))
    image.putdata(
        [
            (0, 0, 0, 255),
            (20, 40, 60, 255),
            (100, 120, 140, 255),
            (120, 160, 180, 255),
            (40, 20, 0, 255),
            (60, 60, 60, 255),
            (140, 100, 100, 255),
            (160, 140, 140, 255),
        ]
    )

    result = area_resize(image, (2, 1))

    assert result.size == (2, 1)
    assert list(result.getdata()) == [(30, 30, 30, 255), (130, 130, 140, 255)]


def test_area_non_integer_reduction_uses_partial_source_coverage() -> None:
    image = Image.new("RGBA", (3, 1))
    image.putdata([(0, 0, 0, 255), (60, 60, 60, 255), (120, 120, 120, 255)])

    result = area_resize(image, (2, 1))

    assert list(result.getdata()) == [(20, 20, 20, 255), (100, 100, 100, 255)]


def test_area_preserves_constant_color_and_exact_dimensions() -> None:
    image = Image.new("RGBA", (13, 7), (37, 91, 143, 201))
    result = area_resize(image, (5, 3))
    assert result.size == (5, 3)
    assert set(result.getdata()) == {(37, 91, 143, 201)}


def test_area_transparent_hidden_color_does_not_create_fringe() -> None:
    image = Image.new("RGBA", (2, 1))
    image.putdata([(255, 0, 0, 255), (0, 255, 255, 0)])
    assert area_resize(image, (1, 1)).getpixel((0, 0)) == (255, 0, 0, 128)


def test_lanczos_constant_color_dimensions_and_edge_normalization() -> None:
    image = Image.new("RGBA", (11, 7), (23, 67, 109, 173))
    result = lanczos3_resize(image, (4, 3))
    assert result.size == (4, 3)
    assert set(result.getdata()) == {(23, 67, 109, 173)}


def test_lanczos_pattern_is_deterministic() -> None:
    values = np.zeros((9, 11, 4), dtype=np.uint8)
    yy, xx = np.indices(values.shape[:2])
    values[..., 0] = (xx * 31 + yy * 17) % 256
    values[..., 1] = (xx * 7 + yy * 43) % 256
    values[..., 2] = ((xx + yy) % 2) * 255
    values[..., 3] = 255
    image = Image.fromarray(values, mode="RGBA")

    first = lanczos3_resize(image, (5, 4))
    second = lanczos3_resize(image, (5, 4))

    assert first.tobytes() == second.tobytes()
    assert first.getpixel((0, 0)) == (29, 27, 125, 255)
    assert first.getpixel((4, 3)) == (163, 113, 125, 255)


def test_lanczos_ignores_rgb_hidden_by_transparency() -> None:
    image = Image.new("RGBA", (8, 1), (0, 255, 0, 0))
    for x in range(4):
        image.putpixel((x, 0), (255, 0, 0, 255))

    result = lanczos3_resize(image, (4, 1))

    for red, green, blue, alpha in result.getdata():
        if alpha > 0:
            assert red >= 250
            assert green == 0
            assert blue == 0


def test_resize_dispatch_preserves_original_pillow_methods() -> None:
    image = Image.new("RGBA", (4, 4), (10, 20, 30, 255))
    for method, pil_method in (
        ("Nearest", Image.Resampling.NEAREST),
        ("Bilinear", Image.Resampling.BILINEAR),
        ("Bicubic", Image.Resampling.BICUBIC),
    ):
        assert resize_image(image, (3, 2), method).tobytes() == image.resize(
            (3, 2), pil_method
        ).tobytes()


def test_denoise_uniform_region_is_unchanged_and_strength_zero_is_exact() -> None:
    uniform = Image.new("RGBA", (5, 5), (70, 80, 90, 123))
    assert edge_preserving_denoise(uniform, radius=2, strength=35).tobytes() == uniform.tobytes()

    hidden = Image.new("RGBA", (2, 1))
    hidden.putdata([(1, 2, 3, 0), (20, 30, 40, 255)])
    assert edge_preserving_denoise(hidden, strength=0).tobytes() == hidden.tobytes()


def test_denoise_reduces_mild_noise_but_preserves_strong_edge() -> None:
    image = Image.new("RGBA", (7, 5), (20, 20, 20, 255))
    for y in range(5):
        for x in range(4, 7):
            image.putpixel((x, y), (230, 230, 230, 255))
    image.putpixel((1, 2), (30, 30, 30, 255))

    result = edge_preserving_denoise(image, radius=1, strength=35)

    assert 20 < result.getpixel((1, 2))[0] < 30
    assert result.getpixel((2, 2))[0] < 25
    assert result.getpixel((3, 2))[0] < 30
    assert result.getpixel((4, 2))[0] > 220


def test_denoise_does_not_pull_hidden_transparent_rgb_into_output() -> None:
    image = Image.new("RGBA", (3, 1))
    image.putdata([(0, 255, 0, 0), (255, 0, 0, 255), (0, 255, 0, 0)])
    result = edge_preserving_denoise(image, strength=100)
    for red, green, blue, alpha in result.getdata():
        if alpha > 0:
            assert green == 0
            assert blue == 0


def test_cleanup_output_round_trips_through_undo_and_redo_history() -> None:
    original = Image.new("RGBA", (3, 3), (100, 100, 100, 255))
    original.putpixel((1, 1), (112, 112, 112, 255))
    document = PixelDocument(image=original.copy())
    processed = edge_preserving_denoise(original, radius=1, strength=35)

    push_image_history(document)
    document.image = processed
    assert undo_image_history(document)
    assert document.image.tobytes() == original.tobytes()
    assert redo_image_history(document)
    assert document.image.tobytes() == processed.tobytes()


def test_despeckle_removes_single_pixel_but_not_two_pixel_cluster() -> None:
    single = Image.new("RGBA", (5, 5), (10, 20, 30, 255))
    single.putpixel((2, 2), (240, 230, 220, 255))
    assert despeckle(single, max_speck_size=1).getpixel((2, 2)) == (10, 20, 30, 255)

    pair = single.copy()
    pair.putpixel((2, 3), (240, 230, 220, 255))
    result = despeckle(pair, max_speck_size=1)
    assert result.getpixel((2, 2)) == (240, 230, 220, 255)
    assert result.getpixel((2, 3)) == (240, 230, 220, 255)


def test_despeckle_preserves_connected_diagonal_and_long_thin_line() -> None:
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 255))
    diagonal = [(1, 1), (2, 2), (3, 3)]
    line = [(x, 6) for x in range(1, 7)]
    for point in diagonal + line:
        image.putpixel(point, (255, 255, 255, 255))

    result = despeckle(image, max_speck_size=1)

    assert all(result.getpixel(point) == (255, 255, 255, 255) for point in diagonal + line)


def test_despeckle_clears_hidden_rgb_in_transparent_regions() -> None:
    image = Image.new("RGBA", (3, 3), (90, 80, 70, 0))
    image.putpixel((1, 1), (255, 0, 0, 255))
    result = despeckle(image, max_speck_size=1)
    assert all(pixel[:3] == (0, 0, 0) for pixel in result.getdata() if pixel[3] == 0)


def test_cluster_cleanup_merges_an_isolated_pixel() -> None:
    background = (20, 30, 40, 255)
    image = Image.new("RGBA", (3, 3), background)
    image.putpixel((1, 1), (200, 190, 180, 255))

    result = cluster_cleanup(image, threshold=1)

    assert result.getpixel((1, 1)) == background


def test_cluster_cleanup_prioritizes_shared_boundary_over_color_distance() -> None:
    surrounding = (10, 10, 10, 255)
    candidate = (102, 102, 102, 255)
    close_neighbor = (100, 100, 100, 255)
    image = Image.new("RGBA", (3, 3), surrounding)
    image.putpixel((1, 1), candidate)
    image.putpixel((2, 1), close_neighbor)
    image.putpixel((2, 2), close_neighbor)

    result = cluster_cleanup(image, threshold=1)

    assert result.getpixel((1, 1)) == surrounding


def test_cluster_cleanup_uses_neighbor_area_after_a_distance_tie(monkeypatch) -> None:
    small = (220, 40, 40, 255)
    candidate = (100, 100, 100, 255)
    large = (40, 40, 220, 255)
    transparent = (0, 0, 0, 0)
    image = Image.new("RGBA", (3, 3), transparent)
    image.putdata(
        [
            large,
            candidate,
            small,
            large,
            transparent,
            small,
            large,
            large,
            small,
        ]
    )
    monkeypatch.setattr("src.core.image_processing.lab_distance", lambda *_args: 0.0)

    result = cluster_cleanup(image, threshold=1)

    assert result.getpixel((1, 0)) == large


def test_cluster_cleanup_uses_row_major_id_for_a_complete_tie(monkeypatch) -> None:
    first = (220, 40, 40, 255)
    candidate = (100, 100, 100, 255)
    last = (40, 40, 220, 255)
    image = Image.new("RGBA", (3, 1))
    image.putdata([first, candidate, last])
    monkeypatch.setattr("src.core.image_processing.lab_distance", lambda *_args: 0.0)

    result = cluster_cleanup(image, threshold=1)

    assert result.getpixel((1, 0)) == first


def test_cluster_cleanup_preserves_large_and_diagonally_separate_components() -> None:
    background = (15, 25, 35, 255)
    accent = (210, 180, 50, 255)
    large = Image.new("RGBA", (4, 4), background)
    large.putpixel((1, 1), accent)
    large.putpixel((1, 2), accent)
    assert cluster_cleanup(large, threshold=1).tobytes() == large.tobytes()

    diagonal = Image.new("RGBA", (4, 4), background)
    diagonal.putpixel((1, 1), accent)
    diagonal.putpixel((2, 2), accent)
    result = cluster_cleanup(diagonal, threshold=1)
    assert result.getpixel((1, 1)) == background
    assert result.getpixel((2, 2)) == background


def test_cluster_cleanup_preserves_transparency_and_opaque_edge_islands() -> None:
    transparent = (90, 80, 70, 0)
    opaque = (200, 30, 20, 255)
    image = Image.new("RGBA", (3, 3), transparent)
    image.putpixel((1, 1), opaque)

    result = cluster_cleanup(image, threshold=1)

    assert result.getpixel((1, 1)) == opaque
    assert result.getpixel((0, 0)) == transparent

    hole = Image.new("RGBA", (3, 3), opaque)
    hole.putpixel((1, 1), transparent)
    assert cluster_cleanup(hole, threshold=1).getpixel((1, 1)) == transparent


def test_cluster_cleanup_preserves_palette_dimensions_and_determinism() -> None:
    colors = [
        (10, 20, 30, 255),
        (40, 50, 60, 255),
        (70, 80, 90, 128),
        (0, 0, 0, 0),
    ]
    image = Image.new("RGBA", (5, 4))
    image.putdata([colors[(x + y * 2) % len(colors)] for y in range(4) for x in range(5)])

    first = cluster_cleanup(image, threshold=3)
    second = cluster_cleanup(image, threshold=3)

    input_colors = {image.getpixel((x, y)) for y in range(4) for x in range(5)}
    output_colors = {first.getpixel((x, y)) for y in range(4) for x in range(5)}
    assert first.size == image.size
    assert output_colors <= input_colors
    assert first.tobytes() == second.tobytes()


def test_macro_pixels_2x2_makes_each_complete_block_indivisible() -> None:
    red = (220, 30, 40, 255)
    blue = (30, 40, 220, 255)
    green = (30, 200, 60, 255)
    yellow = (220, 200, 30, 255)
    image = Image.new("RGBA", (4, 2))
    image.putdata(
        [
            red,
            red,
            green,
            blue,
            red,
            blue,
            yellow,
            red,
        ]
    )

    result = macro_pixels_2x2(image)

    assert [result.getpixel((x, y)) for y in range(2) for x in range(2)] == [red] * 4
    assert [result.getpixel((x, y)) for y in range(2) for x in range(2, 4)] == [
        green
    ] * 4


def test_macro_pixels_2x2_preserves_unmatched_odd_edges() -> None:
    background = (20, 30, 40, 255)
    accent = (210, 190, 170, 255)
    image = Image.new("RGBA", (3, 3), background)
    image.putpixel((1, 0), accent)
    image.putpixel((2, 0), accent)
    image.putpixel((2, 1), accent)
    image.putpixel((0, 2), accent)

    result = macro_pixels_2x2(image)

    assert [result.getpixel((x, y)) for y in range(2) for x in range(2)] == [
        background
    ] * 4
    assert result.getpixel((2, 0)) == accent
    assert result.getpixel((2, 1)) == accent
    assert result.getpixel((0, 2)) == accent


def test_macro_pixels_2x2_preserves_palette_alpha_dimensions_and_determinism() -> None:
    colors = [
        (10, 20, 30, 255),
        (80, 90, 100, 128),
        (120, 130, 140, 0),
    ]
    image = Image.new("RGBA", (6, 4))
    image.putdata([colors[(x + y) % 3] for y in range(4) for x in range(6)])

    first = macro_pixels_2x2(image)
    second = macro_pixels_2x2(image)

    input_colors = {image.getpixel((x, y)) for y in range(4) for x in range(6)}
    output_colors = {first.getpixel((x, y)) for y in range(4) for x in range(6)}
    assert first.size == image.size
    assert output_colors <= input_colors
    assert first.tobytes() == second.tobytes()
