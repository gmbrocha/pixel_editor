# Tomorrow's Pixel Forge Checklist

Last updated: 2026-08-28

## Start Here

1. After cloning or pulling on the other machine, run `git lfs pull`.
2. Open `animation_images_models/elf_bald_female/editable/run_redo_v1.blend` in Blender 5.1 or newer.
3. Use **File > Save As** to create a personal Run work file before changing poses.
4. Edit `PF_Run_Redo_Edit` on frames 1-8 at 10 FPS. Use `PF_Run_Meshy_Edit` if the untouched original motion is a better starting point.
5. Review the Run from front and side and check the frame-8-to-frame-1 seam before promotion.

## Walk Decision

- [x] Treat the edited Walk motion as the current completed Walk.
- [x] Approve the current figure scale and framing for the new 128x128 base.
- [x] Approve foot contact, foot sliding, arm swing, head stability, and the frame-8-to-frame-1 loop.
- [x] Approve the side views and silhouettes.
- [ ] Check `walk_regions_preview.png` for visibly incorrect face, head, hand, pelvis, or limb assignments.
- [x] Preserve `walk_manual_v1.blend` as the approved artist source. Do **not** edit `walk_manual_v1_pipeline.blend`; that is the sanitized render input.
- [ ] If only pixel cleanup is needed, preserve the region map alongside every art correction so the two remain aligned.

## Next Blender Work

Continue from the portable Run redo starter:

`animation_images_models/elf_bald_female/editable/run_redo_v1.blend`

- [x] Preserve `PF_Idle_Edit` as a 13-pose authored loop and derive a 26-frame interpolated runtime.
- [x] Approve the finished Idle motion.
- [x] Validate frame 14 as the authored closure, then validate derived frame 27 as the 26-frame closure.
- [ ] Redo the Run in `PF_Run_Redo_Edit`; use `PF_Run_Meshy_Edit` as the clean original-motion fallback.
- [ ] Keep the protected `PF_Run` and `PF_Run_ForwardLean_HeadDown` actions unchanged.
- [ ] Save new artist versions under clear names; never overwrite the original source actions.

Beginner references:

- `docs/BLENDER_ANIMATION_EDITING.md`
- `docs/BLENDER_BASIC_CONTROLS.md`

## After Run Is Edited

- [x] Run the non-destructive finalizer and interpolation pass.
- [x] Render synchronized 1024px beauty and semantic passes.
- [x] Build the 128x128 art, region, slot, hide-mask, strip, GIF, and manifest packages.
- [x] Run deterministic package checks for Idle and Walk.
- [x] Install Idle, Walk, and Run plus five recolorable starter components in Character Forge.

The exact generalized commands are documented under **128px Semantic Animation Packages** in `docs/BLENDER_CHARACTER_PIPELINE.md`. The finalizer, paired renderer, and package builder now accept variable sequence names and frame counts; the current Idle contract is 13 frames at the artist file's saved 6 FPS.

## Integration Decisions — Do Not Rush

- [x] Install the elf as the sole live `elf-01` Character Forge base.
- [x] Treat the installed Walk and Idle as approved working defaults.
- [ ] Decide how component geometry will consume slot masks, hide masks, and attachment landmarks.
- [x] Preserve the retired 64px runtime and factory under `legacy_sources/pre-semantic-elf-20260821/` outside discovery.

## Current Good State

- The manually edited Walk is safely preserved in `walk_manual_v1.blend`.
- The staged Walk package contains 128x128 art, all 32 anatomical IDs, all 13 slot masks, all 13 hide masks, four strips, four native 10 FPS GIFs, individual frames, and a hash-linked manifest.
- Art and semantic transparency match exactly.
- Deterministic package regeneration passes.
- The expanded Idle artist save is preserved untouched. Its runtime derivative contains 26 visible frames at 12 FPS and exact closure frame 27.
- Character Forge exposes only the semantic elf, five basic recolorable items, and the new 128px Idle/Walk/Run sheets.
- The full active test suite passes: **169 tests**. Obsolete exact-content and reserved-blue factory tests moved with the legacy implementation.

