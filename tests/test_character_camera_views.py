from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).parents[1]
ASSET_ROOT = ROOT / "assets" / "character-forge"
MANIFEST = ASSET_ROOT / "camera_views_manifest.json"
CAMERAS = {
    "top_down": 70.0,
    "three_quarter": 45.0,
    "low": 28.0,
}
BASES = {
    "elf-01",
    "tiefling-female-01",
    "dwarf-male-01",
    "human-muscular-male-01",
}
SEQUENCES = {"idle": 14, "walk": 8, "run": 8}
DIRECTIONS = {"front", "back", "right", "left"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_camera_view_manifest_covers_every_approved_base_motion_and_direction() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["status"] == "canonical"
    assert list(data["camera_heights"]) == list(CAMERAS)
    assert {
        camera: record["pitch_degrees"]
        for camera, record in data["camera_heights"].items()
    } == CAMERAS
    assert set(data["bases"]) == BASES
    assert data["excluded_models"] == ["human_bald_male_less_muscular"]
    assert all(
        view["framing_scale"] == 1.12
        for view in data["bases"]["dwarf-male-01"]["camera_views"].values()
    )
    assert (
        data["bases"]["elf-01"]["camera_views"]["low"]["framing_scale"]
        > 1.25
    )

    for base in data["bases"].values():
        assert set(base["camera_views"]) == set(CAMERAS)
        for camera_height, camera in base["camera_views"].items():
            assert camera["orthographic"] is True
            assert camera["framing_scale"] > 0
            assert camera["pitch_degrees"] == CAMERAS[camera_height]
            canonical = ROOT / camera["canonical_blend"]
            assert _sha256(canonical) == camera["canonical_blend_sha256"]
            assert set(camera["sequences"]) == set(SEQUENCES)
            for sequence_name, sequence in camera["sequences"].items():
                frame_count = SEQUENCES[sequence_name]
                runtime = ASSET_ROOT / sequence["runtime_file"]
                assert _sha256(runtime) == sequence["runtime_sha256"]
                with Image.open(runtime) as sheet:
                    assert sheet.size == (128 * frame_count, 128 * 4)
                assert len(sequence["frame_durations_ms"]) == frame_count
                if sequence_name == "idle":
                    assert sequence["frame_durations_ms"][5] == 167
                    assert sequence["frame_durations_ms"][12] == 1500
                assert set(sequence["gifs"]) == DIRECTIONS
                for gif_record in sequence["gifs"].values():
                    gif = ASSET_ROOT / gif_record["file"]
                    assert _sha256(gif) == gif_record["sha256"]
                    with Image.open(gif) as opened:
                        assert opened.size == (128, 128)
                        assert opened.n_frames == frame_count
                        assert opened.info["loop"] == 0
