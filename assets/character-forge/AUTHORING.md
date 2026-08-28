# Character Forge Elf Component Authoring

The approved `elf-01` Idle and Walk bases, semantic regions, per-frame sources, and placement masks are tracked in the repository. They can be pulled to another machine and used as drawing references for components such as hair or an eyepatch.

## Fastest drawing references

| Animation | Ordinary base sheet | Semantic region sheet | Colored region preview |
| --- | --- | --- | --- |
| Idle | [`bases/elf-01/idle.png`](bases/elf-01/idle.png) | [`semantic/elf-01/idle/idle_regions.png`](semantic/elf-01/idle/idle_regions.png) | [`semantic/elf-01/idle/idle_regions_preview.png`](semantic/elf-01/idle/idle_regions_preview.png) |
| Walk | [`bases/elf-01/walk.png`](bases/elf-01/walk.png) | [`semantic/elf-01/walk/walk_regions.png`](semantic/elf-01/walk/walk_regions.png) | [`semantic/elf-01/walk/walk_regions_preview.png`](semantic/elf-01/walk/walk_regions_preview.png) |

Each frame is 128 by 128 pixels. Sheet rows are Front, Back, Right, and Left. Idle has 26 columns at 12 FPS; Walk has 8 columns at 10 FPS. The exact runtime layout is recorded in [`sheet_specs.json`](sheet_specs.json).

## Easier per-frame drawing

If a full sheet is unwieldy, use the matching files below:

- `semantic/elf-01/idle/frames/art/<direction>/` and `frames/regions/<direction>/`
- `semantic/elf-01/walk/frames/art/<direction>/` and `frames/regions/<direction>/`
- `semantic/elf-01/idle/strips/` and `semantic/elf-01/walk/strips/` for one-row direction strips
- `semantic/elf-01/idle/gifs/` and `semantic/elf-01/walk/gifs/` for native-speed motion review

## Component placement guides

The `slots/` folders show where a component may be placed. The `hide/` folders show body pixels that can be hidden beneath equipped geometry. Useful starting slots are:

- Eyepatch or other face detail: `face`
- Hair silhouette: `hair`
- Hat or hood: `headwear`
- Beard or similar facial geometry: `facial_hair`

Every animation package contains one full-sheet mask per slot, for example `semantic/elf-01/walk/slots/walk_slot_face.png` and `semantic/elf-01/idle/slots/idle_slot_hair.png`.

Draw on a separate transparent layer over the ordinary base. The finished component overlay must retain only the new component pixels; do not leave copied body/base pixels in the overlay. Preserve the source sheet dimensions, frame alignment, row order, and transparency. Keep an editable working source separate from the exported overlay.

The five installed starter components under `parts/` provide working manifest and sheet examples across Idle, Walk, and Run.
