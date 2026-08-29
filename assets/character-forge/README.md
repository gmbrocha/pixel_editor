# Character Forge assets

Character Forge provides four approved 128x128 character bases. Superseded 64px
runtime assets, the reserved-blue prototype workflow, old workbench sources, and
retired component-factory code have been removed from the active repository.

## Runtime bases

`sheet_specs.json` registers `elf-01`, `tiefling-female-01`, `dwarf-male-01`,
and `human-muscular-male-01`. The less-muscular Human male remains excluded.
The Forge displays the first model as `Elf Female Base`; “semantic” describes
its authoring data, not its user-facing model name.
Every sheet uses Front, Back, Right, Left row order:

- Idle: 14 runtime frames per direction at 6 FPS, 1792×512 sheet.
- Walk: 8 frames per direction at 10 FPS, 1024×512 sheet.
- Run: 8 frames per direction at 10 FPS, 1024×512 sheet.

The sheets live under `bases/<base-id>/`. They are ordinary indexed-palette pixel
art with binary transparency and 128×128 cells. Idle is derived non-destructively
from 13 manually authored poses by placing those poses on alternating frames and
using Blender's keyed-transform interpolation for the in-betweens. Run uses the
manually revised and user-approved `PF_Run_Approved` action.

Every Idle plays both weight shifts consecutively at the normal 6 FPS cadence,
then holds runtime frame 13 for 1500 ms before frame 25 and the next loop.
`frame_durations_ms` in `sheet_specs.json` is authoritative;
Character Forge and the tracked GIFs honor those durations without duplicating
sheet columns.

## Canonical camera heights

Every approved base and every Idle, Walk, and Run sheet is available at exactly
three orthographic camera heights. Character Forge exposes these independently
from the Front, Back, Right, and Left direction selector:

- Near Top-Down (`top_down`): 70-degree downward pitch.
- Three-Quarter (`three_quarter`): 45-degree downward pitch.
- Low (`low`): the existing 28-degree downward pitch.

The original Low sheets remain at `bases/<base-id>/<animation>.png`. Elevated
variants live below `bases/<base-id>/camera_views/<camera-height>/`. The
hash-linked `camera_views_manifest.json` covers all four bases, three motions,
three heights, and four directions. All 105 current components have Low-view
coverage only, so the Forge offers model-matched components only when Low is
selected.

Camera framing is model-specific but fixed across a model's animations. The elf
Low framing is normalized to the same apparent height as the other elf camera
variants. The Dwarf uses a 1.12 orthographic framing multiplier at all three
heights, making it roughly 10–11% shorter on the canvas than the full-height
models while preserving its broader proportions.

## Semantic packages

`semantic/elf-01/<animation>/` contains the complete durable semantic package
for each elf animation:

- ordinary art sheet and native-speed direction GIFs;
- exact 8-bit per-pixel anatomical region IDs;
- color-coded region inspection sheet;
- individual art, ID, and preview frames;
- all 13 component-slot masks and all 13 body-hide masks;
- direction strips, palette, hashes, source-frame mapping, and manifest.

Every opaque art pixel has exactly one region ID, and transparent pixels have ID
zero. `tools/build_semantic_sprite_package.py --check` recreates a package and
byte-compares it.

Tiefling, Dwarf, and muscular Human Low views have lighter-weight anatomical
region sheets under `base_regions/<base-id>/<animation>/`. These use the same 32
region IDs, are derived from each model's matching 24-bone rig weights, and
cover the exact opaque pixels of the promoted runtime sheet. They exist to fit
component families to each body; they do not add elevated-view masks or the
elf's complete slot/hide/frame package.

## Component catalog

The original five simple elf starters remain installed:

- Basic Linen Shirt (`torso`)
- Simple Work Vest (`outerwear`)
- Basic Trousers (`legwear`)
- Plain Leather Gloves (`hands`)
- Tall Work Boots (`feet`)

Each covers Idle, Walk, and Run in all four directions. Each manifest declares a
five-color material ramp, so Character Forge's existing color picker can produce
arbitrary color variants without duplicating component entries. These are basic
pipeline proofs intended for later pixel cleanup, not final costume design.
Their dark sewn outline is limited to the one-pixel pixel-art minimum. Dilated
components use only the outside contour, preserving the luminance-derived shaded
interior instead of covering it with the former three-pixel edge band.

