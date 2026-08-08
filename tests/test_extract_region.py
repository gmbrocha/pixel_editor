from PIL import Image

from src.core.extract_region import ExtractSettings, extract_to_preview
from src.core.selection_models import RegionSelection


def _full_selection(width: int, height: int) -> list[RegionSelection]:
    return [
        RegionSelection(
            kind="polygon",
            points=[
                (0, 0),
                (width - 1, 0),
                (width - 1, height - 1),
                (0, height - 1),
            ],
        )
    ]


def test_preview_median_filter_removes_single_pixel_noise() -> None:
    image = Image.new("RGBA", (3, 3), (0, 0, 0, 255))
    image.putpixel((1, 1), (255, 255, 255, 255))

    preview = extract_to_preview(
        image,
        _full_selection(3, 3),
        ExtractSettings(fit_mode="Actual", post_process_mode="Median Filter"),
    )

    assert preview.getpixel((1, 1)) == (0, 0, 0, 255)


def test_preview_posterize_reduces_rgb_channels_and_preserves_alpha() -> None:
    image = Image.new("RGBA", (1, 1), (250, 17, 129, 123))

    preview = extract_to_preview(
        image,
        _full_selection(1, 1),
        ExtractSettings(fit_mode="Actual", post_process_mode="Posterize"),
    )

    assert preview.getpixel((0, 0)) == (240, 16, 128, 123)


def test_preview_small_gaussian_blur_softens_neighboring_pixels() -> None:
    image = Image.new("RGBA", (3, 3), (0, 0, 0, 255))
    image.putpixel((1, 1), (255, 0, 0, 255))

    preview = extract_to_preview(
        image,
        _full_selection(3, 3),
        ExtractSettings(fit_mode="Actual", post_process_mode="Small Gaussian Blur"),
    )

    center_red = preview.getpixel((1, 1))[0]
    neighbor_red = preview.getpixel((1, 0))[0]
    assert 0 < neighbor_red < center_red < 255


def test_preview_and_direct_cleanup_use_same_processing_path() -> None:
    image = Image.new("RGBA", (5, 5), (50, 50, 50, 255))
    image.putpixel((2, 2), (60, 60, 60, 255))
    settings = ExtractSettings(
        fit_mode="Actual",
        post_process_mode="Edge-Preserving Denoise",
        denoise_radius=1,
        denoise_strength=35,
    )

    preview = extract_to_preview(image, _full_selection(5, 5), settings)

    from src.core.image_processing import edge_preserving_denoise

    assert preview.tobytes() == edge_preserving_denoise(
        image, radius=1, strength=35
    ).tobytes()


def test_extract_preview_never_runs_an_automatic_palette_quantization_pass() -> None:
    image = Image.new("RGBA", (16, 16))
    image.putdata(
        [
            ((x * 31) % 256, (y * 47) % 256, ((x + y) * 19) % 256, 255)
            for y in range(16)
            for x in range(16)
        ]
    )
    settings = ExtractSettings(
        width=8,
        height=8,
        fit_mode="Fit",
        resample_mode="Area (Box Average)",
    )

    result = extract_to_preview(image, _full_selection(16, 16), settings)

    visible_rgb = {pixel[:3] for pixel in result.getdata() if pixel[3] > 0}
    assert len(visible_rgb) > 16
    assert not hasattr(settings, "quantize_enabled")
    assert not hasattr(settings, "reference_palette")
