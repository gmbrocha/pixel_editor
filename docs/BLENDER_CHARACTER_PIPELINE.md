# Blender Character Capture Pipeline

Last updated: 2026-08-21

## Purpose

This pipeline converts locally supplied character exports into a self-contained Blender master, promotes reviewed models into semantic mannequins, supports manual refinement of the established authored and Meshy motions, renders repeatable four-direction source frames, and assembles Pixel Forge sprite packages. Raw FBXs and ZIP archives remain local and untouched.

The current pilot character is `animation_images_models/elf_bald_female`.

## Current Source Findings

- Blender: 5.1.2.
- Mesh: 100,029 vertices and 200,054 polygons.
- Skeleton: 24 bones with identical names and hierarchy in the master, Walk, and Run FBXs.
- Frame rate: 30 FPS.
- Bind Pose: frame 1 only.
- Authored Idle: frames 1-49; frame 49 is an exact duplicate of frame 1.
- Walk: frames 1-32; frame 32 duplicates the loop-start pose.
- Run: frames 1-20; frame 20 duplicates the loop-start pose.
- Textures: 2048x2048 base color plus metallic, normal, and roughness maps.

The clean rig's bind pose has the hands beside the thighs. The extreme backward-arm behavior seen in Meshy's Idle previews is therefore animation-specific; applying a global armature rest-pose correction would damage the valid Walk and Run baseline.

## Tools

- `tools/blender/inspect_fbx.py`: imports FBXs and writes structural JSON diagnostics.
- `tools/blender/build_character_master.py`: creates a packed master `.blend`, explicitly rebuilds its PBR material, and stores Bind Pose, Walk, and Run actions on one armature.
- `tools/blender/render_character_diagnostics.py`: renders front and side pose samples and records evaluated bone positions.
- `tools/blender/create_run_posture_variant.py`: bakes a reversible distributed forward-lean Run variant while retaining the original action.
- `tools/blender/create_idle_action.py`: bakes a restrained seamless Idle from the clean bind pose without importing Meshy's broken Idle motion.
- `tools/blender/interpolate_manual_motion.py`: time-stretches a finalized manual loop and exposes Blender's transform interpolation as additional sprite frames while proving every authored pose remains unchanged.
- `tools/blender/render_sprite_sequences.py`: renders transparent four-direction source frames from selected action frames.
- `tools/blender/assemble_sprite_sheets.py`: downsamples source renders and assembles fixed-cell direction strips and sheets.
- `tools/blender/pixelize_sprite_sheets.py`: converts immutable high-resolution renders into shared-palette, binary-alpha pixel sheets and animated review GIFs, with deterministic `--check` verification.
- `tools/blender/build_semantic_mannequin.py`: adds the canonical 32-region face map, 13 slot/hide masks, semantic UV/debug material, and 17 attachment landmarks while hashing protected mesh, rig, material, and action data.
- `tools/blender/validate_semantic_mannequin.py`: validates the tracked canonical blend against its semantic manifest without requiring any raw FBX.
- `tools/blender/render_semantic_inspection.py`: renders six semantic views and non-destructive previews of every slot's default body-hide mask.
- `tools/promote_character_motion.py`: separately promotes approved eight-frame pixel Idle and Walk sheets while asserting that Run is unchanged.

## Canonical Semantic Mannequin

The tracked production mannequin lives at `animation_images_models/elf_bald_female/canonical/`. Its original PBR material remains the active material. Semantics are stored separately from deformation data:

- `pf_region_id`: one face-domain integer ID across 32 populated anatomical regions.
- `pf_region_color`: exact corner colors used by `PF_Semantic_Debug`.
- `pf_slot_<slot>` and `pf_hide_<slot>`: overlapping face-domain booleans for all 13 Character Forge slots.
- `PF_SemanticUV`: an 8x4 palette-atlas UV where only faces sharing a region ID may overlap.
- `PF_ATTACH_*`: 17 bone-parented rest-space landmarks for head, face, neck, chest, back, waist, shoulders, hands, hips, ankles, and feet.

