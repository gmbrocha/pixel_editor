# Character Forge Elf Component Authoring

The approved `elf-01` Idle, Walk, and Run bases, semantic regions, per-frame sources, and placement masks are tracked in the repository. They can be pulled to another machine and used as drawing references for components such as hair or an eyepatch.

## Fastest drawing references

| Animation | Ordinary base sheet | Semantic region sheet | Colored region preview |
| --- | --- | --- | --- |
| Idle | [`bases/elf-01/idle.png`](bases/elf-01/idle.png) | [`semantic/elf-01/idle/idle_regions.png`](semantic/elf-01/idle/idle_regions.png) | [`semantic/elf-01/idle/idle_regions_preview.png`](semantic/elf-01/idle/idle_regions_preview.png) |
| Walk | [`bases/elf-01/walk.png`](bases/elf-01/walk.png) | [`semantic/elf-01/walk/walk_regions.png`](semantic/elf-01/walk/walk_regions.png) | [`semantic/elf-01/walk/walk_regions_preview.png`](semantic/elf-01/walk/walk_regions_preview.png) |
| Run | [`bases/elf-01/run.png`](bases/elf-01/run.png) | [`semantic/elf-01/run/run_regions.png`](semantic/elf-01/run/run_regions.png) | [`semantic/elf-01/run/run_regions_preview.png`](semantic/elf-01/run/run_regions_preview.png) |

Each frame is 128 by 128 pixels. Sheet rows are Front, Back, Right, and Left. Idle has 14 runtime columns at 6 FPS; Walk and Run each have 8 columns at 10 FPS. Both Idle weight shifts play consecutively at the normal cadence, and runtime frame 13 alone has a 1500 ms display duration before the loop restarts. The 14 Idle columns select authored Blender frames `1,3,5,7,9,11,13,15,17,19,21,23,24,25`; the 26-frame Blender actions remain intact. The exact runtime layout and per-frame timing are recorded in [`sheet_specs.json`](sheet_specs.json).

Tiefling female, Dwarf male, and muscular Human male are also installed as approved bases under `bases/`. Their Low views have exact 32-region anatomical fitting sheets at `base_regions/<base-id>/<animation>/<animation>_regions.png`. Use the sheet matching the target body; never apply an elf-fit overlay directly to another model.

Character Forge provides Near Top-Down (70 degrees), Three-Quarter (45 degrees),
and Low (28 degrees) base views in both `Standard Pixel` and `JRPG Chibi`. Chibi
base sheets are under `bases/<base-id>/styles/jrpg_chibi/<camera>/`; their exact
fitting regions are under
`style_regions/jrpg_chibi/<base-id>/<camera>/`. The 25 generated families have
fitted chibi variants at all three heights. Existing hand-authored hair, face
accessories, and approved Standard overrides remain Standard-only until a
separate chibi fit is authored; the Forge hides them in chibi recipes rather
than resizing them.

## Easier per-frame drawing

If a full sheet is unwieldy, use the matching files below:

- `semantic/elf-01/idle/frames/art/<direction>/` and `frames/regions/<direction>/`
- `semantic/elf-01/walk/frames/art/<direction>/` and `frames/regions/<direction>/`
- `semantic/elf-01/run/frames/art/<direction>/` and `frames/regions/<direction>/`
- `semantic/elf-01/idle/strips/` and `semantic/elf-01/walk/strips/` for one-row direction strips
- `semantic/elf-01/run/strips/` for Run direction strips
- `semantic/elf-01/idle/gifs/`, `semantic/elf-01/walk/gifs/`, and `semantic/elf-01/run/gifs/` for native-speed motion review

## Component placement guides

The `slots/` folders show where a component may be placed. The `hide/` folders show body pixels that can be hidden beneath equipped geometry. Useful starting slots are:

- Eyepatch or other face detail: `face`
- Hair silhouette: `hair`
- Hat or hood: `headwear`
- Beard or similar facial geometry: `facial_hair`

Every animation package contains one full-sheet mask per slot, for example `semantic/elf-01/walk/slots/walk_slot_face.png` and `semantic/elf-01/idle/slots/idle_slot_hair.png`.

Draw on a separate transparent layer over the ordinary base. The finished component overlay must retain only the new component pixels; do not leave copied body/base pixels in the overlay. Preserve the source sheet dimensions, frame alignment, row order, and transparency. Keep an editable working source separate from the exported overlay.

## Two-layer hair and occlusion