The catalog also contains 25 generated component families, each with a
separately fitted Elf, Tiefling, Dwarf, and muscular Human version: 100 new
selectable variants total. The families comprise four tops, four outerwear
pieces, six legwear cuts, three handwear styles, four footwear heights, and four
headwear styles. They include sleeveless, cap-sleeve, long-sleeve, cropped,
padded, leather, open-front, and hooded tops; shorts, breeches, fitted,
high-waist, low-waist, and reinforced pants; fingerless gloves, gauntlets, and
bracers; low shoes through tall boots; and a headband, cap, coif, and guard helm.
Every variant covers Idle, Walk, and Run in all four directions, uses a
five-color recolorable ramp, and retains the one-pixel outline minimum. The live
family generator applies the canonical cleanup pass once: detached artifacts,
removable solid corners, tiny enclosed holes, and supported one-/two-pixel
terminal spurs are resolved before the sheets enter the Forge. The 300 sheets
under `animation_images_models/component_cleanup_v2/` are byte-identical
editable mirrors of this promoted baseline.

The catalog also contains the user-approved third-edit Tiefling long hair as an
incomplete Low-view component. Its exact eight-frame Front, Back, and Right Run
artwork is live. Left is derived by horizontally mirroring the complete composed
Right view, keeping the body, selected clothing, and hair aligned; Idle, Walk,
and elevated cameras remain transparent. Its five authored colors form one
declared ramp, so Main Color remaps every visible hair shade. Character Forge supports
two aligned layers per hair selection (`hair_back` behind the body/clothing and
`hair_front` above it), plus an under-hair face-accessory layer. Headwear owns an
explicit hair policy: the cloth headband shows hair, the travel cap and padded
coif clip hair to their visible alpha, and the guard helm hides hair. Legacy
single-layer component manifests remain compatible.

The hand-authored Tiefling Blindfold is an incomplete Low-view Run component in
the Face slot. All four authored direction rows are preserved exactly. It uses
the `face_accessory_under_hair` layer, so the selected hair is composited above
it: covered blindfold pixels disappear beneath the bangs while every exposed
pixel remains visible. Its four-color ramp is recolorable through Main Color;
Idle, Walk, and elevated cameras remain transparent.

The Tiefling Ankle Boots, Cap-Sleeve Field Shirt, and Cropped Training Top also
have user-approved Run overrides. Their Front, Back, and Right rows are preserved exactly from the
editable cleanup-v2 sheets. Left is generated by mirroring the complete composed
Right view, so the base, clothing layers, and any hair remain aligned. The
canonical override manifest and normalized sheets live under
`animation_images_models/component_overrides/`; forced family rebuilds consume
these overrides instead of replacing them with procedural output.

Review contact sheets for the original starters are under `review/`; twelve
5-by-5 family boards are under `review/component-families/`. Components are
fit-checked, so only the version fitted to the selected model appears.

## Regeneration

After building the three semantic animation packages, reinstall the runtime and
starter components with:

```powershell
python tools/build_semantic_character_forge.py `
  --asset-root assets/character-forge `
  --idle-package animation_images_models/elf_bald_female/working/idle_26f_128_semantic `
  --walk-package animation_images_models/elf_bald_female/working/walk_manual_v1_128_semantic `
  --run-package animation_images_models/elf_bald_female/working/run_redo_candidate_128_semantic `
  --force
```

Runtime discovery reads only manifests beneath the live `parts/` directory.

Rebuild or byte-verify all 25 fitted component families with:

```powershell
python tools/promote_component_overrides.py
python tools/promote_component_overrides.py --check
python tools/build_character_component_families.py --force
python tools/build_character_component_families.py --check
python tools/build_component_cleanup_bundle.py --force
python tools/build_component_cleanup_bundle.py --check
```

Reinstall or byte-verify the approved incomplete Tiefling hair component with:

```powershell
python tools/install_tiefling_long_hair_prototype.py
python tools/install_tiefling_long_hair_prototype.py --check
```

Reinstall or byte-verify the Tiefling Run blindfold with:

```powershell
python tools/install_tiefling_blindfold.py
python tools/install_tiefling_blindfold.py --check
```

The semantic elf installer owns only its five starter directories and preserves
the generated fitted-family directories during a forced rebuild.

Rebuild or verify the approved target bases with:

```powershell
python tools/promote_motion_transfer_bases.py --target all --force
python tools/promote_motion_transfer_bases.py --target all --check
```

Rebuild or byte-verify the two elevated canonical camera views with:

```powershell
python tools/build_character_camera_views.py --force
python tools/build_character_camera_views.py --check
```
