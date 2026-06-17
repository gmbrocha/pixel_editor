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
