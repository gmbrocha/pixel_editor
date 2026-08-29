from __future__ import annotations

import colorsys
import json
import random
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops

CHARACTER_SLOTS = (
    "headwear",
    "face",
    "neck",
    "torso",
    "outerwear",
    "waist",
    "hands",
    "legwear",
    "feet",
    "hair",
    "facial_hair",
    "shoulder_chest",
    "back",
)
CHARACTER_SLOT_LABELS = {
    "headwear": "Headwear",
    "face": "Face",
    "neck": "Neck",
    "torso": "Tops",
    "outerwear": "Outerwear",
    "waist": "Waist",
    "hands": "Hands",
    "legwear": "Legwear",
    "feet": "Feet",
    "hair": "Hair",
    "facial_hair": "Facial Hair",
    "shoulder_chest": "Shoulder / Chest",
    "back": "Back",
}
CHARACTER_LAYER_ORDER = (
    "body_back",
    "hair_back",
    "body",
    "legwear",
    "footwear",
    "torso",
    "outerwear",
    "handwear",
    "waist",
    "neck",
    "face_accessory_under_hair",
    "hair_front",
    "face_accessory",
    "headwear",
    "foreground_accessory",
)
LEGACY_SLOT_ALIASES = {
    "headgear": "headwear",
    "top": "torso",
    "bottom": "legwear",
}
DIRECTION_LABELS = {
    "front": "Front",
    "back": "Back",
    "left": "Left",
    "right": "Right",
}
DISPLAY_DIRECTION_ORDER = ("front", "back", "left", "right")
CAMERA_HEIGHT_ORDER = ("top_down", "three_quarter", "low")
CAMERA_HEIGHT_LABELS = {
    "top_down": "Near Top-Down",
    "three_quarter": "Three-Quarter",
    "low": "Low",
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHARACTER_ASSET_ROOT = PROJECT_ROOT / "assets" / "character-forge"
RECIPE_SCHEMA_VERSION = 3
MANIFEST_SCHEMA_VERSION = 1
VALID_COMPONENT_STATUSES = {"approved", "incomplete"}
VALID_HAIR_OCCLUSION_POLICIES = {"show", "clip", "hide"}


class CharacterForgeError(ValueError):
    """Raised when character data or aligned assets are invalid."""


@dataclass(frozen=True, slots=True)
class CharacterAnimation:
    id: str
    name: str
    filename: str
    sheet_size: tuple[int, int]
    frame_size: tuple[int, int]
    frames_per_direction: int
    direction_rows: Mapping[str, int]
    fps: int
    matte_rgb: tuple[int, int, int] | None
    direction_frame_counts: Mapping[str, int] = field(default_factory=dict)
    direction_playback: Mapping[str, tuple[int, ...]] = field(default_factory=dict)
    frame_durations_ms: tuple[int, ...] = ()
    camera_variants: Mapping[str, str] = field(default_factory=dict)

    @property
    def directions(self) -> tuple[str, ...]:
        return tuple(
            direction
            for direction in DISPLAY_DIRECTION_ORDER
            if direction in self.direction_rows
        )

    def frame_box(self, direction: str, frame_index: int) -> tuple[int, int, int, int]:
        if direction not in self.direction_rows:
            raise CharacterForgeError(
                f"Animation {self.id!r} does not have direction {direction!r}"
            )
        if not 0 <= frame_index < self.frame_count(direction):
            raise CharacterForgeError(
                f"Frame {frame_index} is outside animation {self.id!r}"
            )
        frame_width, frame_height = self.frame_size
        left = frame_index * frame_width
        top = self.direction_rows[direction] * frame_height
        return left, top, left + frame_width, top + frame_height

    def frame_count(self, direction: str) -> int:
        if direction not in self.direction_rows:
            raise CharacterForgeError(
                f"Animation {self.id!r} does not have direction {direction!r}"
            )
        return self.direction_frame_counts.get(direction, self.frames_per_direction)

    def playback_frames(self, direction: str) -> tuple[int, ...]:
        count = self.frame_count(direction)
        return self.direction_playback.get(direction, tuple(range(count)))

    def frame_duration_ms(self, frame_index: int) -> int:
        if self.frame_durations_ms:
            if not 0 <= frame_index < len(self.frame_durations_ms):
                raise CharacterForgeError(
                    f"Frame {frame_index} has no duration in animation {self.id!r}"
                )
            return self.frame_durations_ms[frame_index]
        return max(10, round(1000 / self.fps))

    def filename_for_camera(self, camera_height: str) -> str:
        if camera_height == "low" and not self.camera_variants:
            return self.filename
        try:
            return self.camera_variants[camera_height]
        except KeyError as exc:
            raise CharacterForgeError(
                f"Animation {self.id!r} has no {camera_height!r} camera variant"
            ) from exc


@dataclass(frozen=True, slots=True)
class CharacterBase:
    id: str
    name: str
    directory: Path
    animations: Mapping[str, CharacterAnimation]
    camera_heights: tuple[str, ...] = ("low",)

    def animation_path(self, animation_id: str, camera_height: str = "low") -> Path:
        try:
            animation = self.animations[animation_id]
        except KeyError as exc:
            raise CharacterForgeError(
                f"Unknown animation {animation_id!r} for base {self.id!r}"
            ) from exc
        if camera_height not in self.camera_heights:
            raise CharacterForgeError(
                f"Base {self.id!r} has no {camera_height!r} camera height"
            )
        return self.directory / animation.filename_for_camera(camera_height)


@dataclass(frozen=True, slots=True)
class CharacterPartRenderLayer:
    animations: Mapping[str, Path]
    camera_variants: Mapping[str, Mapping[str, Path]] = field(default_factory=dict)

    def animation_path(self, animation_id: str, camera_height: str) -> Path | None:
        if camera_height == "low":
            return self.animations.get(animation_id)
        return self.camera_variants.get(camera_height, {}).get(animation_id)


@dataclass(frozen=True, slots=True)
class CharacterPart:
    id: str
    name: str
    slot: str
    layer: str
    animations: Mapping[str, Path]
    occupies_slots: tuple[str, ...]
    reserved_slots: tuple[str, ...] = ()
    status: str = "approved"
    tags: tuple[str, ...] = ()
    fit: str = "standard"
    version: int = 1
    coverage: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    manifest_path: Path | None = None
    color_ramp: tuple[tuple[int, int, int], ...] = ()
    ramp_main_color: tuple[int, int, int] | None = None
    alpha_occluded_by_tags: tuple[str, ...] = ()
    camera_variants: Mapping[str, Mapping[str, Path]] = field(default_factory=dict)
    render_layers: Mapping[str, CharacterPartRenderLayer] = field(default_factory=dict)
    hair_occlusion: str = "show"
    direction_mirrors: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    @property
    def claimed_slots(self) -> frozenset[str]:
        return frozenset((*self.occupies_slots, *self.reserved_slots))

    def animation_path(self, animation_id: str, camera_height: str) -> Path | None:
        if camera_height == "low":
            return self.animations.get(animation_id)
        return self.camera_variants.get(camera_height, {}).get(animation_id)

    def render_layer_path(
        self, layer: str, animation_id: str, camera_height: str
    ) -> Path | None:
        if self.render_layers:
            render_layer = self.render_layers.get(layer)
            return (
                None if render_layer is None
                else render_layer.animation_path(animation_id, camera_height)
            )
        return self.animation_path(animation_id, camera_height) if layer == self.layer else None


@dataclass(frozen=True, slots=True)
class CharacterCatalog:
    bases: tuple[CharacterBase, ...]
    parts: tuple[CharacterPart, ...]

    def base(self, base_id: str) -> CharacterBase:
        for base in self.bases:
            if base.id == base_id:
                return base
        raise CharacterForgeError(f"Unknown character base {base_id!r}")

    def part(self, part_id: str) -> CharacterPart:
        for part in self.parts:
            if part.id == part_id:
                return part
        raise CharacterForgeError(f"Unknown character part {part_id!r}")

    def parts_for_slot(
        self,
        slot: str,
        base_id: str | None = None,
        camera_height: str | None = None,
    ) -> tuple[CharacterPart, ...]:
        if slot not in CHARACTER_SLOTS:
            raise CharacterForgeError(f"Unknown character slot {slot!r}")
        if base_id is not None:
            self.base(base_id)
        return tuple(
            part
            for part in self.parts
            if (
                part.slot == slot
                and (base_id is None or part.fit == base_id)
                and (
                    camera_height is None
                    or all(
                        part.animation_path(animation_id, camera_height) is not None
                        for animation_id in self.base(base_id or part.fit).animations
                    )
                )
            )
        )


@dataclass(slots=True)
class CharacterRecipe:
    base_id: str = "elf-01"
    camera_height: str = "low"
    name: str = "character"
    parts: dict[str, str | None] = field(
        default_factory=lambda: {slot: None for slot in CHARACTER_SLOTS}
    )
    part_colors: dict[str, str] = field(default_factory=dict)
    random_seed: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": RECIPE_SCHEMA_VERSION,
            "name": self.name,
            "base": self.base_id,
            "camera_height": self.camera_height,
            "seed": self.random_seed,
            "parts": {slot: self.parts.get(slot) for slot in CHARACTER_SLOTS},
            "part_colors": dict(sorted(self.part_colors.items())),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CharacterRecipe:
        version = data.get("schema_version", 1)
        if version not in (1, 2, RECIPE_SCHEMA_VERSION):
            raise CharacterForgeError(
                f"Unsupported character recipe version {version!r}"
            )
        base_id = data.get("base")
        if not isinstance(base_id, str) or not base_id:
            raise CharacterForgeError("Character recipe must contain a base id")
        name = data.get("name", "character")
        if not isinstance(name, str):
            raise CharacterForgeError("Character recipe name must be text")
        camera_height = data.get("camera_height", "low")
        if not isinstance(camera_height, str) or not camera_height:
            raise CharacterForgeError("Character recipe camera height must be text")
        raw_parts = data.get("parts", {})
        if not isinstance(raw_parts, Mapping):
            raise CharacterForgeError("Character recipe parts must be an object")

        migrated: dict[str, object] = dict(raw_parts)
        for legacy, current in LEGACY_SLOT_ALIASES.items():
            if current not in migrated and legacy in migrated:
                migrated[current] = migrated[legacy]
            if current not in migrated and legacy in data:
                migrated[current] = data[legacy]
        parts: dict[str, str | None] = {}
        for slot in CHARACTER_SLOTS:
            value = migrated.get(slot, data.get(slot))
            if value is not None and not isinstance(value, str):
                raise CharacterForgeError(
                    f"Part selection for {slot!r} must be text or null"
                )
            parts[slot] = value

        seed = data.get("seed")
        if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
            raise CharacterForgeError(
                "Character recipe seed must be an integer or null"
            )
        raw_colors = data.get("part_colors", {})
        if not isinstance(raw_colors, Mapping):
            raise CharacterForgeError("Character recipe part_colors must be an object")
        part_colors: dict[str, str] = {}
        for part_id, color in raw_colors.items():
            if not isinstance(part_id, str) or not isinstance(color, str):
                raise CharacterForgeError("Part colors must map part ids to hex colors")
            part_colors[part_id] = normalize_color_hex(color)
        return cls(
            base_id=base_id,
            camera_height=camera_height,
            name=name,
            parts=parts,
            part_colors=part_colors,
            random_seed=seed,
        )


def normalize_color_hex(color: str) -> str:
    value = color.strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        raise CharacterForgeError(f"Invalid RGB color {color!r}; expected #RRGGBB")
    return value.upper()


def color_hex_to_rgb(color: str) -> tuple[int, int, int]:
    normalized = normalize_color_hex(color)
    return tuple(int(normalized[index : index + 2], 16) for index in (1, 3, 5))


def color_rgb_to_hex(color: tuple[int, int, int]) -> str:
    if len(color) != 3 or any(not 0 <= channel <= 255 for channel in color):
        raise CharacterForgeError(f"Invalid RGB color {color!r}")
    return "#{:02X}{:02X}{:02X}".format(*color)


def load_character_sheet_specs(
    asset_root: str | Path = DEFAULT_CHARACTER_ASSET_ROOT,
) -> dict[str, object]:
    path = Path(asset_root) / "sheet_specs.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CharacterForgeError(
            f"Could not load character sheet specs: {exc}"
        ) from exc
    if not isinstance(data, dict) or data.get("schema_version") not in (1, 2):
        raise CharacterForgeError(
            "Unsupported or invalid character sheet specification"
        )
    return data


