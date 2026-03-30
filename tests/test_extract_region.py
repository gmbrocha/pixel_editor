from PIL import Image

from src.core.extract_region import ExtractSettings, extract_to_preview
from src.core.selection_models import RegionSelection


def test_extract_preserve_keeps_selected_pixels_on_transparent_canvas():
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for y in range(2, 5):
        for x in range(1, 4):
            image.putpixel((x, y), (255, 0, 0, 255))

    selection = RegionSelection(
        kind="polygon",
        points=[(1, 2), (3, 2), (3, 4), (1, 4)],
    )
    preview = extract_to_preview(
        image,
        [selection],
        ExtractSettings(width=6, height=6, fit_mode="Preserve", resample_mode="Nearest"),
    )

    assert preview.size == (6, 6)
    assert preview.getbbox() == (0, 0, 3, 3)
    assert preview.getpixel((0, 0))[3] == 255
    assert preview.getpixel((5, 5))[3] == 0


def test_extract_fit_scales_into_target_tile():
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for y in range(2, 5):
        for x in range(1, 4):
            image.putpixel((x, y), (0, 255, 0, 255))

    selection = RegionSelection(
        kind="polygon",
        points=[(1, 2), (3, 2), (3, 4), (1, 4)],
    )
    preview = extract_to_preview(
        image,
        [selection],
        ExtractSettings(width=6, height=6, fit_mode="Fit", resample_mode="Nearest"),
    )

    assert preview.size == (6, 6)
    assert preview.getbbox() == (0, 0, 6, 6)


def test_extract_actual_keeps_original_crop_size_without_resampling():
    image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    for y in range(1, 5):
        for x in range(2, 6):
            image.putpixel((x, y), (0, 0, 255, 255))

    selection = RegionSelection(
        kind="polygon",
        points=[(2, 1), (5, 1), (5, 4), (2, 4)],
    )
    preview = extract_to_preview(
        image,
        [selection],
        ExtractSettings(width=32, height=32, fit_mode="Actual", resample_mode="Nearest"),
    )

    assert preview.size == (4, 4)
    assert preview.getpixel((0, 0)) == (0, 0, 255, 255)
    assert preview.getpixel((3, 3)) == (0, 0, 255, 255)
