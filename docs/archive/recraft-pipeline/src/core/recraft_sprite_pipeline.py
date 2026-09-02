"""Provider-isolated Recraft sprite generation, validation, and review support.

Heroic Character Forge sheets and their semantic region maps are immutable
authority. Recraft responses are untrusted candidates stored below ``working``.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import math
import os
import re
import shutil
import tempfile
import time
import webbrowser
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Self
from urllib.parse import urlparse

import httpx
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, binary_erosion, distance_transform_edt

from src.core.character_forge import CHARACTER_LAYER_ORDER, CHARACTER_SLOTS
from src.core.component_cleanup import cleanup_component_frame
from src.core.image_processing import area_resize, cluster_cleanup
from src.core.mannequin_semantics import (
    REGION_BY_NAME,
    SLOT_SURFACE_REGIONS,
)
from src.core.palette import (
    PaletteExtractionSettings,
    palette_from_image_with_debug,
    quantize_to_palette,
)

ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = ROOT / "assets" / "character-forge"
HEROIC_MANIFEST = ASSET_ROOT / "heroic_manifest.json"
SHEET_SPECS = ASSET_ROOT / "sheet_specs.json"
STYLE_PROFILE = ROOT / "docs" / "PIXEL_ART_STYLE_PROFILE_V1.json"
PIPELINE_CONFIG = ROOT / "animation_images_models" / "recraft_pipeline.json"
VALIDATION_PROFILE = (
    ROOT / "animation_images_models" / "recraft_validation_profile_v1.json"
)
DEFAULT_WORK_ROOT = ROOT / "working" / "recraft"

JOB_SCHEMA_VERSION = 1
CANDIDATE_SCHEMA_VERSION = 1
DIRECTIONS = ("front", "back", "right", "left")
ANIMATIONS = ("idle", "walk", "run")
CAMERAS = ("top_down", "three_quarter", "low")
JOB_MODES = ("component", "full_style_experiment")

SLOT_LAYERS = {
    "headwear": "headwear",
    "face": "face_accessory",
    "neck": "neck",
    "torso": "torso",
    "outerwear": "outerwear",
    "waist": "waist",
    "hands": "handwear",
    "legwear": "legwear",
    "feet": "footwear",
    "hair": "hair_front",
    "facial_hair": "face_accessory",
    "shoulder_chest": "foreground_accessory",
    "back": "body_back",
}

SLOT_ENVELOPE_PX = {
    "headwear": 2,
    "face": 1,
    "neck": 1,
    "torso": 1,
    "outerwear": 4,
    "waist": 1,
    "hands": 2,
    "legwear": 4,
    "feet": 2,
    "hair": 3,
    "facial_hair": 3,
    "shoulder_chest": 2,
    "back": 4,
}

SLOT_PROTECTED_REGIONS = {
    "headwear": ("face",),
    "face": (),
    "neck": ("left_hand", "right_hand"),
    "torso": ("left_forearm", "right_forearm", "left_hand", "right_hand"),
    "outerwear": ("left_hand", "right_hand"),
    "waist": ("left_forearm", "right_forearm", "left_hand", "right_hand"),
    "hands": (),
    "legwear": ("left_forearm", "right_forearm", "left_hand", "right_hand"),
    "feet": ("left_hand", "right_hand"),
    "hair": (),
    "facial_hair": (),
    "shoulder_chest": ("left_forearm", "right_forearm", "left_hand", "right_hand"),
    "back": ("left_hand", "right_hand"),
}


class RecraftPipelineError(RuntimeError):
    """Raised when a Recraft job or candidate violates the pipeline contract."""


class RecraftAmbiguousSubmissionError(RecraftPipelineError):
    """Raised only when a POST may have reached Recraft before transport failure."""


@dataclass(frozen=True, slots=True)
class Layout:
    name: str
    columns: int
    rows: int
    width: int | None = None
    height: int | None = None

    @property
    def cell_count(self) -> int:
        return self.columns * self.rows


@dataclass(frozen=True, slots=True)
class FrameMetrics:
    board_cell: int
    source_frame: int
    registration_dx: int
    registration_dy: int
    silhouette_iou: float
    core_recall: float
    minimum_region_recall: float
    centroid_drift_px: float
    bbox_size_delta_ratio: float
    expected_pose_score: float
    best_pose_score: float
    best_pose_frame: int
    pose_match_margin: float
    safe_margin_px: int
    raw_partial_alpha_pixels: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_hash(data: object) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RecraftPipelineError(f"Expected an object in {path}")
    return data


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
    temporary.replace(path)


def _save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGBA").save(
        path, format="PNG", optimize=False, compress_level=9
    )


def _relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not cleaned:
        raise RecraftPipelineError("A nonempty identifier is required")
    return cleaned


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def load_pipeline_config(path: Path = PIPELINE_CONFIG) -> dict[str, Any]:
    data = _read_json(path)
    if data.get("schema_version") != 1 or data.get("provider") != "recraft":
        raise RecraftPipelineError(f"Unsupported Recraft configuration: {path}")
    return data


def load_validation_profile(path: Path = VALIDATION_PROFILE) -> dict[str, Any]:
    data = _read_json(path)
    if data.get("schema_version") != 1:
        raise RecraftPipelineError(f"Unsupported validation profile: {path}")
    return data


def parse_layout(value: str, *, width: int | None = None, height: int | None = None) -> Layout:
    match = re.fullmatch(r"(\d+)x(\d+)", value.strip().lower())
    if match is None:
        raise RecraftPipelineError(f"Invalid layout {value!r}; expected COLSxROWS")
    columns, rows = (int(item) for item in match.groups())
    if columns < 1 or rows < 1 or columns * rows > 64:
        raise RecraftPipelineError(f"Unsafe layout {value!r}")
    return Layout(value.lower(), columns, rows, width, height)


def _heroic_identity(value: str) -> tuple[str, str, str]:
    manifest = _read_json(HEROIC_MANIFEST)
    specs = _read_json(SHEET_SPECS)
    for character_id, model in manifest["models"].items():
        base_id = str(model["base_id"])
        if value in (character_id, base_id):
            return character_id, base_id, str(specs["bases"][base_id]["name"])
    raise RecraftPipelineError(f"Unknown Heroic character/base {value!r}")


def _source_record(
    character_id: str, camera: str, animation: str
) -> tuple[dict[str, Any], Path, Path]:
    manifest = _read_json(HEROIC_MANIFEST)
    try:
        record = manifest["characters"][character_id][camera]["sequences"][animation]
    except KeyError as exc:
        raise RecraftPipelineError(
            f"No Heroic source for {character_id}/{camera}/{animation}"
        ) from exc
    sheet = ASSET_ROOT / str(record["sheet"])
    regions = ASSET_ROOT / str(record["regions"])
    if not sheet.is_file() or not regions.is_file():
        raise FileNotFoundError(sheet if not sheet.is_file() else regions)
    if sha256_path(sheet) != record["sheet_sha256"]:
        raise RecraftPipelineError(f"Heroic source hash drifted: {sheet}")
    if sha256_path(regions) != record["regions_sha256"]:
        raise RecraftPipelineError(f"Heroic region hash drifted: {regions}")
    return record, sheet, regions


def _direction_row(base_id: str, animation: str, direction: str) -> int:
    specs = _read_json(SHEET_SPECS)
    try:
        return int(
            specs["bases"][base_id]["animations"][animation]["direction_rows"][direction]
        )
    except KeyError as exc:
        raise RecraftPipelineError(
            f"No direction row for {base_id}/{animation}/{direction}"
        ) from exc


def _sheet_frames(
    sheet_path: Path,
    *,
    frame_count: int,
    row: int,
    mode: str = "RGBA",
) -> list[Image.Image]:
    with Image.open(sheet_path) as opened:
        sheet = opened.convert(mode)
    expected = (frame_count * 128, 4 * 128)
    if sheet.size != expected:
        raise RecraftPipelineError(f"{sheet_path} is {sheet.size}; expected {expected}")
    return [
        sheet.crop((index * 128, row * 128, (index + 1) * 128, (row + 1) * 128))
        for index in range(frame_count)
    ]


def _hex_rgb(value: str) -> tuple[int, int, int]:
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        raise RecraftPipelineError(f"Invalid color {value!r}; expected #RRGGBB")
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))


def _dominant_colors(frames: Sequence[Image.Image], count: int) -> list[tuple[int, int, int]]:
    colors: Counter[tuple[int, int, int]] = Counter()
    for frame in frames:
        raw = np.asarray(frame.convert("RGBA"), dtype=np.uint8)
        visible = raw[..., 3] > 0
        colors.update(tuple(int(channel) for channel in rgb) for rgb in raw[..., :3][visible])
    return [color for color, _frequency in colors.most_common(count)]


def _validate_component_spec(raw: Mapping[str, Any]) -> dict[str, Any]:
    required = ("id", "display_name", "description", "slot")
    for key in required:
        if not isinstance(raw.get(key), str) or not str(raw[key]).strip():
            raise RecraftPipelineError(f"Component spec requires {key}")
    slot = str(raw["slot"])
    if slot not in CHARACTER_SLOTS:
        raise RecraftPipelineError(f"Unknown component slot {slot!r}")
    occupies = raw.get("occupies_slots", [slot])
    if not isinstance(occupies, list) or not occupies or any(
        value not in CHARACTER_SLOTS for value in occupies
    ):
        raise RecraftPipelineError("occupies_slots contains an unknown slot")
    if slot not in occupies:
        raise RecraftPipelineError("The primary slot must be in occupies_slots")
    layer = str(raw.get("layer", SLOT_LAYERS[slot]))
    if layer not in CHARACTER_LAYER_ORDER:
        raise RecraftPipelineError(f"Unknown Character Forge layer {layer!r}")
    colors = raw.get("colors", [])
    if not isinstance(colors, list) or any(not isinstance(color, str) for color in colors):
        raise RecraftPipelineError("Component colors must be a list")
    parsed_colors = ["#{:02X}{:02X}{:02X}".format(*_hex_rgb(color)) for color in colors]
    expected_pieces = int(raw.get("expected_pieces", 1))
    if not 1 <= expected_pieces <= 8:
        raise RecraftPipelineError("expected_pieces must be between 1 and 8")
    envelope = int(raw.get("envelope_px", max(SLOT_ENVELOPE_PX[value] for value in occupies)))
    if not 0 <= envelope <= 8:
        raise RecraftPipelineError("envelope_px must be between 0 and 8")
    render_layers = raw.get("render_layers", {layer: []})
    if not isinstance(render_layers, Mapping) or layer not in render_layers:
        raise RecraftPipelineError("render_layers must contain the primary layer")
    normalized_layers: dict[str, list[str]] = {}
    for render_layer, names in render_layers.items():
        if render_layer not in CHARACTER_LAYER_ORDER:
            raise RecraftPipelineError(f"Unknown render layer {render_layer!r}")
        if not isinstance(names, list) or any(name not in REGION_BY_NAME for name in names):
            raise RecraftPipelineError(f"Invalid semantic regions for {render_layer}")
        normalized_layers[str(render_layer)] = [str(name) for name in names]
    return {
        "id": _slug(str(raw["id"])),
        "display_name": str(raw["display_name"]).strip(),
        "description": str(raw["description"]).strip(),
        "slot": slot,
        "occupies_slots": list(dict.fromkeys(str(value) for value in occupies)),
        "layer": layer,
        "material": str(raw.get("material", "unspecified")).strip(),
        "colors": parsed_colors,
        "mirror_safe": bool(raw.get("mirror_safe", True)),
        "expected_pieces": expected_pieces,
        "envelope_px": envelope,
        "hair_occlusion": str(raw.get("hair_occlusion", "show")),
        "render_layers": normalized_layers,
    }


def _prompt(job: Mapping[str, Any]) -> tuple[str, str]:
    component = job.get("component")
    task = (
        f"Add only this component: {component['display_name']} — {component['description']}. "
        f"Material: {component['material']}."
        if isinstance(component, Mapping)
        else "Restyle only the rendering treatment while preserving every structural fact."
    )
    frame_order = ", ".join(str(index + 1) for index in job["board_frame_indices"])
    prompt = (
        "LOCKED ANIMATION CONTACT-SHEET CONTRACT. "
        f"This image contains the same {job['character_name']} in one continuous "
        f"{job['animation']} animation facing {job['direction']}. "
        "This is one locked animation contact sheet, not a collage to rearrange. "
        f"Read cells row-major in this exact source-frame order: {frame_order}. "
        f"{task} Apply the identical design consistently in every cell. "
        "Preserve exactly: grid and cell order, transparent background, character position and scale, "
        "body proportions, pose, facing, anatomy, which arm and leg is forward, limb bends, hands, feet, "
        "horns, tail, hair, existing clothing not named by the task, camera, and silhouette of the body. "
        "The declared component alone may extend slightly around the body regions it belongs to. "
        "Return one transparent raster contact sheet with the same aspect, layout, cell count, and order. "
        "Do not add labels or a background. Do not redesign or re-pose the character."
    )
    negative = (
        "text, labels, captions, background, extra character, extra limb, missing limb, mirrored limb, "
        "swapped legs, swapped arms, changed pose, duplicate pose, rearranged frames, changed grid, "
        "cropping, recentering, altered body proportions, unrelated clothing, anatomy changes"
    )
    return prompt, negative


def prepare_job(
    *,
    base: str,
    camera: str,
    animation: str,
    direction: str,
    mode: str = "component",
    component: Mapping[str, Any] | None = None,
    selected_frames: Sequence[int] | None = None,
    model: str | None = None,
    job_id: str | None = None,
    work_root: Path = DEFAULT_WORK_ROOT,
) -> Path:
    """Build an offline request package without contacting Recraft."""
    if camera not in CAMERAS or animation not in ANIMATIONS or direction not in DIRECTIONS:
        raise RecraftPipelineError("Unknown camera, animation, or direction")
    if mode not in JOB_MODES:
        raise RecraftPipelineError(f"Unknown Recraft job mode {mode!r}")
    if mode == "component" and component is None:
        raise RecraftPipelineError("Component mode requires a component specification")
    normalized_component = (
        _validate_component_spec(component or {}) if mode == "component" else None
    )
    character_id, base_id, character_name = _heroic_identity(base)
    record, source_sheet, source_regions = _source_record(character_id, camera, animation)
    frame_count = int(record["frame_count"])
    indices = list(range(frame_count)) if selected_frames is None else [int(v) for v in selected_frames]
    if not indices or len(set(indices)) != len(indices) or any(
        index < 0 or index >= frame_count for index in indices
    ):
        raise RecraftPipelineError("selected_frames must be unique zero-based source indices")
    config = load_pipeline_config()
    selected_model = str(model or config["model"])
    supported_models = {str(config["model"]), str(config["pro_model"])}
    if selected_model not in supported_models:
        raise RecraftPipelineError(
            f"Unsupported configured Recraft model {selected_model!r}; "
            f"choose one of {sorted(supported_models)}"
        )
    configured = config["layouts"][animation]
    if len(indices) == frame_count:
        layout = Layout(
            str(configured["name"]),
            int(configured["columns"]),
            int(configured["rows"]),
            int(configured["width"]),
            int(configured["height"]),
        )
    else:
        columns = min(4, len(indices))
        rows = math.ceil(len(indices) / columns)
        layout = Layout(f"{columns}x{rows}", columns, rows, columns * 384, rows * 384)
    board_indices = list(indices)
    if animation == "idle" and len(indices) == frame_count:
        board_indices.extend((0, frame_count - 1))
    if len(board_indices) > layout.cell_count:
        raise RecraftPipelineError("Configured board has too few cells")
    while len(board_indices) < layout.cell_count:
        board_indices.append(indices[-1])

    row = _direction_row(base_id, animation, direction)
    source_frames = _sheet_frames(source_sheet, frame_count=frame_count, row=row)
    region_frames = _sheet_frames(
        source_regions, frame_count=frame_count, row=row, mode="L"
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    identity = normalized_component["id"] if normalized_component else "full-style"
    resolved_id = _slug(job_id or f"{identity}-{base_id}-{camera}-{animation}-{direction}-{timestamp}")
    job_root = Path(work_root).resolve() / resolved_id
    if job_root.exists():
        raise FileExistsError(job_root)
    source_root = job_root / "source"
    for index in indices:
        _save_png(source_frames[index], source_root / "frames" / f"frame_{index:02d}.png")
        region_path = source_root / "regions" / f"frame_{index:02d}.png"
        region_path.parent.mkdir(parents=True, exist_ok=True)
        region_frames[index].save(region_path, format="PNG", optimize=False, compress_level=9)

    assert layout.width is not None and layout.height is not None
    cell_width = layout.width // layout.columns
    cell_height = layout.height // layout.rows
    board = Image.new("RGBA", (layout.width, layout.height), (0, 0, 0, 0))
    for cell, frame_index in enumerate(board_indices):
        resized = source_frames[frame_index].resize(
            (cell_width, cell_height), Image.Resampling.NEAREST
        )
        board.alpha_composite(
            resized, ((cell % layout.columns) * cell_width, (cell // layout.columns) * cell_height)
        )
    board_path = source_root / "request_board.png"
    _save_png(board, board_path)

    requested_colors = [
        _hex_rgb(value) for value in (normalized_component or {}).get("colors", [])
    ]
    for color in _dominant_colors([source_frames[index] for index in indices], 10):
        if color not in requested_colors:
            requested_colors.append(color)
    requested_colors = requested_colors[:10]
    job: dict[str, Any] = {
        "schema_version": JOB_SCHEMA_VERSION,
        "kind": "pixel_forge_recraft_sprite_job",
        "job_id": resolved_id,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "state": "prepared",
        "mode": mode,
        "character_id": character_id,
        "base_id": base_id,
        "character_name": character_name,
        "camera": camera,
        "animation": animation,
        "direction": direction,
        "frame_count": frame_count,
        "selected_frame_indices": indices,
        "board_frame_indices": board_indices,
        "fps": int(record["fps"]),
        "frame_durations_ms": [int(value) for value in record["frame_durations_ms"]],
        "layout": asdict(layout),
        "source": {
            "sheet": _relative(source_sheet),
            "sheet_sha256": sha256_path(source_sheet),
            "regions": _relative(source_regions),
            "regions_sha256": sha256_path(source_regions),
            "board": _relative(board_path),
            "board_sha256": sha256_path(board_path),
            "heroic_manifest_sha256": sha256_path(HEROIC_MANIFEST),
            "style_profile_sha256": sha256_path(STYLE_PROFILE),
            "frame_sha256": {
                str(index): sha256_path(source_root / "frames" / f"frame_{index:02d}.png")
                for index in indices
            },
            "region_frame_sha256": {
                str(index): sha256_path(source_root / "regions" / f"frame_{index:02d}.png")
                for index in indices
            },
        },
        "pipeline": {
            "config": _relative(PIPELINE_CONFIG),
            "config_sha256": sha256_path(PIPELINE_CONFIG),
            "implementation": _relative(Path(__file__)),
            "implementation_sha256": sha256_path(Path(__file__)),
        },
        "component": normalized_component,
        "provider": {
            "name": "recraft",
            "endpoint": str(config["endpoint"]),
            "model": selected_model,
            "strength": float(config["default_strength"]),
            "response_format": str(config["response_format"]),
            "palette_colors": [list(color) for color in requested_colors],
            "prompt_contract_version": int(config["prompt_contract_version"]),
        },
        "candidates": [],
    }
    prompt, negative_prompt = _prompt(job)
    job["provider"]["prompt"] = prompt
    job["provider"]["negative_prompt"] = negative_prompt
    job["request_hash"] = _json_hash(
        {
            "source": job["source"],
            "mode": mode,
            "component": normalized_component,
            "provider": job["provider"],
            "pipeline": job["pipeline"],
            "frames": board_indices,
        }
    )
    _write_json(job_root / "job.json", job)
    _write_json(
        job_root / "request.json",
        {
            "endpoint": job["provider"]["endpoint"],
            "model": job["provider"]["model"],
            "strength": job["provider"]["strength"],
            "response_format": job["provider"]["response_format"],
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "controls": {
                "colors": [{"rgb": color} for color in job["provider"]["palette_colors"]]
            },
            "source_board": job["source"]["board"],
            "source_board_sha256": job["source"]["board_sha256"],
        },
    )
    return job_root


def load_job(job_root: Path) -> dict[str, Any]:
    root = Path(job_root).resolve()
    path = root / "job.json"
    job = _read_json(path)
    if (
        job.get("schema_version") != JOB_SCHEMA_VERSION
        or job.get("kind") != "pixel_forge_recraft_sprite_job"
    ):
        raise RecraftPipelineError(f"Unsupported Recraft job: {path}")
    expected_inputs = (
        (_resolve_repo_path(str(job["source"]["sheet"])), str(job["source"]["sheet_sha256"])),
        (
            _resolve_repo_path(str(job["source"]["regions"])),
            str(job["source"]["regions_sha256"]),
        ),
        (_resolve_repo_path(str(job["source"]["board"])), str(job["source"]["board_sha256"])),
        (HEROIC_MANIFEST, str(job["source"]["heroic_manifest_sha256"])),
        (STYLE_PROFILE, str(job["source"]["style_profile_sha256"])),
        (
            _resolve_repo_path(str(job["pipeline"]["config"])),
            str(job["pipeline"]["config_sha256"]),
        ),
        (
            _resolve_repo_path(str(job["pipeline"]["implementation"])),
            str(job["pipeline"]["implementation_sha256"]),
        ),
    )
    for input_path, expected_hash in expected_inputs:
        if not input_path.is_file() or sha256_path(input_path) != expected_hash:
            raise RecraftPipelineError(f"Recraft job input hash drift: {input_path}")
    for frame_index in job["selected_frame_indices"]:
        key = str(frame_index)
        frame = root / "source" / "frames" / f"frame_{int(frame_index):02d}.png"
        region = root / "source" / "regions" / f"frame_{int(frame_index):02d}.png"
        if not frame.is_file() or sha256_path(frame) != job["source"]["frame_sha256"][key]:
            raise RecraftPipelineError(f"Recraft source frame hash drift: {frame}")
        if (
            not region.is_file()
            or sha256_path(region) != job["source"]["region_frame_sha256"][key]
        ):
            raise RecraftPipelineError(f"Recraft source region hash drift: {region}")
    return job


def _update_job(job_root: Path, job: dict[str, Any], *, state: str | None = None) -> None:
    if state is not None:
        job["state"] = state
    job["updated_at"] = _utc_now()
    _write_json(Path(job_root) / "job.json", job)


def _binary_alpha(image: Image.Image, threshold: int) -> Image.Image:
    raw = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    visible = raw[..., 3] >= int(threshold)
    raw[~visible] = 0
    raw[visible, 3] = 255
    return Image.fromarray(raw, "RGBA")


def _sampling_atlas(images: Sequence[Image.Image]) -> Image.Image:
    if not images:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    columns = min(8, len(images))
    rows = math.ceil(len(images) / columns)
    atlas = Image.new("RGBA", (columns * 128, rows * 128), (0, 0, 0, 0))
    for index, frame in enumerate(images):
        atlas.alpha_composite(frame, ((index % columns) * 128, (index // columns) * 128))
    return atlas


def _normalize_cells(
    cells: Sequence[Image.Image], settings: Mapping[str, Any]
) -> tuple[list[Image.Image], list[tuple[int, int, int, int]]]:
    reduced = [
        _binary_alpha(
            area_resize(cell.convert("RGBA"), (128, 128)),
            int(settings["alpha_threshold"]),
        )
        for cell in cells
    ]
    palette_settings = PaletteExtractionSettings(
        palette_size=int(settings["palette_size"]),
        min_cluster_percent=0.0005,
        min_perceptual_distance=4.0,
        preserve_accent_colors=True,
        apply_family_cap_to_most_frequent=False,
    )
    palette, _debug = palette_from_image_with_debug(
        _sampling_atlas(reduced),
        max_colors=int(settings["palette_size"]),
        selection="most_frequent",
        settings=palette_settings,
    )
    opaque = [(*color[:3], 255) for color in palette if color[3] > 0]
    if not opaque:
        raise RecraftPipelineError("Candidate contains no visible colors")
    normalized: list[Image.Image] = []
    for frame in reduced:
        converted = quantize_to_palette(frame, opaque, dither=False)
        if int(settings["cleanup_threshold"]) > 0:
            converted = cluster_cleanup(
                converted, threshold=int(settings["cleanup_threshold"])
            )
        normalized.append(_binary_alpha(converted, 1))
    return normalized, opaque


def _normalize_source_to_palette(
    source: Image.Image,
    palette: Sequence[tuple[int, int, int, int]],
) -> Image.Image:
    """Apply the same final-scale transform used for candidate cells."""
    config = load_pipeline_config()["normalization"]
    converted = quantize_to_palette(source.convert("RGBA"), list(palette), dither=False)
    if int(config["cleanup_threshold"]) > 0:
        converted = cluster_cleanup(
            converted, threshold=int(config["cleanup_threshold"])
        )
    return _binary_alpha(converted, 1)


def _split_cells(image: Image.Image, layout: Layout) -> list[Image.Image]:
    if image.width % layout.columns or image.height % layout.rows:
        raise RecraftPipelineError(
            f"Candidate {image.size} is not divisible by layout {layout.name}"
        )
    width = image.width // layout.columns
    height = image.height // layout.rows
    return [
        image.crop(
            (
                (index % layout.columns) * width,
                (index // layout.columns) * height,
                (index % layout.columns + 1) * width,
                (index // layout.columns + 1) * height,
            )
        )
        for index in range(layout.cell_count)
    ]


def _mask(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGBA"), dtype=np.uint8)[..., 3] > 0


def _translated(mask: np.ndarray, dx: int, dy: int) -> np.ndarray:
    result = np.zeros_like(mask)
    source_x0 = max(0, -dx)
    source_x1 = min(mask.shape[1], mask.shape[1] - dx)
    source_y0 = max(0, -dy)
    source_y1 = min(mask.shape[0], mask.shape[0] - dy)
    if source_x1 <= source_x0 or source_y1 <= source_y0:
        return result
    result[source_y0 + dy : source_y1 + dy, source_x0 + dx : source_x1 + dx] = mask[
        source_y0:source_y1, source_x0:source_x1
    ]
    return result


def _iou(first: np.ndarray, second: np.ndarray) -> float:
    union = np.count_nonzero(first | second)
    return 1.0 if union == 0 else float(np.count_nonzero(first & second) / union)


def _best_registration(candidate: np.ndarray, source: np.ndarray) -> tuple[int, int, float]:
    best = (0, 0, _iou(candidate, source))
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            score = _iou(_translated(candidate, dx, dy), source)
            if score > best[2] + 1e-12:
                best = (dx, dy, score)
    return best


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    points = np.argwhere(mask)
    if not len(points):
        return None
    top, left = points.min(axis=0)
    bottom, right = points.max(axis=0) + 1
    return int(left), int(top), int(right), int(bottom)


def _centroid(mask: np.ndarray) -> tuple[float, float]:
    points = np.argwhere(mask)
    if not len(points):
        # Keep persisted reports strict-JSON compatible even for empty candidates.
        return 999.0, 999.0
    y, x = points.mean(axis=0)
    return float(x), float(y)


def _safe_margin(mask: np.ndarray) -> int:
    bounds = _bbox(mask)
    if bounds is None:
        return 0
    left, top, right, bottom = bounds
    return min(left, top, mask.shape[1] - right, mask.shape[0] - bottom)


def _shape_score(candidate: np.ndarray, source: np.ndarray) -> float:
    candidate = binary_dilation(candidate, iterations=1)
    source = binary_dilation(source, iterations=1)
    overlap = _iou(candidate, source)
    candidate_edge = candidate & ~binary_erosion(candidate)
    source_edge = source & ~binary_erosion(source)
    edge_union = np.count_nonzero(candidate_edge | source_edge)
    edge_iou = (
        1.0 if edge_union == 0 else np.count_nonzero(candidate_edge & source_edge) / edge_union
    )
    distance = distance_transform_edt(~source_edge)
    edge_points = distance[candidate_edge]
    distance_score = 1.0 if not len(edge_points) else math.exp(-float(edge_points.mean()) / 3.0)
    return float(0.55 * overlap + 0.25 * edge_iou + 0.20 * distance_score)


def _metric_failed(value: float, rule: Mapping[str, Any]) -> bool:
    threshold = float(rule["threshold"])
    return value < threshold if rule["direction"] == "higher" else value > threshold


def _frame_metrics(
    *,
    board_cell: int,
    frame_index: int,
    candidate: Image.Image,
    raw_cell: Image.Image,
    source: Image.Image,
    region_image: Image.Image,
    all_source_frames: Sequence[Image.Image],
    profile: Mapping[str, Any],
) -> FrameMetrics:
    candidate_mask = _mask(candidate)
    source_mask = _mask(source)
    if not np.any(candidate_mask):
        return FrameMetrics(
            board_cell, frame_index, 0, 0, 0.0, 0.0, 0.0, 999.0, 999.0,
            0.0, 0.0, -1, -1.0, 0, 0, ("empty_frame",), ()
        )
    dx, dy, silhouette_iou = _best_registration(candidate_mask, source_mask)
    aligned = _translated(candidate_mask, dx, dy)
    core_recall = float(
        np.count_nonzero(aligned & source_mask) / max(1, np.count_nonzero(source_mask))
    )
    source_center = _centroid(source_mask)
    candidate_center = _centroid(candidate_mask)
    centroid_drift = math.dist(source_center, candidate_center)
    source_box = _bbox(source_mask)
    candidate_box = _bbox(candidate_mask)
    assert source_box is not None and candidate_box is not None
    source_size = (source_box[2] - source_box[0], source_box[3] - source_box[1])
    candidate_size = (
        candidate_box[2] - candidate_box[0],
        candidate_box[3] - candidate_box[1],
    )
    bbox_delta = max(
        abs(candidate_size[0] - source_size[0]) / max(1, source_size[0]),
        abs(candidate_size[1] - source_size[1]) / max(1, source_size[1]),
    )
    regions = np.asarray(region_image.convert("L"), dtype=np.uint8)
    present_ids = [int(value) for value in np.unique(regions) if value > 0]
    recalls = [
        np.count_nonzero(aligned & (regions == region_id))
        / max(1, np.count_nonzero(regions == region_id))
        for region_id in present_ids
    ]
    minimum_region_recall = float(min(recalls, default=0.0))
    structural = candidate_mask & binary_dilation(source_mask, iterations=4)
    pose_scores = [
        _shape_score(structural, _mask(other)) for other in all_source_frames
    ]
    expected_pose_score = float(pose_scores[frame_index])
    best_pose_frame = int(np.argmax(pose_scores))
    best_pose_score = float(pose_scores[best_pose_frame])
    ordered = sorted(pose_scores, reverse=True)
    pose_margin = float(ordered[0] - ordered[1]) if len(ordered) > 1 else 1.0
    raw_alpha = np.asarray(raw_cell.convert("RGBA"), dtype=np.uint8)[..., 3]
    partial = int(np.count_nonzero((raw_alpha > 0) & (raw_alpha < 255)))
    values = {
        "silhouette_iou": silhouette_iou,
        "core_recall": core_recall,
        "minimum_region_recall": minimum_region_recall,
        "centroid_drift_px": centroid_drift,
        "bbox_size_delta_ratio": bbox_delta,
    }
    errors = [
        name
        for name, rule in profile["hard_metrics"].items()
        if _metric_failed(values[name], rule)
    ]
    safe_margin = _safe_margin(candidate_mask)
    if safe_margin < 4:
        errors.append("unsafe_canvas_margin")
    warnings: list[str] = []
    if best_pose_frame != frame_index:
        pose_rule = profile.get("warning_metrics", {}).get("pose_match_margin", {})
        pose_threshold = float(pose_rule.get("threshold", 0.01))
        if pose_margin >= pose_threshold:
            errors.append("unexpected_pose_match")
        else:
            warnings.append("ambiguous_pose_match")
    return FrameMetrics(
        board_cell=board_cell,
        source_frame=frame_index,
        registration_dx=dx,
        registration_dy=dy,
        silhouette_iou=silhouette_iou,
        core_recall=core_recall,
        minimum_region_recall=minimum_region_recall,
        centroid_drift_px=centroid_drift,
        bbox_size_delta_ratio=float(bbox_delta),
        expected_pose_score=expected_pose_score,
        best_pose_score=best_pose_score,
        best_pose_frame=best_pose_frame,
        pose_match_margin=pose_margin,
        safe_margin_px=safe_margin,
        raw_partial_alpha_pixels=partial,
        errors=tuple(sorted(set(errors))),
        warnings=tuple(sorted(set(warnings))),
    )


def _component_masks(
    job: Mapping[str, Any],
    source: Image.Image,
    candidate: Image.Image,
    regions_image: Image.Image,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    component = job["component"]
    regions = np.asarray(regions_image.convert("L"), dtype=np.uint8)
    allowed_names: list[str] = []
    protected_names: list[str] = []
    for slot in component["occupies_slots"]:
        allowed_names.extend(SLOT_SURFACE_REGIONS[slot])
        protected_names.extend(SLOT_PROTECTED_REGIONS[slot])
    allowed_ids = [REGION_BY_NAME[name].id for name in dict.fromkeys(allowed_names)]
    protected_ids = [REGION_BY_NAME[name].id for name in dict.fromkeys(protected_names)]
    legal = np.isin(regions, allowed_ids)
    legal = binary_dilation(legal, iterations=int(component["envelope_px"]))
    protected = np.isin(regions, protected_ids)
    legal &= ~protected
    source_raw = np.asarray(source.convert("RGBA"), dtype=np.int16)
    candidate_raw = np.asarray(candidate.convert("RGBA"), dtype=np.int16)
    color_distance = np.max(np.abs(candidate_raw[..., :3] - source_raw[..., :3]), axis=2)
    alpha_changed = candidate_raw[..., 3] != source_raw[..., 3]
    candidate_visible = candidate_raw[..., 3] > 0
    strong_change = (color_distance >= 16) | alpha_changed
    weak_change = (color_distance >= 6) | alpha_changed
    component_mask = candidate_visible & legal & strong_change
    uncertain = candidate_visible & legal & weak_change & ~strong_change
    illegal = candidate_visible & ~legal & ~(_mask(source))
    return component_mask, uncertain, illegal


def _derive_ramp(images: Sequence[Image.Image], max_colors: int = 5) -> list[tuple[int, int, int, int]]:
    visible = [image for image in images if image.getchannel("A").getbbox() is not None]
    if not visible:
        return []
    palette, _debug = palette_from_image_with_debug(
        _sampling_atlas(visible),
        max_colors=max_colors,
        selection="most_frequent",
        settings=PaletteExtractionSettings(
            palette_size=max_colors,
            min_cluster_percent=0.0,
            min_perceptual_distance=3.0,
            preserve_accent_colors=True,
            apply_family_cap_to_most_frequent=False,
        ),
    )
    return [(*color[:3], 255) for color in palette if color[3] > 0]


def _save_strip(frames: Sequence[Image.Image], path: Path) -> Image.Image:
    sheet = Image.new("RGBA", (128 * len(frames), 128), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, (index * 128, 0))
    _save_png(sheet, path)
    return sheet


def _save_gif(
    frames: Sequence[Image.Image], path: Path, durations: Sequence[int], *, scale: int = 1
) -> None:
    if not frames:
        return
    rendered: list[Image.Image] = []
    for frame in frames:
        scaled = frame.resize((128 * scale, 128 * scale), Image.Resampling.NEAREST)
        background = Image.new("RGBA", scaled.size, (27, 29, 34, 255))
        background.alpha_composite(scaled)
        rendered.append(background.convert("RGB"))
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=rendered[1:],
        duration=[int(value) for value in durations],
        loop=0,
        optimize=False,
        disposal=2,
    )


def _difference_image(source: Image.Image, candidate: Image.Image) -> Image.Image:
    first = np.asarray(source.convert("RGBA"), dtype=np.int16)
    second = np.asarray(candidate.convert("RGBA"), dtype=np.int16)
    distance = np.max(np.abs(first - second), axis=2).astype(np.uint8)
    result = np.zeros_like(first, dtype=np.uint8)
    result[..., 0] = distance
    result[..., 1] = np.minimum(255, distance * 2)
    result[..., 3] = np.where(distance > 0, 255, 0)
    return Image.fromarray(result, "RGBA")


def _write_review_html(
    job_root: Path,
    candidate_root: Path,
    job: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> None:
    frame_rows: list[str] = []
    for metric in validation["frames"]:
        cell = int(metric["board_cell"])
        frame = int(metric["source_frame"])
        error_text = ", ".join(metric["errors"]) or "—"
        warning_text = ", ".join(metric["warnings"]) or "—"
        extracted = (
            f'<img src="../extracted/frame_{cell:02d}.png">'
            if job["mode"] == "component"
            else "—"
        )
        uncertain = (
            f'<img src="../extracted/uncertain/frame_{cell:02d}.png">'
            if job["mode"] == "component"
            else "—"
        )
        frame_rows.append(
            "<tr>"
            f"<td>{frame + 1}</td>"
            f'<td><img src="../../../source/frames/frame_{frame:02d}.png"></td>'
            f'<td><img src="../normalized/frame_{cell:02d}.png"></td>'
            f"<td>{extracted}</td>"
            f"<td>{uncertain}</td>"
            f'<td><img src="../review/diff_{cell:02d}.png"></td>'
            f"<td>IoU {metric['silhouette_iou']:.3f}<br>Core {metric['core_recall']:.3f}<br>"
            f"Pose → {int(metric['best_pose_frame']) + 1}</td>"
            f"<td class=bad>{html.escape(error_text)}</td>"
            f"<td class=warn>{html.escape(warning_text)}</td>"
            "</tr>"
        )
    title = html.escape(
        f"{job['character_name']} · {job['camera']} · {job['animation']} · {job['direction']}"
    )
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Pixel Forge Recraft Review</title>
<style>
body{{font:14px system-ui;background:#1b1d22;color:#eee;margin:24px}} h1{{font-size:22px}}
img{{width:128px;height:128px;image-rendering:pixelated;background:#24272d}}
.board{{width:auto;height:256px;max-width:100%;object-fit:contain}}
table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #454953;padding:6px;vertical-align:top}}
.bad{{color:#ff8888}} .warn{{color:#ffd27b}} button{{font-size:16px;padding:10px 18px;margin:8px}}
textarea{{width:600px;max-width:90%;height:80px}} .status{{font-weight:700}}
</style></head><body>
<h1>{title}</h1>
<p class="status">Automatic result: {html.escape(str(validation['status']).upper())}</p>
<p>Automatic validation never constitutes artistic approval. Review the complete native-speed loop.</p>
<h2>Request and raw response boards</h2>
<p><img class="board" src="../../../source/request_board.png" alt="authoritative request board">
<img class="board" src="../raw/output.png" alt="raw provider response"></p>
<h2>Complete-loop playback</h2>
<p><img src="../review/normalized.gif"> {'<img src="../review/extracted.gif">' if job['mode'] == 'component' else ''}</p>
<details><summary>Nearest-neighbor 8x playback</summary>
<p><img class="board" src="../review/normalized_8x.gif"> {'<img class="board" src="../review/extracted_8x.gif">' if job['mode'] == 'component' else ''}</p>
</details>
<table><thead><tr><th>Frame</th><th>Authority</th><th>Candidate</th><th>Extracted</th><th>Uncertain</th><th>Difference</th><th>Metrics</th><th>Errors</th><th>Warnings</th></tr></thead>
<tbody>{''.join(frame_rows)}</tbody></table>
<h2>Manual decision</h2><textarea id="notes" placeholder="Review notes"></textarea><br>
<button onclick="decide('approved')">Approve complete loop</button>
<button onclick="decide('rejected')">Reject</button><span id="saved"></span>
<script>
async function decide(status){{
 const response=await fetch('/api/review',{{method:'POST',headers:{{'Content-Type':'application/json'}},
 body:JSON.stringify({{status,notes:document.getElementById('notes').value}})}});
 document.getElementById('saved').textContent=response.ok?' Saved.':' Save failed.';
}}
</script></body></html>"""
    target = candidate_root / "review" / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8", newline="\n")


