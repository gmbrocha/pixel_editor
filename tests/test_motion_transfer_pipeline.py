from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "animation_images_models"
CONFIG = MODEL_ROOT / "motion_transfer_targets.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _matmul(left: tuple[tuple[float, ...], ...], right: tuple[tuple[float, ...], ...]):
    return tuple(
        tuple(sum(left[row][index] * right[index][column] for index in range(3)) for column in range(3))
        for row in range(3)
    )


def _transpose(matrix: tuple[tuple[float, ...], ...]):
    return tuple(tuple(matrix[column][row] for column in range(3)) for row in range(3))


def _rotation(axis: str, degrees: float):
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    if axis == "x":
        return ((1.0, 0.0, 0.0), (0.0, cosine, -sine), (0.0, sine, cosine))
    if axis == "y":
        return ((cosine, 0.0, sine), (0.0, 1.0, 0.0), (-sine, 0.0, cosine))
    return ((cosine, -sine, 0.0), (sine, cosine, 0.0), (0.0, 0.0, 1.0))


def _max_difference(left, right) -> float:
    return max(abs(left[row][column] - right[row][column]) for row in range(3) for column in range(3))


def test_motion_transfer_target_contract() -> None:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert set(data["targets"]) == {
        "tiefling_bald_female",
        "dwarf_bald_male",
        "human_bald_male",
    }
    assert len(data["expected_bones"]) == 24
    assert data["expected_bones"][0] == "Hips"
    assert "human_bald_male_less_musculature" not in data["targets"]
    for target in data["targets"].values():
        assert target["base_id"].endswith("-01")
        assert target["walk_entry"].endswith("Animation_Walking_withSkin.fbx")
        assert target["run_entry"].endswith("Animation_Running_withSkin.fbx")


@pytest.mark.parametrize(
    "target_id",
    ["tiefling_bald_female", "dwarf_bald_male", "human_bald_male"],
)
def test_promoted_target_canonical_contract(target_id: str) -> None:
    canonical = MODEL_ROOT / target_id / "canonical" / f"{target_id}_approved_motions.blend"
    manifest_path = MODEL_ROOT / target_id / "canonical" / "approved_motions_manifest.json"
    assert canonical.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "approved_motion_canonical"
    assert manifest["character_id"] == target_id
    assert manifest["canonical_blend_sha256"] == _sha256(canonical)
    for sequence, count, fps, closure in (
        ("idle", 26, 12, 27),
        ("walk", 8, 10, 9),
        ("run", 8, 10, 9),
    ):
        entry = manifest["sequences"][sequence]
        assert len(entry["visible_frames"]) == count
        assert entry["fps"] == fps
        assert entry["closure_frame"] == closure
    idle_durations = manifest["sequences"]["idle"]["frame_durations_ms"]
    assert idle_durations[10] == 83
    assert idle_durations[23] == 1500
    assert len(idle_durations) == 26


def test_approved_motion_profile_is_hash_linked_and_self_checked() -> None:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    canonical = MODEL_ROOT / data["source"]["canonical_blend"]
    profile_path = MODEL_ROOT / data["source"]["profile"]
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["kind"] == "approved_motion_transfer_profile"
    assert profile["source_blend_sha256"] == _sha256(canonical)
    assert profile["bone_order"] == data["expected_bones"]
    expected = {"idle": (26, 12, 27), "walk": (8, 10, 9), "run": (8, 10, 9)}
    for name, (count, fps, closure) in expected.items():
        sequence = profile["sequences"][name]
        assert len(sequence["visible_frames"]) == count
        assert sequence["fps"] == fps
        assert sequence["closure_frame"] == closure
        assert sequence["source_self_check"]["max_rotation_error_radians"] <= 1e-5
        assert sequence["source_self_check"]["max_hips_translation_error"] <= 1e-5


def test_rest_local_delta_maps_through_altered_target_rest_axis() -> None:
    """The same bone-local correction must produce a target-rest-basis world correction."""
    source_rest = _matmul(_rotation("z", 17.0), _rotation("x", -9.0))
    target_rest = _matmul(_rotation("y", 43.0), _rotation("z", -28.0))
    local_delta = _matmul(_rotation("x", 12.0), _rotation("z", -7.0))

    source_world_delta = _matmul(_matmul(source_rest, local_delta), _transpose(source_rest))
    expected_target_world_delta = _matmul(
        _matmul(target_rest, local_delta), _transpose(target_rest)
    )

    # Applying the profile delta to matrix_basis lets Blender conjugate it
    # through the target bone's rest basis. Copying the source world/F-curve
    # correction would rotate around the wrong axes on this synthetic rig.
    transferred_target_world_delta = _matmul(
        _matmul(target_rest, local_delta), _transpose(target_rest)
    )
    assert _max_difference(transferred_target_world_delta, expected_target_world_delta) < 1e-12
    assert _max_difference(source_world_delta, expected_target_world_delta) > 0.1


@pytest.mark.parametrize(
    "target_id",
    ["tiefling_bald_female", "dwarf_bald_male", "human_bald_male"],
)
def test_local_motion_transfer_candidate_contract_when_available(target_id: str) -> None:
    work = MODEL_ROOT / target_id / "working" / "motion_transfer"
    manifest_path = work / f"{target_id}_motion_transfer_candidate.json"
    qa_path = work / "pixel_review" / "motion_transfer_qa.json"
    if not manifest_path.is_file() or not qa_path.is_file():
        pytest.skip("Ignored local Meshy sources/candidates are not available")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "motion_transfer_review_candidate"
    assert manifest["character_id"] == target_id
    assert set(manifest["sequences"]) == {"idle", "walk", "run"}
    assert qa["shared_palette_size"] == 16
    for sequence_name, frame_count, fps in (
        ("idle", 26, 12), ("walk", 8, 10), ("run", 8, 10),
    ):
        sequence = manifest["sequences"][sequence_name]
        assert len(sequence["visible_frames"]) == frame_count
        assert sequence["fps"] == fps
        assert max(
            (item["magnitude"] for item in sequence["contact_corrections"].values()),
            default=0.0,
        ) <= sequence["contact_cap"]
        assert qa["sequences"][sequence_name]["frame_count"] == frame_count
        assert qa["sequences"][sequence_name]["fps"] == fps
