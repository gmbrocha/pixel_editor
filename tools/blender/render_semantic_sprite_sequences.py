"""Render paired beauty and anatomical-region passes for sprite packaging."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.mannequin_semantics import (  # noqa: E402
    REGIONS,
    REGION_BY_NAME,
    sha256_path,
)
from tools.blender.render_sprite_sequences import (  # noqa: E402
    _armature,
    _position_view,
    _setup,
)
from tools.blender.build_semantic_mannequin import (  # noqa: E402
    _assign_regions,
    _bone_point_in_mesh,
    _dominant_groups,
    _region_for_face,
    _write_attributes,
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
    parser.add_argument("--action", default="PF_Walk_Meshy_Edit")
    parser.add_argument("--sequence", default="walk")
    parser.add_argument(
        "--frame-count", type=int,
        help="Expected frame count; defaults to the action's sample-frame metadata",
    )
    parser.add_argument(
        "--frames",
        help="Comma-separated source frames; overrides action sample-frame metadata",
    )
    parser.add_argument("--render-size", type=int, default=1024)
    parser.add_argument("--ortho-scale", type=float, default=1.95)
    parser.add_argument("--pitch", type=float, default=28.0)
    parser.add_argument(
        "--target",
        help="Comma-separated camera target X,Y,Z; defaults to 0,0,0.82",
    )
    parser.add_argument(
        "--derive-weight-regions",
        action="store_true",
        help="Derive temporary anatomical face regions from the shared rig weights",
    )
    return parser.parse_args(argv)


def _derive_weight_regions(armature: bpy.types.Object) -> dict[str, int]:
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(
            f"Expected one mesh for weight-region derivation, found {[obj.name for obj in meshes]}"
        )
    mesh_obj = meshes[0]
    try:
        assignments, counts = _assign_regions(mesh_obj, armature, None, "")
    except RuntimeError as exc:
        if "left_knee" not in str(exc) and "right_knee" not in str(exc):
            raise
        joints = {
            "left_shoulder": _bone_point_in_mesh(mesh_obj, armature, "LeftArm", "head"),
            "right_shoulder": _bone_point_in_mesh(mesh_obj, armature, "RightArm", "head"),
            "left_elbow": _bone_point_in_mesh(mesh_obj, armature, "LeftForeArm", "head"),
            "right_elbow": _bone_point_in_mesh(mesh_obj, armature, "RightForeArm", "head"),
            "left_knee": _bone_point_in_mesh(mesh_obj, armature, "LeftLeg", "head"),
            "right_knee": _bone_point_in_mesh(mesh_obj, armature, "RightLeg", "head"),
            "left_ankle": _bone_point_in_mesh(mesh_obj, armature, "LeftFoot", "head"),
            "right_ankle": _bone_point_in_mesh(mesh_obj, armature, "RightFoot", "head"),
        }
        dominant = _dominant_groups(mesh_obj)
        centers = []
        assignments = []
        for polygon, group in zip(mesh_obj.data.polygons, dominant, strict=True):
            center = sum(
                (mesh_obj.data.vertices[index].co for index in polygon.vertices),
                Vector(),
            ) / len(polygon.vertices)
            centers.append(center)
            assignments.append(_region_for_face(center, group, joints))
        counts_by_id = Counter(assignments)
        for side in ("left", "right"):
            knee_id = REGION_BY_NAME[f"{side}_knee"].id
            if counts_by_id[knee_id] > 0:
                continue
            title = side.title()
            candidates = [
                index
                for index, group in enumerate(dominant)
                if group in {f"{title}UpLeg", f"{title}Leg"}
            ]
            candidates.sort(
                key=lambda index: (centers[index] - joints[f"{side}_knee"]).length
            )
            for index in candidates[:1200]:
                assignments[index] = knee_id
        final_counts = Counter(assignments)
        missing = [region.name for region in REGIONS if final_counts[region.id] == 0]
        if missing:
            raise RuntimeError(f"Weight-region fallback left empty regions: {missing}")
        counts = {region.name: final_counts[region.id] for region in REGIONS}
    _write_attributes(mesh_obj.data, assignments)
    return counts


def _mesh() -> bpy.types.Object:
    candidates = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj.data.attributes.get("pf_region_id") is not None
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            "Expected one mesh with pf_region_id, found "
            f"{[obj.name for obj in candidates]}"
        )
    mesh_obj = candidates[0]
    attribute = mesh_obj.data.attributes["pf_region_id"]
    if attribute.domain != "FACE":
        raise RuntimeError("pf_region_id must be a face-domain attribute")
    return mesh_obj


def _semantic_material(region_id: int, color: tuple[int, int, int, int]) -> bpy.types.Material:
    material = bpy.data.materials.new(f"PF_Sprite_Region_{region_id:02d}")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = tuple(channel / 255.0 for channel in color)
    emission.inputs["Strength"].default_value = 1.0
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _install_semantic_materials(mesh_obj: bpy.types.Object) -> tuple[list[bpy.types.Material], list[int]]:
    mesh = mesh_obj.data
    original_materials = list(mesh.materials)
    original_indices = [polygon.material_index for polygon in mesh.polygons]
    mesh.materials.clear()
    for region in REGIONS:
        mesh.materials.append(_semantic_material(region.id, region.color))
    attribute = mesh.attributes["pf_region_id"]
    for polygon in mesh.polygons:
        region_id = int(attribute.data[polygon.index].value)
        if region_id < 1 or region_id > len(REGIONS):
            raise RuntimeError(f"Polygon {polygon.index} has invalid region ID {region_id}")
        polygon.material_index = region_id - 1
    return original_materials, original_indices


def _restore_materials(
    mesh_obj: bpy.types.Object,
    materials: list[bpy.types.Material],
    indices: list[int],
) -> None:
    mesh = mesh_obj.data
    mesh.materials.clear()
    for material in materials:
        mesh.materials.append(material)
    for polygon, material_index in zip(mesh.polygons, indices, strict=True):
        polygon.material_index = material_index


def _configure_semantic_color() -> None:
    scene = bpy.context.scene
    # Loaded production files expose Blender's full color-management enum even
    # though factory-startup exposes the internal NONE sentinel. Raw avoids a
    # display transform; package decoding still uses nearest marker color.
    scene.view_settings.view_transform = "Raw"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 15


def _render_frames(
    output_dir: Path,
    pass_name: str,
    sequence_name: str,
    frames: list[int],
    camera: bpy.types.Object,
    key: bpy.types.Object,
    fill: bpy.types.Object,
    pitch: float,
    target: Vector,
) -> dict[str, list[str]]:
    outputs: dict[str, list[str]] = {}
    for direction_name, horizontal in DIRECTIONS.items():
        _position_view(camera, key, fill, horizontal, pitch, target)
        direction_outputs = []
        for frame_index, source_frame in enumerate(frames):
            bpy.context.scene.frame_set(source_frame)
            output = (
                output_dir
                / pass_name
                / sequence_name
                / direction_name
                / f"frame_{frame_index:02d}_source_{source_frame:03d}.png"
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            if not output.is_file():
                bpy.context.scene.render.filepath = str(output.resolve())
                bpy.ops.render.render(write_still=True)
            direction_outputs.append(str(output.resolve()))
        outputs[direction_name] = direction_outputs
    return outputs


def main() -> None:
    args = _args()
    if args.render_size < 128 or args.render_size % 128:
        raise ValueError("render-size must be a multiple of 128 and at least 128")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    camera, key, fill = _setup(args.render_size, args.ortho_scale)
    armature = _armature()
    derived_counts = (
        _derive_weight_regions(armature) if args.derive_weight_regions else None
    )
    mesh_obj = _mesh()
    if armature.animation_data is None:
        armature.animation_data_create()
    action = bpy.data.actions.get(args.action)
    if action is None:
        raise RuntimeError(f"Missing action {args.action}")
    armature.animation_data.action = action
    raw_samples = action.get("pf_sample_frames_json")
    if args.frames:
        frames = [int(value.strip()) for value in args.frames.split(",") if value.strip()]
    else:
        frames = (
            [int(frame) for frame in json.loads(raw_samples)]
            if raw_samples
            else list(range(1, 9))
        )
    expected_count = int(args.frame_count or len(frames))
    if (
        expected_count < 1
        or len(frames) != expected_count
        or len(set(frames)) != expected_count
        or any(frame < 1 for frame in frames)
    ):
        raise RuntimeError(
            f"Expected {expected_count} distinct sprite frames, found {frames}"
        )

    target = Vector((0.0, 0.0, 0.82))
    if args.target:
        values = [float(value.strip()) for value in args.target.split(",")]
        if len(values) != 3:
            raise ValueError("target must contain exactly X,Y,Z")
        target = Vector(values)

    beauty = _render_frames(
        args.output_dir, "beauty", args.sequence, frames,
        camera, key, fill, args.pitch, target,
    )
    original_materials, original_indices = _install_semantic_materials(mesh_obj)
    try:
        _configure_semantic_color()
        semantic = _render_frames(
            args.output_dir, "semantic", args.sequence, frames,
            camera, key, fill, args.pitch, target,
        )
    finally:
        _restore_materials(mesh_obj, original_materials, original_indices)

    manifest = {
        "schema_version": 1,
        "kind": "paired_semantic_sprite_render",
        "blender_version": bpy.app.version_string,
        "blend": bpy.data.filepath,
        "blend_sha256": sha256_path(Path(bpy.data.filepath)),
        "render_size": args.render_size,
        "ortho_scale": args.ortho_scale,
        "pitch_degrees": args.pitch,
        "target": [float(value) for value in target],
        "direction_order": list(DIRECTIONS),
        "semantic": {
            "attribute": "pf_region_id",
            "encoding": "flat_rgba_region_colors",
            "regions": [
                {
                    "id": region.id,
                    "name": region.name,
                    "side": region.side,
                    "color": list(region.color),
                }
                for region in REGIONS
            ],
            "derived_from_weights": args.derive_weight_regions,
            "derived_region_face_counts": derived_counts,
        },
        "sequences": {
            args.sequence: {
                "action": action.name,
                "source_frames": frames,
                "directions": beauty,
                "semantic_directions": semantic,
            }
        },
    }
    manifest_path = args.output_dir / "paired_sprite_render_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path.resolve()}")


if __name__ == "__main__":
    main()