def _string_list(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise CharacterForgeError(
            f"Component manifest {field_name} must be a string list"
        )
    return tuple(value)


def load_component_manifest(path: str | Path) -> CharacterPart:
    manifest_path = Path(path)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CharacterForgeError(
            f"Could not load component manifest {manifest_path}: {exc}"
        ) from exc
    if (
        not isinstance(data, dict)
        or data.get("schemaVersion") != MANIFEST_SCHEMA_VERSION
    ):
        raise CharacterForgeError(f"Unsupported component manifest: {manifest_path}")
    required_text = ("id", "displayName", "slot", "layer", "status", "fit")
    for key in required_text:
        if not isinstance(data.get(key), str) or not data[key]:
            raise CharacterForgeError(
                f"Component manifest {manifest_path} requires {key}"
            )
    part_id = data["id"]
    slot = data["slot"]
    layer = data["layer"]
    if slot not in CHARACTER_SLOTS:
        raise CharacterForgeError(f"Component {part_id!r} uses unknown slot {slot!r}")
    if layer not in CHARACTER_LAYER_ORDER:
        raise CharacterForgeError(f"Component {part_id!r} uses unknown layer {layer!r}")
    status = data["status"]
    if status not in VALID_COMPONENT_STATUSES:
        raise CharacterForgeError(
            f"Production component {part_id!r} has invalid status {status!r}"
        )
    occupies = _string_list(data.get("occupiesSlots", [slot]), "occupiesSlots")
    reserved = _string_list(data.get("reservedSlots", []), "reservedSlots")
    if slot not in occupies:
        raise CharacterForgeError(f"Component {part_id!r} must occupy its primary slot")
    if any(value not in CHARACTER_SLOTS for value in (*occupies, *reserved)):
        raise CharacterForgeError(f"Component {part_id!r} claims an unknown slot")
    raw_animations = data.get("animations")
    if not isinstance(raw_animations, Mapping):
        raise CharacterForgeError(f"Component {part_id!r} animations must be an object")
    animations: dict[str, Path] = {}
    for animation_id, filename in raw_animations.items():
        if not isinstance(animation_id, str) or not isinstance(filename, str):
            raise CharacterForgeError(
                f"Component {part_id!r} animation entries must be text"
            )
        animations[animation_id] = manifest_path.parent / filename
    raw_camera_variants = data.get("cameraVariants", {})
    if not isinstance(raw_camera_variants, Mapping):
        raise CharacterForgeError(
            f"Component {part_id!r} cameraVariants must be an object"
        )
    camera_variants: dict[str, dict[str, Path]] = {}
    for camera_height, raw_camera_animations in raw_camera_variants.items():
        if not isinstance(camera_height, str) or not isinstance(
            raw_camera_animations, Mapping
        ):
            raise CharacterForgeError(
                f"Component {part_id!r} camera variant is invalid"
            )
        camera_variants[camera_height] = {
            str(animation_id): manifest_path.parent / str(filename)
            for animation_id, filename in raw_camera_animations.items()
        }
    render_layers: dict[str, CharacterPartRenderLayer] = {}
    raw_render_layers = data.get("renderLayers")
    if raw_render_layers is not None:
        if not isinstance(raw_render_layers, Mapping) or not raw_render_layers:
            raise CharacterForgeError(
                f"Component {part_id!r} renderLayers must be a non-empty object"
            )
        for render_layer, raw_render_layer in raw_render_layers.items():
            if (
                not isinstance(render_layer, str)
                or render_layer not in CHARACTER_LAYER_ORDER
                or not isinstance(raw_render_layer, Mapping)
            ):
                raise CharacterForgeError(
                    f"Component {part_id!r} has an invalid render layer"
                )
            raw_layer_animations = raw_render_layer.get("animations")
            if not isinstance(raw_layer_animations, Mapping):
                raise CharacterForgeError(
                    f"Component {part_id!r} render layer {render_layer!r} "
                    "requires animations"
                )
            layer_animations = {
                str(animation_id): manifest_path.parent / str(filename)
                for animation_id, filename in raw_layer_animations.items()
                if isinstance(animation_id, str) and isinstance(filename, str)
            }
            if len(layer_animations) != len(raw_layer_animations):
                raise CharacterForgeError(
                    f"Component {part_id!r} render layer animations must be text"
                )
            raw_layer_variants = raw_render_layer.get("cameraVariants", {})
            if not isinstance(raw_layer_variants, Mapping):
                raise CharacterForgeError(
                    f"Component {part_id!r} render layer cameraVariants is invalid"
                )
            layer_variants: dict[str, dict[str, Path]] = {}
            for camera_height, raw_layer_camera in raw_layer_variants.items():
                if not isinstance(camera_height, str) or not isinstance(
                    raw_layer_camera, Mapping
                ):
                    raise CharacterForgeError(
                        f"Component {part_id!r} render layer camera variant is invalid"
                    )
                layer_variants[camera_height] = {
                    str(animation_id): manifest_path.parent / str(filename)
                    for animation_id, filename in raw_layer_camera.items()
                }
            render_layers[render_layer] = CharacterPartRenderLayer(
                animations=layer_animations,
                camera_variants=layer_variants,
            )
        if layer not in render_layers:
            raise CharacterForgeError(
                f"Component {part_id!r} primary layer {layer!r} is absent from renderLayers"
            )
    raw_coverage = data.get("coverage", {})
    if not isinstance(raw_coverage, Mapping):
        raise CharacterForgeError(f"Component {part_id!r} coverage must be an object")
    coverage = {
        animation_id: _string_list(directions, f"coverage.{animation_id}")
        for animation_id, directions in raw_coverage.items()
        if isinstance(animation_id, str)
    }
    ramp: tuple[tuple[int, int, int], ...] = ()
    ramp_main: tuple[int, int, int] | None = None
    raw_ramp = data.get("colorRamp")
    if raw_ramp is not None:
        if not isinstance(raw_ramp, Mapping) or not isinstance(
            raw_ramp.get("main"), str
        ):
            raise CharacterForgeError(f"Component {part_id!r} colorRamp is invalid")
        raw_colors = _string_list(raw_ramp.get("colors", []), "colorRamp.colors")
        ramp = tuple(color_hex_to_rgb(color) for color in raw_colors)
        ramp_main = color_hex_to_rgb(raw_ramp["main"])
        if ramp_main not in ramp:
            raise CharacterForgeError(
                f"Component {part_id!r} ramp main must be in its colors"
            )
    tags = _string_list(data.get("tags", []), "tags")
    alpha_occluded_by_tags = _string_list(
        data.get("alphaOccludedByTags", []), "alphaOccludedByTags"
    )
    version = data.get("version", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise CharacterForgeError(f"Component {part_id!r} version must be positive")
    hair_occlusion = data.get("hairOcclusion", "show")
    if (
        not isinstance(hair_occlusion, str)
        or hair_occlusion not in VALID_HAIR_OCCLUSION_POLICIES
    ):
        raise CharacterForgeError(
            f"Component {part_id!r} has invalid hairOcclusion {hair_occlusion!r}"
        )
    raw_direction_mirrors = data.get("directionMirrors", {})
    if not isinstance(raw_direction_mirrors, Mapping):
        raise CharacterForgeError(
            f"Component {part_id!r} directionMirrors must be an object"
        )
    direction_mirrors: dict[str, dict[str, str]] = {}
    for animation_id, raw_mirrors in raw_direction_mirrors.items():
        if not isinstance(animation_id, str) or not isinstance(raw_mirrors, Mapping):
            raise CharacterForgeError(
                f"Component {part_id!r} has invalid directionMirrors"
            )
        mirrors = {
            str(target): str(source)
            for target, source in raw_mirrors.items()
            if isinstance(target, str) and isinstance(source, str)
        }
        if len(mirrors) != len(raw_mirrors):
            raise CharacterForgeError(
                f"Component {part_id!r} direction mirror entries must be text"
            )
        direction_mirrors[animation_id] = mirrors
    return CharacterPart(
        id=part_id,
        name=data["displayName"],
        slot=slot,
        layer=layer,
        animations=animations,
        occupies_slots=occupies,
        reserved_slots=reserved,
        status=status,
        tags=tags,
        fit=data["fit"],
        version=version,
        coverage=coverage,
        manifest_path=manifest_path,
        color_ramp=ramp,
        ramp_main_color=ramp_main,
        alpha_occluded_by_tags=alpha_occluded_by_tags,
        camera_variants=camera_variants,
        render_layers=render_layers,
        hair_occlusion=str(hair_occlusion),
        direction_mirrors=direction_mirrors,
    )


def create_default_catalog(
    asset_root: str | Path = DEFAULT_CHARACTER_ASSET_ROOT,
    *,
    include_incomplete: bool = True,
) -> CharacterCatalog:
    root = Path(asset_root)
    specs = load_character_sheet_specs(root)
    raw_frame_size = specs.get("frame_size")
    if not isinstance(raw_frame_size, list) or len(raw_frame_size) != 2:
        raise CharacterForgeError("Character frame_size is invalid")
    frame_size = tuple(int(value) for value in raw_frame_size)
    raw_camera_heights = specs.get("camera_heights", {"low": {}})
    if not isinstance(raw_camera_heights, Mapping) or not raw_camera_heights:
        raise CharacterForgeError("Character camera_heights specification is invalid")
    camera_height_ids = tuple(str(value) for value in raw_camera_heights)
    if specs["schema_version"] == 1:
        raw_bases = {
            str(specs.get("base_id", "elf-01")): {
                "name": specs.get("base_name", specs.get("base_id", "elf-01")),
                "animations": specs.get("animations"),
            }
        }
    else:
        raw_bases = specs.get("bases")
    if not isinstance(raw_bases, Mapping) or not raw_bases:
        raise CharacterForgeError("Character bases specification is invalid")

    bases: list[CharacterBase] = []
    for base_id, raw_base in raw_bases.items():
        if not isinstance(base_id, str) or not isinstance(raw_base, Mapping):
            raise CharacterForgeError("Character base entry is invalid")
        raw_animations = raw_base.get("animations")
        if not isinstance(raw_animations, Mapping):
            raise CharacterForgeError(
                f"Character base {base_id!r} animations specification is invalid"
            )
        animations: dict[str, CharacterAnimation] = {}
        for animation_id, raw in raw_animations.items():
            if not isinstance(animation_id, str) or not isinstance(raw, Mapping):
                raise CharacterForgeError("Character animation entry is invalid")
            sheet_size = tuple(int(value) for value in raw["sheet_size"])
            direction_rows = {
                str(direction): int(row)
                for direction, row in raw["direction_rows"].items()
            }
            raw_frame_counts = raw.get("direction_frame_counts", {})
            if not isinstance(raw_frame_counts, Mapping):
                raise CharacterForgeError(
                    f"Character animation {animation_id!r} direction_frame_counts is invalid"
                )
            direction_frame_counts = {
                str(direction): int(count)
                for direction, count in raw_frame_counts.items()
            }
            raw_playback = raw.get("direction_playback", {})
            if not isinstance(raw_playback, Mapping):
                raise CharacterForgeError(
                    f"Character animation {animation_id!r} direction_playback is invalid"
                )
            direction_playback: dict[str, tuple[int, ...]] = {}
            for direction, indices in raw_playback.items():
                if not isinstance(indices, list):
                    raise CharacterForgeError(
                        f"Character animation {animation_id!r} playback for "
                        f"{direction!r} must be a list"
                    )
                direction_playback[str(direction)] = tuple(
                    int(index) for index in indices
                )
            raw_durations = raw.get("frame_durations_ms", [])
            if not isinstance(raw_durations, list):
                raise CharacterForgeError(
                    f"Character animation {animation_id!r} frame_durations_ms is invalid"
                )
            matte = raw.get("source_matte")
            filename = Path(str(raw["runtime_file"])).name
            raw_variants = raw.get("camera_variants", {})
            if not isinstance(raw_variants, Mapping):
                raise CharacterForgeError(
                    f"Character animation {animation_id!r} camera_variants is invalid"
                )
            camera_variants: dict[str, str] = {"low": filename}
            for camera_height, variant in raw_variants.items():
                if isinstance(variant, Mapping):
                    variant_file = variant.get("runtime_file")
                else:
                    variant_file = variant
                if not isinstance(camera_height, str) or not isinstance(
                    variant_file, str
                ):
                    raise CharacterForgeError(
                        f"Character animation {animation_id!r} camera variant is invalid"
                    )
                camera_variants[camera_height] = str(
                    Path(variant_file).relative_to(Path("bases") / base_id)
                ).replace("\\", "/")
            animations[animation_id] = CharacterAnimation(
                id=animation_id,
                name=str(raw["name"]),
                filename=filename,
                sheet_size=sheet_size,
                frame_size=frame_size,
                frames_per_direction=int(raw["frames_per_direction"]),
                direction_rows=direction_rows,
                fps=int(raw["fps"]),
                matte_rgb=color_hex_to_rgb(matte) if isinstance(matte, str) else None,
                direction_frame_counts=direction_frame_counts,
                direction_playback=direction_playback,
                frame_durations_ms=tuple(int(value) for value in raw_durations),
                camera_variants=camera_variants,
            )
        bases.append(
            CharacterBase(
                id=base_id,
                name=str(raw_base.get("name", base_id)),
                directory=root / "bases" / base_id,
                animations=animations,
                camera_heights=tuple(
                    value
                    for value in camera_height_ids
                    if all(
                        value in animation.camera_variants
                        for animation in animations.values()
                    )
                ),
            )
        )
    parts: list[CharacterPart] = []
    parts_root = root / "parts"
    if parts_root.is_dir():
        for manifest_path in sorted(parts_root.rglob("manifest.json")):
            part = load_component_manifest(manifest_path)
            if part.status == "approved" or include_incomplete:
                parts.append(part)
    return CharacterCatalog(bases=tuple(bases), parts=tuple(parts))


def create_default_recipe(name: str = "character") -> CharacterRecipe:
    parts = {slot: None for slot in CHARACTER_SLOTS}
    return CharacterRecipe(name=name, parts=parts)


def validate_catalog(catalog: CharacterCatalog) -> None:
    base_ids: set[str] = set()
    for base in catalog.bases:
        if base.id in base_ids:
            raise CharacterForgeError(f"Duplicate character base id {base.id!r}")
        base_ids.add(base.id)
        for animation in base.animations.values():
            for camera_height in base.camera_heights:
                _validate_image_size(
                    base.animation_path(animation.id, camera_height),
                    animation.sheet_size,
                )
            columns = animation.sheet_size[0] // animation.frame_size[0]
            unknown_counts = set(animation.direction_frame_counts) - set(
                animation.direction_rows
            )
            unknown_playback = set(animation.direction_playback) - set(
                animation.direction_rows
            )
            if unknown_counts or unknown_playback:
                raise CharacterForgeError(
                    f"Animation {animation.id!r} has metadata for unknown directions"
                )
            for direction in animation.directions:
                count = animation.frame_count(direction)
                row = animation.direction_rows[direction]
                rows = animation.sheet_size[1] // animation.frame_size[1]
                if count < 1 or count > columns or row < 0 or row >= rows:
                    raise CharacterForgeError(
                        f"Animation {animation.id!r} direction {direction!r} has "
                        "invalid sheet geometry"
                    )
                playback = animation.playback_frames(direction)
                if not playback or any(
                    index < 0 or index >= count for index in playback
                ):
                    raise CharacterForgeError(
                        f"Animation {animation.id!r} direction {direction!r} has "
                        "invalid playback frames"
                    )
                if animation.frame_durations_ms and (
                    len(animation.frame_durations_ms) != animation.frames_per_direction
                    or any(value < 1 for value in animation.frame_durations_ms)
                ):
                    raise CharacterForgeError(
                        f"Animation {animation.id!r} has invalid frame durations"
                    )
    ids: set[str] = set()
    for part in catalog.parts:
        if part.id in ids:
            raise CharacterForgeError(
                f"Duplicate character component id {part.id!r}"
            )
        ids.add(part.id)
        if part.slot not in CHARACTER_SLOTS or part.layer not in CHARACTER_LAYER_ORDER:
            raise CharacterForgeError(
                f"Component {part.id!r} has an invalid slot or layer"
            )
        try:
            fit_base = catalog.base(part.fit)
        except CharacterForgeError as exc:
            raise CharacterForgeError(
                f"Component {part.id!r} fits unknown base {part.fit!r}"
            ) from exc
        for animation_id, path in part.animations.items():
            if animation_id not in fit_base.animations:
                raise CharacterForgeError(
                    f"Component {part.id!r} uses unknown animation {animation_id!r}"
                )
            _validate_image_size(path, fit_base.animations[animation_id].sheet_size)
        for camera_height, variants in part.camera_variants.items():
            if camera_height not in fit_base.camera_heights:
                raise CharacterForgeError(
                    f"Component {part.id!r} uses unknown camera height {camera_height!r}"
                )
            for animation_id, path in variants.items():
                if animation_id not in fit_base.animations:
                    raise CharacterForgeError(
                        f"Component {part.id!r} uses unknown animation {animation_id!r}"
                    )
                _validate_image_size(
                    path, fit_base.animations[animation_id].sheet_size
                )
        for render_layer, layer_data in part.render_layers.items():
            if render_layer not in CHARACTER_LAYER_ORDER:
                raise CharacterForgeError(
                    f"Component {part.id!r} uses unknown render layer {render_layer!r}"
                )
            for animation_id, path in layer_data.animations.items():
                if animation_id not in fit_base.animations:
                    raise CharacterForgeError(
                        f"Component {part.id!r} render layer uses unknown animation"
                    )
                _validate_image_size(path, fit_base.animations[animation_id].sheet_size)
            for camera_height, variants in layer_data.camera_variants.items():
                if camera_height not in fit_base.camera_heights:
                    raise CharacterForgeError(
                        f"Component {part.id!r} render layer uses unknown camera height"
                    )
                for animation_id, path in variants.items():
                    if animation_id not in fit_base.animations:
                        raise CharacterForgeError(
                            f"Component {part.id!r} render layer uses unknown animation"
                        )
                    _validate_image_size(path, fit_base.animations[animation_id].sheet_size)
        for animation_id, directions in part.coverage.items():
            if animation_id not in fit_base.animations:
                raise CharacterForgeError(
                    f"Component {part.id!r} coverage is invalid"
                )
            unknown = set(directions) - set(
                fit_base.animations[animation_id].direction_rows
            )
            if unknown:
                raise CharacterForgeError(
                    f"Component {part.id!r} has unknown coverage directions {sorted(unknown)}"
                )
        for animation_id, mirrors in part.direction_mirrors.items():
            if animation_id not in fit_base.animations:
                raise CharacterForgeError(
                    f"Component {part.id!r} mirrors an unknown animation"
                )
            animation = fit_base.animations[animation_id]
            directions = set(animation.direction_rows)
            for target, source in mirrors.items():
                if target not in directions or source not in directions or target == source:
                    raise CharacterForgeError(
                        f"Component {part.id!r} has invalid {target!r} <- {source!r} mirror"
                    )
                if animation.frame_count(target) != animation.frame_count(source):
                    raise CharacterForgeError(
                        f"Component {part.id!r} mirrored directions differ in frame count"
                    )


def validate_recipe(catalog: CharacterCatalog, recipe: CharacterRecipe) -> None:
    base = catalog.base(recipe.base_id)
    if recipe.camera_height not in base.camera_heights:
        raise CharacterForgeError(
            f"Base {recipe.base_id!r} has no camera height {recipe.camera_height!r}"
        )
    claimed_by: dict[str, str] = {}
    selected_ids: set[str] = set()
    for slot in CHARACTER_SLOTS:
        part_id = recipe.parts.get(slot)
        if part_id is None:
            continue
        if part_id in selected_ids:
            raise CharacterForgeError(f"Part {part_id!r} is selected more than once")
        selected_ids.add(part_id)
        part = catalog.part(part_id)
        if part.fit != recipe.base_id:
            raise CharacterForgeError(
                f"Part {part_id!r} fits {part.fit!r}, not {recipe.base_id!r}"
            )
        if any(
            part.animation_path(animation_id, recipe.camera_height) is None
            for animation_id in base.animations
        ):
            raise CharacterForgeError(
                f"Part {part_id!r} has no complete {recipe.camera_height!r} camera coverage"
            )
        if part.slot != slot:
            raise CharacterForgeError(
                f"Part {part_id!r} belongs to {part.slot!r}, not {slot!r}"
            )
        for claimed_slot in part.claimed_slots:
            previous = claimed_by.get(claimed_slot)
            if previous is not None:
                raise CharacterForgeError(
                    f"Parts {previous!r} and {part_id!r} both claim slot {claimed_slot!r}"
                )
            claimed_by[claimed_slot] = part_id
    for part_id, color in recipe.part_colors.items():
        part = catalog.part(part_id)
        if part_id not in selected_ids:
            raise CharacterForgeError(
                f"Part color refers to unselected part {part_id!r}"
            )
        if not part.color_ramp or part.ramp_main_color is None:
            raise CharacterForgeError(f"Part {part_id!r} does not support recoloring")
        normalize_color_hex(color)


def part_default_main_color(part: CharacterPart) -> str | None:
    if not part.color_ramp or part.ramp_main_color is None:
        return None
    return color_rgb_to_hex(part.ramp_main_color)


def recolor_part_ramp(
    image: Image.Image,
    part: CharacterPart,
    main_color: str,
) -> Image.Image:
    """Remap only a part's declared ramp around a selected main RGB color."""
    if not part.color_ramp or part.ramp_main_color is None:
        return image.copy()
    target_main = color_hex_to_rgb(main_color)
    if target_main == part.ramp_main_color:
        return image.copy()
    source_main_h, source_main_l, source_main_s = colorsys.rgb_to_hls(
        *(channel / 255 for channel in part.ramp_main_color)
    )
    target_h, target_l, target_s = colorsys.rgb_to_hls(
        *(channel / 255 for channel in target_main)
    )
    replacements: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    for source_color in part.color_ramp:
        source_h, source_l, source_s = colorsys.rgb_to_hls(
            *(channel / 255 for channel in source_color)
        )
        hue_delta = ((source_h - source_main_h + 0.5) % 1.0) - 0.5
        new_hue = (target_h + hue_delta) % 1.0
        new_saturation = (
            min(1.0, target_s * (source_s / source_main_s))
            if source_main_s > 0
            else target_s
        )
        if source_l >= source_main_l:
            distance = (source_l - source_main_l) / max(1e-9, 1.0 - source_main_l)
            new_lightness = target_l + distance * (1.0 - target_l)
        else:
            distance = (source_main_l - source_l) / max(1e-9, source_main_l)
            new_lightness = target_l * (1.0 - distance)
        red, green, blue = colorsys.hls_to_rgb(
            new_hue,
            max(0.0, min(1.0, new_lightness)),
            max(0.0, min(1.0, new_saturation)),
        )
        replacements[source_color] = (
            round(red * 255),
            round(green * 255),
            round(blue * 255),
        )
    pixels = []
    for red, green, blue, alpha in _pixels(image):
        replacement = replacements.get((red, green, blue))
        pixels.append(
            (red, green, blue, alpha) if replacement is None else (*replacement, alpha)
        )
    result = Image.new("RGBA", image.size, (0, 0, 0, 0))
    result.putdata(pixels)
    return result


def _pixels(image: Image.Image):
    return (
        image.get_flattened_data()
        if hasattr(image, "get_flattened_data")
        else image.getdata()
    )


def _validate_image_size(path: Path, expected: tuple[int, int]) -> None:
    if not path.is_file():
        raise CharacterForgeError(f"Character asset is missing: {path}")
    with Image.open(path) as image:
        actual = image.size
        mode = image.mode
    if actual != expected:
        raise CharacterForgeError(
            f"Character asset {path.name!r} is {actual}, expected {expected}"
        )
    if mode != "RGBA":
        raise CharacterForgeError(
            f"Character asset {path.name!r} must be RGBA, not {mode}"
        )


@lru_cache(maxsize=256)
def _load_rgba(path_text: str, matte_rgb: tuple[int, int, int] | None) -> Image.Image:
    path = Path(path_text)
    if not path.is_file():
        raise CharacterForgeError(f"Character asset is missing: {path}")
    with Image.open(path) as source:
        image = source.convert("RGBA")
    if matte_rgb is None:
        return image
    pixels = [
        (red, green, blue, 0 if (red, green, blue) == matte_rgb else alpha)
        for red, green, blue, alpha in _pixels(image)
    ]
    image.putdata(pixels)
    return image


def clear_character_image_cache() -> None:
    _load_rgba.cache_clear()


def load_base_animation(
    catalog: CharacterCatalog,
    base_id: str,
    animation_id: str,
    camera_height: str = "low",
) -> Image.Image:
    base = catalog.base(base_id)
    animation = base.animations.get(animation_id)
    if animation is None:
        raise CharacterForgeError(f"Unknown character animation {animation_id!r}")
    image = _load_rgba(
        str(base.animation_path(animation_id, camera_height)), animation.matte_rgb
    ).copy()
    if image.size != animation.sheet_size:
        raise CharacterForgeError(
            f"Base animation {animation_id!r} is {image.size}, expected {animation.sheet_size}"
        )
    return image


def load_part_animation(
    catalog: CharacterCatalog,
    part_id: str,
    animation_id: str,
    camera_height: str = "low",
) -> Image.Image:
    part = catalog.part(part_id)
    path = part.animation_path(animation_id, camera_height)
    if path is None:
        raise CharacterForgeError(f"Part {part_id!r} has no {animation_id!r} animation")
    return _load_rgba(str(path), None).copy()


def load_part_render_layer(
    catalog: CharacterCatalog,
    part_id: str,
    render_layer: str,
    animation_id: str,
    camera_height: str = "low",
) -> Image.Image:
    part = catalog.part(part_id)
    path = part.render_layer_path(render_layer, animation_id, camera_height)
    if path is None:
        raise CharacterForgeError(
            f"Part {part_id!r} has no {render_layer!r}/{animation_id!r} animation"
        )
    return _load_rgba(str(path), None).copy()


def _combined_part_alpha(
    catalog: CharacterCatalog,
    part: CharacterPart,
    animation_id: str,
    camera_height: str,
    size: tuple[int, int],
) -> Image.Image:
    alpha = Image.new("L", size, 0)
    layers = tuple(part.render_layers) if part.render_layers else (part.layer,)
    for render_layer in layers:
        path = part.render_layer_path(render_layer, animation_id, camera_height)
        if path is None:
            continue
        source = _load_rgba(str(path), None)
        if source.size != size:
            raise CharacterForgeError(
                f"Occlusion source {part.id!r} is {source.size}; expected {size}"
            )
        alpha = ImageChops.lighter(alpha, source.getchannel("A"))
    return alpha


def _apply_selected_part_alpha_occlusion(
    overlay: Image.Image,
    part: CharacterPart,
    selected: list[CharacterPart],
    catalog: CharacterCatalog,
    animation_id: str,
    camera_height: str,
) -> Image.Image:
    """Hide a part wherever matching selected component pixels are opaque."""
    result = overlay
    if part.slot == "hair":
        for occluder in selected:
            if occluder.id == part.id:
                continue
            if occluder.hair_occlusion == "hide":
                return Image.new("RGBA", result.size, (0, 0, 0, 0))
            if occluder.hair_occlusion != "clip":
                continue
            occluder_alpha = _combined_part_alpha(
                catalog, occluder, animation_id, camera_height, result.size
            )
            keep_mask = ImageChops.invert(occluder_alpha)
            masked_alpha = ImageChops.multiply(result.getchannel("A"), keep_mask)
            result = result.copy()
            result.putalpha(masked_alpha)
    if not part.alpha_occluded_by_tags:
        return result
    occluding_tags = set(part.alpha_occluded_by_tags)
    for occluder in selected:
        if (
            occluder.id == part.id
            or occluder.animation_path(animation_id, camera_height) is None
            or not (occluding_tags & set(occluder.tags))
        ):
            continue
        occluder_alpha = _combined_part_alpha(
            catalog, occluder, animation_id, camera_height, result.size
        )
        keep_mask = ImageChops.invert(occluder_alpha)
        masked_alpha = ImageChops.multiply(result.getchannel("A"), keep_mask)
        result = result.copy()
        result.putalpha(masked_alpha)
    return result


def _apply_selected_direction_mirrors(
    sheet: Image.Image,
    animation: CharacterAnimation,
    selected: list[CharacterPart],
    animation_id: str,
) -> Image.Image:
    """Derive requested final directions by mirroring the complete composite."""
    mirrors: dict[str, tuple[str, str]] = {}
    for part in selected:
        for target, source in part.direction_mirrors.get(animation_id, {}).items():
            previous = mirrors.get(target)
            if previous is not None and previous[0] != source:
                raise CharacterForgeError(
                    f"Parts {previous[1]!r} and {part.id!r} request conflicting "
                    f"mirrors for {animation_id!r}/{target!r}"
                )
            mirrors[target] = (source, part.id)
    if not mirrors:
        return sheet
    source_sheet = sheet.copy()
    result = sheet.copy()
    for target, (source, _part_id) in mirrors.items():
        frame_count = animation.frame_count(target)
        for frame_index in range(frame_count):
            source_frame = source_sheet.crop(
                animation.frame_box(source, frame_index)
            ).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            result.paste(source_frame, animation.frame_box(target, frame_index))
    return result


def composite_character_animation(
    catalog: CharacterCatalog,
    recipe: CharacterRecipe,
    animation_id: str,
) -> Image.Image:
    validate_recipe(catalog, recipe)
    base = catalog.base(recipe.base_id)
    if animation_id not in base.animations:
        raise CharacterForgeError(f"Unknown character animation {animation_id!r}")
    body = load_base_animation(
        catalog, recipe.base_id, animation_id, recipe.camera_height
    )
    result = Image.new("RGBA", body.size, (0, 0, 0, 0))
    selected = [
        catalog.part(part_id)
        for slot in CHARACTER_SLOTS
        if (part_id := recipe.parts.get(slot)) is not None
    ]
    mirror_active: dict[str, CharacterPart] = {}
    for layer in CHARACTER_LAYER_ORDER:
        if layer == "body":
            if result.getbbox() is None:
                # Preserve canonical hidden RGB bytes when nothing renders behind the body.
                result = body.copy()
            else:
                result = Image.alpha_composite(result, body)
        for part in selected:
            if (
                part.render_layer_path(layer, animation_id, recipe.camera_height) is None
            ):
                continue
            overlay = load_part_render_layer(
                catalog, part.id, layer, animation_id, recipe.camera_height
            )
            selected_color = recipe.part_colors.get(part.id)
            if selected_color is not None:
                overlay = recolor_part_ramp(overlay, part, selected_color)
            overlay = _apply_selected_part_alpha_occlusion(
                overlay,
                part,
                selected,
                catalog,
                animation_id,
                recipe.camera_height,
            )
            if overlay.getchannel("A").getbbox() is not None:
                mirror_active[part.id] = part
            if overlay.size != result.size:
                raise CharacterForgeError(
                    f"Part {part.id!r} {animation_id!r} sheet is {overlay.size}; base sheet is {result.size}"
                )
            result = Image.alpha_composite(result, overlay)
    return _apply_selected_direction_mirrors(
        result,
        base.animations[animation_id],
        list(mirror_active.values()),
        animation_id,
    )


def extract_character_frame(
    sheet: Image.Image,
    animation: CharacterAnimation,
    direction: str,
    frame_index: int,
) -> Image.Image:
    if sheet.size != animation.sheet_size:
        raise CharacterForgeError(
            f"Animation sheet is {sheet.size}, expected {animation.sheet_size}"
        )
    return sheet.crop(animation.frame_box(direction, frame_index)).copy()


def randomize_recipe(
    catalog: CharacterCatalog,
    base_id: str,
    seed: int,
    *,
    name: str = "character",
    camera_height: str = "low",
) -> CharacterRecipe:
    catalog.base(base_id)
    generator = random.Random(seed)
    selections = {slot: None for slot in CHARACTER_SLOTS}
    claimed: set[str] = set()
    for slot in CHARACTER_SLOTS:
        candidates = list(
            catalog.parts_for_slot(slot, base_id, camera_height)
        )
        generator.shuffle(candidates)
        choices: list[CharacterPart | None] = [None, *candidates]
        choice = generator.choice(choices)
        if choice is not None and not (choice.claimed_slots & claimed):
            selections[slot] = choice.id
            claimed.update(choice.claimed_slots)
    return CharacterRecipe(
        base_id=base_id,
        camera_height=camera_height,
        name=name,
        parts=selections,
        random_seed=seed,
    )


def recipe_json(recipe: CharacterRecipe) -> str:
    return json.dumps(recipe.to_dict(), indent=2) + "\n"


def load_recipe(path: str | Path) -> CharacterRecipe:
    recipe_path = Path(path)
    try:
        data = json.loads(recipe_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CharacterForgeError(f"Could not load character recipe: {exc}") from exc
    if not isinstance(data, Mapping):
        raise CharacterForgeError("Character recipe root must be an object")
    return CharacterRecipe.from_dict(data)


def save_recipe(recipe: CharacterRecipe, path: str | Path) -> Path:
    recipe_path = Path(path)
    recipe_path.parent.mkdir(parents=True, exist_ok=True)
    recipe_path.write_text(recipe_json(recipe), encoding="utf-8")
    return recipe_path


def local_recipe_directory() -> Path:
    return Path.home() / ".pixelforge" / "characters"


def safe_character_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-._")
    return cleaned or "character"


def local_recipe_path(name: str) -> Path:
    return local_recipe_directory() / f"{safe_character_name(name)}.json"


def export_character(
    catalog: CharacterCatalog,
    recipe: CharacterRecipe,
    output_directory: str | Path,
    *,
    stem: str | None = None,
) -> dict[str, Path]:
    validate_recipe(catalog, recipe)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    export_stem = safe_character_name(stem or recipe.name)
    base = catalog.base(recipe.base_id)
    outputs: dict[str, Path] = {}
    for animation_id in base.animations:
        sheet = composite_character_animation(catalog, recipe, animation_id)
        path = directory / f"{export_stem}-{animation_id}.png"
        sheet.save(path)
        outputs[animation_id] = path
    recipe_path = directory / f"{export_stem}.json"
    save_recipe(recipe, recipe_path)
    outputs["recipe"] = recipe_path
    return outputs
