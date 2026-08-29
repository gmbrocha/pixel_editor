"""Canonical authored-action and sampled-runtime motion timing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class RuntimeTiming:
    source_frames: tuple[int, ...]
    fps: int
    frame_durations_ms: tuple[int, ...]


def runtime_timing(config: Mapping[str, Any], sequence: str) -> RuntimeTiming:
    """Return runtime sampling without changing the authored Blender action contract."""
    spec = config[sequence]
    source_frames = tuple(int(value) for value in spec.get(
        "runtime_source_frames", range(1, int(spec["frame_count"]) + 1)
    ))
    if not source_frames or len(set(source_frames)) != len(source_frames):
        raise ValueError(f"{sequence} runtime source frames must be unique and non-empty")
    action_count = int(spec["frame_count"])
    if any(frame < 1 or frame > action_count for frame in source_frames):
        raise ValueError(f"{sequence} runtime source frame is outside the authored action")
    fps = int(spec.get("runtime_fps", spec["fps"]))
    default = int(spec.get(
        "runtime_default_frame_duration_ms", spec["default_frame_duration_ms"]
    ))
    durations = [default] * len(source_frames)
    overrides = spec.get(
        "runtime_frame_duration_overrides_ms",
        spec.get("frame_duration_overrides_ms", {}),
    )
    for raw_frame, raw_duration in overrides.items():
        frame = int(raw_frame)
        if not 1 <= frame <= len(source_frames):
            raise ValueError(f"{sequence} runtime duration override is out of range: {frame}")
        durations[frame - 1] = int(raw_duration)
    if fps < 1 or any(value < 1 for value in durations):
        raise ValueError(f"{sequence} runtime timing must be positive")
    return RuntimeTiming(source_frames, fps, tuple(durations))
