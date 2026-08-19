from __future__ import annotations

import base64
import colorsys
import hashlib
import json
import math
import os
import random
import shutil
import statistics
import time
from collections import Counter, deque
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Iterable, Mapping

import yaml
from PIL import Image, ImageDraw

from src.core.character_forge import (
    CHARACTER_LAYER_ORDER,
    CHARACTER_SLOTS,
    DEFAULT_CHARACTER_ASSET_ROOT,
    CharacterAnimation,
    CharacterForgeError,
    color_hex_to_rgb,
    create_default_catalog,
    load_base_animation,
    load_character_sheet_specs,
    load_component_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = DEFAULT_CHARACTER_ASSET_ROOT
PIPELINE_ROOT = PROJECT_ROOT / "art_pipeline"
CATALOG_PATH = ASSET_ROOT / "custom_parts" / "components.yaml"
SPEC_PATH = ASSET_ROOT / "sheet_specs.json"
PILOT_COMPONENT_IDS = (
    "weathered_captains_cap_01",
    "round_spectacles_01",
    "linen_neckerchief_01",
    "wide_leather_belt_01",
    "leather_work_vest_01",
    "plain_leather_gloves_01",
    "ankle_work_boots_01",
)
COMPONENT_STATUSES = {
    "idea",
    "queued",
    "generated",
    "review",
    "approved",
    "rejected",
    "incomplete",
}
NORMALIZATION_METHODS = ("center", "dominant", "palette")


class PipelineError(RuntimeError):
    """Raised for a safe, actionable component-pipeline failure."""


class PermanentAPIError(PipelineError):
    """A non-retryable API rejection scoped to one generated candidate."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id


@dataclass(frozen=True, slots=True)
class ComponentIdea:
    id: str
    slot: str
    layer: str
    concept: str
    tags: tuple[str, ...]
    fit: str
    priority: str
    status: str


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _image_data(image: Image.Image):
    return (
        image.get_flattened_data()
        if hasattr(image, "get_flattened_data")
        else image.getdata()
    )


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Could not read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Expected an object in {path}")
    return value


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def load_component_ideas(path: str | Path | None = None) -> tuple[ComponentIdea, ...]:
    catalog_path = Path(path) if path is not None else CATALOG_PATH
    try:
        raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Could not load component catalog: {exc}") from exc
    if not isinstance(raw, Mapping) or not isinstance(raw.get("components"), list):
        raise PipelineError("Component catalog must contain a components list")
    ideas: list[ComponentIdea] = []
    ids: set[str] = set()
    for index, item in enumerate(raw["components"]):
        if not isinstance(item, Mapping):
            raise PipelineError(f"Component record {index + 1} is not an object")
        required = ("id", "slot", "layer", "concept", "fit", "priority", "status")
        if any(not isinstance(item.get(key), str) or not item[key] for key in required):
            raise PipelineError(
                f"Component record {index + 1} is missing required text"
            )
        component_id = str(item["id"])
        if component_id in ids:
            raise PipelineError(f"Duplicate component id {component_id!r}")
        ids.add(component_id)
        tags = item.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise PipelineError(f"Component {component_id!r} tags must be text")
        slot = str(item["slot"])
        layer = str(item["layer"])
        if slot not in CHARACTER_SLOTS:
            raise PipelineError(
                f"Component {component_id!r} uses unknown slot {slot!r}"
            )
        if layer not in CHARACTER_LAYER_ORDER:
            raise PipelineError(
                f"Component {component_id!r} uses unknown layer {layer!r}"
            )
        status = str(item["status"])
        if status not in COMPONENT_STATUSES:
            raise PipelineError(
                f"Component {component_id!r} has invalid status {status!r}"
            )
        ideas.append(
            ComponentIdea(
                id=component_id,
                slot=slot,
                layer=layer,
                concept=str(item["concept"]),
                tags=tuple(tags),
                fit=str(item["fit"]),
                priority=str(item["priority"]),
                status=status,
            )
        )
    return tuple(ideas)


def component_idea(component_id: str) -> ComponentIdea:
    for idea in load_component_ideas():
        if idea.id == component_id:
            return idea
    raise PipelineError(f"Unknown component idea {component_id!r}")


def _animation_spec(
    specs: Mapping[str, object], animation_id: str
) -> Mapping[str, object]:
    animations = specs.get("animations")
    if not isinstance(animations, Mapping) or not isinstance(
        animations.get(animation_id), Mapping
    ):
        raise PipelineError(f"Unknown animation specification {animation_id!r}")
    return animations[animation_id]


def _asset_path(relative: object) -> Path:
    if not isinstance(relative, str) or not relative:
        raise PipelineError("Character asset path is invalid")
    path = (ASSET_ROOT / relative).resolve()
    if ASSET_ROOT.resolve() not in path.parents:
        raise PipelineError(f"Character asset escapes its root: {relative}")
    return path


def assemble_authoritative_run() -> Image.Image:
    specs = load_character_sheet_specs(ASSET_ROOT)
    run = _animation_spec(specs, "run")
    sources = run.get("sources")
    if not isinstance(sources, list):
        raise PipelineError("Run sources are missing")
    raw_rows = run.get("direction_rows")
    raw_counts = run.get("direction_frame_counts")
    if not isinstance(raw_rows, Mapping) or not isinstance(raw_counts, Mapping):
        raise PipelineError("Run direction geometry is missing")
    rows = {str(direction): int(row) for direction, row in raw_rows.items()}
    counts = {str(direction): int(count) for direction, count in raw_counts.items()}
    frame_width, frame_height = (int(value) for value in specs["frame_size"])
    sheet_size = tuple(int(value) for value in run["sheet_size"])
    result = Image.new("RGBA", sheet_size, (0, 0, 0, 0))
    found: set[str] = set()
    for source in sources:
        if not isinstance(source, Mapping) or source.get("row") not in rows:
            raise PipelineError("Run source row metadata is invalid")
        row = str(source["row"])
        path = _asset_path(source.get("file"))
        with Image.open(path) as opened:
            strip = opened.convert("RGBA")
        expected_size = (counts[row] * frame_width, frame_height)
        if strip.size != expected_size:
            raise PipelineError(
                f"Run source {path.name} is {strip.size}, expected {expected_size}"
            )
        result.paste(strip, (0, rows[row] * frame_height))
        found.add(row)
    if found != set(rows):
        raise PipelineError(f"Run sources are incomplete: {sorted(set(rows) - found)}")
    return result


def validate_canonical_checksums() -> None:
    specs = load_character_sheet_specs(ASSET_ROOT)
    animations = specs.get("animations")
    if not isinstance(animations, Mapping):
        raise PipelineError("Animation specifications are missing")
    for animation_id, raw in animations.items():
        if not isinstance(raw, Mapping):
            raise PipelineError(f"Animation {animation_id!r} is invalid")
        runtime_path = _asset_path(raw.get("runtime_file"))
        expected_runtime = raw.get("runtime_sha256")
        if sha256_file(runtime_path) != expected_runtime:
            raise PipelineError(
                f"Canonical {animation_id} master checksum changed. Run "
                "`python component_pipeline.py rebaseline --confirm human-01` only if intentional."
            )
        sources = raw.get("sources", [])
        if not isinstance(sources, list):
            raise PipelineError(f"Animation {animation_id!r} sources are invalid")
        for source in sources:
            if not isinstance(source, Mapping):
                raise PipelineError(f"Animation {animation_id!r} source is invalid")
            path = _asset_path(source.get("file"))
            if sha256_file(path) != source.get("sha256"):
                raise PipelineError(f"Canonical source checksum changed: {path.name}")
        expected_size = tuple(int(value) for value in raw["sheet_size"])
        with Image.open(runtime_path) as image:
            if image.size != expected_size or image.mode != "RGBA":
                raise PipelineError(
                    f"Canonical {animation_id} must be RGBA {expected_size}, got {image.mode} {image.size}"
                )
    expected_run = assemble_authoritative_run()
    run_path = _asset_path(_animation_spec(specs, "run").get("runtime_file"))
    with Image.open(run_path) as current:
        if current.convert("RGBA").tobytes() != expected_run.tobytes():
            raise PipelineError(
                "Derived run.png does not match its authoritative strips"
            )


def validate_pipeline() -> dict[str, int]:
    validate_canonical_checksums()
    ideas = load_component_ideas()
    catalog = create_default_catalog(ASSET_ROOT, include_incomplete=True)
    try:
        from src.core.character_forge import validate_catalog

        validate_catalog(catalog)
    except CharacterForgeError as exc:
        raise PipelineError(str(exc)) from exc
    return {
        "component_ideas": len(ideas),
        "production_components": len(catalog.parts),
        "animations": len(catalog.bases[0].animations),
    }


def rebaseline_canonical(base_id: str, *, confirmed: bool) -> dict[str, str]:
    if base_id != "human-01" or not confirmed:
        raise PipelineError("Rebaseline requires `--confirm human-01`")
    specs = load_character_sheet_specs(ASSET_ROOT)
    animations = specs.get("animations")
    if not isinstance(animations, dict):
        raise PipelineError("Animation specifications are invalid")
    run_image = assemble_authoritative_run()
    run_path = _asset_path(animations["run"]["runtime_file"])
    run_image.save(run_path)
    hashes: dict[str, str] = {}
    for animation_id, raw in animations.items():
        if not isinstance(raw, dict):
            raise PipelineError(f"Animation {animation_id!r} is invalid")
        runtime_path = _asset_path(raw["runtime_file"])
        expected_size = tuple(int(value) for value in raw["sheet_size"])
        with Image.open(runtime_path) as image:
            if image.size != expected_size or image.mode != "RGBA":
                raise PipelineError(
                    f"Cannot rebaseline changed geometry for {animation_id}"
                )
        raw["runtime_sha256"] = sha256_file(runtime_path)
        hashes[str(animation_id)] = str(raw["runtime_sha256"])
        for source in raw.get("sources", []):
            source_path = _asset_path(source["file"])
            source["sha256"] = sha256_file(source_path)
    _write_json(SPEC_PATH, specs)
    return hashes


def _matte_rgb(specs: Mapping[str, object]) -> tuple[int, int, int]:
    generation = specs.get("generation")
    if not isinstance(generation, Mapping) or not isinstance(
        generation.get("matte"), str
    ):
        raise PipelineError("Generation matte is missing")
    return color_hex_to_rgb(generation["matte"])


def _mannequin_config(specs: Mapping[str, object]) -> Mapping[str, object]:
    generation = specs.get("generation")
    if not isinstance(generation, Mapping):
        raise PipelineError("Generation settings are missing")
    config = generation.get("mannequin")
    if not isinstance(config, Mapping) or config.get("enabled") is not True:
        raise PipelineError("Reserved mannequin-ramp settings are missing or disabled")
    for name in ("target_dark", "target_light"):
        value = config.get(name)
        if not isinstance(value, list) or len(value) != 3:
            raise PipelineError(f"Mannequin {name} must contain three RGB values")
    return config


def _is_mannequin_source_color(
    color: tuple[int, int, int, int],
    config: Mapping[str, object],
) -> bool:
    red, green, blue, alpha = color
    return (
        alpha > 0
        and red >= int(config["minimum_red"])
        and red >= green + int(config["minimum_red_lead"])
        and green >= blue + int(config["minimum_green_lead"])
    )


def build_mannequin_ramp(
    native: Image.Image,
    config: Mapping[str, object],
) -> dict[tuple[int, int, int], tuple[int, int, int]]:
    colors = sorted(
        {
            color
            for color in _image_data(native.convert("RGBA"))
            if _is_mannequin_source_color(color, config)
        },
        key=lambda color: (
            0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2],
            color,
        ),
    )
    if not colors:
        raise PipelineError("Canonical base contains no colors for the mannequin ramp")
    dark = tuple(int(value) for value in config["target_dark"])
    light = tuple(int(value) for value in config["target_light"])
    denominator = max(1, len(colors) - 1)
    mapping: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    used: set[tuple[int, int, int]] = set()
    for index, source in enumerate(colors):
        amount = index / denominator
        target = tuple(
            round(dark[channel] + (light[channel] - dark[channel]) * amount)
            for channel in range(3)
        )
        if target in used:
            red, green, blue = target
            alternatives = (
                (red + offset, green, blue)
                for radius in range(1, 256)
                for offset in (radius, -radius)
            )
            target = next(
                (
                    candidate
                    for candidate in alternatives
                    if all(0 <= channel <= 255 for channel in candidate)
                    and candidate[2] > candidate[1] > candidate[0]
                    and candidate not in used
                ),
                (),
            )
            if not target:
                raise PipelineError(
                    "Configured mannequin ramp cannot represent every source shade uniquely"
                )
        used.add(target)
        mapping[source[:3]] = target
    return mapping


def apply_mannequin_ramp(
    image: Image.Image,
    mapping: Mapping[tuple[int, int, int], tuple[int, int, int]],
) -> Image.Image:
    source = image.convert("RGBA")
    result = Image.new("RGBA", source.size, (0, 0, 0, 0))
    result.putdata(
        [
            (*mapping.get(pixel[:3], pixel[:3]), pixel[3])
            for pixel in _image_data(source)
        ]
    )
    return result


def reverse_mannequin_ramp(
    image: Image.Image,
    mapping: Mapping[tuple[int, int, int], tuple[int, int, int]],
    *,
    threshold: float,
    canonical: Image.Image | None = None,
    matte_rgb: tuple[int, int, int] | None = None,
    matte_restore_threshold: float = 0.0,
) -> Image.Image:
    reverse = {target: source for source, target in mapping.items()}
    targets = tuple((*target, 255) for target in reverse)
    if not targets:
        raise PipelineError("Mannequin ramp is empty")
    result = image.convert("RGBA")
    canonical_rgba = canonical.convert("RGBA") if canonical is not None else None
    if canonical_rgba is not None and canonical_rgba.size != result.size:
        raise PipelineError("Canonical mannequin reversal image has the wrong geometry")
    if canonical_rgba is not None and matte_rgb is None:
        raise PipelineError("Position-aware mannequin reversal requires a matte color")
    canonical_pixels = canonical_rgba.load() if canonical_rgba is not None else None
    pixels = list(_image_data(result))
    threshold_squared = threshold * threshold
    lookup: dict[tuple[int, int, int, int], tuple[int, int, int, int]] = {}
    for pixel in set(pixels):
        nearest = min(
            targets,
            key=lambda target: sum(
                (int(pixel[channel]) - int(target[channel])) ** 2
                for channel in range(3)
            ),
        )
        distance_squared = sum(
            (int(pixel[channel]) - int(nearest[channel])) ** 2 for channel in range(3)
        )
        lookup[pixel] = (
            (*reverse[nearest[:3]], pixel[3])
            if distance_squared <= threshold_squared
            else pixel
        )
    restored: list[tuple[int, int, int, int]] = []
    for index, pixel in enumerate(pixels):
        x = index % result.width
        y = index // result.width
        source = canonical_pixels[x, y] if canonical_pixels is not None else None
        if (
            source is not None
            and matte_restore_threshold > 0
            and rgb_distance(pixel, matte_rgb) <= matte_restore_threshold
        ):
            restored.append(source if source[3] > 0 else (*matte_rgb, 255))
            continue
        mapped = lookup[pixel]
        if mapped == pixel or source is None:
            restored.append(mapped)
        else:
            restored.append(source if source[3] > 0 else (*matte_rgb, 255))
    result.putdata(restored)
    return result


def restore_generation_background(
    image: Image.Image,
    animation: CharacterAnimation,
    region: tuple[int, int, int, int],
    *,
    matte_rgb: tuple[int, int, int],
    tolerance: float = 48.0,
    dark_ceiling: int = 96,
    matte_threshold: float = 96.0,
) -> Image.Image:
    result = image.convert("RGBA")
    pixels = result.load()
    left, top, right, bottom = region
    for direction, row in animation.direction_rows.items():
        for frame_index in range(animation.frame_count(direction)):
            x0 = frame_index * animation.frame_size[0] + left
            y0 = row * animation.frame_size[1] + top
            x1 = min(result.width, frame_index * animation.frame_size[0] + right)
            y1 = min(result.height, row * animation.frame_size[1] + bottom)
            if x0 >= x1 or y0 >= y1:
                continue
            perimeter = [(x, y) for x in range(x0, x1) for y in (y0, y1 - 1)] + [
                (x, y) for y in range(y0 + 1, y1 - 1) for x in (x0, x1 - 1)
            ]
            border_colors = Counter(pixels[x, y][:3] for x, y in perimeter)
            background_colors = tuple(
                color
                for color in border_colors
                if max(color) <= dark_ceiling
                or rgb_distance(color, matte_rgb) <= matte_threshold
            )
            if not background_colors:
                background_colors = (border_colors.most_common(1)[0][0],)

            def is_background(
                color: tuple[int, int, int, int] | tuple[int, int, int],
            ) -> bool:
                return (
                    min(rgb_distance(color, target) for target in background_colors)
                    <= tolerance
                )

            queue = deque((x, y) for x, y in perimeter if is_background(pixels[x, y]))
            visited = set(queue)
            while queue:
                x, y = queue.popleft()
                color = pixels[x, y]
                if not is_background(color):
                    continue
                pixels[x, y] = (*matte_rgb, 255)
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if x0 <= nx < x1 and y0 <= ny < y1 and (nx, ny) not in visited:
                        visited.add((nx, ny))
                        queue.append((nx, ny))
    return result


def clamp_outside_generation_region(
    generated: Image.Image,
    canonical: Image.Image,
    allowed_region: Image.Image,
    *,
    matte_rgb: tuple[int, int, int],
) -> Image.Image:
    if len({generated.size, canonical.size, allowed_region.size}) != 1:
        raise PipelineError(
            "Generated, canonical, and region images must share geometry"
        )
    result = generated.convert("RGBA")
    base = canonical.convert("RGBA")
    allowed = allowed_region.convert("L")
    output = result.load()
    base_pixels = base.load()
    allowed_pixels = allowed.load()
    for y in range(result.height):
        for x in range(result.width):
            if allowed_pixels[x, y] != 0:
                continue
            source = base_pixels[x, y]
            output[x, y] = source if source[3] > 0 else (*matte_rgb, 255)
    return result


def _mannequin_ramp_path(animation_id: str) -> Path:
    return PIPELINE_ROOT / "mannequin_ramps" / f"{animation_id}.json"


def load_mannequin_ramp(
    animation_id: str,
) -> tuple[dict[tuple[int, int, int], tuple[int, int, int]], dict[str, object]]:
    path = _mannequin_ramp_path(animation_id)
    if not path.is_file():
        raise PipelineError(f"Prepared mannequin ramp is missing: {path}")
    data = _read_json(path)
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise PipelineError(f"Prepared mannequin ramp is invalid: {path}")
    mapping = {
        color_hex_to_rgb(entry["source"]): color_hex_to_rgb(entry["target"])
        for entry in entries
        if isinstance(entry, Mapping)
        and isinstance(entry.get("source"), str)
        and isinstance(entry.get("target"), str)
    }
    if len(mapping) != len(entries):
        raise PipelineError(f"Prepared mannequin ramp contains invalid entries: {path}")
    return mapping, data


def _rgb_hex(color: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02X}" for channel in color)


def create_allowed_region_mask(
    animation: CharacterAnimation,
    region: tuple[int, int, int, int],
) -> Image.Image:
    mask = Image.new("L", animation.sheet_size, 0)
    draw = ImageDraw.Draw(mask)
    for direction, row in animation.direction_rows.items():
        for frame_index in range(animation.frame_count(direction)):
            frame_left = frame_index * animation.frame_size[0]
            frame_top = row * animation.frame_size[1]
            left, top, right, bottom = region
            draw.rectangle(
                (
                    frame_left + left,
                    frame_top + top,
                    frame_left + right - 1,
                    frame_top + bottom - 1,
                ),
                fill=255,
            )
    return mask


def create_native_region_mask(
    animation: CharacterAnimation,
    region: tuple[int, int, int, int],
) -> Image.Image:
    """Return an API mask: opaque means protected, transparent means editable."""
    allowed = create_allowed_region_mask(animation, region)
    alpha = allowed.point(lambda value: 0 if value else 255)
    mask = Image.new("RGBA", animation.sheet_size, (255, 255, 255, 255))
    mask.putalpha(alpha)
    return mask


def _generation_transform(
    native: Image.Image,
    animation_spec: Mapping[str, object],
    matte: tuple[int, int, int],
) -> Image.Image:
    scale = 4
    opaque = Image.new("RGBA", native.size, (*matte, 255))
    opaque.alpha_composite(native.convert("RGBA"))
    scaled = opaque.resize(
        (native.width * scale, native.height * scale),
        Image.Resampling.NEAREST,
    )
    left, top, right, bottom = (int(value) for value in animation_spec["padding"])
    expected = tuple(int(value) for value in animation_spec["generation_size"])
    if (scaled.width + left + right, scaled.height + top + bottom) != expected:
        raise PipelineError("Generation transform does not match the declared geometry")
    result = Image.new("RGBA", expected, (*matte, 255))
    result.paste(scaled, (left, top))
    return result


def prepare_pipeline() -> dict[str, list[Path]]:
    validate_pipeline()
    specs = load_character_sheet_specs(ASSET_ROOT)
    catalog = create_default_catalog(ASSET_ROOT, include_incomplete=True)
    base = catalog.base(str(specs.get("base_id", "human-01")))
    matte = _matte_rgb(specs)
    mannequin_config = _mannequin_config(specs)
    outputs: dict[str, list[Path]] = {
        "canonical": [],
        "mannequins": [],
        "ramps": [],
        "masters": [],
        "masks": [],
    }
    for directory in (
        PIPELINE_ROOT / "canonical",
        PIPELINE_ROOT / "mannequins",
        PIPELINE_ROOT / "mannequin_ramps",
        PIPELINE_ROOT / "generation_masters",
        PIPELINE_ROOT / "masks",
        PIPELINE_ROOT / "catalog",
        PIPELINE_ROOT / "jobs",
        PIPELINE_ROOT / "review_queue",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    regions = specs.get("regions")
    if not isinstance(regions, Mapping):
        raise PipelineError("Slot regions are missing")
    for animation_id, animation in base.animations.items():
        native = load_base_animation(catalog, base.id, animation_id)
        canonical_path = PIPELINE_ROOT / "canonical" / f"{animation_id}.png"
        native.save(canonical_path)
        outputs["canonical"].append(canonical_path)
        ramp = build_mannequin_ramp(native, mannequin_config)
        mannequin = apply_mannequin_ramp(native, ramp)
        mannequin_path = PIPELINE_ROOT / "mannequins" / f"{animation_id}.png"
        mannequin.save(mannequin_path)
        outputs["mannequins"].append(mannequin_path)
        ramp_path = _mannequin_ramp_path(animation_id)
        ramp_document = {
            "schema_version": 1,
            "animation_id": animation_id,
            "name": mannequin_config["name"],
            "processing_version": mannequin_config["processing_version"],
            "canonical_sha256": sha256_file(canonical_path),
            "mannequin_sha256": sha256_file(mannequin_path),
            "reverse_threshold": mannequin_config["reverse_threshold"],
            "leak_threshold": mannequin_config["leak_threshold"],
            "matte_restore_threshold": mannequin_config["matte_restore_threshold"],
            "border_background_tolerance": mannequin_config[
                "border_background_tolerance"
            ],
            "border_dark_ceiling": mannequin_config["border_dark_ceiling"],
            "border_matte_threshold": mannequin_config["border_matte_threshold"],
            "entries": [
                {"source": _rgb_hex(source), "target": _rgb_hex(target)}
                for source, target in ramp.items()
            ],
        }
        _write_json(ramp_path, ramp_document)
        outputs["ramps"].append(ramp_path)
        animation_spec = _animation_spec(specs, animation_id)
        master = _generation_transform(mannequin, animation_spec, matte)
        master_path = PIPELINE_ROOT / "generation_masters" / f"{animation_id}.png"
        master.save(master_path)
        outputs["masters"].append(master_path)
        for slot, raw_region in regions.items():
            if (
                not isinstance(slot, str)
                or not isinstance(raw_region, list)
                or len(raw_region) != 4
            ):
                raise PipelineError("Slot region metadata is invalid")
            region = tuple(int(value) for value in raw_region)
            native_mask = create_native_region_mask(animation, region)
            scaled_mask = native_mask.resize(
                (native_mask.width * 4, native_mask.height * 4),
                Image.Resampling.NEAREST,
            )
            left, top, right, bottom = (
                int(value) for value in animation_spec["padding"]
            )
            api_mask = Image.new(
                "RGBA",
                tuple(int(value) for value in animation_spec["generation_size"]),
                (255, 255, 255, 255),
            )
            api_mask.paste(scaled_mask, (left, top))
            mask_path = PIPELINE_ROOT / "masks" / slot / f"{animation_id}.png"
            mask_path.parent.mkdir(parents=True, exist_ok=True)
            api_mask.save(mask_path)
            outputs["masks"].append(mask_path)
    catalog_snapshot = {
        "created_at": utc_now(),
        "components": [
            {
                "id": idea.id,
                "slot": idea.slot,
                "layer": idea.layer,
                "concept": idea.concept,
                "tags": list(idea.tags),
                "fit": idea.fit,
                "priority": idea.priority,
                "status": idea.status,
            }
            for idea in load_component_ideas()
        ],
    }
    _write_json(PIPELINE_ROOT / "catalog" / "components.json", catalog_snapshot)
    return outputs


def _block_representative(
    block: list[tuple[int, int, int, int]],
) -> tuple[int, int, int, int]:
    counts = Counter(block)
    highest = max(counts.values())
    tied = [color for color, count in counts.items() if count == highest]
    if len(tied) == 1:
        return tied[0]
    medians = tuple(
        statistics.median(color[channel] for color in block) for channel in range(4)
    )
    return min(
        tied,
        key=lambda color: (
            sum((color[channel] - medians[channel]) ** 2 for channel in range(4)),
            color,
        ),
    )


def _nearest_color(
    color: tuple[int, int, int, int],
    palette: tuple[tuple[int, int, int, int], ...],
    threshold: float,
) -> tuple[int, int, int, int]:
    nearest = min(palette, key=lambda value: rgb_distance(color, value))
    return nearest if rgb_distance(color, nearest) <= threshold else color


def _snap_image_to_palette(
    image: Image.Image,
    palette: tuple[tuple[int, int, int, int], ...],
    threshold: float,
) -> Image.Image:
    result = image.convert("RGBA")
    if not palette:
        return result
    pixels = list(_image_data(result))
    lookup = {color: _nearest_color(color, palette, threshold) for color in set(pixels)}
    result.putdata([lookup[color] for color in pixels])
    return result


def normalize_generated_image(
    generated: Image.Image,
    native_size: tuple[int, int],
    padding: tuple[int, int, int, int],
    *,
    method: str = "dominant",
    canonical_palette: Iterable[tuple[int, int, int, int]] = (),
) -> Image.Image:
    if method not in NORMALIZATION_METHODS:
        raise PipelineError(f"Unknown normalization method {method!r}")
    left, top, right, bottom = padding
    expected_size = (
        native_size[0] * 4 + left + right,
        native_size[1] * 4 + top + bottom,
    )
    source = generated.convert("RGBA")
    if source.size != expected_size:
        raise PipelineError(
            f"Generated image is {source.size}, expected {expected_size}"
        )
    cropped = source.crop((left, top, source.width - right, source.height - bottom))
    if method == "center":
        return cropped.resize(native_size, Image.Resampling.NEAREST)
    src = cropped.load()
    result = Image.new("RGBA", native_size, (0, 0, 0, 0))
    out = result.load()
    for y in range(native_size[1]):
        for x in range(native_size[0]):
            block = [src[x * 4 + dx, y * 4 + dy] for dy in range(4) for dx in range(4)]
            out[x, y] = _block_representative(block)
    if method == "palette":
        frequent = [
            color for color, _count in Counter(_image_data(result)).most_common(16)
        ]
        canonical = tuple(canonical_palette)
        palette = tuple(dict.fromkeys(canonical if canonical else tuple(frequent)))
        result = _snap_image_to_palette(result, palette, 32.0)
    return result


def rgb_distance(
    first: tuple[int, int, int, int] | tuple[int, int, int],
    second: tuple[int, int, int, int] | tuple[int, int, int],
) -> float:
    return math.sqrt(
        sum((int(first[index]) - int(second[index])) ** 2 for index in range(3))
    )


def extract_component_overlay(
    base: Image.Image,
    generated_native: Image.Image,
    allowed_region: Image.Image,
    *,
    matte_rgb: tuple[int, int, int] = (255, 0, 255),
    difference_threshold: float = 24.0,
    matte_threshold: float = 20.0,
) -> Image.Image:
    base_rgba = base.convert("RGBA")
    generated_rgba = generated_native.convert("RGBA")
    mask = allowed_region.convert("L")
    if base_rgba.size != generated_rgba.size or base_rgba.size != mask.size:
        raise PipelineError(
            "Base, generated image, and region mask must have identical geometry"
        )
    output = Image.new("RGBA", base_rgba.size, (0, 0, 0, 0))
    out = output.load()
    base_pixels = base_rgba.load()
    generated_pixels = generated_rgba.load()
    allowed = mask.load()
    for y in range(base_rgba.height):
        for x in range(base_rgba.width):
            if allowed[x, y] == 0:
                continue
            source = base_pixels[x, y]
            candidate = generated_pixels[x, y]
            if source[3] == 0:
                changed = rgb_distance(candidate, matte_rgb) > matte_threshold
            else:
                changed = (
                    rgb_distance(candidate, source) > difference_threshold
                    or candidate[3] != source[3]
                )
            if changed:
                out[x, y] = candidate
    return output


def reconstruct_component(base: Image.Image, overlay: Image.Image) -> Image.Image:
    if base.size != overlay.size:
        raise PipelineError("Reconstruction images must have identical geometry")
    return Image.alpha_composite(base.convert("RGBA"), overlay.convert("RGBA"))


def _flatten_on_matte(image: Image.Image, matte: tuple[int, int, int]) -> Image.Image:
    result = Image.new("RGBA", image.size, (*matte, 255))
    result.alpha_composite(image.convert("RGBA"))
    return result


def analyze_candidate(
    base: Image.Image,
    generated_native: Image.Image,
    overlay: Image.Image,
    allowed_region: Image.Image,
    animation: CharacterAnimation,
    *,
    matte_rgb: tuple[int, int, int] = (255, 0, 255),
    difference_threshold: float = 24.0,
    reserved_colors: Iterable[tuple[int, int, int]] = (),
    reserved_color_threshold: float = 0.0,
) -> dict[str, object]:
    if len({base.size, generated_native.size, overlay.size, allowed_region.size}) != 1:
        return {
            "status": "fail",
            "score": 0.0,
            "hard_failures": ["geometry"],
            "warnings": [],
        }
    base_rgba = base.convert("RGBA")
    generated = generated_native.convert("RGBA")
    extracted = overlay.convert("RGBA")
    allowed = allowed_region.convert("L")
    reconstruction = reconstruct_component(base_rgba, extracted)
    flat_reconstruction = _flatten_on_matte(reconstruction, matte_rgb)
    flat_generated = _flatten_on_matte(generated, matte_rgb)
    allowed_pixels = allowed.load()
    base_pixels = base_rgba.load()
    generated_pixels = flat_generated.load()
    overlay_pixels = extracted.load()
    recon_pixels = flat_reconstruction.load()
    outside_changed = 0
    visible_base = 0
    reconstruction_errors: list[float] = []
    silhouette_growth = 0
    edge_contact = False
    region_bbox = allowed.getbbox()
    for y in range(base.height):
        for x in range(base.width):
            source = base_pixels[x, y]
            candidate = generated_pixels[x, y]
            if source[3] > 0:
                visible_base += 1
            if allowed_pixels[x, y] == 0:
                if source[3] == 0:
                    changed = rgb_distance(candidate, matte_rgb) > difference_threshold
                else:
                    changed = rgb_distance(candidate, source) > difference_threshold
                outside_changed += int(changed)
            else:
                reconstruction_errors.append(
                    rgb_distance(recon_pixels[x, y], candidate)
                )
            if overlay_pixels[x, y][3] > 0 and source[3] == 0:
                silhouette_growth += 1
            if overlay_pixels[x, y][3] > 0 and region_bbox is not None:
                left, top, right, bottom = region_bbox
                edge_contact |= x in (left, right - 1) or y in (top, bottom - 1)
    frame_coverage: dict[str, list[int]] = {}
    missing_frames: list[str] = []
    alpha = extracted.getchannel("A")
    for direction in animation.directions:
        counts = []
        for frame_index in range(animation.frame_count(direction)):
            count = sum(
                1
                for value in _image_data(
                    alpha.crop(animation.frame_box(direction, frame_index))
                )
                if value
            )
            counts.append(count)
            if count == 0:
                missing_frames.append(f"{direction}:{frame_index + 1}")
        frame_coverage[direction] = counts
    colors = Counter(pixel for pixel in _image_data(extracted) if pixel[3] > 0)
    reserved = tuple(reserved_colors)
    reserved_leak_pixels = sum(
        count
        for color, count in colors.items()
        if reserved
        and min(rgb_distance(color, target) for target in reserved)
        <= reserved_color_threshold
    )
    partial_alpha = sum(1 for color in colors if 0 < color[3] < 255)
    outside_ratio = outside_changed / max(1, visible_base)
    mean_reconstruction = (
        statistics.fmean(reconstruction_errors) if reconstruction_errors else 0.0
    )
    hard_failures: list[str] = []
    warnings: list[str] = []
    if reserved_leak_pixels:
        hard_failures.append("reserved_mannequin_color_leak")
    if missing_frames:
        hard_failures.append("missing_frame_coverage")
    if outside_ratio > 0.05:
        hard_failures.append("outside_region_drift")
    elif outside_ratio > 0.01:
        warnings.append("outside_region_drift")
    if len(colors) > 48:
        hard_failures.append("palette_complexity")
    elif len(colors) > 24:
        warnings.append("palette_complexity")
    if mean_reconstruction > 16:
        hard_failures.append("reconstruction_error")
    elif mean_reconstruction > 8:
        warnings.append("reconstruction_error")
    if edge_contact:
        warnings.append("region_edge_contact")
    if partial_alpha > 4:
        warnings.append("partial_alpha_noise")
    overlay_count = sum(colors.values())
    if silhouette_growth > max(32, int(overlay_count * 0.75)):
        warnings.append("silhouette_growth")
    outside_score = max(0.0, 1.0 - outside_ratio / 0.05)
    total_frames = sum(
        animation.frame_count(direction) for direction in animation.directions
    )
    coverage_score = 1.0 - len(missing_frames) / max(1, total_frames)
    reconstruction_score = max(0.0, 1.0 - mean_reconstruction / 16.0)
    bounds_score = 0.5 if edge_contact else 1.0
    silhouette_score = max(0.0, 1.0 - silhouette_growth / max(1, overlay_count * 1.5))
    palette_score = max(0.0, 1.0 - max(0, len(colors) - 16) / 32.0)
    score = 100 * (
        outside_score * 0.30
        + coverage_score * 0.20
        + reconstruction_score * 0.20
        + bounds_score * 0.10
        + silhouette_score * 0.10
        + palette_score * 0.10
    )
    status = "fail" if hard_failures else "warn" if warnings else "pass"
    return {
        "status": status,
        "score": round(score, 2),
        "hard_failures": hard_failures,
        "warnings": warnings,
        "metrics": {
            "outside_changed_pixels": outside_changed,
            "outside_drift_ratio": outside_ratio,
            "frame_coverage": frame_coverage,
            "missing_frames": missing_frames,
            "unique_colors": len(colors),
            "partial_alpha_colors": partial_alpha,
            "reserved_mannequin_leak_pixels": reserved_leak_pixels,
            "silhouette_growth_pixels": silhouette_growth,
            "reconstruction_mean_rgb_error": mean_reconstruction,
            "overlay_bbox": extracted.getbbox(),
        },
    }


def _checkerboard(size: tuple[int, int], cell: int = 4) -> Image.Image:
    image = Image.new("RGBA", size, (205, 205, 205, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                draw.rectangle(
                    (x, y, x + cell - 1, y + cell - 1), fill=(150, 150, 150, 255)
                )
    return image


def write_candidate_previews(
    directory: Path,
    base: Image.Image,
    normalized: Image.Image,
    overlay: Image.Image,
    animation: CharacterAnimation,
) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    reconstruction = reconstruct_component(base, overlay)
    checker = _checkerboard(overlay.size)
    checker.alpha_composite(overlay)
    paths = {
        "overlay": directory / "overlay-checker.png",
        "reconstruction": directory / "reconstruction.png",
        "normalized": directory / "normalized.png",
    }
    checker.save(paths["overlay"])
    reconstruction.save(paths["reconstruction"])
    normalized.save(paths["normalized"])
    for direction in animation.directions:
        frames = [
            reconstruction.crop(animation.frame_box(direction, index)).resize(
                (512, 512), Image.Resampling.NEAREST
            )
            for index in range(animation.frame_count(direction))
        ]
        path = directory / f"{direction}.webp"
        frames[0].save(
            path,
            save_all=True,
            append_images=frames[1:],
            duration=max(10, round(1000 / animation.fps)),
            loop=0,
            lossless=True,
        )
        paths[direction] = path
    return paths


def build_generation_prompt(idea: ComponentIdea, animation: CharacterAnimation) -> str:
    forbidden = {
        "headwear": "shirt, pants, beard, face accessory, weapon, necklace, or scenery",
        "face": "hat, shirt, beard, weapon, necklace, or scenery",
        "neck": "hat, coat, gloves, weapon, backpack, or scenery",
        "torso": "coat, hat, gloves, weapon, backpack, unrelated accessory, or scenery",
        "waist": "coat, gloves, hat, weapon, backpack, unrelated accessory, or scenery",
        "outerwear": "hat, face accessory, gloves, weapon, backpack, or scenery",
        "hands": "coat, hat, weapon, jewelry, backpack, or scenery",
        "feet": "coat, hat, gloves, weapon, backpack, or scenery",
    }
    fit_contract = {
        "headwear": (
            "Fit it onto the existing crown and brow. Keep the original head, face, eyes, hair, neck, and facing "
            "direction unchanged; extend beyond the head only where the physical item requires it."
        ),
        "face": (
            "Anchor it to the existing eyes, brow, nose, ears, or jaw as appropriate. Keep the original head outline, "
            "face, eyes, hair, skin, expression, and facing direction unchanged."
        ),
        "neck": (
            "Fit it around the existing neck and collar line. Keep the original head, face, shoulders, torso, and arms "
            "unchanged, and do not turn it into a coat or mantle."
        ),
        "torso": (
            "Fit it over the existing torso and follow the exact shoulder, waist, and arm positions. Keep the original "
            "head, arms, hands, legs, anatomy, and pose unchanged."
        ),
        "waist": (
            "Anchor it to the existing waistline and follow the exact torso and hip position. Keep the original torso, "
            "arms, hands, legs, anatomy, and pose unchanged."
        ),
        "outerwear": (
            "Drape it from the existing shoulders and torso, following the exact pose. Keep the original head, face, "
            "arms, hands, legs, anatomy, and facing direction unchanged; allow only physically necessary garment silhouette growth."
        ),
        "hands": (
            "Fit it directly to the existing hands or wrists. Keep every hand position, finger/mitten silhouette, arm, "
            "weapon-free pose, and facing direction unchanged."
        ),
        "feet": (
            "Fit it directly over the existing feet and lower ankles. Keep every foot position, leg, stance, ground "
            "contact point, pose, and facing direction unchanged."
        ),
    }
    ordered_directions = sorted(
        animation.direction_rows.items(), key=lambda item: item[1]
    )
    row_map = ", ".join(
        f"row {row + 1} = {direction.title()}" for direction, row in ordered_directions
    )
    return "\n".join(
        (
            "USE CASE: precise-object-edit for a production pixel-art paper-doll component.",
            "",
            "EDIT TARGET",
            "Image 1 is the authoritative sprite sheet and immutable raster template, not inspiration to reinterpret. "
            "If Image 2 is supplied, it is a design reference for the wearable only and never replaces Image 1 geometry.",
            "",
            "PRIMARY REQUEST",
            f"Add exactly one wearable component: {idea.concept}",
            f"Component slot: {idea.slot}. {fit_contract[idea.slot]}",
            "",
            "NON-NEGOTIABLE BASE LOCK",
            "Perform additive paper-doll compositing, not character generation. Treat every input pixel as read-only. "
            "Do not redraw, regenerate, reinterpret, improve, clean up, recolor, rescale, rotate, mirror, or reposition "
            "the mannequin or animation. New component pixels may cover the mannequin only where the physical wearable "
            "naturally occludes it. Every original pixel that remains visible must be identical to Image 1.",
            "Preserve exact anatomy, proportions, silhouette, pose, limb and head positions, facing direction, frame "
            "coordinates, spacing, alignment, canvas dimensions, solid magenta matte, and registration. Preserve all "
            "pixels outside the legitimate component coverage area exactly.",
            "The blue/cyan figure is a synthetic opaque fit mannequin. Blue and cyan are reserved pipeline colors, not "
            "skin or garment colors. Do not include blue, cyan, magenta, mannequin, anatomy, or background pixels as part "
            "of the component.",
            "",
            "ANIMATION AND DESIGN LOCK",
            (
                "Frame counts by direction: "
                + ", ".join(
                    f"{direction}={animation.frame_count(direction)}"
                    for direction in animation.directions
                )
                + f". Exact direction layout: {row_map}. Frames progress left to "
                "right. Do not reverse, reorder, omit, duplicate, or invent frames."
            ),
            "Use one identical component design in every frame: the same construction, material, palette, proportions, "
            "fastenings, trim, and recognizable landmarks. Change only its perspective, occlusion, and folds as required "
            "by the existing pose. If a detail cannot be represented consistently, omit that detail everywhere.",
            "",
            "PIXEL-ART REQUIREMENTS",
            "Match the supplied native pixel density, outline weight, lighting direction, and detail level. Use hard "
            "pixel edges, compact intentional clusters, bold readable shapes, and a small shared color ramp. No "
            "antialiasing, blur, gradients, glow, painterly texture, semitransparent fringe, or scattered noise.",
            "",
            "EXCLUSIONS",
            f"Do not add {forbidden[idea.slot]}. Do not add any second garment, unrelated accessory, ground plane, cast "
            "shadow, scenery, effect, text, border, box, label, or object. Never fill an editable or masked rectangle with "
            "black, white, magenta, or any other background color.",
            "",
            "FAIL-SAFE",
            "When uncertain about a pixel, preserve the original pixel unchanged. Missing a minor wearable detail is "
            "preferable to altering the base character.",
            "",
            "OUTPUT CHECK",
            "Return the complete sheet with exactly the same dimensions and layout. The requested wearable must be the "
            "only visible difference. Before returning it, verify that anatomy and poses are unchanged, all frames remain "
            "registered, the design is consistent, no mask-shaped fill was added, and untouched pixels still match Image 1.",
        )
    )


def _request_fingerprint(idea: ComponentIdea, animation_id: str, prompt: str) -> str:
    specs = load_character_sheet_specs(ASSET_ROOT)
    raw = _animation_spec(specs, animation_id)
    payload = json.dumps(
        {
            "component": idea.id,
            "animation": animation_id,
            "prompt": prompt,
            "model": "gpt-image-2",
            "runtime_sha256": raw["runtime_sha256"],
            "generation_master_sha256": sha256_file(
                PIPELINE_ROOT / "generation_masters" / f"{animation_id}.png"
            ),
            "mannequin_ramp_sha256": sha256_file(_mannequin_ramp_path(animation_id)),
            "spec_version": specs["schema_version"],
        },
        sort_keys=True,
    ).encode("utf-8")
    return sha256_bytes(payload)


def _job_directories(job_dir: Path) -> None:
    for name in ("raw_candidates", "normalized", "extracted", "previews"):
        (job_dir / name).mkdir(parents=True, exist_ok=True)


def _find_resumable_job(
    component_id: str,
    animation_id: str,
    fingerprint: str,
    candidate_count: int,
    prompt: str,
    slot: str,
) -> Path | None:
    jobs_root = PIPELINE_ROOT / "jobs"
    if not jobs_root.is_dir():
        return None
    for path in sorted(jobs_root.iterdir(), reverse=True):
        metadata_path = path / "metadata.json"
        if not metadata_path.is_file():
            continue
        data = _read_json(metadata_path)
        request_path = path / "request.json"
        request = _read_json(request_path) if request_path.is_file() else {}
        request_compatible = (
            request.get("model") == "gpt-image-2"
            and request.get("image_sha256")
            == sha256_file(PIPELINE_ROOT / "generation_masters" / f"{animation_id}.png")
            and request.get("mask_sha256")
            == sha256_file(PIPELINE_ROOT / "masks" / slot / f"{animation_id}.png")
            and request.get("prompt_sha256") == sha256_bytes(prompt.encode("utf-8"))
        )
        if (
            data.get("component_id") == component_id
            and data.get("animation_id") == animation_id
            and (data.get("fingerprint") == fingerprint or request_compatible)
            and data.get("candidate_count") == candidate_count
            and data.get("status") not in ("approved", "rejected")
        ):
            return path
    return None


def create_job(
    idea: ComponentIdea,
    animation_id: str,
    *,
    candidates: int = 3,
    force_new: bool = False,
    design_reference: str | None = None,
    prepare_assets: bool = True,
) -> Path:
    if not 1 <= candidates <= 10:
        raise PipelineError("Candidate count must be between 1 and 10")
    if prepare_assets:
        prepare_pipeline()
    catalog = create_default_catalog(ASSET_ROOT, include_incomplete=True)
    animation = catalog.base("human-01").animations.get(animation_id)
    if animation is None:
        raise PipelineError(f"Unknown animation {animation_id!r}")
    prompt = build_generation_prompt(idea, animation)
    fingerprint = _request_fingerprint(idea, animation_id, prompt)
    if not force_new:
        resumable = _find_resumable_job(
            idea.id,
            animation_id,
            fingerprint,
            candidates,
            prompt,
            idea.slot,
        )
        if resumable is not None:
            return resumable
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    job_id = f"{idea.id}-{animation_id}-{stamp}-{fingerprint[:8]}"
    job_dir = PIPELINE_ROOT / "jobs" / job_id
    suffix = 2
    while job_dir.exists():
        job_dir = PIPELINE_ROOT / "jobs" / f"{job_id}-{suffix}"
        suffix += 1
    _job_directories(job_dir)
    (job_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    specs = load_character_sheet_specs(ASSET_ROOT)
    animation_spec = _animation_spec(specs, animation_id)
    request = {
        "model": "gpt-image-2",
        "quality": "medium",
        "background": "opaque",
        "output_format": "png",
        "size": "x".join(str(value) for value in animation_spec["generation_size"]),
        "image_sha256": sha256_file(
            PIPELINE_ROOT / "generation_masters" / f"{animation_id}.png"
        ),
        "mask_sha256": sha256_file(
            PIPELINE_ROOT / "masks" / idea.slot / f"{animation_id}.png"
        ),
        "mannequin_ramp_sha256": sha256_file(_mannequin_ramp_path(animation_id)),
        "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
        "design_reference": design_reference,
    }
    _write_json(job_dir / "request.json", request)
    metadata: dict[str, object] = {
        "schema_version": 1,
        "job_id": job_dir.name,
        "component_id": idea.id,
        "animation_id": animation_id,
        "slot": idea.slot,
        "layer": idea.layer,
        "component": {
            "concept": idea.concept,
            "tags": list(idea.tags),
            "fit": idea.fit,
            "priority": idea.priority,
        },
        "fingerprint": fingerprint,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "status": "queued",
        "candidate_count": candidates,
        "design_reference": design_reference,
        "candidates": {
            f"candidate-{index:03d}": {"status": "queued", "attempts": 0}
            for index in range(1, candidates + 1)
        },
    }
    _write_json(job_dir / "metadata.json", metadata)
    return job_dir


def queue_component_jobs(
    component_id: str,
    *,
    animation_id: str | None = None,
    candidates: int = 3,
    force_new: bool = False,
    design_reference: str | None = None,
    _prepared: bool = False,
) -> tuple[Path, ...]:
    if not _prepared:
        prepare_pipeline()
    idea = component_idea(component_id)
    animation_ids = (animation_id,) if animation_id else ("idle", "walk", "run")
    jobs = tuple(
        create_job(
            idea,
            current,
            candidates=candidates,
            force_new=force_new,
            design_reference=design_reference,
            prepare_assets=False,
        )
        for current in animation_ids
    )
    if idea.status == "idea":
        _update_catalog_status(idea.id, "queued")
    return jobs


def queue_bootstrap_jobs(*, candidates: int = 3) -> tuple[Path, ...]:
    prepare_pipeline()
    jobs: list[Path] = []
    for idea in load_component_ideas():
        jobs.extend(
            queue_component_jobs(idea.id, candidates=candidates, _prepared=True)
        )
    return tuple(jobs)


def load_job(job_id: str | Path) -> tuple[Path, dict[str, object]]:
    path = Path(job_id)
    if not path.is_dir():
        path = PIPELINE_ROOT / "jobs" / str(job_id)
    if not path.is_dir():
        raise PipelineError(f"Unknown job {job_id!r}")
    return path, _read_json(path / "metadata.json")


def save_job(job_dir: Path, metadata: dict[str, object]) -> None:
    metadata["updated_at"] = utc_now()
    _write_json(job_dir / "metadata.json", metadata)


def _load_api_key() -> str | None:
    value = os.getenv("OPENAI_API_KEY")
    if value:
        return value
    for name in (".env.local", ".env"):
        path = PROJECT_ROOT / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("OPENAI_API_KEY="):
                candidate = line.split("=", 1)[1].strip().strip("\"'")
                if candidate:
                    return candidate
    return None


def openai_api_available() -> bool:
    return bool(_load_api_key())


def _openai_edit_candidate(
    job_dir: Path, metadata: Mapping[str, object]
) -> tuple[bytes, dict[str, object]]:
    api_key = _load_api_key()
    if not api_key:
        raise PipelineError(
            "OPENAI_API_KEY is not configured. The job remains queued; set the key and rerun the same generate command."
        )
    try:
        import openai
        from openai import OpenAI
    except ImportError as exc:
        raise PipelineError(
            "Install project requirements before generating components"
        ) from exc
    request = _read_json(job_dir / "request.json")
    animation_id = str(metadata["animation_id"])
    slot = str(metadata["slot"])
    image_path = PIPELINE_ROOT / "generation_masters" / f"{animation_id}.png"
    mask_path = PIPELINE_ROOT / "masks" / slot / f"{animation_id}.png"
    design_reference = metadata.get("design_reference")
    retry_types = (
        openai.RateLimitError,
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.InternalServerError,
    )
    client = OpenAI(api_key=api_key, timeout=180.0, max_retries=0)
    for attempt in range(1, 4):
        try:
            with ExitStack() as stack:
                inputs = [stack.enter_context(image_path.open("rb"))]
                if isinstance(design_reference, str) and design_reference:
                    reference_path = Path(design_reference)
                    if not reference_path.is_file():
                        raise PipelineError(
                            f"Design reference is missing: {reference_path}"
                        )
                    inputs.append(stack.enter_context(reference_path.open("rb")))
                mask_file = stack.enter_context(mask_path.open("rb"))
                raw_response = client.images.with_raw_response.edit(
                    model="gpt-image-2",
                    image=inputs,
                    mask=mask_file,
                    prompt=(job_dir / "prompt.txt").read_text(encoding="utf-8"),
                    size=str(request["size"]),
                    quality="medium",
                    background="opaque",
                    output_format="png",
                    n=1,
                )
            parsed = raw_response.parse()
            if not parsed.data or not parsed.data[0].b64_json:
                raise PipelineError("OpenAI returned no image data")
            response_metadata: dict[str, object] = {
                "request_id": raw_response.headers.get("x-request-id"),
                "attempt": attempt,
                "created": getattr(parsed, "created", None),
                "usage": (
                    parsed.usage.model_dump(mode="json")
                    if getattr(parsed, "usage", None) is not None
                    else None
                ),
            }
            return base64.b64decode(parsed.data[0].b64_json), response_metadata
        except retry_types as exc:
            if attempt == 3:
                raise PipelineError(
                    f"Transient OpenAI failure after 3 attempts: {exc}"
                ) from exc
            retry_after = getattr(getattr(exc, "response", None), "headers", {}).get(
                "retry-after"
            )
            delay = (
                float(retry_after) if retry_after else (2**attempt + random.random())
            )
            time.sleep(min(delay, 10.0))
        except openai.APIError as exc:
            code = getattr(exc, "code", None)
            request_id = getattr(exc, "request_id", None)
            raise PermanentAPIError(
                f"OpenAI request failed ({code or type(exc).__name__}, request {request_id}): {exc}",
                code=str(code) if code else type(exc).__name__,
                request_id=str(request_id) if request_id else None,
            ) from exc
    raise PipelineError("OpenAI edit did not complete")


def normalize_job(job_id: str | Path) -> dict[str, object]:
    job_dir, metadata = load_job(job_id)
    specs = load_character_sheet_specs(ASSET_ROOT)
    animation_id = str(metadata["animation_id"])
    animation_spec = _animation_spec(specs, animation_id)
    catalog = create_default_catalog(ASSET_ROOT, include_incomplete=True)
    animation = catalog.base("human-01").animations[animation_id]
    base = load_base_animation(catalog, "human-01", animation_id)
    palette = tuple(Counter(_image_data(base)).keys())
    allowed = create_allowed_region_mask(
        animation,
        tuple(int(value) for value in specs["regions"][str(metadata["slot"])]),
    )
    region = tuple(int(value) for value in specs["regions"][str(metadata["slot"])])
    matte = _matte_rgb(specs)
    mannequin_ramp, mannequin_document = load_mannequin_ramp(animation_id)
    reverse_threshold = float(mannequin_document["reverse_threshold"])
    candidates = metadata.get("candidates")
    if not isinstance(candidates, dict):
        raise PipelineError("Job candidates metadata is invalid")
    for candidate_id, candidate in candidates.items():
        if not isinstance(candidate, dict):
            continue
        raw_path = job_dir / "raw_candidates" / f"{candidate_id}.png"
        if not raw_path.is_file():
            continue
        with Image.open(raw_path) as opened:
            raw_image = opened.convert("RGBA")
        candidate_dir = job_dir / "normalized" / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        normalized_sources = {
            method: normalize_generated_image(
                raw_image,
                animation.sheet_size,
                tuple(int(value) for value in animation_spec["padding"]),
                method=method,
                canonical_palette=palette,
            )
            for method in ("center", "dominant")
        }
        normalized_sources["palette"] = _snap_image_to_palette(
            normalized_sources["dominant"],
            tuple(palette),
            32.0,
        )
        for method in NORMALIZATION_METHODS:
            normalized_mannequin = normalized_sources[method]
            normalized_mannequin.save(candidate_dir / f"{method}-mannequin-raw.png")
            normalized_mannequin = restore_generation_background(
                normalized_mannequin,
                animation,
                region,
                matte_rgb=matte,
                tolerance=float(mannequin_document["border_background_tolerance"]),
                dark_ceiling=int(mannequin_document["border_dark_ceiling"]),
                matte_threshold=float(mannequin_document["border_matte_threshold"]),
            )
            normalized_mannequin.save(candidate_dir / f"{method}-mannequin.png")
            restored = reverse_mannequin_ramp(
                normalized_mannequin,
                mannequin_ramp,
                threshold=reverse_threshold,
                canonical=base,
                matte_rgb=matte,
                matte_restore_threshold=float(
                    mannequin_document["matte_restore_threshold"]
                ),
            )
            restored.save(candidate_dir / f"{method}-restored-unclamped.png")
            clamped = clamp_outside_generation_region(
                restored,
                base,
                allowed,
                matte_rgb=matte,
            )
            clamped.save(candidate_dir / f"{method}.png")
        candidate["status"] = "normalized"
        candidate["normalization"] = "dominant"
        candidate["processing"] = {
            "version": mannequin_document["processing_version"],
            "mannequin_ramp_sha256": sha256_file(_mannequin_ramp_path(animation_id)),
            "processed_at": utc_now(),
        }
    save_job(job_dir, metadata)
    return metadata


def extract_job(job_id: str | Path) -> dict[str, object]:
    job_dir, metadata = load_job(job_id)
    normalize_job(job_dir)
    job_dir, metadata = load_job(job_dir)
    specs = load_character_sheet_specs(ASSET_ROOT)
    animation_id = str(metadata["animation_id"])
    slot = str(metadata["slot"])
    catalog = create_default_catalog(ASSET_ROOT, include_incomplete=True)
    animation = catalog.base("human-01").animations[animation_id]
    base = load_base_animation(catalog, "human-01", animation_id)
    region = tuple(int(value) for value in specs["regions"][slot])
    allowed = create_allowed_region_mask(animation, region)
    candidates = metadata["candidates"]
    for candidate_id, candidate in candidates.items():
        if not isinstance(candidate, dict):
            continue
        normalized_path = job_dir / "normalized" / candidate_id / "dominant.png"
        if not normalized_path.is_file():
            continue
        with Image.open(normalized_path) as opened:
            normalized = opened.convert("RGBA")
        overlay = extract_component_overlay(
            base,
            normalized,
            allowed,
            matte_rgb=_matte_rgb(specs),
            difference_threshold=float(specs["generation"]["difference_threshold"]),
            matte_threshold=float(specs["generation"]["matte_threshold"]),
        )
        output_path = job_dir / "extracted" / f"{candidate_id}.png"
        overlay.save(output_path)
        candidate["status"] = "extracted"
        candidate["extracted_sha256"] = sha256_file(output_path)
    save_job(job_dir, metadata)
    return metadata


def qa_job(job_id: str | Path) -> dict[str, object]:
    job_dir, metadata = load_job(job_id)
    extract_job(job_dir)
    job_dir, metadata = load_job(job_dir)
    specs = load_character_sheet_specs(ASSET_ROOT)
    animation_id = str(metadata["animation_id"])
    slot = str(metadata["slot"])
    catalog = create_default_catalog(ASSET_ROOT, include_incomplete=True)
    animation = catalog.base("human-01").animations[animation_id]
    base = load_base_animation(catalog, "human-01", animation_id)
    mannequin_ramp, mannequin_document = load_mannequin_ramp(animation_id)
    allowed = create_allowed_region_mask(
        animation, tuple(int(value) for value in specs["regions"][slot])
    )
    qa_document: dict[str, object] = {"job_id": job_dir.name, "candidates": {}}
    candidates = metadata["candidates"]
    review_count = 0
    for candidate_id, candidate in candidates.items():
        if not isinstance(candidate, dict):
            continue
        normalized_path = job_dir / "normalized" / candidate_id / "dominant.png"
        overlay_path = job_dir / "extracted" / f"{candidate_id}.png"
        if not normalized_path.is_file() or not overlay_path.is_file():
            continue
        with Image.open(normalized_path) as opened:
            normalized = opened.convert("RGBA")
        with Image.open(overlay_path) as opened:
            overlay = opened.convert("RGBA")
        qa = analyze_candidate(
            base,
            normalized,
            overlay,
            allowed,
            animation,
            matte_rgb=_matte_rgb(specs),
            reserved_colors=tuple(mannequin_ramp.values()),
            reserved_color_threshold=float(mannequin_document["leak_threshold"]),
        )
        qa_document["candidates"][candidate_id] = qa
        candidate["qa"] = qa
        candidate["status"] = "review"
        review_count += 1
        write_candidate_previews(
            job_dir / "previews" / candidate_id,
            base,
            normalized,
            overlay,
            animation,
        )
    metadata["status"] = "review" if review_count else "failed"
    _write_json(job_dir / "qa.json", qa_document)
    save_job(job_dir, metadata)
    if review_count:
        _update_catalog_status(str(metadata["component_id"]), "review")
    return metadata


def generate_job(job_id: str | Path) -> dict[str, object]:
    job_dir, metadata = load_job(job_id)
    candidates = metadata.get("candidates")
    if not isinstance(candidates, dict):
        raise PipelineError("Job candidates metadata is invalid")
    for candidate_id, candidate in candidates.items():
        if not isinstance(candidate, dict) or candidate.get("status") != "queued":
            continue
        candidate["attempts"] = int(candidate.get("attempts", 0)) + 1
        save_job(job_dir, metadata)
        try:
            image_bytes, response_metadata = _openai_edit_candidate(job_dir, metadata)
        except PermanentAPIError as exc:
            candidate["status"] = "failed"
            candidate["error"] = {
                "type": "permanent_api",
                "code": exc.code,
                "request_id": exc.request_id,
                "message": str(exc),
                "at": utc_now(),
            }
            save_job(job_dir, metadata)
            continue
        raw_path = job_dir / "raw_candidates" / f"{candidate_id}.png"
        raw_path.write_bytes(image_bytes)
        try:
            with Image.open(BytesIO(image_bytes)) as opened:
                opened.verify()
        except Exception as exc:
            raise PipelineError(
                f"OpenAI candidate {candidate_id} is not a valid image"
            ) from exc
        candidate["status"] = "generated"
        candidate["raw_sha256"] = sha256_bytes(image_bytes)
        candidate["api"] = response_metadata
        metadata["status"] = "generated"
        save_job(job_dir, metadata)
    return qa_job(job_dir)


def set_candidate_review(
    job_id: str | Path,
    candidate_id: str,
    decision: str,
    *,
    note: str = "",
) -> dict[str, object]:
    if decision not in ("approved", "rejected"):
        raise PipelineError("Review decision must be approved or rejected")
    job_dir, metadata = load_job(job_id)
    candidates = metadata.get("candidates")
    if not isinstance(candidates, dict) or not isinstance(
        candidates.get(candidate_id), dict
    ):
        raise PipelineError(f"Unknown candidate {candidate_id!r}")
    candidate = candidates[candidate_id]
    if candidate.get("status") != "review":
        raise PipelineError("Only reviewed candidates can receive a human decision")
    candidate["review"] = {"decision": decision, "note": note, "at": utc_now()}
    if decision == "rejected":
        candidate["status"] = "rejected"
    save_job(job_dir, metadata)
    return metadata


def save_cleaned_candidate(
    job_id: str | Path, candidate_id: str, image: Image.Image
) -> Path:
    job_dir, metadata = load_job(job_id)
    candidates = metadata.get("candidates")
    if not isinstance(candidates, dict) or not isinstance(
        candidates.get(candidate_id), dict
    ):
        raise PipelineError(f"Unknown candidate {candidate_id!r}")
    path = job_dir / "extracted" / f"{candidate_id}.png"
    if path.is_file():
        backup = (
            job_dir
            / "extracted"
            / f"{candidate_id}-before-cleanup-{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        )
        shutil.copy2(path, backup)
    image.convert("RGBA").save(path)
    candidate = candidates[candidate_id]
    candidate["status"] = "extracted"
    candidate["edited_at"] = utc_now()
    candidate.pop("review", None)
    save_job(job_dir, metadata)
    qa_job(job_dir)
    return path


def _update_catalog_status(component_id: str, status: str) -> None:
    raw = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("components"), list):
        raise PipelineError("Component catalog is invalid")
    for record in raw["components"]:
        if isinstance(record, dict) and record.get("id") == component_id:
            record["status"] = status
            break
    else:
        raise PipelineError(f"Component {component_id!r} is missing from the catalog")
    CATALOG_PATH.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def promote_candidate(
    job_id: str | Path,
    candidate_id: str,
    *,
    replace: bool = False,
) -> Path:
    validate_canonical_checksums()
    job_dir, metadata = load_job(job_id)
    candidates = metadata.get("candidates")
    if not isinstance(candidates, dict) or not isinstance(
        candidates.get(candidate_id), dict
    ):
        raise PipelineError(f"Unknown candidate {candidate_id!r}")
    candidate = candidates[candidate_id]
    review = candidate.get("review")
    qa = candidate.get("qa")
    if not isinstance(review, Mapping) or review.get("decision") != "approved":
        raise PipelineError("Candidate must be explicitly approved before promotion")
    if not isinstance(qa, Mapping) or qa.get("status") == "fail":
        raise PipelineError("Candidate has failing or missing QA")
    animation_id = str(metadata["animation_id"])
    component_id = str(metadata["component_id"])
    slot = str(metadata["slot"])
    source = job_dir / "extracted" / f"{candidate_id}.png"
    if not source.is_file():
        raise PipelineError("Extracted candidate is missing")
    catalog = create_default_catalog(ASSET_ROOT, include_incomplete=True)
    expected_size = catalog.base("human-01").animations[animation_id].sheet_size
    with Image.open(source) as opened:
        if opened.size != expected_size or opened.mode != "RGBA":
            raise PipelineError(
                "Promotion candidate geometry or alpha format is invalid"
            )
    idea = component_idea(component_id)
    target_dir = ASSET_ROOT / "parts" / slot / component_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{animation_id}.png"
    if target.exists() and not replace:
        raise PipelineError(
            f"Production asset already exists: {target}; pass --replace explicitly"
        )
    shutil.copy2(source, target)
    manifest_path = target_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = _read_json(manifest_path)
        version = int(manifest.get("version", 1)) + 1
    else:
        manifest = {
            "schemaVersion": 1,
            "id": component_id,
            "displayName": component_id.replace("_", " ").title(),
            "slot": slot,
            "occupiesSlots": [slot],
            "reservedSlots": [],
            "layer": idea.layer,
            "tags": list(idea.tags),
            "fit": idea.fit,
            "animations": {},
            "coverage": {},
            "provenance": {},
        }
        version = 1
    manifest["version"] = version
    manifest["animations"][animation_id] = target.name
    directions = list(catalog.base("human-01").animations[animation_id].directions)
    manifest["coverage"][animation_id] = directions
    manifest["provenance"][animation_id] = {
        "jobId": job_dir.name,
        "candidateId": candidate_id,
        "imageSha256": sha256_file(target),
        "promptSha256": sha256_file(job_dir / "prompt.txt"),
        "promotedAt": utc_now(),
    }
    complete = set(manifest["animations"]) >= {"idle", "walk", "run"}
    manifest["status"] = "approved" if complete else "incomplete"
    _write_json(manifest_path, manifest)
    load_component_manifest(manifest_path)
    _update_catalog_status(component_id, str(manifest["status"]))
    candidate["status"] = "approved"
    candidate["promoted_path"] = str(target)
    metadata["status"] = "approved" if complete else "incomplete"
    save_job(job_dir, metadata)
    return target
