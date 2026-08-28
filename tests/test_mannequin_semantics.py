from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image
import pytest

from src.core.character_forge import CHARACTER_SLOTS as RUNTIME_CHARACTER_SLOTS
from src.core.mannequin_semantics import (
    ATTACHMENT_BONES,
    CHARACTER_SLOTS,
    REGIONS,
    SLOT_HIDE_REGIONS,
    SLOT_SURFACE_REGIONS,
    decode_index_runs,
    encode_index_runs,
    resolve_body_hide_regions,
    sha256_path,
    validate_semantic_manifest,
)
from tools import promote_character_motion


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "animation_images_models" / "elf_bald_female" / "canonical"
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")


def test_semantic_contract_has_exact_regions_slots_and_distinct_colors() -> None:
    assert len(REGIONS) == 32
    assert [region.id for region in REGIONS] == list(range(1, 33))
    assert len({region.name for region in REGIONS}) == 32
    assert len({region.color for region in REGIONS}) == 32
    assert CHARACTER_SLOTS == RUNTIME_CHARACTER_SLOTS
    assert set(SLOT_SURFACE_REGIONS) == set(CHARACTER_SLOTS)
    assert set(SLOT_HIDE_REGIONS) == set(CHARACTER_SLOTS)
    known = {region.name for region in REGIONS}
    assert all(set(names) <= known for names in SLOT_SURFACE_REGIONS.values())
    assert all(set(names) <= known for names in SLOT_HIDE_REGIONS.values())
    assert len(ATTACHMENT_BONES) == 17


def test_body_hide_overrides_add_remove_and_validate_regions() -> None:
    resolved = resolve_body_hide_regions(
        "headwear",
        {"add": ["left_ear"], "remove": ["rear_head"]},
    )
    assert "scalp" in resolved
    assert "left_ear" in resolved
    assert "rear_head" not in resolved
    with pytest.raises(ValueError, match="Unknown semantic region"):
        resolve_body_hide_regions("headwear", {"add": ["cape"]})


def test_face_index_runs_are_canonical_and_topology_bounded() -> None:
    indices = (1, 2, 3, 8, 10, 11, 12)
    runs = encode_index_runs(indices)
    assert runs == [[1, 3], [8, 1], [10, 3]]
    assert decode_index_runs(runs, limit=13) == indices
    with pytest.raises(ValueError, match="sorted and non-overlapping"):
        decode_index_runs([[4, 2], [5, 1]])
    with pytest.raises(ValueError, match="beyond face count"):
        decode_index_runs([[12, 2]], limit=13)


