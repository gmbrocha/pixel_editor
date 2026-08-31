"""Render paired beauty/semantic sprites from a rest-retargeted JRPG blend."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.blender.render_semantic_sprite_sequences import (  # noqa: E402
    _configure_semantic_color,
    _derive_weight_regions,
    _install_semantic_materials,
    _mesh,
    _restore_materials,
)
from tools.blender.render_sprite_sequences import (  # noqa: E402
    _armature,
    _auto_frame,
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--style-config", required=True, type=Path)
    parser.add_argument("--model-manifest", required=True, type=Path)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--render-size", type=int, default=1024)
    parser.add_argument("--pitch", type=float, default=28.0)
    parser.add_argument("--framing-scale", type=float, default=1.0)
    parser.add_argument("--timing-config", required=True, type=Path)
    parser.add_argument("--idle-action", default="PF_Idle_JRPG")
    parser.add_argument("--walk-action", default="PF_Walk_JRPG")
    parser.add_argument("--run-action", default="PF_Run_JRPG")
    parser.add_argument(
        "--expected-model-kind",
        default="jrpg_rest_retargeted_character_model",
    )
    parser.add_argument("--manifest-kind", default="paired_jrpg_sprite_render")
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


def _render_pass(
    output_dir: Path,
    pass_name: str,
    sequences: dict[str, dict[str, object]],
    armature: bpy.types.Object,
    camera: bpy.types.Object,
    key: bpy.types.Object,
    fill: bpy.types.Object,
    pitch: float,
    target: Vector,
) -> dict[str, dict[str, list[str]]]:
    rendered: dict[str, dict[str, list[str]]] = {}
    for sequence_name, sequence in sequences.items():
        armature.animation_data.action = bpy.data.actions[str(sequence["action"])]
        rendered[sequence_name] = {}
        for direction_name, horizontal in DIRECTIONS.items():
            _position_view(camera, key, fill, horizontal, pitch, target)
            outputs = []
            for frame_index, source_frame in enumerate(sequence["frames"]):
                bpy.context.scene.frame_set(int(source_frame))
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
            rendered[sequence_name][direction_name] = outputs
    return rendered


def main() -> None:
    args = _args()
    if args.render_size < 128 or args.render_size % 128:
        raise ValueError("render-size must be a multiple of 128 and at least 128")
    if args.framing_scale <= 0.0:
        raise ValueError("framing-scale must be positive")
    style = json.loads(args.style_config.read_text(encoding="utf-8"))
    model = json.loads(args.model_manifest.read_text(encoding="utf-8"))
    if style.get("schema_version") != 2 or style.get("method") != "rest_pose_lbs_rebind":
        raise RuntimeError("JRPG rendering requires the rest-retarget style profile")
    if model.get("kind") != args.expected_model_kind:
        raise RuntimeError(
            "Styled rendering model kind differs: "
            f"expected {args.expected_model_kind!r}, got {model.get('kind')!r}"
        )
    if model.get("character_id") != args.character_id:
        raise RuntimeError("JRPG model manifest character differs")
    if model.get("output_blend_sha256") != _sha256(Path(bpy.data.filepath)):
        raise RuntimeError("Loaded JRPG blend differs from its model manifest")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    camera, key, fill = _setup(args.render_size, 1.95)
    armature = _armature()
    if armature.animation_data is None:
        armature.animation_data_create()
    sequences = _sequences(args)
    target, ortho_scale = _auto_frame(
        armature, sequences, args.pitch
    )
    camera.data.ortho_scale = ortho_scale * args.framing_scale

    try:
        mesh_obj = _mesh()
    except RuntimeError:
        _derive_weight_regions(armature)
        mesh_obj = _mesh()
    beauty = _render_pass(
        args.output_dir,
        "beauty",
        sequences,
        armature,
        camera,
        key,
        fill,
        args.pitch,
        target,
    )
    original_materials, original_indices = _install_semantic_materials(mesh_obj)
    try:
        _configure_semantic_color()
        semantic = _render_pass(
            args.output_dir,
            "semantic",
            sequences,
            armature,
            camera,
            key,
            fill,
            args.pitch,
            target,
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
        }
    manifest = {
        "schema_version": 1,
        "kind": args.manifest_kind,
        "blender_version": bpy.app.version_string,
        "blend": bpy.data.filepath,
        "blend_sha256": _sha256(Path(bpy.data.filepath)),
        "style": {
            "id": style["id"],
            "display_name": style["display_name"],
            "method": style["method"],
            "config": str(args.style_config.resolve()),
            "config_sha256": _sha256(args.style_config),
            "model_manifest": str(args.model_manifest.resolve()),
            "model_manifest_sha256": _sha256(args.model_manifest),
            "character_id": args.character_id,
            "heads_tall": model["heads_tall"],
        },
        "render_size": args.render_size,
        "ortho_scale": float(camera.data.ortho_scale),
        "framing_scale": args.framing_scale,
        "target": [float(value) for value in target],
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
