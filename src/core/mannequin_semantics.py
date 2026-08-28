from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


MANNEQUIN_SCHEMA_VERSION = 1

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


@dataclass(frozen=True, slots=True)
class SemanticRegion:
    id: int
    name: str
    side: str
    color: tuple[int, int, int, int]


_REGION_ROWS = (
    (1, "face", "center", (239, 71, 111, 255)),
    (2, "scalp", "center", (255, 209, 102, 255)),
    (3, "rear_head", "center", (6, 214, 160, 255)),
    (4, "left_ear", "left", (17, 138, 178, 255)),
    (5, "right_ear", "right", (131, 56, 236, 255)),
    (6, "neck", "center", (255, 127, 80, 255)),
    (7, "chest_front", "center", (255, 89, 94, 255)),
    (8, "upper_back", "center", (255, 180, 65, 255)),
    (9, "abdomen_front", "center", (67, 205, 128, 255)),
    (10, "lower_back", "center", (49, 151, 213, 255)),
    (11, "pelvis_front", "center", (151, 86, 214, 255)),
    (12, "pelvis_back", "center", (220, 92, 170, 255)),
    (13, "left_shoulder", "left", (229, 57, 53, 255)),
    (14, "right_shoulder", "right", (255, 152, 0, 255)),
    (15, "left_upper_arm", "left", (76, 175, 80, 255)),
    (16, "right_upper_arm", "right", (3, 169, 244, 255)),
    (17, "left_elbow", "left", (103, 58, 183, 255)),
    (18, "right_elbow", "right", (233, 30, 99, 255)),
    (19, "left_forearm", "left", (198, 40, 40, 255)),
    (20, "right_forearm", "right", (245, 124, 0, 255)),
    (21, "left_hand", "left", (46, 125, 50, 255)),
    (22, "right_hand", "right", (2, 119, 189, 255)),
    (23, "left_thigh", "left", (81, 45, 168, 255)),
    (24, "right_thigh", "right", (194, 24, 91, 255)),
    (25, "left_knee", "left", (255, 107, 107, 255)),
    (26, "right_knee", "right", (255, 202, 40, 255)),
    (27, "left_shin", "left", (102, 187, 106, 255)),
    (28, "right_shin", "right", (79, 195, 247, 255)),
    (29, "left_ankle", "left", (149, 117, 205, 255)),
    (30, "right_ankle", "right", (240, 98, 146, 255)),
    (31, "left_foot", "left", (141, 110, 99, 255)),
    (32, "right_foot", "right", (120, 144, 156, 255)),
)

REGIONS = tuple(SemanticRegion(*row) for row in _REGION_ROWS)
REGION_BY_ID = {region.id: region for region in REGIONS}
REGION_BY_NAME = {region.name: region for region in REGIONS}


SLOT_SURFACE_REGIONS: Mapping[str, tuple[str, ...]] = {
    "headwear": ("scalp", "rear_head", "left_ear", "right_ear"),
    "face": ("face", "left_ear", "right_ear"),
    "neck": ("neck", "chest_front", "upper_back"),
    "torso": ("chest_front", "upper_back", "abdomen_front", "lower_back"),
    "outerwear": (
        "chest_front", "upper_back", "abdomen_front", "lower_back",
        "pelvis_front", "pelvis_back", "left_shoulder", "right_shoulder",
        "left_upper_arm", "right_upper_arm", "left_forearm", "right_forearm",
    ),
    "waist": ("pelvis_front", "pelvis_back", "abdomen_front", "lower_back"),
    "hands": ("left_hand", "right_hand", "left_forearm", "right_forearm"),
    "legwear": (
        "pelvis_front", "pelvis_back", "left_thigh", "right_thigh",
        "left_knee", "right_knee", "left_shin", "right_shin",
        "left_ankle", "right_ankle",
    ),
    "feet": ("left_ankle", "right_ankle", "left_foot", "right_foot"),
    "hair": ("scalp", "rear_head", "left_ear", "right_ear", "neck"),
    "facial_hair": ("face",),
    "shoulder_chest": (
        "chest_front", "upper_back", "left_shoulder", "right_shoulder",
    ),
    "back": ("upper_back", "lower_back", "pelvis_back"),
}

SLOT_HIDE_REGIONS: Mapping[str, tuple[str, ...]] = {
    "headwear": ("scalp", "rear_head"),
    "face": (),
    "neck": ("neck",),
    "torso": ("chest_front", "upper_back", "abdomen_front", "lower_back"),
    "outerwear": (
        "chest_front", "upper_back", "abdomen_front", "lower_back",
        "pelvis_front", "pelvis_back", "left_shoulder", "right_shoulder",
    ),
    "waist": ("pelvis_front", "pelvis_back"),
    "hands": ("left_hand", "right_hand"),
    "legwear": (
        "pelvis_front", "pelvis_back", "left_thigh", "right_thigh",
        "left_knee", "right_knee", "left_shin", "right_shin",
        "left_ankle", "right_ankle",
    ),
    "feet": ("left_ankle", "right_ankle", "left_foot", "right_foot"),
    "hair": ("scalp", "rear_head"),
    "facial_hair": (),
    "shoulder_chest": (
        "chest_front", "upper_back", "left_shoulder", "right_shoulder",
    ),
    "back": (),
}