`mannequin_semantics.json` contains topology, weight, rest-pose, production-material, and action hashes; exact region colors and counts; slot defaults; landmark transforms; and output hashes. `semantic_region_overrides.json` is a topology-guarded run-length-encoded face-override file. It is intentionally empty until a reviewed debug render identifies a boundary worth refining.

Rebuild and validate the canonical asset:

```powershell
$blender = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
$base = Resolve-Path animation_images_models\elf_bald_female

& $blender --background --factory-startup --python tools\blender\build_semantic_mannequin.py -- `
  --source (Join-Path $base working\elf_bald_female_complete.blend) `
  --output (Join-Path $base canonical\elf_bald_female_mannequin.blend) `
  --manifest (Join-Path $base canonical\mannequin_semantics.json) `
  --debug-texture (Join-Path $base canonical\semantic_regions.png) `
  --overrides (Join-Path $base canonical\semantic_region_overrides.json) --force

& $blender --background --factory-startup --python tools\blender\validate_semantic_mannequin.py -- `
  --blend (Join-Path $base canonical\elf_bald_female_mannequin.blend) `
  --manifest (Join-Path $base canonical\mannequin_semantics.json)

& $blender --background --factory-startup --python tools\blender\render_semantic_inspection.py -- `
  --blend (Join-Path $base canonical\elf_bald_female_mannequin.blend) `
  --output-dir (Join-Path $base canonical\inspection) --size 384
```

The builder aborts if semantic work changes topology, vertex-group weights, armature rest data, the production material graph, or any existing action evaluation.

## Manual Motion Editing

`prepare_legacy_motion_edit_session.py` builds one canonical-mannequin teaching file containing `PF_Idle_Edit`, `PF_Walk_Meshy_Edit`, and `PF_Run_Meshy_Edit`. Each is an exact eight-pose copy with a ninth closure frame and action-specific markers. The complete `PF_Idle`, `PF_Walk`, and untouched `PF_Run` actions remain protected in the same file. `validate_legacy_motion_edit_session.py` verifies every sampled pose, closure, source-action hash, default UI state, and safety setting.

The beginner walkthrough is `docs/BLENDER_ANIMATION_EDITING.md`, with a separate compact shortcut reference in `docs/BLENDER_BASIC_CONTROLS.md`.

Before rendering a manually edited action, `finalize_manual_motion_edit.py` creates a separate pipeline copy. `--frame-count` defines the visible poses; the tool hashes and preserves frames `1..N`, removes keys outside `1..N+1`, rebuilds frame `N+1` as a complete frame-1 closure, and writes an audit manifest. It preserves the artist file's saved FPS unless `--fps` is supplied. The artist's saved `.blend` is never overwritten. Omitting `--frame-count` retains the original eight-pose/frame-9 behavior.

The expanded Idle artist save is `working/idle_more_frames.blend`. Its authored range is frames 1–13. The sanitized `working/idle_more_frames_pipeline.blend` removes accidental frame-0 keys and rebuilds frame 14 as the exact closure. `interpolate_manual_motion.py` then maps those 13 poses to odd frames in `idle_26f_pipeline.blend`; Blender supplies the even-frame in-betweens. The result is 26 visible frames at 12 FPS with closure frame 27 and the same 2.17-second duration. The artist save remains untouched.

```powershell
$base = Resolve-Path animation_images_models\elf_bald_female
$blender = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'