## Sensible Stopping Point Tomorrow

A productive session is complete when the revised Run has a clean eight-pose loop saved under a new artist filename and is ready for front/side review. Promotion can wait for explicit approval.

---

# Longer-Term Horizon

## North Star

Build a durable character-production system that can populate and enliven the village in **Pip & Pyre**.

The goal is not to hand-author every villager as a separate character. The goal is to finish four or five strong semantic base characters, give each dependable Idle, Walk, and Run cycles, and combine those bases with a compact library of reusable components, palettes, and material treatments. A small set of excellent inputs should produce a large, coherent cast of animated villagers.

The durable production equation is:

**4–5 bases × body/face variations × components × recolors/retextures = a large village cast**

## Milestone 1 — Prove One Complete Character

Finish the elf as the reference implementation for the entire pipeline.

- [x] Approve the elf Walk motion at 128x128.
- [x] Finish and approve a natural Idle.
- [ ] Approve or refine the existing Run.
- [x] Produce ordinary art sheets and GIFs for Idle, Walk, and Run.
- [x] Produce exact anatomical-region maps for all three animations.
- [x] Produce slot and body-hide masks for all three animations.
- [ ] Confirm every frame uses consistent scale, camera, baseline, direction order, palette policy, and semantic IDs.
- [x] Test saving, regenerating, checking, and loading the complete package without depending on disposable source renders.
- [x] Register the semantic elf as the sole live Character Forge base while archiving the superseded base.

**Exit gate:** one character can be selected in Character Forge, animated in four directions, equipped with at least one component, recolored, exported, and reproduced deterministically.

## Milestone 2 — Generalize the Pipeline

Remove assumptions that only work for the elf or Walk.

- [x] Generalize the finalizer, paired renderer, and semantic package builder for sequence names and variable frame counts.
- [ ] Make character ID, action names, frame samples, FPS, output location, and palette policy manifest-driven.
- [ ] Define one versioned base-character package contract.
- [ ] Validate topology, region coverage, slot coverage, frame dimensions, direction order, loop closure, and output hashes automatically.
- [ ] Add a visual review index showing every animation and direction for one character.
- [ ] Add an explicit approval state so staged characters cannot accidentally become production defaults.
- [ ] Document the shortest reliable workflow for adding the next character.

**Exit gate:** creating character two requires new art/model decisions, not new one-off pipeline code.

## Milestone 3 — Complete Four or Five Base Characters

Choose bases that create useful visual and silhouette diversity rather than five minor variations of the same body.

Suggested coverage:

1. Elf or human feminine base — current reference implementation.
2. Human masculine base — average proportions and broad component compatibility.
3. Stocky dwarf base — short, broad silhouette requiring its own component fit profile.
4. Slender or small-framed base — useful for younger, agile, scholarly, or lightly built villagers.
5. Optional large/heavy base — useful for smiths, guards, laborers, or unusually imposing characters.

For every base:

- [ ] Four directions: Front, Back, Right, Left.
- [ ] Idle, Walk, and Run ordinary loops.
- [ ] Approved 128x128 pixel artwork.
- [ ] Exact anatomical-region maps.
- [ ] All component-slot and body-hide masks.
- [ ] Stable attachment landmarks.
- [ ] A documented production palette or material-remapping policy.
- [ ] Character Forge registration and deterministic export.

**Exit gate:** at least four visually distinct bases pass the same acceptance checks and can appear together without obvious scale, camera, lighting, or motion-style mismatch.

## Milestone 4 — Build the Minimum Useful Component Library

Start small. Components should be chosen for combinatorial value and common village roles, not for completeness.

### First component set

- [ ] Simple hair family: short, long, tied-back, messy, bald-compatible head treatment.
- [ ] Basic shirts/tunics: plain shirt, work tunic, nicer town tunic.
- [ ] Legwear: trousers, skirt or long lower garment, work apron where appropriate.
- [ ] Footwear: simple shoes, boots, heavy work boots.
- [ ] Outerwear: short coat, cloak or shawl.
- [ ] Headwear: cap, hood, simple hat.
- [ ] Role accents: belt/pouch, blacksmith apron, guard shoulder/chest piece, merchant or scholar accessory.
- [ ] A restrained face-detail set: brows, facial hair, scars or age marks where the base allows it.