def process_candidate(
    job_root: Path,
    candidate_id: str,
    *,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Normalize, validate, extract, and generate review artifacts."""
    job_root = Path(job_root).resolve()
    job = load_job(job_root)
    source_candidate_root = job_root / "candidates" / candidate_id
    candidate_root = Path(output_root).resolve() if output_root else source_candidate_root
    candidate_manifest = _read_json(source_candidate_root / "candidate.json")
    raw_path = source_candidate_root / "raw" / "output.png"
    with Image.open(raw_path) as opened:
        raw = opened.convert("RGBA")
    ingest_layout = parse_layout(str(candidate_manifest["ingest_layout"]))
    strict = bool(candidate_manifest.get("strict_layout", False))
    expected_layout = parse_layout(str(job["layout"]["name"]))
    layout_errors: list[str] = []
    if strict and ingest_layout.name != expected_layout.name:
        layout_errors.append("wrong_layout")
    raw_cells = _split_cells(raw, ingest_layout)
    required = len(job["board_frame_indices"])
    if len(raw_cells) < required:
        raise RecraftPipelineError(
            f"Candidate has {len(raw_cells)} cells; job requires {required}"
        )
    config = load_pipeline_config()
    normalized, palette = _normalize_cells(raw_cells[:required], config["normalization"])
    normalized_root = candidate_root / "normalized"
    for cell, frame in enumerate(normalized):
        _save_png(frame, normalized_root / f"frame_{cell:02d}.png")
    actual_count = len(job["selected_frame_indices"])
    actual_normalized = normalized[:actual_count]
    _save_strip(actual_normalized, normalized_root / "contact_sheet.png")

    record, sheet_path, regions_path = _source_record(
        str(job["character_id"]), str(job["camera"]), str(job["animation"])
    )
    row = _direction_row(str(job["base_id"]), str(job["animation"]), str(job["direction"]))
    all_sources = _sheet_frames(
        sheet_path, frame_count=int(record["frame_count"]), row=row
    )
    all_regions = _sheet_frames(
        regions_path, frame_count=int(record["frame_count"]), row=row, mode="L"
    )
    profile = load_validation_profile()
    metrics: list[FrameMetrics] = []
    extracted_frames: list[Image.Image] = []
    uncertain_frames: list[Image.Image] = []
    illegal_counts: list[int] = []
    layer_frames: dict[str, list[Image.Image]] = {}
    cleanup_reports: list[dict[str, Any]] = []
    provisional_components: list[Image.Image] = []
    for cell, frame_index in enumerate(job["selected_frame_indices"]):
        source = all_sources[int(frame_index)]
        extraction_source = _normalize_source_to_palette(source, palette)
        region = all_regions[int(frame_index)]
        metric = _frame_metrics(
            board_cell=cell,
            frame_index=int(frame_index),
            candidate=actual_normalized[cell],
            raw_cell=raw_cells[cell],
            source=source,
            region_image=region,
            all_source_frames=all_sources,
            profile=profile,
        )
        metrics.append(metric)
        _save_png(
            _difference_image(source, actual_normalized[cell]),
            candidate_root / "review" / f"diff_{cell:02d}.png",
        )
        if job["mode"] != "component":
            continue
        component_mask, uncertain, illegal = _component_masks(
            job, extraction_source, actual_normalized[cell], region
        )
        candidate_array = np.asarray(actual_normalized[cell], dtype=np.uint8).copy()
        candidate_array[~component_mask] = 0
        component_frame = Image.fromarray(candidate_array, "RGBA")
        provisional_components.append(component_frame)
        uncertain_array = np.zeros_like(candidate_array)
        uncertain_array[uncertain] = (255, 196, 0, 255)
        uncertain_frames.append(Image.fromarray(uncertain_array, "RGBA"))
        illegal_counts.append(int(np.count_nonzero(illegal)))

    ramp = _derive_ramp(provisional_components, max_colors=5)
    if job["mode"] == "component":
        cleanup_palette = tuple(color[:3] for color in ramp) or ((255, 255, 255),)
        outline = min(
            cleanup_palette,
            key=lambda color: 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2],
        )
        for cell, (frame_index, frame) in enumerate(
            zip(job["selected_frame_indices"], provisional_components, strict=True)
        ):
            cleaned, cleanup = cleanup_component_frame(
                frame,
                outline_rgb=outline,
                palette=cleanup_palette,
                protected_components=int(job["component"]["expected_pieces"]),
            )
            extracted_frames.append(cleaned)
            cleanup_reports.append(cleanup.to_dict())
            _save_png(cleaned, candidate_root / "extracted" / f"frame_{cell:02d}.png")
            _save_png(
                uncertain_frames[cell],
                candidate_root / "extracted" / "uncertain" / f"frame_{cell:02d}.png",
            )
            component = job["component"]
            region_ids = np.asarray(all_regions[int(frame_index)].convert("L"), dtype=np.uint8)
            assigned = np.zeros((128, 128), dtype=bool)
            for render_layer, region_names in component["render_layers"].items():
                if region_names:
                    ids = [REGION_BY_NAME[name].id for name in region_names]
                    layer_mask = binary_dilation(
                        np.isin(region_ids, ids), iterations=int(component["envelope_px"])
                    ) & _mask(cleaned) & ~assigned
                elif render_layer == component["layer"]:
                    layer_mask = _mask(cleaned) & ~assigned
                else:
                    layer_mask = np.zeros((128, 128), dtype=bool)
                raw_layer = np.asarray(cleaned, dtype=np.uint8).copy()
                raw_layer[~layer_mask] = 0
                layer_frames.setdefault(render_layer, []).append(
                    Image.fromarray(raw_layer, "RGBA")
                )
                assigned |= layer_mask
        _save_strip(extracted_frames, candidate_root / "extracted" / "contact_sheet.png")
        for render_layer, frames in layer_frames.items():
            for cell, frame in enumerate(frames):
                _save_png(
                    frame,
                    candidate_root / "extracted" / "layers" / render_layer / f"frame_{cell:02d}.png",
                )

    duplicate_pairs: list[list[int]] = []
    for first in range(len(actual_normalized)):
        for second in range(first + 1, len(actual_normalized)):
            candidate_iou = _iou(_mask(actual_normalized[first]), _mask(actual_normalized[second]))
            source_first = all_sources[int(job["selected_frame_indices"][first])]
            source_second = all_sources[int(job["selected_frame_indices"][second])]
            source_iou = _iou(_mask(source_first), _mask(source_second))
            if candidate_iou >= 0.985 and source_iou < 0.94:
                duplicate_pairs.append([first, second])
    sentinel_checks: list[dict[str, Any]] = []
    sentinel_errors: list[str] = []
    sentinel_warnings: list[str] = []
    for cell in range(actual_count, len(job["board_frame_indices"])):
        frame_index = int(job["board_frame_indices"][cell])
        try:
            authority_cell = [int(value) for value in job["selected_frame_indices"]].index(
                frame_index
            )
        except ValueError as exc:
            raise RecraftPipelineError("Sentinel references an unselected source frame") from exc
        first = np.asarray(normalized[authority_cell].convert("RGBA"), dtype=np.int16)
        second = np.asarray(normalized[cell].convert("RGBA"), dtype=np.int16)
        silhouette_iou = _iou(first[..., 3] > 0, second[..., 3] > 0)
        exact_pixel_ratio = float(np.mean(np.all(first == second, axis=2)))
        sentinel_checks.append(
            {
                "cell": cell,
                "source_frame": frame_index,
                "authority_cell": authority_cell,
                "silhouette_iou": silhouette_iou,
                "exact_pixel_ratio": exact_pixel_ratio,
            }
        )
        if silhouette_iou < 0.90:
            sentinel_errors.append(f"sentinel_pose_mismatch_cell_{cell + 1}")
        elif exact_pixel_ratio < 0.90:
            sentinel_warnings.append(f"sentinel_render_inconsistency_cell_{cell + 1}")
    all_errors = set(layout_errors)
    all_warnings: set[str] = set()
    for metric in metrics:
        all_errors.update(metric.errors)
        all_warnings.update(metric.warnings)
    if duplicate_pairs:
        all_errors.add("accidental_duplicate_pose")
    all_errors.update(sentinel_errors)
    all_warnings.update(sentinel_warnings)
    if job["mode"] == "component" and any(illegal_counts):
        all_warnings.add("illegal_candidate_excursions_discarded")
    areas = [np.count_nonzero(_mask(frame)) for frame in extracted_frames]
    if areas:
        median = float(np.median(areas))
        minimum_ratio = min(areas) / max(1.0, median)
        component_rule = profile.get("warning_metrics", {}).get(
            "component_area_ratio_to_median", {}
        )
        if minimum_ratio < float(component_rule.get("threshold", 0.50)):
            all_warnings.add("component_popping_or_missing")
    validation = {
        "schema_version": 1,
        "kind": "pixel_forge_recraft_candidate_validation",
        "job_id": job["job_id"],
        "candidate_id": candidate_id,
        "status": "reject" if all_errors else ("warn" if all_warnings else "pass"),
        "profile": _relative(VALIDATION_PROFILE),
        "profile_sha256": sha256_path(VALIDATION_PROFILE),
        "frames": [asdict(metric) for metric in metrics],
        "errors": sorted(all_errors),
        "warnings": sorted(all_warnings),
        "duplicate_pairs": duplicate_pairs,
        "sentinel_checks": sentinel_checks,
        "illegal_excursion_pixels": illegal_counts,
        "shared_palette": [list(color) for color in palette],
        "component_ramp": [list(color) for color in ramp],
        "cleanup_reports": cleanup_reports,
        "manual_review_required": True,
    }
    _write_json(candidate_root / "validation.json", validation)
    durations = [
        int(job["frame_durations_ms"][int(frame_index)])
        for frame_index in job["selected_frame_indices"]
    ]
    _save_gif(actual_normalized, candidate_root / "review" / "normalized.gif", durations)
    _save_gif(actual_normalized, candidate_root / "review" / "normalized_8x.gif", durations, scale=8)
    if extracted_frames:
        _save_gif(extracted_frames, candidate_root / "review" / "extracted.gif", durations)
        _save_gif(extracted_frames, candidate_root / "review" / "extracted_8x.gif", durations, scale=8)
    _write_review_html(job_root, candidate_root, job, validation)

    if output_root is None:
        candidate_manifest["processed_at"] = _utc_now()
        candidate_manifest["state"] = "validated"
        candidate_manifest["validation_status"] = validation["status"]
        candidate_manifest["outputs_sha256"] = {
            path.relative_to(candidate_root).as_posix(): sha256_path(path)
            for path in sorted(candidate_root.rglob("*"))
            if path.is_file() and path.name not in {"candidate.json"}
        }
        _write_json(candidate_root / "candidate.json", candidate_manifest)
        job = load_job(job_root)
        for record in job["candidates"]:
            if record["id"] == candidate_id:
                record["state"] = "validated"
                record["validation_status"] = validation["status"]
        _update_job(job_root, job, state="validated")
    return validation


def ingest_candidate(
    job_root: Path,
    source: Path,
    *,
    layout: str,
    candidate_id: str | None = None,
    strict_layout: bool = False,
    provider: Mapping[str, Any] | None = None,
) -> str:
    """Copy a downloaded or API result into a job and process it."""
    job_root = Path(job_root).resolve()
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    parsed = parse_layout(layout)
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    if image.width < parsed.columns or image.height < parsed.rows:
        raise RecraftPipelineError("Candidate is smaller than its declared layout")
    suffix = hashlib.sha256(source.read_bytes()).hexdigest()[:10]
    resolved_id = _slug(candidate_id or f"candidate-{suffix}")
    candidate_root = job_root / "candidates" / resolved_id
    if candidate_root.exists():
        raise FileExistsError(candidate_root)
    raw_path = candidate_root / "raw" / "output.png"
    _save_png(image, raw_path)
    manifest = {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "kind": "pixel_forge_recraft_candidate",
        "id": resolved_id,
        "state": "received",
        "received_at": _utc_now(),
        "ingest_layout": parsed.name,
        "strict_layout": bool(strict_layout),
        "raw_source": _relative(source),
        "raw_sha256": sha256_path(raw_path),
        "provider": dict(provider or {"kind": "manual_import"}),
    }
    _write_json(candidate_root / "candidate.json", manifest)
    job = load_job(job_root)
    if any(record["id"] == resolved_id for record in job["candidates"]):
        raise RecraftPipelineError(f"Duplicate candidate id {resolved_id}")
    job["candidates"].append({"id": resolved_id, "state": "received"})
    _update_job(job_root, job, state="received")
    process_candidate(job_root, resolved_id)
    return resolved_id


def record_review(
    job_root: Path, candidate_id: str, *, status: str, notes: str = ""
) -> dict[str, Any]:
    if status not in ("approved", "rejected"):
        raise RecraftPipelineError("Review status must be approved or rejected")
    job_root = Path(job_root).resolve()
    candidate_root = job_root / "candidates" / candidate_id
    validation = _read_json(candidate_root / "validation.json")
    decision = {
        "schema_version": 1,
        "job_id": load_job(job_root)["job_id"],
        "candidate_id": candidate_id,
        "status": status,
        "notes": str(notes),
        "reviewed_at": _utc_now(),
        "validation_status": validation["status"],
        "validation_sha256": sha256_path(candidate_root / "validation.json"),
    }
    _write_json(candidate_root / "review.json", decision)
    job = load_job(job_root)
    for record in job["candidates"]:
        if record["id"] == candidate_id:
            record["state"] = status
            record["review"] = _relative(candidate_root / "review.json")
    _update_job(job_root, job, state="reviewed")
    return decision


class _ReviewHandler(SimpleHTTPRequestHandler):
    job_root: Path
    candidate_id: str

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/review":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 64_000:
                raise ValueError("invalid request length")
            payload = json.loads(self.rfile.read(length))
            decision = record_review(
                self.job_root,
                self.candidate_id,
                status=str(payload["status"]),
                notes=str(payload.get("notes", "")),
            )
            encoded = json.dumps(decision).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except (KeyError, OSError, RecraftPipelineError, ValueError) as exc:  # pragma: no cover
            encoded = json.dumps({"error": str(exc)}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)


def serve_review(
    job_root: Path,
    candidate_id: str,
    *,
    port: int = 0,
    open_browser: bool = True,
) -> None:
    job_root = Path(job_root).resolve()
    candidate_root = job_root / "candidates" / candidate_id
    if not (candidate_root / "review" / "index.html").is_file():
        raise FileNotFoundError(candidate_root / "review" / "index.html")

    class Handler(_ReviewHandler):
        pass

    Handler.job_root = job_root
    Handler.candidate_id = candidate_id
    handler = lambda *args, **kwargs: Handler(
        *args, directory=str(job_root), **kwargs
    )
    server = ThreadingHTTPServer(("127.0.0.1", int(port)), handler)
    url = (
        f"http://127.0.0.1:{server.server_port}/candidates/"
        f"{candidate_id}/review/index.html"
    )
    print(f"Recraft review: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def check_candidate(job_root: Path, candidate_id: str) -> list[str]:
    """Reprocess a candidate and return deterministic output mismatches."""
    job_root = Path(job_root).resolve()
    actual_root = job_root / "candidates" / candidate_id
    with tempfile.TemporaryDirectory(prefix="pf-recraft-check-") as temporary:
        expected_root = Path(temporary) / "candidate"
        process_candidate(job_root, candidate_id, output_root=expected_root)
        mismatches: list[str] = []
        compare_roots = ("normalized", "extracted", "review")
        for directory in compare_roots:
            for expected in sorted((expected_root / directory).rglob("*")):
                if not expected.is_file() or expected.suffix.lower() == ".html":
                    continue
                relative = expected.relative_to(expected_root)
                actual = actual_root / relative
                if not actual.is_file() or actual.read_bytes() != expected.read_bytes():
                    mismatches.append(relative.as_posix())
        expected_validation = expected_root / "validation.json"
        actual_validation = actual_root / "validation.json"
        if not actual_validation.is_file() or actual_validation.read_bytes() != expected_validation.read_bytes():
            mismatches.append("validation.json")
        return sorted(set(mismatches))


def calibrate_validation_profile(
    job_roots: Sequence[Path],
    *,
    output_path: Path = VALIDATION_PROFILE,
) -> dict[str, Any]:
    """Learn only perfectly separating gates from manual candidate decisions."""
    rows: list[tuple[str, Mapping[str, Any]]] = []
    for job_root in job_roots:
        job = load_job(job_root)
        for record in job["candidates"]:
            candidate_root = Path(job_root) / "candidates" / record["id"]
            review_path = candidate_root / "review.json"
            if not review_path.is_file():
                continue
            review = _read_json(review_path)
            validation = _read_json(candidate_root / "validation.json")
            for frame in validation["frames"]:
                rows.append((str(review["status"]), frame))
    approved = [frame for status, frame in rows if status == "approved"]
    rejected = [frame for status, frame in rows if status == "rejected"]
    if not approved or not rejected:
        raise RecraftPipelineError(
            "Calibration needs at least one approved and one rejected candidate"
        )
    directions = {
        "silhouette_iou": "higher",
        "core_recall": "higher",
        "minimum_region_recall": "higher",
        "centroid_drift_px": "lower",
        "bbox_size_delta_ratio": "lower",
        "pose_match_margin": "higher",
    }
    hard: dict[str, Any] = {}
    warning: dict[str, Any] = {}
    for metric, direction in directions.items():
        good = [float(frame[metric]) for frame in approved]
        bad = [float(frame[metric]) for frame in rejected]
        if direction == "higher" and min(good) > max(bad):
            hard[metric] = {
                "direction": direction,
                "threshold": (min(good) + max(bad)) / 2.0,
                "calibration": {"minimum_approved": min(good), "maximum_rejected": max(bad)},
            }
        elif direction == "lower" and max(good) < min(bad):
            hard[metric] = {
                "direction": direction,
                "threshold": (max(good) + min(bad)) / 2.0,
                "calibration": {"maximum_approved": max(good), "minimum_rejected": min(bad)},
            }
        else:
            warning[metric] = {
                "direction": direction,
                "reason": "Manual labels overlap; human review remains authoritative.",
                "approved_range": [min(good), max(good)],
                "rejected_range": [min(bad), max(bad)],
            }
    profile = {
        "schema_version": 1,
        "id": "recraft_heroic_component_v1",
        "status": "calibrated",
        "calibrated_at": _utc_now(),
        "approved_frame_samples": len(approved),
        "rejected_frame_samples": len(rejected),
        "hard_metrics": hard,
        "warning_metrics": warning,
        "always_hard_reject": [
            "wrong_layout", "empty_frame", "unsafe_canvas_margin",
            "unexpected_pose_match", "accidental_duplicate_pose",
        ],
        "source_jobs": [
            {"job_id": load_job(root)["job_id"], "job_sha256": sha256_path(Path(root) / "job.json")}
            for root in job_roots
        ],
        "policy": "Only metrics that perfectly separated calibration labels became hard gates.",
    }
    _write_json(Path(output_path), profile)
    return profile


class RecraftClient:
    """Small direct REST client; it never serializes its bearer token."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        config = load_pipeline_config()
        self._token = token or os.environ.get("RECRAFT_API_TOKEN", "")
        if not self._token:
            raise RecraftPipelineError("RECRAFT_API_TOKEN is not set")
        self._client = httpx.Client(
            base_url=base_url or str(config["base_url"]),
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def doctor(self) -> dict[str, Any]:
        response = self._client.get("/users/me")
        response.raise_for_status()
        data = response.json()
        return {
            "id": data.get("id"),
            "email": data.get("email"),
            "name": data.get("name"),
            "credits": int(data.get("credits", 0)),
        }

    def image_to_image(
        self,
        *,
        image: Path,
        prompt: str,
        negative_prompt: str,
        model: str,
        strength: float,
        seed: int,
        colors: Sequence[Sequence[int]],
    ) -> tuple[bytes, dict[str, Any]]:
        encoded_image = base64.b64encode(Path(image).read_bytes()).decode("ascii")
        body = {
            "image_url": f"data:image/png;base64,{encoded_image}",
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "model": model,
            "strength": float(strength),
            "random_seed": int(seed),
            "n": 1,
            "response_format": "b64_json",
            "controls": {"colors": [{"rgb": [int(v) for v in color]} for color in colors[:10]]},
        }
        try:
            response = self._client.post("/images/imageToImage", json=body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise RecraftAmbiguousSubmissionError(
                "Ambiguous Recraft POST failure; the request was not automatically retried "
                "because it may already have consumed API units."
            ) from exc
        response.raise_for_status()
        payload = response.json()
        try:
            record = payload["data"][0]
            image_bytes = base64.b64decode(record["b64_json"], validate=True)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RecraftPipelineError("Recraft returned no decodable b64_json image") from exc
        public_meta = {
            "response": {key: value for key, value in payload.items() if key != "data"},
            "image": {
                key: value for key, value in record.items() if key not in {"b64_json", "url"}
            },
        }
        return image_bytes, public_meta


def submit_job_candidates(
    job_root: Path,
    *,
    strengths: Sequence[float],
    seeds: Sequence[int],
    max_outputs: int,
    submit: bool,
    client: RecraftClient | None = None,
) -> list[str]:
    if not submit:
        raise RecraftPipelineError("Paid submission requires the explicit --submit flag")
    combinations = [(float(strength), int(seed)) for strength in strengths for seed in seeds]
    if len(combinations) > int(max_outputs):
        raise RecraftPipelineError(
            f"Requested {len(combinations)} outputs exceeds --max-outputs {max_outputs}"
        )
    job_root = Path(job_root).resolve()
    job = load_job(job_root)
    owned_client = client is None
    active = client or RecraftClient()
    submitted: list[str] = []
    try:
        before = active.doctor()
        if before["credits"] <= 0:
            raise RecraftPipelineError("Recraft account has no API units")
        for strength, seed in combinations:
            candidate_id = _slug(f"recraft-{job['provider']['model']}-s{strength:.3f}-seed{seed}")
            if (job_root / "candidates" / candidate_id).exists():
                raise FileExistsError(job_root / "candidates" / candidate_id)
            started = time.perf_counter()
            try:
                image_bytes, response_meta = active.image_to_image(
                    image=_resolve_repo_path(str(job["source"]["board"])),
                    prompt=str(job["provider"]["prompt"]),
                    negative_prompt=str(job["provider"]["negative_prompt"]),
                    model=str(job["provider"]["model"]),
                    strength=strength,
                    seed=seed,
                    colors=job["provider"]["palette_colors"],
                )
            except RecraftAmbiguousSubmissionError:
                unknown_root = job_root / "candidates" / candidate_id
                record = {
                    "schema_version": CANDIDATE_SCHEMA_VERSION,
                    "kind": "pixel_forge_recraft_candidate",
                    "id": candidate_id,
                    "state": "unknown_submission",
                    "submitted_at": _utc_now(),
                    "provider": {
                        "model": job["provider"]["model"],
                        "strength": strength,
                        "seed": seed,
                    },
                }
                _write_json(unknown_root / "candidate.json", record)
                job["candidates"].append(
                    {
                        "id": candidate_id,
                        "state": "unknown_submission",
                        "candidate": _relative(unknown_root / "candidate.json"),
                    }
                )
                _update_job(job_root, job, state="unknown_submission")
                raise
            temporary = job_root / f".{candidate_id}.png"
            temporary.write_bytes(image_bytes)
            try:
                ingest_candidate(
                    job_root,
                    temporary,
                    layout=str(job["layout"]["name"]),
                    candidate_id=candidate_id,
                    strict_layout=True,
                    provider={
                        "kind": "recraft_api",
                        "model": job["provider"]["model"],
                        "strength": strength,
                        "seed": seed,
                        "elapsed_seconds": time.perf_counter() - started,
                        "response": response_meta,
                    },
                )
            finally:
                temporary.unlink(missing_ok=True)
            submitted.append(candidate_id)
        after = active.doctor()
        spend = {
            "checked_at": _utc_now(),
            "outputs": len(submitted),
            "credits_before": before["credits"],
            "credits_after": after["credits"],
            "credits_used": max(0, before["credits"] - after["credits"]),
        }
        _write_json(job_root / "api_units.json", spend)
    finally:
        if owned_client:
            active.close()
    return submitted


def _approved_candidate(job_root: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    job = load_job(job_root)
    approved: list[tuple[Path, dict[str, Any]]] = []
    for record in job["candidates"]:
        candidate_root = Path(job_root) / "candidates" / str(record["id"])
        review_path = candidate_root / "review.json"
        if not review_path.is_file():
            continue
        review = _read_json(review_path)
        if review.get("status") == "approved":
            validation = _read_json(candidate_root / "validation.json")
            if validation.get("status") == "reject":
                raise RecraftPipelineError(
                    f"Approved candidate still has hard validation failures: {candidate_root}"
                )
            approved.append((candidate_root, validation))
    if len(approved) != 1:
        raise RecraftPipelineError(
            f"Job {job['job_id']} must contain exactly one approved non-rejected candidate"
        )
    return job, approved[0][0], approved[0][1]


def _candidate_layer_frames(
    job: Mapping[str, Any], candidate_root: Path, layer: str
) -> list[Image.Image]:
    layer_root = candidate_root / "extracted" / "layers" / layer
    frames: list[Image.Image] = []
    for cell in range(len(job["selected_frame_indices"])):
        path = layer_root / f"frame_{cell:02d}.png"
        if not path.is_file() and layer == job["component"]["layer"]:
            path = candidate_root / "extracted" / f"frame_{cell:02d}.png"
        if not path.is_file():
            frames.append(Image.new("RGBA", (128, 128), (0, 0, 0, 0)))
        else:
            with Image.open(path) as opened:
                frames.append(opened.convert("RGBA"))
    return frames


def _derived_left_frames(
    job: Mapping[str, Any], candidate_root: Path, layer: str
) -> list[Image.Image]:
    """Mirror the complete Right composite, then re-extract against Left truth."""
    record, sheet_path, regions_path = _source_record(
        str(job["character_id"]), str(job["camera"]), str(job["animation"])
    )
    left_row = _direction_row(str(job["base_id"]), str(job["animation"]), "left")
    left_sources = _sheet_frames(
        sheet_path, frame_count=int(record["frame_count"]), row=left_row
    )
    left_regions = _sheet_frames(
        regions_path, frame_count=int(record["frame_count"]), row=left_row, mode="L"
    )
    validation = _read_json(candidate_root / "validation.json")
    palette = [tuple(int(value) for value in color) for color in validation["shared_palette"]]
    ramp = [tuple(int(value) for value in color[:3]) for color in validation["component_ramp"]]
    cleanup_palette = tuple(ramp) or ((255, 255, 255),)
    outline = min(
        cleanup_palette,
        key=lambda color: 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2],
    )
    result: list[Image.Image] = []
    for cell, frame_index in enumerate(job["selected_frame_indices"]):
        with Image.open(candidate_root / "normalized" / f"frame_{cell:02d}.png") as opened:
            mirrored_composite = opened.convert("RGBA").transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        source = _normalize_source_to_palette(left_sources[int(frame_index)], palette)
        component_mask, _uncertain, _illegal = _component_masks(
            {**job, "direction": "left"},
            source,
            mirrored_composite,
            left_regions[int(frame_index)],
        )
        raw = np.asarray(mirrored_composite, dtype=np.uint8).copy()
        raw[~component_mask] = 0
        cleaned, _report = cleanup_component_frame(
            Image.fromarray(raw, "RGBA"),
            outline_rgb=outline,
            palette=cleanup_palette,
            protected_components=int(job["component"]["expected_pieces"]),
        )
        render_layers = job["component"]["render_layers"]
        region_names = render_layers.get(layer, [])
        if layer != job["component"]["layer"] and not region_names:
            cleaned = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        elif region_names:
            ids = np.asarray(left_regions[int(frame_index)].convert("L"), dtype=np.uint8)
            allowed = binary_dilation(
                np.isin(ids, [REGION_BY_NAME[name].id for name in region_names]),
                iterations=int(job["component"]["envelope_px"]),
            )
            layer_raw = np.asarray(cleaned, dtype=np.uint8).copy()
            layer_raw[~allowed] = 0
            cleaned = Image.fromarray(layer_raw, "RGBA")
        result.append(cleaned)
    return result


def _assemble_four_direction_sheet(
    direction_frames: Mapping[str, Sequence[Image.Image]], frame_count: int
) -> Image.Image:
    sheet = Image.new("RGBA", (128 * frame_count, 512), (0, 0, 0, 0))
    rows = {"front": 0, "back": 1, "right": 2, "left": 3}
    for direction, row in rows.items():
        frames = direction_frames[direction]
        if len(frames) != frame_count:
            raise RecraftPipelineError(
                f"{direction} has {len(frames)} frames; expected {frame_count}"
            )
        for column, frame in enumerate(frames):
            sheet.alpha_composite(frame, (column * 128, row * 128))
    return sheet


def promote_recraft_component(
    job_roots: Sequence[Path],
    *,
    asset_root: Path = ASSET_ROOT,
) -> Path:
    """Promote one fully approved 3-camera/3-animation Heroic component matrix."""
    approved = [_approved_candidate(Path(root).resolve()) for root in job_roots]
    if not approved:
        raise RecraftPipelineError("No approved Recraft jobs were supplied")
    first_job = approved[0][0]
    if first_job["mode"] != "component":
        raise RecraftPipelineError("Full-style experiments cannot be promoted")
    component = first_job["component"]
    identity_hash = _json_hash(component)
    base_id = str(first_job["base_id"])
    for job, _candidate, _validation in approved:
        if (
            job["mode"] != "component"
            or job["base_id"] != base_id
            or _json_hash(job["component"]) != identity_hash
        ):
            raise RecraftPipelineError("Promotion jobs do not describe one component/base")
        if len(job["selected_frame_indices"]) != int(job["frame_count"]):
            raise RecraftPipelineError("Promotion requires complete animation loops")
    required_directions = {"front", "back", "right"}
    if not component["mirror_safe"]:
        required_directions.add("left")
    indexed: dict[tuple[str, str, str], tuple[dict[str, Any], Path, dict[str, Any]]] = {}
    for item in approved:
        job = item[0]
        key = (str(job["camera"]), str(job["animation"]), str(job["direction"]))
        if key in indexed:
            raise RecraftPipelineError(f"Duplicate approved job for {'/'.join(key)}")
        indexed[key] = item
    missing = [
        f"{camera}/{animation}/{direction}"
        for camera in CAMERAS
        for animation in ANIMATIONS
        for direction in sorted(required_directions)
        if (camera, animation, direction) not in indexed
    ]
    if missing:
        raise RecraftPipelineError("Incomplete promotion matrix: " + ", ".join(missing))

    part_dir = (
        Path(asset_root).resolve()
        / "parts"
        / str(component["slot"])
        / f"{component['id']}-{base_id}"
    )
    if part_dir.exists():
        raise FileExistsError(part_dir)
    layers = list(component["render_layers"])
    camera_variants: dict[str, dict[str, str]] = {}
    render_layer_variants: dict[str, dict[str, dict[str, str]]] = {
        layer: {} for layer in layers
    }
    animation_hashes: dict[str, dict[str, str]] = {}
    source_jobs: list[dict[str, Any]] = []
    all_ramp_colors: list[tuple[int, int, int, int]] = []
    for job, candidate_root, validation in approved:
        all_ramp_colors.extend(tuple(color) for color in validation["component_ramp"])
        source_jobs.append(
            {
                "job_id": job["job_id"],
                "request_hash": job["request_hash"],
                "job_sha256": sha256_path(Path(candidate_root).parents[1] / "job.json"),
                "candidate_id": candidate_root.name,
                "candidate_sha256": sha256_path(candidate_root / "candidate.json"),
                "validation_sha256": sha256_path(candidate_root / "validation.json"),
                "review_sha256": sha256_path(candidate_root / "review.json"),
                "camera": job["camera"],
                "animation": job["animation"],
                "direction": job["direction"],
            }
        )
    for camera in CAMERAS:
        variant = f"heroic_{camera}"
        camera_variants[variant] = {}
        animation_hashes[variant] = {}
        for layer in layers:
            render_layer_variants[layer][variant] = {}
        for animation in ANIMATIONS:
            frame_count = int(indexed[(camera, animation, "front")][0]["frame_count"])
            for layer in layers:
                direction_frames: dict[str, Sequence[Image.Image]] = {}
                for direction in required_directions:
                    job, candidate_root, _validation = indexed[(camera, animation, direction)]
                    direction_frames[direction] = _candidate_layer_frames(job, candidate_root, layer)
                if component["mirror_safe"]:
                    right_job, right_candidate, _validation = indexed[(camera, animation, "right")]
                    direction_frames["left"] = _derived_left_frames(
                        right_job, right_candidate, layer
                    )
                sheet = _assemble_four_direction_sheet(direction_frames, frame_count)
                relative = (
                    Path("styles") / "heroic" / camera / "layers" / layer / f"{animation}.png"
                )
                output = part_dir / relative
                _save_png(sheet, output)
                render_layer_variants[layer][variant][animation] = relative.as_posix()
                if layer == component["layer"]:
                    primary_relative = Path("styles") / "heroic" / camera / f"{animation}.png"
                    primary_output = part_dir / primary_relative
                    _save_png(sheet, primary_output)
                    camera_variants[variant][animation] = primary_relative.as_posix()
                    animation_hashes[variant][animation] = sha256_path(primary_output)

    ramp_counter = Counter(tuple(color[:3]) for color in all_ramp_colors)
    ramp = [color for color, _count in ramp_counter.most_common(5)]
    if len(ramp) < 3:
        declared = [_hex_rgb(value) for value in component["colors"]]
        for color in declared:
            if color not in ramp:
                ramp.append(color)
            if len(ramp) >= 3:
                break
    if not ramp:
        raise RecraftPipelineError("Approved matrix produced no component color ramp")
    ramp.sort(key=lambda color: 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2])
    main = ramp[len(ramp) // 2]
    hex_ramp = ["#{:02X}{:02X}{:02X}".format(*color) for color in ramp]
    empty_animations: dict[str, str] = {}
    render_layers_manifest = {
        layer: {
            "animations": {},
            "cameraVariants": render_layer_variants[layer],
        }
        for layer in layers
    }
    manifest = {
        "schemaVersion": 1,
        "id": f"{component['id']}-{base_id}",
        "familyId": component["id"],
        "displayName": component["display_name"],
        "slot": component["slot"],
        "occupiesSlots": component["occupies_slots"],
        "reservedSlots": [],
        "layer": component["layer"],
        "hairOcclusion": component["hair_occlusion"],
        "tags": ["recraft_assisted", "heroic_only", "recolorable"],
        "fit": base_id,
        "version": 1,
        "status": "approved",
        "animations": empty_animations,
        "cameraVariants": camera_variants,
        "renderLayers": render_layers_manifest,
        "directionMirrors": (
            {animation: {"left": "right"} for animation in ANIMATIONS}
            if component["mirror_safe"] else {}
        ),
        "coverage": {animation: list(DIRECTIONS) for animation in ANIMATIONS},
        "colorRamp": {
            "main": "#{:02X}{:02X}{:02X}".format(*main),
            "colors": hex_ramp,
        },
        "suggestedColors": ["#{:02X}{:02X}{:02X}".format(*main)],
        "provenance": {
            "kind": "approved_recraft_heroic_component",
            "generator": "tools/run_recraft_sprite_jobs.py",
            "provider": "recraft",
            "model": first_job["provider"]["model"],
            "componentSpec": component,
            "validationProfile": _relative(VALIDATION_PROFILE),
            "validationProfileSha256": sha256_path(VALIDATION_PROFILE),
            "styleProfile": _relative(STYLE_PROFILE),
            "styleProfileSha256": sha256_path(STYLE_PROFILE),
            "sourceJobs": sorted(
                source_jobs,
                key=lambda record: (record["camera"], record["animation"], record["direction"]),
            ),
            "styleVariants": {
                "heroic": {
                    "cameras": list(CAMERAS),
                    "animationSha256": animation_hashes,
                }
            },
        },
    }
    _write_json(part_dir / "manifest.json", manifest)
    # Validate through the public catalog loader before returning authority.
    from src.core.character_forge import create_default_catalog, validate_catalog

    try:
        catalog = create_default_catalog(Path(asset_root))
        validate_catalog(catalog)
        promoted = catalog.part(str(manifest["id"]))
        if promoted.fit != base_id:
            raise RecraftPipelineError("Promoted component failed catalog verification")
    except Exception:
        # Promotion owns this newly-created directory. Never leave a partially
        # registered component behind when catalog verification fails.
        shutil.rmtree(part_dir, ignore_errors=True)
        raise
    return part_dir / "manifest.json"