& $blender --background --factory-startup `
  --python tools\blender\finalize_manual_motion_edit.py -- `
  --blend (Join-Path $base working\idle_more_frames.blend) `
  --action PF_Idle_Edit --frame-count 13 `
  --output-blend (Join-Path $base working\idle_more_frames_pipeline.blend) `
  --output-manifest (Join-Path $base working\idle_more_frames_pipeline.json)

& $blender --background --factory-startup `
  --python tools\blender\interpolate_manual_motion.py -- `
  --blend (Join-Path $base working\idle_more_frames_pipeline.blend) `
  --action PF_Idle_Edit --source-frame-count 13 --subdivisions 2 --fps 12 `
  --output-blend (Join-Path $base working\idle_26f_pipeline.blend) `
  --output-manifest (Join-Path $base working\idle_26f_pipeline.json)
```

## 128px Semantic Animation Packages

The finalized `PF_Walk_Meshy_Edit` can also be rendered as synchronized beauty and anatomical-ID passes, then reduced into a staged 128x128 package. This does not replace the 64px proof or any Character Forge runtime asset.

```powershell
$base = Resolve-Path animation_images_models\elf_bald_female
$blender = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
$pipeline = Join-Path $base working\walk_manual_v1_pipeline.blend
$source = Join-Path $base working\walk_manual_v1_128_source
$package = Join-Path $base working\walk_manual_v1_128_semantic

& $blender --background $pipeline `
  --python tools\blender\render_semantic_sprite_sequences.py -- `
  --output-dir $source --action PF_Walk_Meshy_Edit `
  --sequence walk --render-size 1024

python tools\build_semantic_sprite_package.py `
  (Join-Path $source paired_sprite_render_manifest.json) $package --sequence walk

python tools\build_semantic_sprite_package.py `
  (Join-Path $source paired_sprite_render_manifest.json) $package --sequence walk --check
```

The output contains `walk.png`, exact 8-bit `walk_regions.png` IDs, `walk_regions_preview.png`, four native 128x128 GIFs, four strips, every individual art/ID/preview frame, all 13 `walk_slot_<slot>.png` masks, all 13 `walk_hide_<slot>.png` masks, the shared art palette, and `walk_manifest.json`. The region reducer performs coverage voting from the 1024px flat-color pass, uses the final art alpha as the authoritative silhouette, and rescues small visible anatomical regions that would otherwise disappear. Every opaque art pixel must receive exactly one region ID and every mask is derived from that ID image rather than inferred independently.

The current `PF_Idle`, manually edited `PF_Walk_Meshy_Edit`, untouched `PF_Run`, and approved `PF_Run_ForwardLean_HeadDown` remain separate actions. The reviewed 128px outputs are now installed as the `elf-01` Character Forge base; the Blender actions and local working renders remain separately recoverable.

## Approved Motion Transfer

The tracked canonical mannequin also contains `PF_Idle_Approved`,
`PF_Walk_Approved`, and `PF_Run_Approved` without replacing the protected Meshy
actions. `approved_motion_transfer_profile.json` records the 24-bone hierarchy,
rest data, source hashes, per-frame quaternion corrections, Hips translation,
contact paths, timing, and source self-checks.

`tools/build_motion_transfer_candidates.py` extracts only configured entries
from the ignored Meshy archives, builds a packed target master, applies the
approved correction profile, renders all directions with one per-character
camera frame, and creates a shared-palette 128px review set. Walk and Run apply
the approved-versus-Meshy delta to the matching target Meshy actions. Idle maps
the full approved bind-relative motion. Non-Hips translations and all scales
remain target-owned; Hips motion is proportion-scaled, and planted-foot drift is
corrected through capped root offsets without IK.

```powershell
python tools/build_motion_transfer_candidates.py --target all --force
python tools/build_motion_transfer_candidates.py --target all --check
```

The approved Tiefling female, Dwarf male, and muscular Human male are finalized
non-destructively into tracked `canonical/` blends and promoted as base-only
Character Forge models with:

```powershell
python tools/promote_motion_transfer_bases.py --target all --force
python tools/promote_motion_transfer_bases.py --target all --check
```

