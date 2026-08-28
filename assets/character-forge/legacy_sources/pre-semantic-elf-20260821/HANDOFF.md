# Pixel Forge Handoff

Last updated: 2026-08-16

## Re-entry summary

Pixel Forge is on branch `agent/image-processing-palette-workflow` with a large,
intentional dirty worktree. Do not discard, reset, or overwrite existing changes.
No commit was created during this work.

There are no background services or component-generation processes running. Do
not resume the remaining GPT Image bootstrap queue after reboot.

The project-root `.env` is intentionally ignored and contains
`OPENAI_API_KEY`. Never print, copy, commit, or place the key in job metadata.

## Current product direction

Character Forge remains important, but production components are moving to a
manual/hybrid authoring workflow. The GPT Image pilot showed that general image
editing does not preserve the authoritative sprite geometry reliably enough for
production overlays. Text/image generation is still welcome for independent
concept art and design ideation, but generated art should not be treated as a
fitted component.

The visual direction is serious, grounded fantasy. Avoid whimsical costume
language such as the generated captain's hat. The owner repeatedly returns to an
eyepatch as a signature component and also wants monocles, relics, jewelry,
prosthetics, badges, manacles, lanterns, and similarly story-bearing accessories.

## Character Forge and component factory

- Canonical base: `human-01`.
- Idle: `64x256`, one `64x64` frame for Front, Left, Right, Back.
- Walk: `384x259`, six frames for Front, Back, Right, Left; preserve the final
  three pixels of native sheet height.
- Run: `384x256`, six frames for Front, Back, Right, Left, assembled from the
  four authoritative strips.
- The walking shirt is an incomplete, recolorable Tops/`torso` part covering
  Walk/Front only.
- The manually authored Leather Boots are available as an incomplete Feet part
  covering all six Walk/Front frames only. The production overlay contains only
  the authored top row; the source sheet's three base-reference rows were
  intentionally stripped.
- Manifest-driven slots, layer composition, recipe schema 2, recoloring,
  canonical validation, preview/export, review, cleanup, and guarded promotion
  are implemented.
- The seven-component pilot completed 21 jobs and 63/63 API candidates without
  moderation/API failure after adding a reversible reserved-blue mannequin.
- Full visual audit result: 0 production-ready candidates and 0 coherent
  Idle/Walk/Run component sets. None is promoted.
- The 28 remaining component ideas stay queued. Do not run:
  `python component_pipeline.py generate --bootstrap --remaining`.
- Pilot artifacts under ignored `art_pipeline/` must be preserved as audit and
  optional concept-reference material.

Read [COMPONENT_FACTORY_FINDINGS.md](COMPONENT_FACTORY_FINDINGS.md) before any
component-generation changes. It contains the full 63-candidate audit,
per-category verdicts, fuchsia/black-mask/head-direction findings, cleanup and
zoom requirements, and the hybrid-authoring recommendation.

Pipeline commands and schemas are documented in
[docs/COMPONENT_PIPELINE.md](docs/COMPONENT_PIPELINE.md).

## Slot decisions

The runtime currently defines 13 selectable slots:

1. Headwear
2. Face
3. Neck
4. Tops (`torso`)
5. Outerwear
6. Waist
7. Hands
8. Legwear
9. Feet
10. Hair
11. Facial Hair
12. Shoulder / Chest
13. Back

The body is permanent and not counted as an equipment slot. Components may claim
or reserve multiple slots, reducing the number that can coexist.

Agreed but not yet implemented:

- Add one broad `jewelry` slot, bringing the theoretical maximum to 14 parts.
- Relabel the existing `face` slot in the UI to **Eye / Face Accessory**. The
  internal `face` ID can remain stable.
- Eyepatches, monocles, spectacles, blindfolds, face wraps, and similar items use
  the `face` slot. An eyepatch must coexist with Headwear, Hair, Facial Hair, and
  Jewelry.
- A hood remains Headwear and may reserve Hair when it fully conceals it. It
  should not automatically block an eyepatch or facial hair.

