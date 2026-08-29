import json
from pathlib import Path

from src.core.motion_timing import runtime_timing


ROOT = Path(__file__).resolve().parents[1]


def test_idle_runtime_samples_authored_action_without_expanding_holds() -> None:
    config = json.loads(
        (ROOT / "animation_images_models" / "approved_motion_timing.json").read_text()
    )
    assert config["idle"]["frame_count"] == 26
    assert config["idle"]["fps"] == 12
    runtime = runtime_timing(config, "idle")
    assert runtime.source_frames == (1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 24, 25)
    assert runtime.fps == 6
    assert len(runtime.frame_durations_ms) == 14
    assert runtime.frame_durations_ms[5] == 167
    assert runtime.frame_durations_ms[12] == 1500
    assert sum(runtime.frame_durations_ms) == 3671


def test_walk_and_run_runtime_contracts_fall_back_to_authored_timing() -> None:
    config = json.loads(
        (ROOT / "animation_images_models" / "approved_motion_timing.json").read_text()
    )
    for sequence in ("walk", "run"):
        runtime = runtime_timing(config, sequence)
        assert runtime.source_frames == tuple(range(1, 9))
        assert runtime.fps == 10
        assert runtime.frame_durations_ms == (100,) * 8