ATTACHMENT_BONES: Mapping[str, str] = {
    "head_top": "Head",
    "face_center": "Head",
    "neck_base": "neck",
    "chest_front": "Spine",
    "upper_back": "Spine",
    "waist_front": "Hips",
    "waist_back": "Hips",
    "left_shoulder": "LeftShoulder",
    "right_shoulder": "RightShoulder",
    "left_hand": "LeftHand",
    "right_hand": "RightHand",
    "left_hip": "LeftUpLeg",
    "right_hip": "RightUpLeg",
    "left_ankle": "LeftFoot",
    "right_ankle": "RightFoot",
    "left_foot": "LeftToeBase",
    "right_foot": "RightToeBase",
}


def sha256_path(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def region_ids(names: Iterable[str]) -> frozenset[int]:
    try:
        return frozenset(REGION_BY_NAME[name].id for name in names)
    except KeyError as exc:
        raise ValueError(f"Unknown semantic region {exc.args[0]!r}") from exc


def resolve_body_hide_regions(
    slot: str,
    override: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    if slot not in SLOT_HIDE_REGIONS:
        raise ValueError(f"Unknown Character Forge slot {slot!r}")
    selected = set(SLOT_HIDE_REGIONS[slot])
    if override is not None:
        unknown_keys = set(override) - {"add", "remove"}
        if unknown_keys:
            raise ValueError(f"Unknown body-hide override fields: {sorted(unknown_keys)}")
        for field, operation in (("add", selected.add), ("remove", selected.discard)):
            raw_names = override.get(field, [])
            if not isinstance(raw_names, list) or any(not isinstance(name, str) for name in raw_names):
                raise ValueError(f"Body-hide override {field} must be a list of region names")
            for name in raw_names:
                if name not in REGION_BY_NAME:
                    raise ValueError(f"Unknown semantic region {name!r}")
                operation(name)
    return tuple(region.name for region in REGIONS if region.name in selected)


def encode_index_runs(indices: Iterable[int]) -> list[list[int]]:
    ordered = sorted(set(int(index) for index in indices))
    if any(index < 0 for index in ordered):
        raise ValueError("Face indices must be non-negative")
    if not ordered:
        return []
    runs: list[list[int]] = []
    start = previous = ordered[0]
    for index in ordered[1:]:
        if index == previous + 1:
            previous = index
            continue
        runs.append([start, previous - start + 1])
        start = previous = index
    runs.append([start, previous - start + 1])
    return runs


def decode_index_runs(runs: Sequence[Sequence[int]], *, limit: int | None = None) -> tuple[int, ...]:
    result: list[int] = []
    previous_end = -1
    for raw in runs:
        if len(raw) != 2:
            raise ValueError("Each face-index run must contain start and count")
        start, count = (int(value) for value in raw)
        if start < 0 or count <= 0:
            raise ValueError("Face-index runs require non-negative starts and positive counts")
        end = start + count
        if start <= previous_end:
            raise ValueError("Face-index runs must be sorted and non-overlapping")
        if limit is not None and end > limit:
            raise ValueError(f"Face-index run ends at {end}, beyond face count {limit}")
        result.extend(range(start, end))
        previous_end = end - 1
    return tuple(result)


def validate_semantic_manifest(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != MANNEQUIN_SCHEMA_VERSION:
        raise ValueError("Unsupported mannequin semantic manifest")
    raw_regions = data.get("regions")
    if not isinstance(raw_regions, list) or len(raw_regions) != len(REGIONS):
        raise ValueError("Semantic manifest must contain exactly 32 regions")
    actual = {(int(row["id"]), str(row["name"])) for row in raw_regions if isinstance(row, Mapping)}
    expected = {(region.id, region.name) for region in REGIONS}
    if actual != expected:
        raise ValueError("Semantic manifest region IDs or names do not match the canonical contract")
    slots = data.get("slots")
    if not isinstance(slots, Mapping) or set(slots) != set(CHARACTER_SLOTS):
        raise ValueError("Semantic manifest must contain all Character Forge slots")
    attachments = data.get("attachments")
    if not isinstance(attachments, Mapping) or set(attachments) != set(ATTACHMENT_BONES):
        raise ValueError("Semantic manifest attachment set is incomplete")
