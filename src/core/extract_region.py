from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from src.core.image_processing import (
    cluster_cleanup,
    despeckle,
    edge_preserving_denoise,
    macro_pixels_2x2,
    resize_image,
)
from src.core.selection_models import RegionSelection


RESAMPLE_MAP = {
    "Nearest": Image.Resampling.NEAREST,
    "Nearest Neighbor": Image.Resampling.NEAREST,
    "Bilinear": Image.Resampling.BILINEAR,
    "Bicubic": Image.Resampling.BICUBIC,
}


@dataclass(slots=True)
class ExtractSettings:
    width: int = 16
    height: int = 16
    fit_mode: str = "Preserve"
    resample_mode: str = "Nearest"
    post_process_mode: str = "None"
    denoise_radius: int = 1
    denoise_strength: int = 35
    despeckle_max_size: int = 1
    despeckle_tolerance: int = 24
    cluster_cleanup_threshold: int = 3


def build_selection_mask(
    size: tuple[int, int],
    selections: list[RegionSelection],
) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for selection in selections:
        if len(selection.points) >= 3:
            draw.polygon(selection.points, fill=255)
    return mask


def selection_source_size(
    image: Image.Image,
    selections: list[RegionSelection],
) -> tuple[int, int] | None:
    """Return the native pixel extent covered by the current selections."""
    bounds = build_selection_mask(image.size, selections).getbbox()
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    return right - left, bottom - top


def extract_to_preview(
    image: Image.Image,
    selections: list[RegionSelection],
    settings: ExtractSettings,
) -> Image.Image:
    if not selections:
        return Image.new("RGBA", (settings.width, settings.height), (0, 0, 0, 0))

    source = image.convert("RGBA")
    mask = build_selection_mask(source.size, selections)
    masked = source.copy()
    original_alpha = masked.getchannel("A")
    from PIL import ImageChops
    combined_alpha = ImageChops.multiply(original_alpha, mask)
    masked.putalpha(combined_alpha)

    crop_box = mask.getbbox()
    if crop_box is None:
        return Image.new("RGBA", (settings.width, settings.height), (0, 0, 0, 0))

    cropped = masked.crop(crop_box)
    if settings.fit_mode == "Actual":
        return _finalize_preview(cropped, settings)

    target_size = (settings.width, settings.height)

    if settings.fit_mode == "Fit":
        return _finalize_preview(
            resize_image(cropped, target_size, settings.resample_mode),
            settings,
        )

    preview = Image.new("RGBA", target_size, (0, 0, 0, 0))
    if cropped.size == target_size:
        preview.alpha_composite(cropped)
        return _finalize_preview(preview, settings)

    if cropped.width > settings.width or cropped.height > settings.height:
        scale = min(settings.width / cropped.width, settings.height / cropped.height)
        new_size = (
            max(1, int(round(cropped.width * scale))),
            max(1, int(round(cropped.height * scale))),
        )
        cropped = resize_image(cropped, new_size, settings.resample_mode)

    preview.alpha_composite(cropped, (0, 0))
    return _finalize_preview(preview, settings)


def _finalize_preview(image: Image.Image, settings: ExtractSettings) -> Image.Image:
    return _apply_post_process(image, settings)


def _apply_post_process(image: Image.Image, settings: ExtractSettings) -> Image.Image:
    mode = settings.post_process_mode
    if mode == "Median Filter":
        return image.filter(ImageFilter.MedianFilter(size=3))
    if mode == "Posterize":
        alpha = image.getchannel("A")
        posterized = ImageOps.posterize(image.convert("RGB"), bits=4).convert("RGBA")
        posterized.putalpha(alpha)
        return posterized
    if mode == "Small Gaussian Blur":
        return image.filter(ImageFilter.GaussianBlur(radius=0.75))
    if mode == "Edge-Preserving Denoise":
        return edge_preserving_denoise(
            image,
            radius=settings.denoise_radius,
            strength=settings.denoise_strength,
        )
    if mode == "Despeckle":
        return despeckle(
            image,
            max_speck_size=settings.despeckle_max_size,
            color_tolerance=settings.despeckle_tolerance,
        )
    if mode == "Cluster Cleanup":
        return cluster_cleanup(
            image,
            threshold=settings.cluster_cleanup_threshold,
        )
    if mode == "2x2 Macro Pixels":
        return macro_pixels_2x2(image)
    return image