Long hair may declare two aligned render sheets in one component manifest:
`hair_back`, drawn behind the body and clothing, and `hair_front`, drawn above
the body, clothing, and under-hair face accessories. Both sheets use the same
dimensions, frames, rows, palette, and camera coverage. Put every pixel in the
layer that gives the intended arm/body overlap; the Forge does not guess or
simulate strand collisions. A layer may be completely transparent.

The approved Tiefling Low Run hair is the reference implementation at
`parts/hair/tiefling-long-hair-run-front-prototype/`. Its approved third edit is
currently all in `hair_front`, with transparent `hair_back`. The source Front,
Back, and Right rows are authoritative. Its Left row is generated from Right,
and `directionMirrors.run.left = "right"` tells the Forge to mirror the final
composite—not merely the hair overlay—so body, clothing, and hair remain aligned.
This is the supported right-only authoring shortcut for directional components.
Its complete five-color source palette is the declared `colorRamp`, so Main
Color remaps every visible shade together. Idle, Walk, and elevated cameras
remain intentionally incomplete.

Face accessories that must sit beneath hair, such as a blindfold crossed by
bangs, use `face_accessory_under_hair`. Ordinary `face_accessory` remains above
hair. Headwear declares `hairOcclusion`:

- `show`: leave all selected hair visible, used by the cloth headband.
- `clip`: remove hair pixels beneath the headwear's combined visible alpha,
  used by the travel cap and padded coif.
- `hide`: suppress the selected hair entirely, used by the guard helm.

Existing single-layer manifests remain valid. A multi-layer manifest retains
its primary `layer` and `animations` for compatibility, then adds aligned
`renderLayers` entries for `hair_back` and `hair_front`.

The live reference for an under-hair face accessory is
`parts/face/tiefling-blindfold-run/`. Its exact four-direction Low Run source is
`animation_images_models/component_cleanup_v2/new_hand_authored/teifling_blindfold_run.png`.
The blindfold does not need a custom hair mask: normal alpha compositing places
`hair_front` above it, leaving only the correctly exposed blindfold pixels.

The five original elf starters and the 25 four-base fitted families under
`parts/` provide working manifest and sheet examples across Idle, Walk, and Run.
Generated family IDs end with their fit, such as
`sleeveless-travel-tunic-tiefling-female-01`; each manifest records its shared
`familyId`, source regions, style, palette, one-pixel outline, and output hashes.
Their generated dark outline is exactly one pixel: the outside contour for
dilated garments and the inside boundary for the already-undilated vest. Keep
interior material shading separate from this outline when authoring replacements.
Generated family manifests store chibi sheets in
`styles/jrpg_chibi/<camera>/<animation>.png` and expose them through
`cameraVariants` keys such as `jrpg_chibi_three_quarter`. A hand-authored chibi
component must provide complete Idle, Walk, and Run coverage for a camera before
the selector will offer it.

## Pre-cleaned editable family sheets

The editable sheets under
`animation_images_models/component_cleanup_v2/<base-id>/<family-id>/` are the
recommended manual-editing starting point for the 25 generated families. They
are byte-identical mirrors of the currently promoted Character Forge sheets and
preserve canonical dimensions and palette after one conservative pass
for tiny detached islands, removable solid-outline corners, and enclosed
one-/two-pixel transparency holes. The pass also removes one-pixel-wide terminal
silhouette spurs up to two pixels long, but only where the stem joins a broader
edge supported on both sides. Edit `idle.png`, `walk.png`, and `run.png`;
do not edit the flattened images under the bundle's `review/` directory.

The live family generator owns the one-time preprocessing; the editable mirror
does not apply it again. Repeating the convex corner pass would erode newly
exposed corners. Every folder's
`cleanup_manifest.json` records exactly what changed in every frame, and the
top-level `index.csv` provides the model/family paths.

## Promoting an approved manual override

Approved cleanup-v2 edits are registered in
`animation_images_models/component_override_sources.json` and normalized by
`tools/promote_component_overrides.py`. The current Tiefling Ankle Boots,
Cap-Sleeve Field Shirt, and Cropped Training Top Run overrides treat Front,
Back, and Right as exact artist-authored rows. Left is derived frame-by-frame from Right, and the
component manifest requests a final-composite mirror so every selected layer
uses the same silhouette and orientation.

After approving an edit, rebuild in this order:

```powershell
python tools/promote_component_overrides.py
python tools/promote_component_overrides.py --check
python tools/build_character_component_families.py --force
python tools/build_character_component_families.py --check
python tools/build_component_cleanup_bundle.py --force
python tools/build_component_cleanup_bundle.py --check
```

This makes the override regeneration-safe and then refreshes cleanup-v2 as an
exact editable mirror of what Character Forge serves.
