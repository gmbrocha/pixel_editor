import numpy as np
from PIL import Image

from src.core.image_processing import (
    area_resize,
    despeckle,
    edge_preserving_denoise,
    lanczos3_resize,
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
