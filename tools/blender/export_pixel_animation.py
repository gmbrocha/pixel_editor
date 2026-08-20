"""Experimental Blender-to-Pixel-Forge animation package exporter.

Run with Blender, not ordinary Python:

    blender --background --python tools/blender/export_pixel_animation.py -- \
        --input character-run.fbx --output exports/pilot-run \
        --name pilot-human --animation run --frames 8

The script intentionally supports one humanoid/action first. It has not been
verified against a real FBX in this repository yet; package output must pass
``tools/validate_3d_animation_package.py`` before import.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

PACKAGE_KIND = "pixel-forge-3d-animation"
PACKAGE_SCHEMA_VERSION = 1

# High-separation ID colors. These are data labels, never art colors.
REGION_COLORS: dict[str, tuple[int, int, int, int]] = {
    "background": (0, 0, 0, 0),
    "head": (255, 32, 32, 255),
    "neck": (255, 160, 32, 255),
    "torso": (255, 255, 32, 255),
    "pelvis": (128, 255, 32, 255),
    "upper_arm_left": (32, 255, 32, 255),
    "lower_arm_left": (32, 255, 160, 255),
    "hand_left": (32, 255, 255, 255),
    "upper_arm_right": (32, 128, 255, 255),
    "lower_arm_right": (32, 32, 255, 255),
    "hand_right": (160, 32, 255, 255),
    "thigh_left": (255, 32, 255, 255),
    "shin_left": (255, 32, 128, 255),
    "foot_left": (192, 96, 64, 255),
    "thigh_right": (128, 96, 64, 255),
    "shin_right": (96, 160, 192, 255),
    "foot_right": (192, 192, 192, 255),
}

DIRECTION_CAMERA_POSITIONS = {
    "front": (0.0, -1.0, 0.0),
    "back": (0.0, 1.0, 0.0),
    # With normalized model-forward = -Y, the -X view projects -Y to screen-right.
    "right": (-1.0, 0.0, 0.0),
    "left": (1.0, 0.0, 0.0),
}

ANCHOR_BONE_HINTS: dict[str, tuple[str, ...]] = {
    "head": ("head",),
    "neck": ("neck",),
    "shoulder_left": ("leftshoulder", "shoulder_l", "clavicle_l"),
    "shoulder_right": ("rightshoulder", "shoulder_r", "clavicle_r"),
    "elbow_left": ("leftforearm", "lowerarm_l", "forearm_l"),
    "elbow_right": ("rightforearm", "lowerarm_r", "forearm_r"),
    "hand_left": ("lefthand", "hand_l", "wrist_l"),
    "hand_right": ("righthand", "hand_r", "wrist_r"),
    "hip_center": ("hips", "pelvis", "root"),
    "knee_left": ("leftleg", "calf_l", "shin_l"),
    "knee_right": ("rightleg", "calf_r", "shin_r"),
    "foot_left": ("leftfoot", "foot_l", "ankle_l"),
    "foot_right": ("rightfoot", "foot_r", "ankle_r"),
    "weapon_grip_left": ("lefthand", "hand_l", "wrist_l"),
    "weapon_grip_right": ("righthand", "hand_r", "wrist_r"),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export one rigged FBX action as a Pixel Forge 3D animation package."
    )
    parser.add_argument("--input", required=True, type=Path, help="Rigged FBX input")
    parser.add_argument("--output", required=True, type=Path, help="Package directory")
    parser.add_argument("--name", required=True, help="Stable model/base-family name")
    parser.add_argument("--animation", required=True, help="Animation ID, such as run")
    parser.add_argument("--action", help="Blender action name; defaults to active/first")
    parser.add_argument("--frames", type=int, default=8, help="Phases per direction")
    parser.add_argument("--frame-size", type=int, default=64, help="Square output pixels")
    parser.add_argument("--fps", type=int, default=8, help="Pixel animation playback FPS")
    parser.add_argument(
        "--forward-axis",
        choices=("-Y", "Y", "X", "-X"),
        default="-Y",
        help="The model's forward axis before normalization",
    )
    parser.add_argument(
        "--normalized-height",
        type=float,
        default=2.0,
        help="Normalized Blender-unit character height",
    )
    parser.add_argument(
        "--camera-margin",
        type=float,
        default=1.18,
        help="Orthographic scale multiplier around normalized height",
    )
    parser.add_argument(
        "--visible-color",
        choices=("MATERIAL", "TEXTURE", "OBJECT"),
        default="MATERIAL",
        help="Workbench visible-pass color source",
    )
    return parser


def _script_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]


def _safe_identifier(value: str, field: str) -> str:
    normalized = value.strip().casefold().replace(" ", "-")
    if not normalized or not normalized[0].isalpha() or any(
        not (char.isalnum() or char in "_-") for char in normalized
    ):
        raise ValueError(f"{field} must be a lowercase-compatible identifier")
    return normalized


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _set_if_present(owner: Any, name: str, value: Any) -> None:
    if hasattr(owner, name):
        setattr(owner, name, value)


def _clear_scene(bpy: Any) -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.armatures,
        bpy.data.cameras,
        bpy.data.materials,
    ):
        for item in list(collection):
            if item.users == 0:
                collection.remove(item)


def _import_fbx(bpy: Any, path: Path) -> list[Any]:
    if not path.is_file():
        raise RuntimeError(f"FBX does not exist: {path}")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(path.resolve()))
    imported = [obj for obj in bpy.data.objects if obj not in before]
    if not imported:
        raise RuntimeError("FBX import created no Blender objects")
    return imported


def _find_armature(imported: list[Any]) -> Any:
    armatures = [obj for obj in imported if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(
            f"Pilot exporter requires exactly one armature; found {len(armatures)}"
        )
    return armatures[0]


def _find_meshes(imported: list[Any]) -> list[Any]:
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("FBX contains no mesh objects")
    return meshes


def _choose_action(bpy: Any, armature: Any, requested: str | None) -> Any:
    if requested:
        action = bpy.data.actions.get(requested)
        if action is None:
            raise RuntimeError(f"Blender action not found: {requested}")
    else:
        action = (
            armature.animation_data.action
            if armature.animation_data and armature.animation_data.action
            else (bpy.data.actions[0] if bpy.data.actions else None)
        )
    if action is None:
        raise RuntimeError("FBX contains no discoverable animation action")
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    return action


def _parent_import_to_root(bpy: Any, imported: list[Any]) -> Any:
    root = bpy.data.objects.new("PF_Normalized_Root", None)
    bpy.context.scene.collection.objects.link(root)
    imported_set = set(imported)
    for obj in imported:
        if obj.parent not in imported_set:
            world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = world
    return root


def _forward_rotation(axis: str) -> float:
    return {"-Y": 0.0, "Y": math.pi, "X": -math.pi / 2, "-X": math.pi / 2}[axis]


def _evaluated_bounds(bpy: Any, meshes: list[Any]) -> tuple[float, float, float, float, float, float]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    for source in meshes:
        evaluated = source.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            points.extend(evaluated.matrix_world @ vertex.co for vertex in mesh.vertices)
        finally:
            evaluated.to_mesh_clear()
    if not points:
        raise RuntimeError("Could not calculate character bounds")
    return (
        min(point.x for point in points),
        max(point.x for point in points),
        min(point.y for point in points),
        max(point.y for point in points),
        min(point.z for point in points),
        max(point.z for point in points),
    )


def _normalize_character(
    bpy: Any,
    root: Any,
    meshes: list[Any],
    forward_axis: str,
    normalized_height: float,
) -> None:
    if normalized_height <= 0:
        raise RuntimeError("Normalized height must be positive")
    root.rotation_euler.z = _forward_rotation(forward_axis)
    bpy.context.view_layer.update()
    left, right, rear, front, bottom, top = _evaluated_bounds(bpy, meshes)
    height = top - bottom
    if height <= 1e-6:
        raise RuntimeError("Character bounds have no usable height")
    scale = normalized_height / height
    root.scale = (scale, scale, scale)
    root.location = (
        -((left + right) / 2) * scale,
        -((rear + front) / 2) * scale,
        -bottom * scale,
    )
    bpy.context.view_layer.update()


def _look_at(camera: Any, target: Any) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def _make_cameras(bpy: Any, height: float, margin: float) -> dict[str, Any]:
    from mathutils import Vector

    if margin <= 1.0:
        raise RuntimeError("Camera margin must be greater than 1")
    cameras: dict[str, Any] = {}
    distance = height * 4
    target = Vector((0.0, 0.0, height / 2))
    for direction, unit in DIRECTION_CAMERA_POSITIONS.items():
        data = bpy.data.cameras.new(f"PF_{direction.title()}_Camera")
        data.type = "ORTHO"
        data.ortho_scale = height * margin
        camera = bpy.data.objects.new(data.name, data)
        camera.location = (
            unit[0] * distance,
            unit[1] * distance,
            height / 2,
        )
        _look_at(camera, target)
        bpy.context.scene.collection.objects.link(camera)
        cameras[direction] = camera
    return cameras


def _configure_render(bpy: Any, frame_size: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = frame_size
    scene.render.resolution_y = frame_size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = True
    _set_if_present(scene.display, "render_aa", "OFF")
    shading = scene.display.shading
    shading.light = "FLAT"
    _set_if_present(shading, "show_shadows", False)
    _set_if_present(shading, "show_cavity", False)
    _set_if_present(shading, "show_specular_highlight", False)
    _set_if_present(shading, "show_outline", False)
    scene.view_settings.view_transform = "Standard"
    _set_if_present(scene.view_settings, "look", "None")
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1


def _sample_frames(action: Any, count: int) -> list[float]:
    if count < 1 or count > 1024:
        raise RuntimeError("Frame count must be between 1 and 1024")
    start, end = (float(value) for value in action.frame_range)
    span = end - start
    if span <= 0:
        return [start for _ in range(count)]
    # Exclude the duplicated loop endpoint.
    return [start + span * index / count for index in range(count)]


def _set_subframe(scene: Any, value: float) -> None:
    base = math.floor(value)
    scene.frame_set(base, subframe=value - base)


def _render(bpy: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path.resolve())
    bpy.ops.render.render(write_still=True)
    if not path.is_file():
        raise RuntimeError(f"Blender did not create expected render: {path}")


def _compact_bone_name(name: str) -> str:
    return "".join(char for char in name.casefold() if char.isalnum() or char == "_")


def _side_from_name(name: str) -> str | None:
    compact = _compact_bone_name(name)
    if any(token in compact for token in ("left", "_l", ".l")) or compact.endswith("l"):
        return "left"
    if any(token in compact for token in ("right", "_r", ".r")) or compact.endswith("r"):
        return "right"
    return None


def _semantic_for_bone(name: str) -> str:
    compact = _compact_bone_name(name)
    side = _side_from_name(name)
    if "head" in compact:
        return "head"
    if "neck" in compact:
        return "neck"
    if any(token in compact for token in ("hand", "wrist", "finger", "thumb")) and side:
        return f"hand_{side}"
    if any(token in compact for token in ("forearm", "lowerarm")) and side:
        return f"lower_arm_{side}"
    if any(token in compact for token in ("upperarm", "shoulder", "clavicle", "arm")) and side:
        return f"upper_arm_{side}"
    if any(token in compact for token in ("foot", "ankle", "toe")) and side:
        return f"foot_{side}"
    is_plain_leg = (
        compact.endswith("leftleg") or compact.endswith("rightleg")
    ) and "upleg" not in compact and "upperleg" not in compact
    if (
        any(token in compact for token in ("calf", "shin", "lowerleg"))
        or is_plain_leg
    ) and side:
        return f"shin_{side}"
    if any(token in compact for token in ("upleg", "upperleg", "thigh", "leg")) and side:
        return f"thigh_{side}"
    if any(token in compact for token in ("hip", "pelvis", "root")):
        return "pelvis"
    return "torso"


def _dominant_polygon_region(mesh_object: Any, polygon: Any) -> str:
    totals: dict[str, float] = {}
    for vertex_index in polygon.vertices:
        vertex = mesh_object.data.vertices[vertex_index]
        for membership in vertex.groups:
            if membership.group >= len(mesh_object.vertex_groups):
                continue
            bone_name = mesh_object.vertex_groups[membership.group].name
            semantic = _semantic_for_bone(bone_name)
            totals[semantic] = totals.get(semantic, 0.0) + float(membership.weight)
    return max(totals, key=totals.get) if totals else "torso"


def _material(bpy: Any, name: str, color: tuple[int, int, int, int]) -> Any:
    material = bpy.data.materials.new(name)
    material.diffuse_color = tuple(channel / 255 for channel in color)
    return material


def _assign_region_materials(bpy: Any, meshes: list[Any]) -> None:
    materials = {
        region: _material(bpy, f"PF_REGION_{region}", color)
        for region, color in REGION_COLORS.items()
        if region != "background"
    }
    for mesh in meshes:
        mesh.data.materials.clear()
        indexes: dict[str, int] = {}
        for region, material in materials.items():
            indexes[region] = len(mesh.data.materials)
            mesh.data.materials.append(material)
        for polygon in mesh.data.polygons:
            polygon.material_index = indexes[_dominant_polygon_region(mesh, polygon)]


def _assign_silhouette_material(bpy: Any, meshes: list[Any]) -> None:
    material = _material(bpy, "PF_SILHOUETTE", (255, 255, 255, 255))
    for mesh in meshes:
        mesh.data.materials.clear()
        mesh.data.materials.append(material)
        for polygon in mesh.data.polygons:
            polygon.material_index = 0


def _find_pose_bone(armature: Any, hints: tuple[str, ...]) -> Any | None:
    compact_hints = tuple(_compact_bone_name(hint) for hint in hints)
    exact = {
        _compact_bone_name(bone.name): bone for bone in armature.pose.bones
    }
    for hint in compact_hints:
        if hint in exact:
            return exact[hint]
    for hint in compact_hints:
        for compact, bone in exact.items():
            if hint in compact:
                return bone
    return None


def _anchor_world_position(armature: Any, anchor_name: str, bone: Any) -> Any:
    # Head/neck anchors benefit from the bone tip; limb anchors use the joint head.
    point = bone.tail if anchor_name in {"head", "neck"} else bone.head
    return armature.matrix_world @ point


def _project_anchors(
    bpy: Any, armature: Any, camera: Any, frame_size: int
) -> dict[str, list[float]]:
    from bpy_extras.object_utils import world_to_camera_view

    result: dict[str, list[float]] = {}
    scene = bpy.context.scene
    for anchor_name, hints in ANCHOR_BONE_HINTS.items():
        bone = _find_pose_bone(armature, hints)
        if bone is None:
            continue
        world = _anchor_world_position(armature, anchor_name, bone)
        normalized = world_to_camera_view(scene, camera, world)
        result[anchor_name] = [
            round(float(normalized.x * frame_size), 6),
            round(float((1.0 - normalized.y) * frame_size), 6),
        ]
    return result


def _render_pass_set(
    bpy: Any,
    output: Path,
    cameras: dict[str, Any],
    sample_times: list[float],
    pass_name: str,
) -> None:
    scene = bpy.context.scene
    for direction, camera in cameras.items():
        scene.camera = camera
        for index, source_frame in enumerate(sample_times):
            _set_subframe(scene, source_frame)
            _render(bpy, output / pass_name / direction / f"{index:03d}.png")


def _write_anchor_set(
    bpy: Any,
    output: Path,
    armature: Any,
    cameras: dict[str, Any],
    sample_times: list[float],
    frame_size: int,
) -> None:
    scene = bpy.context.scene
    for direction, camera in cameras.items():
        scene.camera = camera
        for index, source_frame in enumerate(sample_times):
            _set_subframe(scene, source_frame)
            anchors = _project_anchors(bpy, armature, camera, frame_size)
            path = output / "anchors" / direction / f"{index:03d}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"anchors": anchors}, indent=2) + "\n", encoding="utf-8"
            )


def _manifest(
    args: argparse.Namespace,
    input_path: Path,
    output: Path,
    action: Any,
    sample_times: list[float],
) -> dict[str, Any]:
    start, end = (float(value) for value in action.frame_range)
    span = end - start
    directions = []
    checksums: dict[str, str] = {}
    for direction in DIRECTION_CAMERA_POSITIONS:
        frames = []
        for index, source_frame in enumerate(sample_times):
            relatives = {
                "visible": f"visible/{direction}/{index:03d}.png",
                "regions": f"regions/{direction}/{index:03d}.png",
                "silhouette": f"silhouettes/{direction}/{index:03d}.png",
                "anchors": f"anchors/{direction}/{index:03d}.json",
            }
            for relative in relatives.values():
                checksums[relative] = _sha256(output / relative)
            frames.append(
                {
                    "index": index,
                    "sourceTime": 0.0 if span <= 0 else (source_frame - start) / span,
                    **relatives,
                }
            )
        directions.append(
            {"id": direction, "name": direction.title(), "frames": frames}
        )
    return {
        "kind": PACKAGE_KIND,
        "schemaVersion": PACKAGE_SCHEMA_VERSION,
        "name": _safe_identifier(args.name, "name"),
        "animation": _safe_identifier(args.animation, "animation"),
        "frameSize": [args.frame_size, args.frame_size],
        "fps": args.fps,
        "playbackMode": "loop",
        "source": {
            "file": input_path.name,
            "sha256": _sha256(input_path),
            "action": action.name,
            "actionFrameRange": [start, end],
            "forwardAxis": args.forward_axis,
        },
        "regions": {name: list(color) for name, color in REGION_COLORS.items()},
        "directions": directions,
        "checksums": checksums,
    }


def export(args: argparse.Namespace) -> Path:
    try:
        import bpy
    except ImportError as exc:
        raise RuntimeError(
            "This exporter must run through Blender's Python interpreter."
        ) from exc

    input_path = args.input.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(
            f"Output directory must be absent or empty to prevent stale frames: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)
    if args.frame_size < 8 or args.frame_size > 4096:
        raise RuntimeError("Frame size must be between 8 and 4096")
    if args.fps < 1 or args.fps > 60:
        raise RuntimeError("FPS must be between 1 and 60")

    _clear_scene(bpy)
    imported = _import_fbx(bpy, input_path)
    armature = _find_armature(imported)
    meshes = _find_meshes(imported)
    action = _choose_action(bpy, armature, args.action)
    sample_times = _sample_frames(action, args.frames)
    _set_subframe(bpy.context.scene, sample_times[0])
    root = _parent_import_to_root(bpy, imported)
    _normalize_character(
        bpy,
        root,
        meshes,
        args.forward_axis,
        args.normalized_height,
    )
    cameras = _make_cameras(bpy, args.normalized_height, args.camera_margin)
    _configure_render(bpy, args.frame_size)

    bpy.context.scene.display.shading.color_type = args.visible_color
    _render_pass_set(bpy, output, cameras, sample_times, "visible")
    _write_anchor_set(
        bpy, output, armature, cameras, sample_times, args.frame_size
    )

    _assign_region_materials(bpy, meshes)
    bpy.context.scene.display.shading.color_type = "MATERIAL"
    _render_pass_set(bpy, output, cameras, sample_times, "regions")

    _assign_silhouette_material(bpy, meshes)
    _render_pass_set(bpy, output, cameras, sample_times, "silhouettes")

    manifest = _manifest(args, input_path, output, action, sample_times)
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(_script_arguments() if argv is None else argv)
    try:
        manifest = export(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1
    print(f"Exported Pixel Forge 3D animation package: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