The finalizer preserves the Meshy and transfer actions and writes separate
`PF_Idle_Approved`, `PF_Walk_Approved`, and `PF_Run_Approved` actions. It removes
stray keys such as the Tiefling artist file's frame-0 keys only in the derived
canonical action. All Blender Idles retain 26 authored pose columns. Character
Forge samples 14 of those poses at 6 FPS, plays both weight shifts consecutively,
and holds only runtime frame 13 for 1500 ms before looping. Timing-only contract
changes can be applied and verified with
`tools/apply_approved_motion_timing.py`. The less-muscular Human is excluded.

## Canonical Character Forge Camera Views

Character Forge treats camera height as a first-class recipe dimension, separate
from base model, animation, and facing direction. The canonical orthographic
heights are Near Top-Down at 70 degrees, Three-Quarter at 45 degrees, and Low at
28 degrees. Each base uses one union auto-frame per height across all three
approved actions and all directions, preventing scale or framing jumps when the
animation changes.

```powershell
python tools/build_character_camera_views.py --force
python tools/build_character_camera_views.py --check
```

The builder reads the four tracked canonical blends, renders only the two new
elevated views, applies `approved_motion_timing.json`, generates 128px sheets and
native-size GIFs, promotes them below `assets/character-forge`, and writes
`camera_views_manifest.json`. Low assets are retained byte-for-byte. A rebuild of
the semantic elf or target motion bases preserves existing camera metadata, but
the camera builder must be rerun whenever a canonical action changes so its
blend and output hashes remain current. Angle-specific semantic regions and
components are not inferred from Low-view masks; current components therefore
remain available only at Low.

`render_sprite_sequences.py --framing-scale` provides the canonical per-model
size adjustment without modifying the rig or resizing finished pixels. Values
above one render the character smaller. The Dwarf uses `1.12` at every height.
The older elf Low semantic capture is normalized with orthographic scale
`2.442563056945801`, matching its apparent height to the newer auto-framed
variants while retaining paired beauty/region rendering and aligned components.

## Low-View Fitted Component Families

The Tiefling, Dwarf, and muscular Human canonical Low cameras can render paired
beauty/anatomical passes with
`render_semantic_sprite_sequences.py --derive-weight-regions`. The renderer
temporarily derives the same 32 anatomical IDs from each model's named 24-bone
vertex groups without modifying the canonical blend. Dwarf knees use a
deterministic nearest-joint fallback where the short proportions leave the
standard knee-radius classification empty.

`tools/build_weight_region_sheet.py` reduces each paired 1024px pass onto the
matching promoted 128px base sheet. It requires exact base-alpha coverage, all
32 IDs, four canonical directions, correct frame counts, portable provenance,
and supports byte verification with `--check`.

`tools/build_character_component_families.py` then generates 25 shared design
families with separately fitted variants for `elf-01`, Tiefling, Dwarf, and
muscular Human. The resulting 100 manifests and 300 animation sheets cover six
slots, all three approved motions, all four directions, five-color recoloring,
and one-pixel outlines. Twelve 5-by-5 review boards are generated under
`assets/character-forge/review/component-families/`.

```powershell
python tools/build_character_component_families.py --force
python tools/build_character_component_families.py --check
```

These overlays are canonical Low-view features. Elevated semantic captures and
angle-specific component variants remain separate future work.

Idle and Run use the same commands with their sequence name, action, output folders, FPS, and optional frame list/count. Render the interpolated Idle with `--sequence idle --action PF_Idle_Edit --frame-count 26`, then build with `--sequence idle --fps 12`. Run uses `PF_Run_ForwardLean_HeadDown` and source frames `1,3,6,8,10,13,15,18`. Closure frames are validation data and are not emitted as sprite frames.

## Repository Policy

Tracked production inputs are the canonical `.blend`, semantic manifest/overrides/debug texture, inspection renders, tools, tests, and approved sprite outputs. Canonical `.blend` files use Git LFS. Raw FBXs, archives, extracted packages, working blends, diagnostics, renders, and `.blend1` backups remain ignored and reproducible or locally reacquirable.

