"""Copy Pixel Forge face-semantic attributes from a topology-identical blend."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-blend", required=True, type=Path)
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def _mesh_object(name: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "MESH":
        raise RuntimeError(f"Current blend has no mesh object {name!r}")
    return obj


def _load_reference(path: Path, name: str) -> bpy.types.Object:
    with bpy.data.libraries.load(str(path.resolve()), link=False) as (
        data_from,
        data_to,
    ):
        if name not in data_from.objects:
            raise RuntimeError(f"Reference blend has no object {name!r}")
        data_to.objects = [name]
    obj = data_to.objects[0]
    if obj is None or obj.type != "MESH":
        raise RuntimeError(f"Reference object {name!r} is not a mesh")
    return obj


def _verify_topology(target: bpy.types.Mesh, reference: bpy.types.Mesh) -> None:
    counts = (
        ("vertices", len(target.vertices), len(reference.vertices)),
        ("edges", len(target.edges), len(reference.edges)),
        ("loops", len(target.loops), len(reference.loops)),
        ("polygons", len(target.polygons), len(reference.polygons)),
    )
    for label, actual, expected in counts:
        if actual != expected:
            raise RuntimeError(
                f"Topology differs at {label}: target {actual}, reference {expected}"
            )
    for target_polygon, reference_polygon in zip(
        target.polygons, reference.polygons, strict=True
    ):
        if tuple(target_polygon.vertices) != tuple(reference_polygon.vertices):
            raise RuntimeError(
                f"Polygon {target_polygon.index} vertex order differs from reference"
            )


def _copy_attribute(
    target_mesh: bpy.types.Mesh, reference_attribute: bpy.types.Attribute
) -> None:
    existing = target_mesh.attributes.get(reference_attribute.name)
    if existing is not None:
        target_mesh.attributes.remove(existing)
    copied = target_mesh.attributes.new(
        name=reference_attribute.name,
        type=reference_attribute.data_type,
        domain=reference_attribute.domain,
    )
    if len(copied.data) != len(reference_attribute.data):
        raise RuntimeError(
            f"Attribute {reference_attribute.name!r} element count differs"
        )
    if reference_attribute.data_type in {"INT", "BOOLEAN", "FLOAT"}:
        values = [item.value for item in reference_attribute.data]
        copied.data.foreach_set("value", values)
    elif reference_attribute.data_type in {"BYTE_COLOR", "FLOAT_COLOR"}:
        values = [channel for item in reference_attribute.data for channel in item.color]
        copied.data.foreach_set("color", values)
    else:
        raise RuntimeError(
            f"Unsupported PF attribute type {reference_attribute.data_type!r}"
        )


def main() -> None:
    args = _args()
    target_obj = _mesh_object(args.mesh)
    reference_obj = _load_reference(args.reference_blend, args.mesh)
    _verify_topology(target_obj.data, reference_obj.data)
    attributes = [
        attribute
        for attribute in reference_obj.data.attributes
        if attribute.name.startswith("pf_")
    ]
    if not attributes or not any(
        attribute.name == "pf_region_id" for attribute in attributes
    ):
        raise RuntimeError("Reference blend has no Pixel Forge semantic attributes")
    for attribute in attributes:
        _copy_attribute(target_obj.data, attribute)
    target_obj["pf_semantic_attribute_source"] = str(
        args.reference_blend.resolve()
    )
    target_obj["pf_semantic_attribute_count"] = len(attributes)
    reference_mesh = reference_obj.data
    bpy.data.objects.remove(reference_obj, do_unlink=True)
    if reference_mesh.users == 0:
        bpy.data.meshes.remove(reference_mesh)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()))
    print(
        f"Copied {len(attributes)} semantic attributes to {args.output.resolve()}"
    )


if __name__ == "__main__":
    main()
