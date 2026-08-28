"""Headless structural validation for a Pixel Forge semantic mannequin."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.mannequin_semantics import (  # noqa: E402
    ATTACHMENT_BONES,
    CHARACTER_SLOTS,
    REGIONS,
    SLOT_HIDE_REGIONS,
    SLOT_SURFACE_REGIONS,
    region_ids,
    sha256_path,
    validate_semantic_manifest,
)
from tools.blender.build_semantic_mannequin import (  # noqa: E402
    action_hashes,
    material_hash,
    rest_pose_hash,
    topology_hash,
    weight_hash,
)


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    return parser.parse_args(argv)


def _attribute_values(attribute) -> list[int | bool]:
    return [item.value for item in attribute.data]


def main() -> None:
    args = _args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate_semantic_manifest(manifest)
    if sha256_path(args.blend) != manifest["canonical_blend_sha256"]:
        raise RuntimeError("Canonical blend hash differs from its semantic manifest")
    debug_path = args.manifest.parent / manifest["debug_texture"]["file"]
    if sha256_path(debug_path) != manifest["debug_texture"]["sha256"]:
        raise RuntimeError("Semantic debug texture hash differs from its manifest")

    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    mesh_obj = bpy.data.objects.get(manifest["mesh"])
    armature = bpy.data.objects.get(manifest["armature"])
    if mesh_obj is None or mesh_obj.type != "MESH":
        raise RuntimeError("Canonical mannequin mesh is missing")
    if armature is None or armature.type != "ARMATURE":
        raise RuntimeError("Canonical mannequin armature is missing")
    mesh = mesh_obj.data
    if len(mesh.polygons) != manifest["face_count"] or len(mesh.vertices) != manifest["vertex_count"]:
        raise RuntimeError("Canonical mannequin geometry counts differ from the manifest")

    region_attribute = mesh.attributes.get("pf_region_id")
    if region_attribute is None or region_attribute.domain != "FACE" or region_attribute.data_type != "INT":
        raise RuntimeError("pf_region_id must be a face-domain integer attribute")
    assignments = [int(value) for value in _attribute_values(region_attribute)]
    expected_ids = {region.id for region in REGIONS}
    if set(assignments) != expected_ids:
        raise RuntimeError("Canonical mannequin does not populate all 32 region IDs")
    actual_counts = {region.id: assignments.count(region.id) for region in REGIONS}
    declared_counts = {int(row["id"]): int(row["face_count"]) for row in manifest["regions"]}
    if actual_counts != declared_counts:
        raise RuntimeError("Semantic face counts differ from the manifest")

    color = mesh.color_attributes.get("pf_region_color")
    if color is None or color.domain != "CORNER" or color.data_type != "BYTE_COLOR":
        raise RuntimeError("pf_region_color must be a corner-domain byte-color attribute")
    for slot in CHARACTER_SLOTS:
        surface = mesh.attributes.get(f"pf_slot_{slot}")
        hidden = mesh.attributes.get(f"pf_hide_{slot}")
        if surface is None or hidden is None:
            raise RuntimeError(f"Missing semantic attributes for slot {slot}")
        expected_surface = region_ids(SLOT_SURFACE_REGIONS[slot])
        expected_hidden = region_ids(SLOT_HIDE_REGIONS[slot])
        if _attribute_values(surface) != [value in expected_surface for value in assignments]:
            raise RuntimeError(f"Surface grouping is incorrect for slot {slot}")
        if _attribute_values(hidden) != [value in expected_hidden for value in assignments]:
            raise RuntimeError(f"Body-hide grouping is incorrect for slot {slot}")

    semantic_uv = mesh.uv_layers.get("PF_SemanticUV")
    if semantic_uv is None:
        raise RuntimeError("PF_SemanticUV is missing")
    uv_to_region: dict[tuple[float, float], int] = {}
    for polygon, region_id in zip(mesh.polygons, assignments, strict=True):
        points = {
            tuple(round(float(value), 6) for value in semantic_uv.data[index].uv)
            for index in polygon.loop_indices
        }
        if len(points) != 1:
            raise RuntimeError(f"Semantic face {polygon.index} spans multiple palette cells")
        point = points.pop()
        previous = uv_to_region.setdefault(point, region_id)
        if previous != region_id:
            raise RuntimeError("Different region IDs overlap in PF_SemanticUV")

    for name, bone_name in ATTACHMENT_BONES.items():
        obj = bpy.data.objects.get(f"PF_ATTACH_{name}")
        if obj is None or obj.parent != armature or obj.parent_type != "BONE":
            raise RuntimeError(f"Attachment {name} is missing or is not bone-parented")
        if obj.parent_bone != bone_name:
            raise RuntimeError(f"Attachment {name} is parented to {obj.parent_bone}, expected {bone_name}")
        if not all(math.isfinite(float(value)) for row in obj.matrix_basis for value in row):
            raise RuntimeError(f"Attachment {name} has a non-finite rest transform")

    invariants = {
        "topology_sha256": topology_hash(mesh),
        "weights_sha256": weight_hash(mesh_obj),
        "rest_pose_sha256": rest_pose_hash(armature),
        "production_material_sha256": material_hash(mesh_obj),
        "actions": action_hashes(armature),
    }
    if invariants != manifest["protected_invariants"]:
        raise RuntimeError("Protected mannequin invariants differ from the semantic manifest")
    if bpy.data.materials.get("PF_Semantic_Debug") is None:
        raise RuntimeError("PF_Semantic_Debug material is missing")
    if not mesh.materials or mesh.materials[0].name != "PF_Elf_Bald_Female_Material":
        raise RuntimeError("The production PBR material is no longer the active mesh material")
    if bpy.data.actions.get("PF_Run_ForwardLean_HeadDown") is None:
        raise RuntimeError("The approved corrected Run action is missing")
    print(
        f"Validated {len(mesh.polygons)} faces, {len(REGIONS)} regions, "
        f"{len(CHARACTER_SLOTS)} slots, and {len(ATTACHMENT_BONES)} attachments"
    )


if __name__ == "__main__":
    main()
