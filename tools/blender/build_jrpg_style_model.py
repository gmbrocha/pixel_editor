"""Build a rest-retargeted JRPG character model from a canonical PF blend.

The transformation rebuilds armature rest geometry and the skinned mesh together.
It preserves topology, UVs, weights, materials, and every source action. Approved
runtime actions are copied to JRPG-specific actions before Hips translation is
scaled for the shorter body.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.blender.render_semantic_sprite_sequences import (  # noqa: E402
    _derive_weight_regions,
)


RUNTIME_ACTIONS = {
    "idle": ("PF_Idle_Approved", "PF_Idle_JRPG"),
    "walk": ("PF_Walk_Approved", "PF_Walk_JRPG"),
    "run": ("PF_Run_Approved", "PF_Run_JRPG"),
}


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--style-config", required=True, type=Path)
    parser.add_argument("--character-id", required=True)
    return parser.parse_args(argv)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_hash(value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _armature() -> bpy.types.Object:
    candidates = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one armature, found {[obj.name for obj in candidates]}"
        )
    return candidates[0]


def _bound_meshes(armature: bpy.types.Object) -> list[bpy.types.Object]:
    meshes = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        if any(
            modifier.type == "ARMATURE" and modifier.object == armature
            for modifier in obj.modifiers
        ):
            meshes.append(obj)
    if not meshes:
        raise RuntimeError(f"No skinned meshes are bound to {armature.name}")
    return meshes


def _action_fcurves(action: bpy.types.Action):
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                yield from channelbag.fcurves


def _curve_hash(
    actions: list[bpy.types.Action],
    *,
    rotations: bool,
    include_action_names: bool = True,
) -> str:
    records = []
    for action in sorted(actions, key=lambda item: item.name):
        for curve in _action_fcurves(action):
            is_rotation = "rotation" in curve.data_path
            if is_rotation != rotations:
                continue
            records.append(
                (
                    action.name if include_action_names else "runtime_action",
                    curve.data_path,
                    curve.array_index,
                    [
                        (
                            round(float(key.co[0]), 6),
                            round(float(key.co[1]), 9),
                        )
                        for key in curve.keyframe_points
                    ],
                )
            )
    return _json_hash(records)


def _mesh_contract(mesh: bpy.types.Object) -> dict[str, object]:
    data = mesh.data
    topology = [tuple(int(index) for index in polygon.vertices) for polygon in data.polygons]
    weights = [
        [(int(group.group), round(float(group.weight), 9)) for group in vertex.groups]
        for vertex in data.vertices
    ]
    uv = []
    if data.uv_layers.active is not None:
        uv = [
            (round(float(item.uv.x), 9), round(float(item.uv.y), 9))
            for item in data.uv_layers.active.data
        ]
    return {
        "name": mesh.name,
        "vertices": len(data.vertices),
        "polygons": len(data.polygons),
        "topology_sha256": _json_hash(topology),
        "weights_sha256": _json_hash(weights),
        "uv_sha256": _json_hash(uv),
        "vertex_groups": [group.name for group in mesh.vertex_groups],
    }


def _load_style(path: Path, character_id: str) -> dict[str, object]:
    style = json.loads(path.read_text(encoding="utf-8"))
    if style.get("schema_version") != 2 or style.get("id") != "jrpg_chibi":
        raise RuntimeError(f"Unsupported JRPG style profile: {path}")
    result = json.loads(json.dumps(style["rest_retarget"]))
    override = style.get("character_overrides", {}).get(character_id, {})
    result["bones"].update(override.get("bones", {}))
    for key, value in override.items():
        if key != "bones":
            result[key] = value
    return {"style": style, "retarget": result}


def _scale_matrix(spec: dict[str, object], bone_name: str) -> Matrix:
    length, girth = spec["bones"].get(bone_name, [1.0, 1.0])
    return Matrix.Diagonal(
        Vector((float(girth), float(length), float(girth), 1.0))
    )


def _eye_centers(
    mesh: bpy.types.Object,
    mesh_to_armature: Matrix,
    head_vertices: set[int],
    spec: dict[str, object],
) -> list[Vector]:
    eye_scale = float(spec["eye_scale"])
    if eye_scale == 1.0 or mesh.data.uv_layers.active is None:
        return []
    image_name = str(spec.get("base_color_image", "PF_BaseColor"))
    image = bpy.data.images.get(image_name)
    if image is None:
        print(f"[jrpg] {image_name} is unavailable; skipping eye inflation")
        return []
    width, height = image.size
    pixels = list(image.pixels)
    uv_layer = mesh.data.uv_layers.active.data
    vertex_uv = {}
    for loop in mesh.data.loops:
        vertex_uv.setdefault(loop.vertex_index, uv_layer[loop.index].uv.copy())
    points = [mesh_to_armature @ mesh.data.vertices[index].co for index in head_vertices]
    low_z = min(point.z for point in points)
    high_z = max(point.z for point in points)
    low = low_z + 0.22 * (high_z - low_z)
    high = low_z + 0.90 * (high_z - low_z)
    hits = []
    for vertex_index in head_vertices:
        point = mesh_to_armature @ mesh.data.vertices[vertex_index].co
        if point.y > -2.0 or not (low < point.z < high):
            continue
        uv = vertex_uv.get(vertex_index)
        if uv is None:
            continue
        x = int(min(max(uv.x, 0.0), 0.999) * width)
        y = int(min(max(uv.y, 0.0), 0.999) * height)
        offset = (y * width + x) * 4
        red, green, blue = pixels[offset : offset + 3]
        maximum = max(red, green, blue)
        minimum = min(red, green, blue)
        if maximum > 0.45 and (maximum - minimum) / max(maximum, 1e-6) < 0.18:
            hits.append(point)
    centers = []
    for sign in (1.0, -1.0):
        side = [point for point in hits if point.x * sign > 0.5]
        if len(side) >= 3:
            centers.append(sum(side, Vector((0.0, 0.0, 0.0))) / len(side))
    if len(centers) != 2:
        print("[jrpg] eye detection was inconclusive; skipping eye inflation")
        return []
    return centers


def _copy_runtime_actions(spec: dict[str, object]) -> dict[str, str]:
    motion_scale = float(spec["motion_scale"])
    outputs = {}
    for sequence, (source_name, target_name) in RUNTIME_ACTIONS.items():
        source = bpy.data.actions.get(source_name)
        if source is None:
            raise RuntimeError(f"Missing approved runtime action {source_name}")
        existing = bpy.data.actions.get(target_name)
        if existing is not None:
            bpy.data.actions.remove(existing)
        target = source.copy()
        target.name = target_name
        target.use_fake_user = True
        target["pf_status"] = "derived_jrpg_runtime"
        target["pf_style_id"] = "jrpg_chibi"
        target["pf_style_source_action"] = source_name
        target["pf_motion_scale"] = motion_scale
        scaled = 0
        for curve in _action_fcurves(target):
            if curve.data_path != 'pose.bones["Hips"].location':
                continue
            scaled += 1
            for key in curve.keyframe_points:
                key.co[1] *= motion_scale
                key.handle_left[1] *= motion_scale
                key.handle_right[1] *= motion_scale
        if scaled != 3:
            raise RuntimeError(
                f"Expected three Hips location curves in {source_name}, found {scaled}"
            )
        outputs[sequence] = target_name
    return outputs


def main() -> None:
    args = _args()
    source_path = Path(bpy.data.filepath).resolve()
    source_sha256 = _sha256(source_path)
    loaded = _load_style(args.style_config, args.character_id)
    style = loaded["style"]
    spec = loaded["retarget"]
    armature = _armature()
    meshes = _bound_meshes(armature)
    # Region IDs belong to mesh topology. Derive them against the untouched
    # canonical anatomy, then carry the face-domain attribute through rebind.
    _derive_weight_regions(armature)
    source_contracts = [_mesh_contract(mesh) for mesh in meshes]
    source_actions = list(bpy.data.actions)
    source_rotation_sha256 = _curve_hash(source_actions, rotations=True)

    bones = armature.data.bones
    missing = sorted(set(spec["bones"]) - set(bones.keys()))
    if missing:
        raise RuntimeError(f"JRPG profile references missing bones: {missing}")
    old_matrices: dict[str, Matrix] = {}
    old_lengths: dict[str, float] = {}
    order: list[str] = []

    def walk(bone: bpy.types.Bone) -> None:
        old_matrices[bone.name] = bone.matrix_local.copy()
        old_lengths[bone.name] = float(bone.length)
        order.append(bone.name)
        for child in bone.children:
            walk(child)

    roots = [bone for bone in bones if bone.parent is None]
    if len(roots) != 1:
        raise RuntimeError(f"Expected one root bone, found {[bone.name for bone in roots]}")
    walk(roots[0])
    parent_of = {
        bone.name: bone.parent.name if bone.parent is not None else None
        for bone in bones
    }
    new_matrices: dict[str, Matrix] = {}
    for bone_name in order:
        parent_name = parent_of[bone_name]
        if parent_name is None:
            new_matrices[bone_name] = old_matrices[bone_name].copy()
            continue
        relative = old_matrices[parent_name].inverted() @ old_matrices[bone_name]
        new_relative = relative.to_3x3().to_4x4()
        new_relative.translation = (
            _scale_matrix(spec, parent_name) @ relative.translation.to_4d()
        ).to_3d()
        new_matrices[bone_name] = new_matrices[parent_name] @ new_relative
    deltas = {
        bone_name: new_matrices[bone_name]
        @ _scale_matrix(spec, bone_name)
        @ old_matrices[bone_name].inverted()
        for bone_name in order
    }

    primary = max(meshes, key=lambda item: len(item.data.vertices))
    primary_group_names = {group.index: group.name for group in primary.vertex_groups}
    head_vertices = {
        vertex.index
        for vertex in primary.data.vertices
        if any(
            primary_group_names.get(group.group) == "Head" and group.weight > 0.7
            for group in vertex.groups
        )
    }
    if not head_vertices:
        raise RuntimeError(f"{primary.name} has no strongly Head-weighted vertices")
    primary_to_armature = armature.matrix_world.inverted() @ primary.matrix_world
    original_head_points = [
        primary_to_armature @ primary.data.vertices[index].co
        for index in head_vertices
    ]
    head_low = min(point.z for point in original_head_points)
    head_high = max(point.z for point in original_head_points)
    head_span = head_high - head_low
    eye_centers = _eye_centers(
        primary, primary_to_armature, head_vertices, spec
    )
    eye_inner = float(spec["eye_radius_in"])
    eye_outer = float(spec["eye_radius_out"])
    eye_scale = float(spec["eye_scale"])
    eye_depth = float(spec["eye_depth"])
    head_matrix = old_matrices["Head"]
    head_inverse = head_matrix.inverted()
    jaw = float(spec["jaw_squash"])
    dome = float(spec["cranium_bulge"])
    depth = float(spec["head_depth"])
    head_lift = float(spec["head_lift"])

    def eye_pass(point: Vector) -> Vector:
        for center in eye_centers:
            difference = point - center
            radius = difference.length
            if radius >= eye_outer:
                continue
            amount = (
                1.0
                if radius <= eye_inner
                else 1.0 - (radius - eye_inner) / (eye_outer - eye_inner)
            )
            amount = amount * amount * (3.0 - 2.0 * amount)
            scale = 1.0 + (eye_scale - 1.0) * amount
            point = center + Vector(
                (
                    difference.x * scale,
                    difference.y * (1.0 + (eye_depth - 1.0) * amount),
                    difference.z * scale,
                )
            )
        return point

    def head_shape(point: Vector, weight: float) -> Vector:
        if weight <= 0.001:
            return point
        local = head_inverse @ point
        amount = max(0.0, min(1.0, local.y / head_span))
        amount = amount * amount * (3.0 - 2.0 * amount)
        girth = 1.0 + ((jaw + (dome - jaw) * amount) - 1.0) * weight
        local.x *= girth
        local.z *= girth * (1.0 + (depth - 1.0) * weight)
        return head_matrix @ local

    transformed: dict[str, list[Vector]] = {}
    for mesh in meshes:
        mesh_to_armature = armature.matrix_world.inverted() @ mesh.matrix_world
        group_names = {group.index: group.name for group in mesh.vertex_groups}
        output = []
        for vertex in mesh.data.vertices:
            point = eye_pass(mesh_to_armature @ vertex.co)
            influences = [
                (group_names.get(group.group), float(group.weight))
                for group in vertex.groups
                if group_names.get(group.group) in deltas
            ]
            total = sum(weight for _, weight in influences)
            if total <= 0.0:
                output.append(point)
                continue
            accumulated = Vector((0.0, 0.0, 0.0))
            head_weight = 0.0
            for bone_name, weight in influences:
                normalized = weight / total
                accumulated += (deltas[bone_name] @ point) * normalized
                if bone_name == "Head":
                    head_weight = normalized
            accumulated = head_shape(accumulated, head_weight)
            accumulated.z += head_lift * head_weight
            output.append(accumulated)
        transformed[mesh.name] = output

    ground_shift = -min(
        point.z for points in transformed.values() for point in points
    )
    for points in transformed.values():
        for point in points:
            point.z += ground_shift
    for matrix in new_matrices.values():
        matrix.translation.z += ground_shift

    for mesh in meshes:
        armature_to_mesh = (
            armature.matrix_world.inverted() @ mesh.matrix_world
        ).inverted()
        for vertex, point in zip(
            mesh.data.vertices, transformed[mesh.name], strict=True
        ):
            vertex.co = armature_to_mesh @ point
        mesh.data.update()

    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    for edit_bone in armature.data.edit_bones:
        edit_bone.use_connect = False
    for bone_name in order:
        edit_bone = armature.data.edit_bones[bone_name]
        edit_bone.matrix = new_matrices[bone_name]
        length_scale = float(spec["bones"].get(bone_name, [1.0, 1.0])[0])
        edit_bone.length = max(old_lengths[bone_name] * length_scale, 1e-4)
    bpy.ops.object.mode_set(mode="OBJECT")

    runtime_actions = _copy_runtime_actions(spec)
    styled_actions = [bpy.data.actions[name] for name in runtime_actions.values()]
    styled_rotation_sha256 = _curve_hash(
        styled_actions, rotations=True, include_action_names=False
    )
    source_runtime_rotation_sha256 = _curve_hash(
        [bpy.data.actions[source] for source, _ in RUNTIME_ACTIONS.values()],
        rotations=True,
        include_action_names=False,
    )
    if styled_rotation_sha256 != source_runtime_rotation_sha256:
        raise RuntimeError("JRPG action copying changed approved rotation keys")
    output_contracts = [_mesh_contract(mesh) for mesh in meshes]
    for before, after in zip(source_contracts, output_contracts, strict=True):
        for key in ("vertices", "polygons", "topology_sha256", "weights_sha256", "uv_sha256", "vertex_groups"):
            if before[key] != after[key]:
                raise RuntimeError(f"JRPG rest retarget changed mesh contract {key}")

    primary_points = transformed[primary.name]
    height = max(point.z for point in primary_points) - min(
        point.z for point in primary_points
    )
    transformed_head = [primary_points[index] for index in head_vertices]
    head_height = max(point.z for point in transformed_head) - min(
        point.z for point in transformed_head
    )
    heads_tall = height / head_height

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()), compress=True)
    manifest = {
        "schema_version": 1,
        "kind": "jrpg_rest_retargeted_character_model",
        "status": "working_render_source",
        "character_id": args.character_id,
        "blender_version": bpy.app.version_string,
        "source_blend": str(source_path),
        "source_blend_sha256": source_sha256,
        "output_blend": str(args.output.resolve()),
        "output_blend_sha256": _sha256(args.output),
        "style_config": str(args.style_config.resolve()),
        "style_config_sha256": _sha256(args.style_config),
        "method": "rest_pose_lbs_rebind",
        "ground_shift_armature_units": ground_shift,
        "heads_tall": heads_tall,
        "armature": {
            "name": armature.name,
            "bone_count": len(armature.data.bones),
            "bone_hierarchy_sha256": _json_hash(
                [
                    (bone.name, bone.parent.name if bone.parent else None)
                    for bone in sorted(armature.data.bones, key=lambda item: item.name)
                ]
            ),
        },
        "meshes": output_contracts,
        "actions": runtime_actions,
        "protected_source_rotation_sha256": source_rotation_sha256,
        "runtime_source_rotation_sha256": source_runtime_rotation_sha256,
        "runtime_jrpg_rotation_sha256": styled_rotation_sha256,
    }
    args.manifest.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"Built {args.character_id} JRPG model at {heads_tall:.2f} heads tall: "
        f"{args.output.resolve()}"
    )


if __name__ == "__main__":
    main()
