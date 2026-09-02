# Pixel Forge

Pixel Forge is a Windows-oriented PySide6 desktop application for pixel-art
work. It includes a pixel editor, animation editor, palette and image-processing
tools, tileset utilities, and **Character Forge**: a modular animated-character
builder assembled from aligned sprite sheets.

The project is an active personal/lab codebase rather than a polished public
package. If you are new to the repository, start with this file and then read
[`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md). That document is the detailed,
current project handoff and records recent decisions.

## Quick start

Python 3.12 is the current development environment. From PowerShell on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

After the environment exists, `launch_pixel_forge.cmd` launches the desktop
application without a console window. The repository also uses Git LFS for
large Blender source files, so install Git LFS before cloning or run
`git lfs pull` if those files appear to be pointers.

Run the test suite with:

```powershell
python -m pytest -q
```

At this handoff the active suite reports 213 passed and 3 skipped tests.

## Explore the rest of the editor

Character Forge is only one part of Pixel Forge. If you want to look around or
experiment elsewhere, the application also includes:

- a layer-based Pixel Editor with selections, drawing and shape tools,
  gesture-level Undo/Redo, and a floating reusable palette;
- Animation Studio for sprite-sheet and animated-GIF import, frame editing,
  onion skinning, per-frame timing, playback, and PNG/GIF/JSON export;
- palette extraction, color reduction, dithering, scaling, denoising,
  despeckling, and deterministic pixel-cluster cleanup tools;
- region extraction and preview workflows for turning source images into
  controlled pixel-art inputs;
- tile layout, tileset processing, and tileset-template generation; and
- procedural texture generation.

Most application behavior is split between `src/core/` and `src/ui/`, with a
focused test module under `tests/` for each mature workflow. Feel free to explore
these areas as well; Character Forge is simply the current priority.

## Character Forge orientation

Character Forge is the main collaboration area. It combines a locked animated
base with independently aligned component layers, previews the result, saves a
recipe, and exports assembled sprites.

Important locations:

- `src/core/character_forge.py` - catalog loading, recipe schema, validation,
  compositing, recoloring, animation extraction, and export.
- `src/ui/character_forge_window.py` - the PySide6 Character Forge window and
  interaction behavior.
- `assets/character-forge/` - live runtime bases, parts, manifests, palettes,
  style-region data, and catalog metadata.
- `tests/test_character_forge.py` - the broadest Forge behavior and UI coverage.
- `animation_images_models/component_cleanup_v2/` - editable Standard Pixel
  component-only sheets and a local README describing their exact layout.
- `tools/promote_component_edit.py` - the normal path for promoting one approved
  manual component edit and refreshing its hashes and live asset.
- `docs/BLENDER_CHARACTER_PIPELINE.md` - deeper model, render, semantic-region,
  camera, and component-generation details.

There are four approved character bases and three sprite styles:

- **Standard Pixel** is the active manual component-editing workflow.
- **JRPG** has generated fitted components at all three camera heights, but some
  hand-authored hair and accessories remain Standard-only.
- **Heroic** retains its authored models, Idle/Walk/Run actions, rendered bases,
  and semantic maps, but is intentionally base-only. Do not resize Standard or
  JRPG components onto Heroic anatomy.

The attempted Recraft component workflow was rejected and moved to
`docs/archive/recraft-pipeline/`. It is an inert historical snapshot, not an
active dependency or roadmap item.

## Sprite and data contracts

These conventions matter because manifests and deterministic checks assume
them:

- Each sprite frame is 128 x 128 pixels with binary transparency.
- Standard editable component sheets use rows in Front, Back, Right, Left
  order. Walk and Run have 8 columns; Idle has 14 runtime columns.
- Component layers must remain aligned to the matching base, motion, camera,
  and style. Preserve transparent canvas pixels and exact sheet dimensions.
- Saved Character Forge recipes currently use schema version 4. Preserve
  backwards-compatible IDs and loading behavior when changing the schema.
- Runtime manifests contain content hashes. Avoid editing generated manifests
  or live component assets by hand; use the promotion/build tool that owns them.
- Registered manual override sources are authoritative. A generated Left row
  may intentionally be mirrored from the complete authored Right composite.

For a normal approved Standard component edit:

```powershell
python tools/promote_component_edit.py `
  --component <component-id> `
  --sequence run
```

The command updates only the affected family/base variant, refreshes cleanup
metadata, and checks the source, override, live sheet, and manifest hashes.
Large all-family rebuilds are checkpoint operations, not the default edit loop.

## Good places to contribute

Useful work includes Character Forge UI and recipe ergonomics, compositing and
layer behavior, focused regression tests, export improvements, and careful
manual cleanup of Standard Pixel components. Known art gaps and current next
actions are maintained in `docs/CURRENT_STATE.md` rather than duplicated here.

Please keep changes scoped and avoid broad asset regeneration unless the change
actually requires it. Preserve unrelated working-tree edits, add focused tests
for behavior changes, and update documentation when a workflow or asset contract
changes. `AGENTS.md` contains additional repository rules for automated coding
agents.