def test_production_semantic_manifest_and_inspection_assets_validate() -> None:
    manifest = json.loads((CANONICAL / "mannequin_semantics.json").read_text(encoding="utf-8"))
    validate_semantic_manifest(manifest)
    assert manifest["face_count"] == 200054
    assert all(row["face_count"] > 0 for row in manifest["regions"])
    assert sha256_path(CANONICAL / "semantic_regions.png") == manifest["debug_texture"]["sha256"]
    with Image.open(CANONICAL / "semantic_regions.png") as opened:
        debug = opened.convert("RGBA")
    assert debug.size == (256, 128)
    for region in REGIONS:
        index = region.id - 1
        assert debug.getpixel(((index % 8) * 32 + 16, (index // 8) * 32 + 16)) == region.color
    overrides = json.loads((CANONICAL / "semantic_region_overrides.json").read_text(encoding="utf-8"))
    assert overrides["topology_sha256"] == manifest["protected_invariants"]["topology_sha256"]
    inspection = json.loads(
        (CANONICAL / "inspection" / "semantic_inspection_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert inspection["view_count"] == 6
    assert inspection["slot_hide_preview_count"] == 13
    for output in inspection["outputs"].values():
        path = CANONICAL / "inspection" / output["file"]
        assert sha256_path(path) == output["sha256"]

def _promotion_fixture(tmp_path: Path) -> tuple[Path, Path]:
    asset_root = tmp_path / "character-forge"
    asset_root.mkdir()
    specs = {
        "schema_version": 1,
        "base_id": "test-base",
        "animations": {
            "idle": {"old": True},
            "walk": {"old": True},
            "run": {"runtime_sha256": "run-is-untouched"},
        },
    }
    (asset_root / "sheet_specs.json").write_text(json.dumps(specs), encoding="utf-8")
    pixel_root = tmp_path / "pixel"
    (pixel_root / "sheets").mkdir(parents=True)
    sequences = {}
    for role in ("idle", "walk"):
        sheet = pixel_root / "sheets" / f"{role}.png"
        Image.new("RGBA", (512, 256), (10, 20, 30, 255)).save(sheet)
        sequences[role] = {
            "action": f"PF_{role.title()}_Approved",
            "source_frames": list(range(8)),
            "frame_count": 8,
            "dimensions": [512, 256],
            "sheet": f"sheets/{role}.png",
        }
    manifest = {
        "schema_version": 1,
        "direction_order": ["front", "back", "right", "left"],
        "settings": {"cell_size": 64},
        "sequences": sequences,
    }
    manifest_path = pixel_root / "pixel_sprite_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return asset_root, manifest_path


def test_character_motion_promotion_requires_approval_and_preserves_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset_root, manifest = _promotion_fixture(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["promote", "--pixel-manifest", str(manifest), "--asset-root", str(asset_root)],
    )
    with pytest.raises(RuntimeError, match="--approved"):
        promote_character_motion.main()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "promote", "--pixel-manifest", str(manifest), "--asset-root", str(asset_root),
            "--approved", "--force",
        ],
    )
    promote_character_motion.main()
    updated = json.loads((asset_root / "sheet_specs.json").read_text(encoding="utf-8"))
    assert updated["animations"]["run"] == {"runtime_sha256": "run-is-untouched"}
    for role in ("idle", "walk"):
        assert updated["animations"][role]["frames_per_direction"] == 8
        assert updated["animations"][role]["fps"] == 10
        assert (asset_root / "bases" / "test-base" / f"{role}.png").is_file()


@pytest.mark.skipif(
    not BLENDER.is_file() or not (CANONICAL / "elf_bald_female_mannequin.blend").is_file(),
    reason="Blender or canonical mannequin is unavailable",
)
def test_canonical_mannequin_passes_headless_blender_validation() -> None:
    result = subprocess.run(
        [
            str(BLENDER), "--background", "--factory-startup",
            "--python", str(ROOT / "tools" / "blender" / "validate_semantic_mannequin.py"),
            "--", "--blend", str(CANONICAL / "elf_bald_female_mannequin.blend"),
            "--manifest", str(CANONICAL / "mannequin_semantics.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Validated 200054 faces, 32 regions, 13 slots, and 17 attachments" in result.stdout


@pytest.mark.skipif(not BLENDER.is_file(), reason="Blender is unavailable")
def test_original_motion_edit_session_preserves_and_exposes_three_actions(
    tmp_path: Path,
) -> None:
    blend = tmp_path / "original_motion_edit_session.blend"
    manifest = tmp_path / "original_motion_edit_session.json"
    prepare = subprocess.run(
        [
            str(BLENDER), "--background", "--factory-startup",
            "--python", str(
                ROOT / "tools" / "blender" / "prepare_legacy_motion_edit_session.py"
            ),
            "--", "--blend", str(CANONICAL / "elf_bald_female_mannequin.blend"),
            "--output-blend", str(blend),
            "--output-manifest", str(manifest),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert prepare.returncode == 0, prepare.stdout + prepare.stderr
    validate = subprocess.run(
        [
            str(BLENDER), "--background", "--factory-startup",
            "--python", str(
                ROOT / "tools" / "blender" / "validate_legacy_motion_edit_session.py"
            ),
            "--", "--blend", str(blend), "--manifest", str(manifest),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert "three editable eight-pose motions" in validate.stdout
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["active_action"] == "PF_Walk_Meshy_Edit"
    assert {
        role: (motion["source_action"], motion["editable_action"])
        for role, motion in data["motions"].items()
    } == {
        "idle": ("PF_Idle", "PF_Idle_Edit"),
        "walk": ("PF_Walk", "PF_Walk_Meshy_Edit"),
        "run": ("PF_Run", "PF_Run_Meshy_Edit"),
    }

    finalized_blend = tmp_path / "walk_manual_pipeline.blend"
    finalized_manifest = tmp_path / "walk_manual_pipeline.json"
    finalize = subprocess.run(
        [
            str(BLENDER), "--background", "--factory-startup",
            "--python", str(
                ROOT / "tools" / "blender" / "finalize_manual_motion_edit.py"
            ),
            "--", "--blend", str(blend),
            "--action", "PF_Walk_Meshy_Edit",
            "--output-blend", str(finalized_blend),
            "--output-manifest", str(finalized_manifest),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert finalize.returncode == 0, finalize.stdout + finalize.stderr
    finalized = json.loads(finalized_manifest.read_text(encoding="utf-8"))
    assert finalized["status"] == "manual_edit_finalized"
    assert finalized["action"] == "PF_Walk_Meshy_Edit"
    assert finalized["visible_frames"] == list(range(1, 9))
    assert finalized["loop_closure_frame"] == 9
    assert finalized["removed_keyframes"]


def test_repository_policy_tracks_canonical_assets_but_ignores_raw_fbx() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "/animation_images_models/**/*.fbx" in ignore
    assert "canonical/*.blend filter=lfs" in attributes