## Regeneration

The commands below assume `blender` is available on `PATH`. During a process that predates the PATH update, use `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe` instead.

```powershell
$base = Resolve-Path animation_images_models\elf_bald_female
$source = Join-Path $base extracted\rigged_animated\Meshy_AI_Neutral_Figure_biped

blender --background --factory-startup --python tools\blender\inspect_fbx.py -- `
  --output (Join-Path $base working\diagnostics\fbx_report.json) `
  (Join-Path $base rigged_no_animation.fbx) `
  (Join-Path $source Meshy_AI_Neutral_Figure_biped_Animation_Walking_withSkin.fbx) `
  (Join-Path $source Meshy_AI_Neutral_Figure_biped_Animation_Running_withSkin.fbx)

blender --background --factory-startup --python tools\blender\build_character_master.py -- `
  --master (Join-Path $base rigged_no_animation.fbx) `
  --walk (Join-Path $source Meshy_AI_Neutral_Figure_biped_Animation_Walking_withSkin.fbx) `
  --run (Join-Path $source Meshy_AI_Neutral_Figure_biped_Animation_Running_withSkin.fbx) `
  --texture-dir $source `
  --output (Join-Path $base working\elf_bald_female_master.blend) `
  --manifest (Join-Path $base working\elf_bald_female_master.json)

blender --background (Join-Path $base working\elf_bald_female_master_posture_test.blend) `
  --python tools\blender\create_run_posture_variant.py -- `
  --source-action PF_Run `
  --output-action PF_Run_ForwardLean_HeadDown `
  --output (Join-Path $base working\elf_bald_female_master_head_down_test.blend) `
  --manifest (Join-Path $base working\diagnostics\run_forward_lean_head_down.json) `
  --lower-spine 3 --middle-spine 2 --upper-spine 1 --neck-compensation 9

blender --background (Join-Path $base working\elf_bald_female_master_head_down_test.blend) `
  --python tools\blender\create_idle_action.py -- `
  --source-action PF_BindPose --output-action PF_Idle `
  --output (Join-Path $base working\elf_bald_female_complete.blend) `
  --manifest (Join-Path $base working\diagnostics\idle_action.json)

blender --background (Join-Path $base working\elf_bald_female_complete.blend) `
  --python tools\blender\render_sprite_sequences.py -- `
  --output-dir (Join-Path $base working\sprite_prototype\raw) `
  --render-size 512 --ortho-scale 1.95 --pitch 28 `
  --idle-action PF_Idle `
  --run-action PF_Run_ForwardLean_HeadDown

python tools\blender\assemble_sprite_sheets.py `
  --manifest (Join-Path $base working\sprite_prototype\raw\sprite_render_manifest.json) `
  --output-dir (Join-Path $base working\sprite_prototype\sheets) `
  --cell-size 64

python tools\blender\pixelize_sprite_sheets.py `
  --manifest (Join-Path $base working\sprite_prototype\raw\sprite_render_manifest.json) `
  --output-dir (Join-Path $base working\pixel_proof) `
  --cell-size 64 --palette-size 16 --alpha-threshold 112 `
  --cleanup-threshold 1 --preview-fps 10

python tools\blender\pixelize_sprite_sheets.py `
  --manifest (Join-Path $base working\sprite_prototype\raw\sprite_render_manifest.json) `
  --output-dir (Join-Path $base working\pixel_proof) `
  --cell-size 64 --palette-size 16 --alpha-threshold 112 `
  --cleanup-threshold 1 --preview-fps 10 --check
```

Pass `--force` to the master builder or posture-variant tool only when intentionally replacing their derived outputs.

## Prototype Capture Contract