## Manual-authoring recommendation

Do not hand-author every catalog item as a wholly independent 52-frame asset.
First author reusable fitted topology families, then derive variants through
ramps and small deterministic edits. Useful initial families include sleeveless,
short-sleeve, and long-sleeve tops; vests/coats; narrow/wide belts; low shoes;
short boots; and tall boots.

High-value editor assistance discussed but not yet implemented:

- Exact authoritative base as a locked cleanup/authoring underlay.
- On Base and Component Only views, underlay opacity, playback, and
  frame/direction navigation.
- Onion skinning and base-relative copy/propagation between related frames.
- Linked component palette ramps.
- Mouse-wheel cursor-centered nearest-neighbor zoom, Fit, 1:1, scrollbars, and
  panning across every Component Review image tab.

## Shade ramp upgrade

The Pixel Editor shade-ramp generator was just replaced and is ready to test in
the app. It now creates:

`Deep / Shadow / Soft / Base / Light / Highlight`

- Three progressively cooler blue-violet shadows.
- The exact selected RGBA value as Base.
- Two progressively warmer, less-saturated lights.
- Adaptive brightness/saturation instead of clipped fixed offsets.
- Explicit cool/warm temperature for near-neutral colors.
- Six compact clickable swatches; **+ Palette**, radial shading, and directional
  shading all consume the complete ramp.

The implementation is in `src/core/shade_ramp.py` and the updated reference is
[pixelforge-shade-ramp.md](pixelforge-shade-ramp.md). New regression coverage is
in `tests/test_shade_ramp.py`.

Latest verification:

```powershell
python -m pytest -q
# 123 passed, 62 pre-existing Pillow deprecation warnings

python -m compileall -q src tests\test_shade_ramp.py
git diff --check
```

## Recent concept boards

Three preview-only pixel-art idea boards were generated independently from the
base sprites. They are references, not project assets or fitted overlays:

- Eye/face accessories: eyepatch, monocle, ritual bandage, half-mask, splint,
  cracked lens.
- Jewelry/relics: oath torc, reliquary, broken coin, signet earring, warding
  stone, ring on a cord.
- Story accessories: hook prosthetic, jailer's keys, repaired pauldron, back
  lantern, pilgrim badges, broken manacle.

The strongest ideas identified were the wax-sealed eye bandage, cracked monocle,
broken-coin pendant, iron oath torc, repaired single pauldron, caged back lantern,
and broken manacle. Focused variation boards for individual favorites would be a
good future use of image generation.

## Important files

- [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md): project pulse and recent work.
- [COMPONENT_FACTORY_FINDINGS.md](COMPONENT_FACTORY_FINDINGS.md): factory audit
  and future direction.
- [docs/COMPONENT_PIPELINE.md](docs/COMPONENT_PIPELINE.md): pipeline commands,
  schemas, and safeguards.
- `assets/character-forge/sheet_specs.json`: canonical geometry, checksums,
  slots, layers, regions, and generation metadata.
- `assets/character-forge/custom_parts/components.yaml`: bootstrap idea catalog;
  it still includes ideas from the abandoned production-generation approach.
- `src/core/character_forge.py`: runtime slot/manifest/recipe/composition logic.
- `src/ui/character_forge_window.py`: Character Forge UI.
- `src/core/shade_ramp.py`: new six-stop ramp algorithm.
- `src/ui/pixel_editor_window.py`: ramp UI and editor behavior.

## Safe next steps

1. Launch `python main.py` and visually test the new six-stop ramp on several base
   colors in Pixel Editor.
2. When requested, add `jewelry` to the slot/layer/recipe registries and relabel
   Face as Eye / Face Accessory with migrations/tests.
3. Improve the manual component-authoring workflow before asking the owner to
   complete large animation sheets.
4. Use generation only for focused concept boards unless a future exact-fit test
   proves otherwise.
5. Preserve all unrelated dirty-worktree changes and update
   `docs/CURRENT_STATE.md` after meaningful project or git-state changes.
