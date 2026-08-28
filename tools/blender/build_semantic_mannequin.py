"""Build the tracked Pixel Forge semantic mannequin from the approved Blender pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

import bpy
from mathutils import Matrix, Vector


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.mannequin_semantics import (  # noqa: E402
    ATTACHMENT_BONES,
    CHARACTER_SLOTS,
    MANNEQUIN_SCHEMA_VERSION,
    REGIONS,
    REGION_BY_ID,
    REGION_BY_NAME,
    SLOT_HIDE_REGIONS,
    SLOT_SURFACE_REGIONS,
    decode_index_runs,
    region_ids,
    sha256_path,
)


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--debug-texture", required=True, type=Path)
    parser.add_argument("--overrides", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def _only_object(object_type: str) -> bpy.types.Object:
    matches = [obj for obj in bpy.data.objects if obj.type == object_type]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {object_type}, found {[obj.name for obj in matches]}")
    return matches[0]


def _digest_rows(rows: list[bytes]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(row)
    return digest.hexdigest()


def topology_hash(mesh: bpy.types.Mesh) -> str:
    rows = [struct.pack("<II", len(mesh.vertices), len(mesh.polygons))]
    rows.extend(struct.pack("<3f", *vertex.co) for vertex in mesh.vertices)
    for polygon in mesh.polygons:
        rows.append(struct.pack("<I", len(polygon.vertices)))
        rows.append(struct.pack(f"<{len(polygon.vertices)}I", *polygon.vertices))
    return _digest_rows(rows)


def weight_hash(mesh_obj: bpy.types.Object) -> str:
    names = {group.index: group.name for group in mesh_obj.vertex_groups}
    rows: list[bytes] = []
    for vertex in mesh_obj.data.vertices:
        rows.append(struct.pack("<I", vertex.index))
        values = sorted((names[item.group], float(item.weight)) for item in vertex.groups)
        for name, weight in values:
            encoded = name.encode("utf-8")
            rows.append(struct.pack("<H", len(encoded)) + encoded + struct.pack("<f", weight))
    return _digest_rows(rows)


def rest_pose_hash(armature: bpy.types.Object) -> str:
    rows: list[bytes] = []
    for bone in sorted(armature.data.bones, key=lambda item: item.name):
        name = bone.name.encode("utf-8")
        parent = (bone.parent.name if bone.parent else "").encode("utf-8")
        rows.append(struct.pack("<H", len(name)) + name)
        rows.append(struct.pack("<H", len(parent)) + parent)
        rows.append(struct.pack("<16f", *(value for row in bone.matrix_local for value in row)))
    return _digest_rows(rows)


def material_hash(mesh_obj: bpy.types.Object) -> str:
    rows: list[bytes] = []
    for material in mesh_obj.data.materials:
        rows.append(material.name.encode("utf-8") + b"\0")
        if not material.use_nodes or material.node_tree is None:
            continue
        for node in sorted(material.node_tree.nodes, key=lambda item: (item.bl_idname, item.name)):
            rows.append(f"{node.bl_idname}|{node.name}|{node.label}".encode("utf-8") + b"\0")
            for socket in node.inputs:
                if not hasattr(socket, "default_value"):
                    continue
                value = socket.default_value
                if hasattr(value, "__iter__") and not isinstance(value, str):
                    serialized = ",".join(f"{float(item):.9g}" for item in value)
                elif isinstance(value, float):
                    serialized = f"{value:.9g}"
                else:
                    serialized = str(value)
                rows.append(f"input:{socket.name}:{serialized}".encode("utf-8") + b"\0")
            image = getattr(node, "image", None)
            if image is not None:
                rows.append(
                    f"image:{image.name}:{image.filepath}:{image.colorspace_settings.name}"
                    .encode("utf-8") + b"\0"
                )
            for property_name in ("interpolation", "extension", "projection", "space"):
                if hasattr(node, property_name):
                    rows.append(
                        f"property:{property_name}:{getattr(node, property_name)}"
                        .encode("utf-8") + b"\0"
                    )
        links = sorted(
            f"{link.from_node.name}:{link.from_socket.name}>{link.to_node.name}:{link.to_socket.name}"
            for link in material.node_tree.links
        )
        rows.extend(link.encode("utf-8") + b"\0" for link in links)
    return _digest_rows(rows)


def action_hashes(armature: bpy.types.Object) -> dict[str, str]:
    if armature.animation_data is None:
        armature.animation_data_create()
    previous = armature.animation_data.action
    previous_frame = bpy.context.scene.frame_current
    result: dict[str, str] = {}
    for action in sorted(bpy.data.actions, key=lambda item: item.name):
        armature.animation_data.action = action
        start, end = (int(round(value)) for value in action.frame_range)
        rows: list[bytes] = [action.name.encode("utf-8") + struct.pack("<ii", start, end)]
        for frame in range(start, end + 1):
            bpy.context.scene.frame_set(frame)
            for bone in sorted(armature.pose.bones, key=lambda item: item.name):
                rows.append(bone.name.encode("utf-8") + b"\0")
                rows.append(struct.pack("<16f", *(value for row in bone.matrix_basis for value in row)))
        result[action.name] = _digest_rows(rows)
    armature.animation_data.action = previous
    bpy.context.scene.frame_set(previous_frame)
    return result


def _bone_point_in_mesh(
    mesh_obj: bpy.types.Object,
    armature: bpy.types.Object,
    bone_name: str,
    endpoint: str,
) -> Vector:
    bone = armature.data.bones.get(bone_name)
    if bone is None:
        raise RuntimeError(f"Missing required bone {bone_name}")
    point = bone.head_local if endpoint == "head" else bone.tail_local
    return mesh_obj.matrix_world.inverted() @ (armature.matrix_world @ point)


def _dominant_groups(mesh_obj: bpy.types.Object) -> list[str]:
    group_names = {group.index: group.name for group in mesh_obj.vertex_groups}
    result: list[str] = []
    for polygon in mesh_obj.data.polygons:
        totals: Counter[str] = Counter()
        for vertex_index in polygon.vertices:
            for assignment in mesh_obj.data.vertices[vertex_index].groups:
                totals[group_names[assignment.group]] += assignment.weight
        result.append(totals.most_common(1)[0][0] if totals else "")
    return result


def _region_for_face(
    center: Vector,
    dominant: str,
    joints: dict[str, Vector],
) -> int:
    x, height, depth = center
    side = "left" if x >= 0.0 else "right"
    side_title = side.title()

    if dominant in {"Head", "head_end", "headfront"} or height >= 139.0:
        if abs(x) >= 6.5 and 145.0 <= height <= 158.5:
            return REGION_BY_NAME[f"{side}_ear"].id
        if height >= 156.0:
            return REGION_BY_NAME["scalp"].id
        if depth >= 0.5:
            return REGION_BY_NAME["face"].id
        return REGION_BY_NAME["rear_head"].id

    if dominant == "neck" or (height >= 129.5 and abs(x) < 6.5):
        return REGION_BY_NAME["neck"].id

    arm_groups = {
        f"{side_title}Shoulder", f"{side_title}Arm",
        f"{side_title}ForeArm", f"{side_title}Hand",
    }
    if dominant in arm_groups:
        if (center - joints[f"{side}_elbow"]).length <= 5.2:
            return REGION_BY_NAME[f"{side}_elbow"].id
        if dominant == f"{side_title}Hand":
            return REGION_BY_NAME[f"{side}_hand"].id
        if dominant == f"{side_title}Shoulder" or (
            center - joints[f"{side}_shoulder"]
        ).length <= 6.0:
            return REGION_BY_NAME[f"{side}_shoulder"].id
        if dominant == f"{side_title}ForeArm":
            return REGION_BY_NAME[f"{side}_forearm"].id
        return REGION_BY_NAME[f"{side}_upper_arm"].id

    leg_groups = {
        f"{side_title}UpLeg", f"{side_title}Leg", f"{side_title}Foot",
        f"{side_title}ToeBase",
    }
    if dominant in leg_groups:
        if dominant in {f"{side_title}Foot", f"{side_title}ToeBase"} and height <= 11.5:
            return REGION_BY_NAME[f"{side}_foot"].id
        if (center - joints[f"{side}_ankle"]).length <= 5.0:
            return REGION_BY_NAME[f"{side}_ankle"].id
        if (center - joints[f"{side}_knee"]).length <= 5.5:
            return REGION_BY_NAME[f"{side}_knee"].id
        if dominant in {f"{side_title}Foot", f"{side_title}ToeBase"}:
            return REGION_BY_NAME[f"{side}_foot"].id
        if dominant == f"{side_title}Leg":
            return REGION_BY_NAME[f"{side}_shin"].id
        return REGION_BY_NAME[f"{side}_thigh"].id

    front = depth >= 0.0
    if height < 99.0:
        return REGION_BY_NAME["pelvis_front" if front else "pelvis_back"].id
    if height < 115.0:
        return REGION_BY_NAME["abdomen_front" if front else "lower_back"].id
    return REGION_BY_NAME["chest_front" if front else "upper_back"].id


def _load_overrides(path: Path | None, topology: str, face_count: int) -> dict[int, int]:
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported semantic override schema")
    if data.get("topology_sha256") != topology:
        raise ValueError("Semantic overrides do not match the source topology")
    raw_regions = data.get("regions", {})
    if not isinstance(raw_regions, dict):
        raise ValueError("Semantic override regions must be an object")
    result: dict[int, int] = {}
    for name, runs in raw_regions.items():
        if name not in REGION_BY_NAME:
            raise ValueError(f"Unknown override region {name!r}")
        for face_index in decode_index_runs(runs, limit=face_count):
            if face_index in result:
                raise ValueError(f"Face {face_index} appears in multiple semantic overrides")
            result[face_index] = REGION_BY_NAME[name].id
    return result


def _assign_regions(
    mesh_obj: bpy.types.Object,
    armature: bpy.types.Object,
    overrides: Path | None,
    topology: str,
) -> tuple[list[int], dict[str, int]]:
    mesh = mesh_obj.data
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
    assignments: list[int] = []
    for polygon, group in zip(mesh.polygons, dominant, strict=True):
        center = sum((mesh.vertices[index].co for index in polygon.vertices), Vector())
        center /= len(polygon.vertices)
        assignments.append(_region_for_face(center, group, joints))
    for face_index, region_id in _load_overrides(overrides, topology, len(mesh.polygons)).items():
        assignments[face_index] = region_id
    counts = Counter(assignments)
    missing = [region.name for region in REGIONS if counts[region.id] == 0]
    if missing:
        raise RuntimeError(f"Semantic assignment left empty regions: {missing}")
    return assignments, {region.name: counts[region.id] for region in REGIONS}


def _replace_attribute(mesh: bpy.types.Mesh, name: str, data_type: str, domain: str):
    existing = mesh.attributes.get(name)
    if existing is not None:
        mesh.attributes.remove(existing)
    return mesh.attributes.new(name=name, type=data_type, domain=domain)


def _write_attributes(mesh: bpy.types.Mesh, assignments: list[int]) -> None:
    region_attribute = _replace_attribute(mesh, "pf_region_id", "INT", "FACE")
    region_attribute.data.foreach_set("value", assignments)

    existing_color = mesh.color_attributes.get("pf_region_color")
    if existing_color is not None:
        mesh.color_attributes.remove(existing_color)
    color_attribute = mesh.color_attributes.new(
        name="pf_region_color", type="BYTE_COLOR", domain="CORNER"
    )
    for polygon, region_id in zip(mesh.polygons, assignments, strict=True):
        rgba = tuple(channel / 255.0 for channel in REGION_BY_ID[region_id].color)
        for loop_index in polygon.loop_indices:
            item = color_attribute.data[loop_index]
            if hasattr(item, "color_srgb"):
                item.color_srgb = rgba
            else:
                item.color = rgba

    for slot in CHARACTER_SLOTS:
        surface_ids = region_ids(SLOT_SURFACE_REGIONS[slot])
        hide_ids = region_ids(SLOT_HIDE_REGIONS[slot])
        surface = _replace_attribute(mesh, f"pf_slot_{slot}", "BOOLEAN", "FACE")
        hidden = _replace_attribute(mesh, f"pf_hide_{slot}", "BOOLEAN", "FACE")
        surface.data.foreach_set("value", [region_id in surface_ids for region_id in assignments])
        hidden.data.foreach_set("value", [region_id in hide_ids for region_id in assignments])


def _write_rgba_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    if len(pixels) != width * height * 4:
        raise ValueError("RGBA byte count does not match PNG dimensions")

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    scanlines = b"".join(
        b"\0" + pixels[row * width * 4 : (row + 1) * width * 4]
        for row in range(height)
    )
    payload = b"\x89PNG\r\n\x1a\n"
    payload += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    payload += chunk(b"IDAT", zlib.compress(scanlines, level=9))
    payload += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _create_debug_texture(mesh: bpy.types.Mesh, path: Path) -> dict[str, Any]:
    columns, rows, cell = 8, 4, 32
    width, height = columns * cell, rows * cell
    pixels = bytearray(width * height * 4)
    for region in REGIONS:
        index = region.id - 1
        column, row = index % columns, index // columns
        for y in range(row * cell, (row + 1) * cell):
            for x in range(column * cell, (column + 1) * cell):
                offset = (y * width + x) * 4
                pixels[offset : offset + 4] = bytes(region.color)
    _write_rgba_png(path, width, height, bytes(pixels))

    existing = mesh.uv_layers.get("PF_SemanticUV")
    if existing is not None:
        mesh.uv_layers.remove(existing)
    uv_layer = mesh.uv_layers.new(name="PF_SemanticUV")
    region_attribute = mesh.attributes["pf_region_id"]
    for polygon in mesh.polygons:
        index = int(region_attribute.data[polygon.index].value) - 1
        column, row = index % columns, index // columns
        uv = ((column + 0.5) / columns, 1.0 - (row + 0.5) / rows)
        for loop_index in polygon.loop_indices:
            uv_layer.data[loop_index].uv = uv
    return {
        "file": path.name,
        "sha256": sha256_path(path),
        "dimensions": [width, height],
        "grid": [columns, rows],
        "cell_size": cell,
        "uv_layer": "PF_SemanticUV",
        "overlap_policy": "faces_may_overlap_only_when_they_share_a_region_id",
    }


def _create_debug_material() -> bpy.types.Material:
    material = bpy.data.materials.get("PF_Semantic_Debug")
    if material is None:
        material = bpy.data.materials.new("PF_Semantic_Debug")
    material.use_fake_user = True
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (400, 0)
    emission = nodes.new("ShaderNodeEmission")
    emission.location = (120, 0)
    attribute = nodes.new("ShaderNodeVertexColor")
    attribute.layer_name = "pf_region_color"
    attribute.location = (-180, 0)
    links.new(attribute.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _region_centroids(mesh_obj: bpy.types.Object, assignments: list[int]) -> dict[str, Vector]:
    sums = {region.id: Vector() for region in REGIONS}
    counts = Counter()
    mesh = mesh_obj.data
    for polygon, region_id in zip(mesh.polygons, assignments, strict=True):
        center = sum((mesh.vertices[index].co for index in polygon.vertices), Vector())
        center /= len(polygon.vertices)
        sums[region_id] += center
        counts[region_id] += 1
    return {
        region.name: mesh_obj.matrix_world @ (sums[region.id] / counts[region.id])
        for region in REGIONS
    }


def _attachment_region(name: str) -> str:
    aliases = {
        "head_top": "scalp",
        "face_center": "face",
        "neck_base": "neck",
        "waist_front": "pelvis_front",
        "waist_back": "pelvis_back",
        "left_hip": "left_thigh",
        "right_hip": "right_thigh",
    }
    return aliases.get(name, name)


def _create_attachments(
    mesh_obj: bpy.types.Object,
    armature: bpy.types.Object,
    assignments: list[int],
) -> dict[str, dict[str, object]]:
    collection = bpy.data.collections.get("PF_ATTACHMENTS")
    if collection is None:
        collection = bpy.data.collections.new("PF_ATTACHMENTS")
        bpy.context.scene.collection.children.link(collection)
    for obj in list(collection.objects):
        if obj.name.startswith("PF_ATTACH_"):
            bpy.data.objects.remove(obj, do_unlink=True)
    centroids = _region_centroids(mesh_obj, assignments)
    result: dict[str, dict[str, object]] = {}
    for name, bone_name in ATTACHMENT_BONES.items():
        bone = armature.data.bones.get(bone_name)
        if bone is None:
            raise RuntimeError(f"Attachment {name} requires missing bone {bone_name}")
        empty = bpy.data.objects.new(f"PF_ATTACH_{name}", None)
        empty.empty_display_type = "CIRCLE"
        empty.empty_display_size = 0.035
        empty.parent = armature
        empty.parent_type = "BONE"
        empty.parent_bone = bone_name
        collection.objects.link(empty)
        world_matrix = armature.matrix_world @ bone.matrix_local
        world_matrix.translation = centroids[_attachment_region(name)]
        empty.matrix_world = world_matrix
        empty["pf_attachment_id"] = name
        empty["pf_region"] = _attachment_region(name)
        result[name] = {
            "bone": bone_name,
            "region": _attachment_region(name),
            "object": empty.name,
            "rest_matrix": [
                round(float(value), 8)
                for row in empty.matrix_basis
                for value in row
            ],
        }
    return result


def main() -> None:
    args = _args()
    if not args.source.is_file():
        raise FileNotFoundError(args.source)
    for path in (args.output, args.manifest, args.debug_texture):
        if path.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {path}; pass --force")

    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    mesh_obj = _only_object("MESH")
    armature = _only_object("ARMATURE")
    mesh = mesh_obj.data
    topology_before = topology_hash(mesh)
    invariants_before = {
        "topology_sha256": topology_before,
        "weights_sha256": weight_hash(mesh_obj),
        "rest_pose_sha256": rest_pose_hash(armature),
        "production_material_sha256": material_hash(mesh_obj),
        "actions": action_hashes(armature),
    }

    assignments, counts = _assign_regions(
        mesh_obj, armature, args.overrides, topology_before
    )
    _write_attributes(mesh, assignments)
    debug_texture = _create_debug_texture(mesh, args.debug_texture)
    debug_material = _create_debug_material()
    attachments = _create_attachments(mesh_obj, armature, assignments)
    mesh_obj["pf_semantic_schema_version"] = MANNEQUIN_SCHEMA_VERSION
    mesh_obj["pf_region_count"] = len(REGIONS)
    mesh_obj["pf_debug_material"] = debug_material.name

    invariants_after = {
        "topology_sha256": topology_hash(mesh),
        "weights_sha256": weight_hash(mesh_obj),
        "rest_pose_sha256": rest_pose_hash(armature),
        "production_material_sha256": material_hash(mesh_obj),
        "actions": action_hashes(armature),
    }
    if invariants_after != invariants_before:
        raise RuntimeError("Semantic build changed protected topology, weights, rig, material, or actions")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()), check_existing=False)
    manifest = {
        "schema_version": MANNEQUIN_SCHEMA_VERSION,
        "mannequin_id": "elf-bald-female-v1",
        "blender_version": bpy.app.version_string,
        "source_blend": args.source.name,
        "source_blend_sha256": sha256_path(args.source),
        "canonical_blend": args.output.name,
        "canonical_blend_sha256": sha256_path(args.output),
        "mesh": mesh_obj.name,
        "armature": armature.name,
        "face_count": len(mesh.polygons),
        "vertex_count": len(mesh.vertices),
        "protected_invariants": invariants_after,
        "regions": [
            {
                "id": region.id,
                "name": region.name,
                "side": region.side,
                "color": list(region.color),
                "face_count": counts[region.name],
            }
            for region in REGIONS
        ],
        "slots": {
            slot: {
                "surface_regions": list(SLOT_SURFACE_REGIONS[slot]),
                "default_hide_regions": list(SLOT_HIDE_REGIONS[slot]),
                "surface_attribute": f"pf_slot_{slot}",
                "hide_attribute": f"pf_hide_{slot}",
                "component_override_policy": "add_remove_region_names",
            }
            for slot in CHARACTER_SLOTS
        },
        "attachments": attachments,
        "debug_texture": debug_texture,
        "debug_material": debug_material.name,
        "overrides": {
            "file": args.overrides.name if args.overrides else None,
            "topology_guard": topology_before,
        },
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.resolve()}")
    print(f"Wrote {args.manifest.resolve()}")
    print("Protected mesh, rig, material, and action invariants are unchanged")


if __name__ == "__main__":
    main()