- Direction order: Front, Back, Right, Left.
- Eight frames per direction.
- Cell size: 64x64.
- Source render size: 512x512 with transparency.
- Camera: orthographic, 28-degree downward pitch, 1.95 orthographic scale.
- Walk samples: 1, 5, 9, 13, 17, 21, 25, 29.
- Run samples: 1, 3, 6, 8, 10, 13, 15, 18.
- Idle samples: 1, 7, 13, 19, 25, 31, 37, 43; frame 49 closes the source loop and is not duplicated in the sheet.

These settings are diagnostic defaults, not approved Character Forge artwork. The 64x64 output still contains antialiased, full-color 3D rendering. It needs silhouette review, contact-frame selection, palette design, deliberate pixel reduction, and cleanup before promotion.

## Deterministic Pixel Proof

The first complete pixel pass lives under `animation_images_models/elf_bald_female/working/pixel_proof`. It is generated directly from the immutable 512x512 renders rather than from the provisional smooth sheet:

- Premultiplied area downsampling to 64x64 prevents hidden transparent RGB from bleeding into edges.
- Alpha is thresholded at 112 and normalized to either 0 or 255.
- Idle, Walk, and Run share one 16-color opaque palette extracted across every frame and direction.
- Pixels map to that palette through non-dithered CIELAB nearest-color matching.
- One-pixel isolated color noise is merged into a structurally adjacent opaque region without changing the silhouette.
- Transparent strips, four-direction sheets, nearest-neighbor 4x reviews, and 10 FPS direction GIFs are generated together.
- `pixel_sprite_manifest.json` records settings, source/render hashes, palette values, actions, frame sampling, output layout, and every output hash.
- `--check` regenerates into a temporary directory and byte-compares every expected artifact.

This proves the repeatable capture-to-pixel path. The result is intentionally still a generated base pass: manual face readability, silhouette accents, art direction, and Character Forge promotion remain separate review gates.

## Authored Idle

`PF_Idle` is a 48-unique-frame, 1.6-second loop baked from `PF_BindPose`; frame 49 exactly repeats frame 1. It leaves the feet and pelvis locked and uses only a restrained upper-body cycle:

- A slow 0.35/0.8-degree middle/upper-spine breathing rotation with 0.45-degree neck compensation.
- A 0.25/0.35/0.45-degree distributed side sway across the spine with 0.55-degree counter-sway at the neck.
- No authored hand swing, knee bend, foot movement, pelvis bob, or backward shoulder pull.

All eight sampled pixel frames are distinct. Depending on direction, 9-56 pixels change relative to the first frame, which is enough for a living idle at 64px without reading as a dramatic sway.

## Run Posture Variant

`PF_Run_ForwardLean` is a non-destructive derivative of `PF_Run`. It adds 3 degrees at `Spine02`, 2 degrees at `Spine01`, and 1 degree at `Spine`, then returns 4 degrees at the neck. The result moves the head about 2.4 cm forward and only 3-6 mm downward while preserving the original legs and foot contacts. Both actions remain available in `elf_bald_female_master_posture_test.blend` for comparison.

`PF_Run_ForwardLean_HeadDown` keeps that same six-degree distributed torso lean but rotates the neck nine degrees forward from its base. This matches the approved painted reference more closely: the head moves about 5.1 cm forward and 0.8-1.4 cm down across the cycle, while the legs, feet, and timing remain byte-for-byte derived from the source action. The original Run, the level-head comparison, and the head-down action all remain in `elf_bald_female_master_head_down_test.blend`.

Pass `--run-action PF_Run_ForwardLean_HeadDown` to `render_sprite_sequences.py` when rendering the current Run prototype. Omitting the option continues to render the untouched `PF_Run` action.

## Next Work

1. Review the installed 14-frame, 6 FPS Idle GIFs for motion phase, planted feet, holds, and loop continuity.
2. Review the twelve fitted-family contact sheets for semantic-boundary errors.
3. Make any deliberate motion or face/silhouette cleanup in derived artist files, never in raw renders or pipeline copies.
4. Refine generated fitted-family pixels or replace them gradually with deliberately authored component geometry while retaining complete model and animation coverage.
