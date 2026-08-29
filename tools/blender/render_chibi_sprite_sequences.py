"""Render paired beauty/semantic sprites with non-destructive chibi proportions."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.blender.chibi_pose import (  # noqa: E402
    apply_pose_style,
    load_style,
    mesh_world_points,
    restore_pose_style,
)
from tools.blender.render_semantic_sprite_sequences import (  # noqa: E402
    _configure_semantic_color,
    _derive_weight_regions,
    _install_semantic_materials,
    _mesh,
    _restore_materials,
)
from tools.blender.render_sprite_sequences import (  # noqa: E402
    _armature,
    _frame_durations,
    _position_view,
    _setup,
    _timing_spec,
)


DIRECTIONS = {
    "front": Vector((0.0, -1.0, 0.0)),
    "back": Vector((0.0, 1.0, 0.0)),
    "right": Vector((-1.0, 0.0, 0.0)),
    "left": Vector((1.0, 0.0, 0.0)),
}


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--style-config", required=True, type=Path)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--render-size", type=int, default=512)
    parser.add_argument("--pitch", type=float, default=28.0)
    parser.add_argument("--framing-scale", type=float, default=1.08)
    parser.add_argument("--timing-config", required=True, type=Path)
    parser.add_argument("--idle-action", default="PF_Idle_Approved")
    parser.add_argument("--walk-action", default="PF_Walk_Approved")
    parser.add_argument("--run-action", default="PF_Run_Approved")
    parser.add_argument(
        "--only", action="append", choices=("idle", "walk", "run")
    )
    return parser.parse_args(argv)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sequences(args: argparse.Namespace) -> dict[str, dict[str, object]]:
    selected = set(args.only or ("idle", "walk", "run"))
    timing = _timing_spec(args.timing_config)
    actions = {
        "idle": args.idle_action,
        "walk": args.walk_action,
        "run": args.run_action,
    }
    result: dict[str, dict[str, object]] = {}
    for sequence_name, action_name in actions.items():
        if sequence_name not in selected:
            continue
        action = bpy.data.actions.get(action_name)
        if action is None:
            raise RuntimeError(f"Missing action {action_name}")
        raw_samples = action.get("pf_sample_frames_json")
        frames = (
            [int(value) for value in json.loads(raw_samples)]
            if raw_samples
            else list(range(1, 9))
        )
        fps = int(action.get("pf_preview_fps", 10))
        override = timing.get(sequence_name)
        if override and "runtime_source_frames" in override:
            frames = [int(value) for value in override["runtime_source_frames"]]
            fps = int(override.get("runtime_fps", fps))
        result[sequence_name] = {
            "action": action_name,
            "frames": frames,
            "fps": fps,
            "frame_durations_ms": _frame_durations(
                action, len(frames), fps, sequence_name, timing
            ),
        }
    if not result:
        raise RuntimeError("No animation sequences were selected")
    return result


def _styled_auto_frame(
    armature: bpy.types.Object,
    meshes: list[bpy.types.Object],
    sequences: dict[str, dict[str, object]],
    pitch: float,
    bone_scales: dict[str, Vector],
) -> tuple[dict[str, Vector], float]:
    bases = {}
    bounds = {}
    for direction_name, horizontal in DIRECTIONS.items():
        view = Vector(
            (horizontal.x, horizontal.y, math.tan(math.radians(pitch)))
        ).normalized()
        right = view.cross(Vector((0.0, 0.0, 1.0))).normalized()
        up = right.cross(view).normalized()
        bases[direction_name] = (right, up, view)
        bounds[direction_name] = [
            float("inf"), float("-inf"),
            float("inf"), float("-inf"),
            float("inf"), float("-inf"),
        ]
    for sequence in sequences.values():
        armature.animation_data.action = bpy.data.actions[str(sequence["action"])]
        for frame in sequence["frames"]:
            bpy.context.scene.frame_set(int(frame))
            snapshot, _ = apply_pose_style(armature, meshes, bone_scales)
            try:
                for point in mesh_world_points(meshes):
                    for direction_name, (right, up, view) in bases.items():
                        x = point.dot(right)
                        y = point.dot(up)
                        depth = point.dot(view)
                        value = bounds[direction_name]
                        value[0] = min(value[0], x)
                        value[1] = max(value[1], x)
                        value[2] = min(value[2], y)
                        value[3] = max(value[3], y)
                        value[4] = min(value[4], depth)
                        value[5] = max(value[5], depth)
            finally:
                restore_pose_style(armature, snapshot)
    targets = {}
    ortho_scale = 0.0
    for direction_name, (right, up, view) in bases.items():
        min_x, max_x, min_y, max_y, min_depth, max_depth = bounds[direction_name]
        target = (
            right * ((min_x + max_x) * 0.5)
            + up * ((min_y + max_y) * 0.5)
            + view * ((min_depth + max_depth) * 0.5)
        )
        targets[direction_name] = target
        ortho_scale = max(ortho_scale, max(max_x - min_x, max_y - min_y) * 1.16)
    if not math.isfinite(ortho_scale) or ortho_scale <= 0.0:
        raise RuntimeError(f"Invalid styled projection bounds: {bounds}")
    return targets, ortho_scale


def _render_pass(
    output_dir: Path,
    pass_name: str,
    sequences: dict[str, dict[str, object]],
    armature: bpy.types.Object,
    meshes: list[bpy.types.Object],
    camera: bpy.types.Object,
    key: bpy.types.Object,
    fill: bpy.types.Object,
    pitch: float,
    targets: dict[str, Vector],
    bone_scales: dict[str, Vector],
) -> tuple[dict[str, dict[str, list[str]]], dict[str, list[float]]]:
    rendered: dict[str, dict[str, list[str]]] = {}
    grounding: dict[str, list[float]] = {}
    for sequence_name, sequence in sequences.items():
        armature.animation_data.action = bpy.data.actions[str(sequence["action"])]
        rendered[sequence_name] = {}
        grounding[sequence_name] = []
        for direction_name, horizontal in DIRECTIONS.items():
            _position_view(
                camera, key, fill, horizontal, pitch, targets[direction_name]
            )
            outputs = []
            for frame_index, source_frame in enumerate(sequence["frames"]):
                bpy.context.scene.frame_set(int(source_frame))
                snapshot, ground_delta = apply_pose_style(
                    armature, meshes, bone_scales
                )
                try:
                    output = (
                        output_dir
                        / pass_name
                        / sequence_name
                        / direction_name
                        / f"frame_{frame_index:02d}_source_{int(source_frame):03d}.png"
                    )
                    output.parent.mkdir(parents=True, exist_ok=True)
                    bpy.context.scene.render.filepath = str(output.resolve())
                    bpy.ops.render.render(write_still=True)
                    outputs.append(str(output.resolve()))
                    if direction_name == "front":
                        grounding[sequence_name].append(ground_delta)
                finally:
                    restore_pose_style(armature, snapshot)
            rendered[sequence_name][direction_name] = outputs
    return rendered, grounding


def main() -> None:
    args = _args()
    if args.render_size < 128 or args.render_size % 128:
        raise ValueError("render-size must be a multiple of 128 and at least 128")
    if args.framing_scale <= 0.0:
        raise ValueError("framing-scale must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    style, bone_scales = load_style(args.style_config, args.character_id)
    camera, key, fill = _setup(args.render_size, 1.95)
    armature = _armature()
    if armature.animation_data is None:
        armature.animation_data_create()
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("Chibi rendering requires at least one mesh")
    sequences = _sequences(args)
    _derive_weight_regions(armature)
    mesh_obj = _mesh()
    targets, ortho_scale = _styled_auto_frame(
        armature, meshes, sequences, args.pitch, bone_scales
    )
    camera.data.ortho_scale = ortho_scale * args.framing_scale

    beauty, grounding = _render_pass(
        args.output_dir,
        "beauty",
        sequences,
        armature,
        meshes,
        camera,
        key,
        fill,
        args.pitch,
        targets,
        bone_scales,
    )
    original_materials, original_indices = _install_semantic_materials(mesh_obj)
    try:
        _configure_semantic_color()
        semantic, _ = _render_pass(
            args.output_dir,
            "semantic",
            sequences,
            armature,
            meshes,
            camera,
            key,
            fill,
            args.pitch,
            targets,
            bone_scales,
        )
    finally:
        _restore_materials(mesh_obj, original_materials, original_indices)

    manifest_sequences = {}
    for sequence_name, sequence in sequences.items():
        manifest_sequences[sequence_name] = {
            "action": sequence["action"],
            "source_frames": sequence["frames"],
            "fps": sequence["fps"],
            "frame_durations_ms": sequence["frame_durations_ms"],
            "directions": beauty[sequence_name],
            "semantic_directions": semantic[sequence_name],
            "grounding_world_z": grounding[sequence_name],
        }
    manifest = {
        "schema_version": 1,
        "kind": "paired_chibi_sprite_render",
        "blender_version": bpy.app.version_string,
        "blend": bpy.data.filepath,
        "blend_sha256": _sha256(Path(bpy.data.filepath)),
        "style": {
            "id": style["id"],
            "display_name": style["display_name"],
            "config": str(args.style_config.resolve()),
            "config_sha256": _sha256(args.style_config),
            "character_id": args.character_id,
            "bone_scales": {
                name: [float(value) for value in scale]
                for name, scale in bone_scales.items()
            },
            "ground_to_source": True,
        },
        "render_size": args.render_size,
        "ortho_scale": float(camera.data.ortho_scale),
        "framing_scale": args.framing_scale,
        "targets": {
            direction: [float(value) for value in target]
            for direction, target in targets.items()
        },
        "pitch_degrees": args.pitch,
        "direction_order": list(DIRECTIONS),
        "semantic": {
            "derived_from_weights": True,
            "encoding": "flat_rgba_region_colors",
        },
        "sequences": manifest_sequences,
    }
    output = args.output_dir / "sprite_render_manifest.json"
    output.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Wrote {output.resolve()}")


if __name__ == "__main__":
    main()
