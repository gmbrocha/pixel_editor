from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from src.core.selection_models import RegionSelection


RESAMPLE_MAP = {
    "Nearest": Image.Resampling.NEAREST,
    "Bilinear": Image.Resampling.BILINEAR,
    "Bicubic": Image.Resampling.BICUBIC,
}


@dataclass(slots=True)
class ExtractSettings:
    width: int = 16
    height: int = 16
    fit_mode: str = "Preserve"
    resample_mode: str = "Nearest"


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
        return cropped

    target_size = (settings.width, settings.height)

    if settings.fit_mode == "Fit":
        return cropped.resize(target_size, RESAMPLE_MAP[settings.resample_mode])

    preview = Image.new("RGBA", target_size, (0, 0, 0, 0))
    if cropped.size == target_size:
        preview.alpha_composite(cropped)
        return preview

    if cropped.width > settings.width or cropped.height > settings.height:
        scale = min(settings.width / cropped.width, settings.height / cropped.height)
        new_size = (
            max(1, int(round(cropped.width * scale))),
            max(1, int(round(cropped.height * scale))),
        )
        cropped = cropped.resize(new_size, RESAMPLE_MAP[settings.resample_mode])

    preview.alpha_composite(cropped, (0, 0))
    return preview
