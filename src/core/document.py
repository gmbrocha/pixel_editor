from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from src.core.assets import SavedAsset
from src.core.extract_region import ExtractSettings
from src.core.selection_models import RegionSelection


@dataclass(slots=True)
class EditorDocument:
    source_image: Image.Image | None = None
    source_path: str | None = None
    selections: list[RegionSelection] = field(default_factory=list)
    preview_settings: ExtractSettings = field(default_factory=ExtractSettings)
    preview_image: Image.Image | None = None
    palette: list[tuple[int, int, int, int]] = field(default_factory=list)
    assets: list[SavedAsset] = field(default_factory=list)
