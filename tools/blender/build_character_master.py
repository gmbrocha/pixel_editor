"""Build a self-contained Pixel Forge Blender master from Meshy FBX exports."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import bpy


def _args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", required=True, type=Path)
    parser.add_argument("--walk", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--texture-dir", required=True, type=Path)
    parser.add_argument("--character-id", default="elf_bald_female")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _import_fbx(path: Path) -> tuple[list[bpy.types.Object], list[bpy.types.Action]]:
    objects_before = set(bpy.data.objects)
    actions_before = set(bpy.data.actions)
    try:
        bpy.ops.import_scene.fbx(filepath=str(path), automatic_bone_orientation=False)
    except AttributeError:
        bpy.ops.wm.fbx_import(filepath=str(path))
    objects = [obj for obj in bpy.data.objects if obj not in objects_before]
    actions = [action for action in bpy.data.actions if action not in actions_before]
    return objects, actions


def _only(objects: list[bpy.types.Object], object_type: str) -> bpy.types.Object:
    matches = [obj for obj in objects if obj.type == object_type]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {object_type}, found {[obj.name for obj in matches]}")
    return matches[0]


def _texture(texture_dir: Path, suffix: str) -> Path:
    matches = sorted(texture_dir.rglob(f"*{suffix}"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one texture matching *{suffix}, found {matches}")
    return matches[0]


def _image_node(
    nodes: bpy.types.Nodes,
    path: Path,
    name: str,
    colorspace: str,
    x: float,
    y: float,
) -> bpy.types.Node:
    image = bpy.data.images.load(str(path.resolve()), check_existing=False)
    image.name = f"PF_{name}"
    image.colorspace_settings.name = colorspace
    node = nodes.new("ShaderNodeTexImage")
    node.name = f"PF_{name}"
    node.label = name
    node.image = image
    node.location = (x, y)
    return node


def _build_material(
    mesh_obj: bpy.types.Object,
    texture_dir: Path,
    material_name: str = "PF_Elf_Bald_Female_Material",
) -> dict[str, str]:
    texture_paths = {
        "base_color": _texture(texture_dir, "texture_0.png"),
        "metallic": _texture(texture_dir, "texture_0_metallic.png"),
        "normal": _texture(texture_dir, "texture_0_normal.png"),
        "roughness": _texture(texture_dir, "texture_0_roughness.png"),
    }
    material = mesh_obj.active_material or bpy.data.materials.new(material_name)
    material.name = material_name
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (700, 0)
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.name = "PF_Principled"
    shader.location = (350, 0)
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    base = _image_node(nodes, texture_paths["base_color"], "BaseColor", "sRGB", -700, 260)
    metallic = _image_node(nodes, texture_paths["metallic"], "Metallic", "Non-Color", -700, 80)
    roughness = _image_node(nodes, texture_paths["roughness"], "Roughness", "Non-Color", -700, -100)
    normal = _image_node(nodes, texture_paths["normal"], "Normal", "Non-Color", -700, -300)
    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.location = (0, -300)
    normal_map.inputs["Strength"].default_value = 1.0

    links.new(base.outputs["Color"], shader.inputs["Base Color"])
    links.new(metallic.outputs["Color"], shader.inputs["Metallic"])
    links.new(roughness.outputs["Color"], shader.inputs["Roughness"])
    links.new(normal.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])

    if len(mesh_obj.data.materials) == 0:
        mesh_obj.data.materials.append(material)
    else:
        mesh_obj.data.materials[0] = material
        while len(mesh_obj.data.materials) > 1:
            mesh_obj.data.materials.pop(index=len(mesh_obj.data.materials) - 1)
    return {name: str(path.resolve()) for name, path in texture_paths.items()}


def _extract_action(
    path: Path,
    target_name: str,
    master_bones: list[str],
) -> bpy.types.Action:
    imported_objects, imported_actions = _import_fbx(path)
    imported_armature = _only(imported_objects, "ARMATURE")
    imported_bones = [bone.name for bone in imported_armature.data.bones]
    if imported_bones != master_bones:
        raise RuntimeError(f"Bone hierarchy mismatch in {path}")
    action = imported_armature.animation_data.action if imported_armature.animation_data else None
    if action is None:
        if len(imported_actions) != 1:
            raise RuntimeError(f"Expected one action in {path}, found {len(imported_actions)}")
        action = imported_actions[0]
    action.name = target_name
    action.use_fake_user = True
    action["pf_source_path"] = str(path.resolve())
    action["pf_source_sha256"] = _sha256(path)
    action["pf_source_fps"] = 30
    for obj in imported_objects:
        bpy.data.objects.remove(obj, do_unlink=True)
    return action


def _move_to_collection(objects: list[bpy.types.Object], collection: bpy.types.Collection) -> None:
    for obj in objects:
        for owner in list(obj.users_collection):
            owner.objects.unlink(obj)
        collection.objects.link(obj)


def _purge_unlinked_data() -> None:
    # Imported animation FBXs carry duplicate skinned meshes and materials. Their
    # actions are retained explicitly, but their now-unlinked data should not be
    # packed into the master blend.
    for collection in (
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.materials,
        bpy.data.images,
    ):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def _action_manifest(action: bpy.types.Action) -> dict[str, Any]:
    return {
        "name": action.name,
        "frame_start": float(action.frame_range[0]),
        "frame_end": float(action.frame_range[1]),
        "source_path": action.get("pf_source_path"),
        "source_sha256": action.get("pf_source_sha256"),
        "source_fps": action.get("pf_source_fps"),
    }


def main() -> None:
    args = _args()
    character_id = args.character_id.strip().lower()
    if not character_id or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
        for character in character_id
    ):
        raise ValueError("character-id must contain only lowercase letters, digits, and underscores")
    title = "_".join(part.capitalize() for part in character_id.split("_"))
    prefix = f"PF_{title}"
    sources = [args.master, args.walk, args.run]
    missing = [path for path in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing FBX source(s): {missing}")
    if not args.texture_dir.is_dir():
        raise FileNotFoundError(f"Missing texture directory: {args.texture_dir}")
    for output in (args.output, args.manifest):
        if output.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {output}; pass --force")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    master_objects, master_import_actions = _import_fbx(args.master)
    master_armature = _only(master_objects, "ARMATURE")
    master_mesh = _only(master_objects, "MESH")
    master_armature.name = f"{prefix}_Rig"
    master_armature.data.name = f"{prefix}_Armature"
    master_mesh.name = prefix
    master_mesh.data.name = f"{prefix}_Mesh"
    master_bones = [bone.name for bone in master_armature.data.bones]

    bind_action = master_armature.animation_data.action if master_armature.animation_data else None
    if bind_action is None and len(master_import_actions) == 1:
        bind_action = master_import_actions[0]
    if bind_action is not None:
        bind_action.name = "PF_BindPose"
        bind_action.use_fake_user = True
        bind_action["pf_source_path"] = str(args.master.resolve())
        bind_action["pf_source_sha256"] = _sha256(args.master)
        bind_action["pf_source_fps"] = 30

    character_collection = bpy.data.collections.new("PF_CHARACTER_MASTER")
    bpy.context.scene.collection.children.link(character_collection)
    _move_to_collection(master_objects, character_collection)

    texture_paths = _build_material(master_mesh, args.texture_dir, f"{prefix}_Material")
    walk_action = _extract_action(args.walk, "PF_Walk", master_bones)
    run_action = _extract_action(args.run, "PF_Run", master_bones)
    _purge_unlinked_data()
    if master_armature.animation_data is None:
        master_armature.animation_data_create()
    master_armature.animation_data.action = walk_action

    scene = bpy.context.scene
    scene.name = f"{prefix}_Master"
    scene.render.fps = 30
    scene.render.fps_base = 1.0
    scene.frame_start = int(walk_action.frame_range[0])
    scene.frame_end = int(walk_action.frame_range[1])
    scene.frame_set(scene.frame_start)
    scene.render.film_transparent = True
    scene["pf_character_id"] = character_id
    scene["pf_master_source"] = str(args.master.resolve())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()), check_existing=False)

    actions = [action for action in (bind_action, walk_action, run_action) if action is not None]
    manifest = {
        "schema_version": 1,
        "blender_version": bpy.app.version_string,
        "character_id": character_id,
        "master_blend": str(args.output.resolve()),
        "master_fbx": {
            "path": str(args.master.resolve()),
            "sha256": _sha256(args.master),
        },
        "mesh": {
            "name": master_mesh.name,
            "vertices": len(master_mesh.data.vertices),
            "polygons": len(master_mesh.data.polygons),
            "uv_layers": [layer.name for layer in master_mesh.data.uv_layers],
        },
        "armature": {
            "name": master_armature.name,
            "bones": master_bones,
        },
        "actions": [_action_manifest(action) for action in actions],
        "textures": {
            name: {"path": path, "sha256": _sha256(Path(path))}
            for name, path in texture_paths.items()
        },
        "fps": 30,
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.resolve()}")
    print(f"Wrote {args.manifest.resolve()}")


if __name__ == "__main__":
    main()
