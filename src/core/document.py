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
    source_history: list[Image.Image] = field(default_factory=list)
    source_redo_history: list[Image.Image] = field(default_factory=list)
    selections: list[RegionSelection] = field(default_factory=list)
    preview_settings: ExtractSettings = field(default_factory=ExtractSettings)
    unquantized_preview_image: Image.Image | None = None
    preview_image: Image.Image | None = None
    preview_quantized: bool = False
    palette: list[tuple[int, int, int, int]] = field(default_factory=list)
    palette_name: str | None = None
    assets: list[SavedAsset] = field(default_factory=list)

    def push_source_history(self, max_entries: int = 20) -> None:
        if self.source_image is None:
            return
        self.source_history.append(self.source_image.copy())
        self.source_redo_history.clear()
        if len(self.source_history) > max_entries:
            self.source_history = self.source_history[-max_entries:]

    def undo_source(self) -> bool:
        if self.source_image is None or not self.source_history:
            return False
        self.source_redo_history.append(self.source_image.copy())
        self.source_image = self.source_history.pop()
        return True

    def redo_source(self, max_entries: int = 20) -> bool:
        if self.source_image is None or not self.source_redo_history:
            return False
        self.source_history.append(self.source_image.copy())
        if len(self.source_history) > max_entries:
            self.source_history = self.source_history[-max_entries:]
        self.source_image = self.source_redo_history.pop()
        return True
