"""Non-destructive render-time pose proportion helpers for chibi sprites."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import bpy
from mathutils import Vector


@dataclass(slots=True)
class PoseStyleSnapshot:
    scales: dict[str, Vector]
    hips_location: Vector


def load_style(path: Path, character_id: str) -> tuple[dict[str, object], dict[str, Vector]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("id"), str):
        raise RuntimeError(f"Unsupported chibi style profile: {path}")
    raw_scales = dict(data.get("bone_scales", {}))
    overrides = data.get("character_overrides", {}).get(character_id, {})
    raw_scales.update(overrides.get("bone_scales", {}))
    scales: dict[str, Vector] = {}
    for bone_name, raw in raw_scales.items():
        if not isinstance(bone_name, str) or not isinstance(raw, list) or len(raw) != 3:
            raise RuntimeError(f"Invalid bone scale for {bone_name!r}")
        value = Vector(float(component) for component in raw)
        if min(value) <= 0.0:
            raise RuntimeError(f"Bone scale for {bone_name!r} must be positive")
        scales[bone_name] = value
    return data, scales


def mesh_world_bounds(meshes: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    minimum = Vector((float("inf"),) * 3)
    maximum = Vector((float("-inf"),) * 3)
    for mesh in meshes:
        evaluated = mesh.evaluated_get(depsgraph)
        evaluated_mesh = evaluated.to_mesh(
            preserve_all_data_layers=False, depsgraph=depsgraph
        )
        try:
            for vertex in evaluated_mesh.vertices:
                point = evaluated.matrix_world @ vertex.co
                for axis in range(3):
                    minimum[axis] = min(minimum[axis], point[axis])
                    maximum[axis] = max(maximum[axis], point[axis])
        finally:
            evaluated.to_mesh_clear()
    return minimum, maximum


def mesh_world_points(meshes: list[bpy.types.Object]):
    """Yield exact evaluated world-space mesh vertices for the current pose."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for mesh in meshes:
        evaluated = mesh.evaluated_get(depsgraph)
        evaluated_mesh = evaluated.to_mesh(
            preserve_all_data_layers=False, depsgraph=depsgraph
        )
        try:
            for vertex in evaluated_mesh.vertices:
                yield evaluated.matrix_world @ vertex.co
        finally:
            evaluated.to_mesh_clear()


def _ground_z(armature: bpy.types.Object) -> float:
    points = []
    for bone_name in ("LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"):
        bone = armature.pose.bones.get(bone_name)
        if bone is None:
            raise RuntimeError(f"Chibi grounding requires {bone_name}")
        points.extend((bone.head, bone.tail))
    return min((armature.matrix_world @ point).z for point in points)


def apply_pose_style(
    armature: bpy.types.Object,
    meshes: list[bpy.types.Object],
    bone_scales: dict[str, Vector],
) -> tuple[PoseStyleSnapshot, float]:
    missing = sorted(set(bone_scales) - set(armature.pose.bones.keys()))
    if missing:
        raise RuntimeError(f"Chibi profile references missing bones: {missing}")
    hips = armature.pose.bones.get("Hips")
    if hips is None:
        raise RuntimeError("Chibi grounding requires the Hips bone")
    snapshot = PoseStyleSnapshot(
        scales={name: armature.pose.bones[name].scale.copy() for name in bone_scales},
        hips_location=hips.location.copy(),
    )
    before_ground = _ground_z(armature)
    for bone_name, multiplier in bone_scales.items():
        bone = armature.pose.bones[bone_name]
        bone.scale = Vector(
            bone.scale[index] * multiplier[index] for index in range(3)
        )
    bpy.context.view_layer.update()
    after_ground = _ground_z(armature)
    world_delta = before_ground - after_ground
    local_delta = armature.matrix_world.inverted().to_3x3() @ Vector(
        (0.0, 0.0, world_delta)
    )
    hips.location += local_delta
    bpy.context.view_layer.update()
    return snapshot, float(world_delta)


def restore_pose_style(
    armature: bpy.types.Object,
    snapshot: PoseStyleSnapshot,
) -> None:
    hips = armature.pose.bones["Hips"]
    hips.location = snapshot.hips_location
    for bone_name, scale in snapshot.scales.items():
        armature.pose.bones[bone_name].scale = scale
    bpy.context.view_layer.update()
