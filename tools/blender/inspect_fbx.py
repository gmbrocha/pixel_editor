"""Inspect FBX scene structure in Blender and emit a deterministic JSON report.

Run with Blender, not the system Python::

    blender --background --factory-startup --python inspect_fbx.py -- \
        --output report.json model.fbx [model.fbx ...]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("fbx", nargs="+", type=Path)
    return parser.parse_args(argv)


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _vector(value: Any) -> list[float]:
    return [_round(component) for component in value]


def _matrix(value: Any) -> list[list[float]]:
    return [[_round(component) for component in row] for row in value]


def _safe_frame_range(action: Any) -> list[float] | None:
    try:
        return [_round(action.frame_range[0]), _round(action.frame_range[1])]
    except Exception:
        return None


def _action_details(action: Any) -> dict[str, Any]:
    details: dict[str, Any] = {
        "name": action.name,
        "frame_range": _safe_frame_range(action),
        "users": action.users,
    }
    for attribute in ("fcurves", "groups", "slots", "layers"):
        collection = getattr(action, attribute, None)
        if collection is not None:
            try:
                details[f"{attribute}_count"] = len(collection)
            except TypeError:
                pass
    return details


def _material_details(material: bpy.types.Material) -> dict[str, Any]:
    images: list[dict[str, str]] = []
    if material.use_nodes and material.node_tree:
        for node in material.node_tree.nodes:
            image = getattr(node, "image", None)
            if image is not None:
                images.append(
                    {
                        "node": node.name,
                        "image": image.name,
                        "filepath": bpy.path.abspath(image.filepath),
                    }
                )
    return {
        "name": material.name,
        "use_nodes": material.use_nodes,
        "images": sorted(images, key=lambda item: (item["node"], item["image"])),
    }


def _mesh_details(obj: bpy.types.Object) -> dict[str, Any]:
    mesh = obj.data
    dimensions = obj.dimensions
    armature_modifiers = [
        {
            "name": modifier.name,
            "object": modifier.object.name if modifier.object else None,
        }
        for modifier in obj.modifiers
        if modifier.type == "ARMATURE"
    ]
    return {
        "name": obj.name,
        "data_name": mesh.name,
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
        "dimensions": _vector(dimensions),
        "location": _vector(obj.location),
        "rotation_euler": _vector(obj.rotation_euler),
        "scale": _vector(obj.scale),
        "uv_layers": [layer.name for layer in mesh.uv_layers],
        "vertex_groups": [group.name for group in obj.vertex_groups],
        "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
        "armature_modifiers": armature_modifiers,
    }


def _armature_details(obj: bpy.types.Object) -> dict[str, Any]:
    bones = []
    for bone in obj.data.bones:
        bones.append(
            {
                "name": bone.name,
                "parent": bone.parent.name if bone.parent else None,
                "head_local": _vector(bone.head_local),
                "tail_local": _vector(bone.tail_local),
                "length": _round(bone.length),
                "matrix_local": _matrix(bone.matrix_local),
                "use_deform": bone.use_deform,
            }
        )
    animation = obj.animation_data
    return {
        "name": obj.name,
        "data_name": obj.data.name,
        "location": _vector(obj.location),
        "rotation_euler": _vector(obj.rotation_euler),
        "scale": _vector(obj.scale),
        "bone_count": len(bones),
        "root_bones": [bone["name"] for bone in bones if bone["parent"] is None],
        "active_action": (
            animation.action.name if animation and animation.action is not None else None
        ),
        "bones": bones,
    }


def _world_bounds(objects: list[bpy.types.Object]) -> dict[str, list[float]] | None:
    points = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        return None
    return {
        "min": [_round(min(point[index] for point in points)) for index in range(3)],
        "max": [_round(max(point[index] for point in points)) for index in range(3)],
    }


def _import_fbx(path: Path) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        bpy.ops.import_scene.fbx(filepath=str(path), automatic_bone_orientation=False)
    except AttributeError:
        bpy.ops.wm.fbx_import(filepath=str(path))


def _inspect(path: Path) -> dict[str, Any]:
    _import_fbx(path)
    objects = sorted(bpy.data.objects, key=lambda obj: obj.name)
    meshes = [_mesh_details(obj) for obj in objects if obj.type == "MESH"]
    armatures = [_armature_details(obj) for obj in objects if obj.type == "ARMATURE"]
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "scene": {
            "fps": bpy.context.scene.render.fps,
            "fps_base": _round(bpy.context.scene.render.fps_base),
            "frame_start": bpy.context.scene.frame_start,
            "frame_end": bpy.context.scene.frame_end,
            "world_bounds": _world_bounds(objects),
        },
        "object_counts": {
            object_type: sum(obj.type == object_type for obj in objects)
            for object_type in sorted({obj.type for obj in objects})
        },
        "objects": [
            {
                "name": obj.name,
                "type": obj.type,
                "parent": obj.parent.name if obj.parent else None,
            }
            for obj in objects
        ],
        "meshes": meshes,
        "armatures": armatures,
        "actions": [
            _action_details(action)
            for action in sorted(bpy.data.actions, key=lambda action: action.name)
        ],
        "materials": [
            _material_details(material)
            for material in sorted(bpy.data.materials, key=lambda material: material.name)
        ],
        "images": [
            {
                "name": image.name,
                "filepath": bpy.path.abspath(image.filepath),
                "size": list(image.size),
            }
            for image in sorted(bpy.data.images, key=lambda image: image.name)
        ],
    }


def main() -> None:
    args = _args()
    missing = [path for path in args.fbx if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing FBX input(s): {missing}")
    report = {
        "blender": {
            "version": bpy.app.version_string,
            "version_tuple": list(bpy.app.version),
        },
        "files": [_inspect(path) for path in args.fbx],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.resolve()}")


if __name__ == "__main__":
    main()