### Existing component migration

- [ ] Audit every current Character Forge component against the new 128x128 bases.
- [ ] Preserve useful designs, palettes, and semantic sources even when their old geometry cannot be reused directly.
- [ ] Refit selected existing components to the elf first.
- [ ] Define per-base fit variants only when scaling or attachment landmarks cannot solve the difference.
- [ ] Rebuild Idle and Run coverage rather than leaving components Walk-only.
- [ ] Use semantic slot and hide masks to eliminate exposed body pixels beneath equipped geometry.

**Exit gate:** each base supports a small but coherent everyday outfit, work outfit, and one distinctive role outfit across Idle, Walk, and Run.

## Milestone 5 — Make Variation Cheap

Once silhouettes work, multiply useful output without multiplying hand-authored geometry.

- [ ] Add controlled skin, hair, eye, and base-clothing palettes.
- [ ] Add material presets for cloth, leather, metal, worn workwear, and nicer garments.
- [ ] Support deterministic recolors and retextures from semantic component regions.
- [ ] Define compatible and incompatible slot combinations.
- [ ] Add seeded villager recipes so a generated character can be reproduced exactly.
- [ ] Prevent combinations that obscure faces, duplicate geometry, expose hidden body regions, or clash with a base's proportions.
- [ ] Produce a visual contact sheet of generated villagers before game integration.

**Exit gate:** a handful of approved components can create dozens of readable, non-identical villagers without manual frame-by-frame repair.

## Milestone 6 — Bring the Village to Life in Pip & Pyre

Connect Character Forge output to actual gameplay rather than stopping at an asset gallery.

- [ ] Define the game's sprite package and metadata contract.
- [ ] Import generated villagers without manual sheet rearrangement.
- [ ] Map game movement states to Idle, Walk, and Run.
- [ ] Verify direction conventions, frame timing, origins, collision feet, and world-scale alignment.
- [ ] Create a small named test cast representing several bases and component combinations.
- [ ] Place the test cast in one village scene.
- [ ] Add simple schedules or behaviors: idle, walk between points, work, converse, return home.
- [ ] Confirm villagers remain visually distinct in motion and at gameplay zoom.
- [ ] Profile memory, loading, batching/atlas use, and animation cost before scaling the population.
- [ ] Expand recipes only after the first village scene feels alive.

**Exit gate:** a representative village scene contains a varied animated population produced through the pipeline, with no bespoke sprite-editing step for each villager.

## Anti-Drift Rules

When deciding what to work on, use these rules:

1. Finish one complete vertical slice before expanding horizontally.
2. Do not begin character three until character two proves the generalized workflow.
3. Do not build a huge component catalog before a small outfit works across every animation.
4. Do not polish generated combinations that expose a pipeline defect; fix the reusable source or rule.
5. Do not replace approved assets silently. Stage, review, then promote explicitly.
6. Keep purchased assets and external model/animation downloads as references or local inputs unless their license and repository policy explicitly allow tracking.
7. Prefer deterministic tools, manifests, and hashes over undocumented manual export steps.
8. Judge every feature by whether it helps create believable villagers for Pip & Pyre.

## Priority Order

If there is uncertainty about what to do next, follow this order:

1. Complete elf Walk review.
2. Complete elf Idle.
3. Confirm elf Run.
4. Finish the elf's full semantic animation package.
5. Equip and export one elf test outfit.
6. Generalize the pipeline.
7. Complete character two.
8. Complete the remaining base characters.
9. Build and migrate the minimum component set.
10. Add controlled variation.
11. Populate a Pip & Pyre village test scene.

## Definition of Success

This project succeeds when Pixel Forge can reliably produce a broad cast of cohesive animated villagers from four or five semantic bases and a deliberately small component library, and those villagers can be placed into Pip & Pyre without hand-rebuilding their animations or sprite sheets one character at a time.
