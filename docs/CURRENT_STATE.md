# Current State

Last updated: 2026-08-28

## Summary
PixelForge is a PySide6 desktop pixel-art and tileset utility. Source-grounded tools include image import and preview extraction, palette handling, pixel editing, animation editing, modular Character Forge assembly/export, tile layout, tileset processing, tileset template generation, and procedural texture generation.

## Current Status
The Animation Editor is a functional two-pane Animation Studio with signed-stride direction tracks, linked sheet editing, pixel tools, onion skinning, Once/Loop/Ping Pong playback, analysis, Undo/Redo, `.pfa` persistence, GIF import, and PNG/GIF/JSON export. Pixel editing includes gesture-level Undo/Redo, Clean Stroke, selection resizing, optional Right-click Transparent painting, layer safeguards, cross-layer selection copy/move, and an editor-owned Floating Palette.

The main Pixel Editor now provides an editor-owned, session-local Floating Palette with explicit color sending, custom RGBA additions, removable swatches, and permanent transparency. Persistent editor and utility windows launch independently, so minimizing or closing their launcher does not minimize or close the work window; the Floating Palette deliberately remains attached to its Pixel Editor.

Animation Studio now imports animated GIFs directly. It composites each frame onto the GIF's full logical canvas, builds an editable horizontal original/working source sheet and track, and fits GIF delays into the shared FPS plus per-frame duration model.

Character Forge now exposes only the 128px `elf-01` semantic base. Idle is a user-approved 26-frame 12 FPS loop derived from 13 manually authored poses with Blender in-betweens; Walk is the user-approved eight-frame 10 FPS edit. The installed eight-frame forward-lean/head-down Run remains the runtime baseline but is scheduled for manual replacement. All use Front, Back, Right, Left rows. Five approved region-derived starters—shirt, vest, trousers, gloves, and boots—cover every animation and direction and retain editable five-color ramps. The retired 64px base, component catalog, workbench, reserved-blue output archive, and old factory source/tests are preserved under `assets/character-forge/legacy_sources/pre-semantic-elf-20260821/` outside runtime discovery.

The main Preview Process workflow now includes Cluster Cleanup, a deterministic four-connected component pass that absorbs exact-color islands at or below a configurable threshold into structurally adjacent same-alpha regions. It preserves dimensions, transparency boundaries, hard pixel edges, and the input RGBA palette while using shared boundary, Lab similarity, neighbor area, and row-major order for stable merge selection.

A headless Blender 5.1 pipeline maintains the canonical semantic mannequin with 32 anatomical IDs, all 13 slot/hide masks, 17 attachment landmarks, protected topology/weights/material/actions, and deterministic inspection. Manual finalization supports arbitrary frame counts. The interpolation pass proves all 13 authored Idle poses unchanged, exposes 13 Blender-generated in-betweens, and produces 26 visible frames with closure frame 27. Idle, Walk, and Run now each have ordinary art, exact ID sheets, color previews, individual frames, all slot/hide masks, direction strips, native-speed GIFs, and hash-linked manifests.

## Blockers
None. Idle and Walk have received user visual approval. Run awaits manual pose revision, and the five starter items are intentionally basic pipeline proofs rather than final costume art.

## Current Decisions
Use `.project-command/project.json` as provisional Command Center V1 project metadata.

Use `docs/CURRENT_STATE.md` as the project pulse for Command Center re-entry.

## Assumptions
The repository should be registered in Command Center as `pixel-forge` / `PixelForge`.

The project is an active personal/lab project unless the owner reclassifies it.

## Known Gaps
Command Center's final manifest schema is not implemented yet, so `.project-command/project.json` is provisional.

No formal task-source file was found during this setup pass.

Palette PNG assets are now tracked under `palettes/`; their color contents were not reviewed during this setup pass.

The base pixel art remains a deterministic reduction of 3D renders and will benefit from deliberate face/silhouette cleanup. Starter garments follow anatomy exactly and therefore read more like fitted base clothing than authored loose geometry. Hair, headwear, facial details, outer silhouettes, and component geometry beyond the five proofs remain future work.

## Next Actions
Edit `animation_images_models/elf_bald_female/editable/run_redo_v1.blend`, review the revised Run from front and side, then finalize, render, and promote it only after approval. Component experiments can use the tracked Idle/Walk bases and semantic guides indexed in `assets/character-forge/AUTHORING.md`.

Review the `category`, `status`, and `priorityRank` values when registering the project in Command Center.

Update this document after commits or other git state changes made during agent sessions.

Use `tools/build_semantic_character_forge.py` to regenerate the live base and five starters after semantic-package changes. The retired factory remains an archive, not an active generation route.

## Recent Activity
2026-08-28: Recorded user approval of the semantic elf Idle and Walk, packaged a self-contained Git LFS Run redo project containing both the current-baseline and original-Meshy eight-pose edit actions plus protected source actions, and added a transfer-safe Character Forge authoring index for the tracked Idle/Walk base sheets, region sheets, frames, strips, slot masks, and hide masks. The portable Blender project reopens with exact baseline poses and closure and requires no external files.

2026-08-28: Audited the repository publication boundary and prepared the complete August 20-21 semantic-elf/Blender working set for commit and remote publication. Kept the intentionally removed Mixamo backup and superseded review visualizations outside the repository, confirmed raw acquisition and working files remain ignored, and verified the active suite passes with 169 tests.

2026-08-21: Completed the semantic-elf Character Forge cutover. Doubled the user's 13 authored Idle poses into a 26-frame 12 FPS loop through audited Blender interpolation, rendered and byte-checked its four-direction 128px art/semantic package, retained the approved Walk, rendered the approved corrected Run, and installed all three as the sole live `elf-01` base. Added five full-coverage recolorable region-derived starters (shirt, vest, trousers, gloves, and boots), contact sheets, and runtime tests. Archived the old 64px base, all old components/workbench/sources, the 2,461-file reserved-blue output tree, retired factory source/tests, and stale root handoff guidance outside discovery; the active suite passes with 169 tests.

2026-08-21: Audited the user's `idle_more_frames.blend` save and formalized its intended 13-pose loop. Preserved the artist file untouched, removed accidental frame-0 keys only in a derived pipeline copy, rebuilt frame 14 as an exact frame-1 closure, set derived playback to frames 1–13, and retained the saved 6 FPS. Generalized the non-destructive finalizer, paired semantic renderer, and 128px semantic package builder for variable frame counts and sequence names; the Idle remains staged and unrendered pending visual approval, and the full suite passes with 212 tests.

2026-08-21: Removed the abandoned third-party motion-retarget experiment after auditing the canonical mannequin and all active authored/Meshy editing and rendering blends for dependencies. Deleted its repository assets, profiles, recipes, tools, validators, fixtures, six dedicated tests, ignore/LFS policy, generated comparisons, staged actions, and documentation; the removed local binary artifacts were moved to a recoverable sibling backup outside the repository. The canonical mannequin and current Idle/Walk/Run manual pipeline are unchanged, and the remaining full suite passes with 211 tests.

2026-08-21: Generated the first complete staged 128x128 semantic package from the manually edited `PF_Walk_Meshy_Edit`: a 1024x512 ordinary art sheet and exact region-ID sheet, color inspection sheet, four strips and native 10 FPS GIFs, individual art/ID/preview frames, all 13 placement masks, all 13 body-hide masks, shared palette, and a frame-level hash manifest. The paired Blender renderer keeps beauty and flat anatomical passes camera/pose-identical; deterministic reduction labels every opaque art pixel, preserves all 32 anatomical IDs across the package, and leaves the existing 64px and Character Forge assets untouched.

2026-08-21: Validated the first manually edited `PF_Walk_Meshy_Edit`: all eight poses contain intentional multi-bone edits, playback remains 1–8 at 10 FPS, and frame 9 exactly closes frame 1. Added a non-destructive finalizer that preserves evaluated poses 1–8, removes stray/outdated keys, rebuilds closure frame 9, and writes an audit manifest; generated four-direction source renders, a shared 16-color 64×64 sheet, and 10 FPS GIF previews while leaving the artist save and Character Forge untouched.

2026-08-21: Documented the imported Meshy Hips bone's asymmetric display tail versus its centered transform head, warned against rest-rig correction in Edit Mode, and added explicit local bone-axis rotation instructions for free pivot rotation, axial twist, perpendicular bend, and the Local rotation gizmo.

2026-08-21: Corrected the beginner keyframing instructions for Blender 5.1: `I` now commonly inserts silently rather than opening the older keying-set menu. The guide, cheat sheet, and embedded Blender quickstarts now lead with the visible right-click `Insert Keyframe with Keying Set...` route, explain existing key diamonds, and retain `I` as the faster shortcut.

2026-08-21: Rewrote the Blender animation-editing documentation for a first-time Blender user with explicit file opening, workspace setup, action selection, Pose Mode, navigation, keyframing, frame-1/frame-9 loop maintenance, preview, saving, recovery, and troubleshooting steps; added a separate compact basic-controls cheat sheet beside it.

2026-08-21: Prepared a canonical-mannequin Blender teaching file around the authored Idle, original 32-frame Meshy Walk, and untouched 20-frame Meshy Run. It provides three independent exact eight-pose editable copies, action-specific markers, 10 FPS preview, embedded guidance, protected full actions, source-hash and pose validation, and no Character Forge promotion.

2026-08-21: Promoted the elf pilot into a canonical semantic mannequin with 32 anatomical regions, 13 placement/hide-mask pairs, 17 attachment landmarks, exact-color debug assets, six-view and per-slot inspection renders, invariant validation, Git LFS policy, and an empty topology-guarded override layer.

2026-08-21: Authored `PF_Idle` from the clean bind pose as a deliberately restrained 48-frame breathing and upper-spine sway loop with locked feet/pelvis, a controlled head, no arm swing, and an exact duplicate closure at frame 49. Added eight-frame Idle capture to every direction, regenerated the shared 16-color pixel proof and 10 FPS previews, verified every sampled direction has eight distinct frames, byte-verified the complete Idle/Walk/Run output set, and confirmed the full suite remains green with 201 tests.

2026-08-21: Advanced the elf Blender pilot through a complete deterministic pixel proof. Added a reusable converter that performs premultiplied 64px downsampling, binary alpha, one shared 16-color animation palette, non-dithered perceptual mapping, conservative one-pixel color cleanup, four-direction sheets, and 10 FPS review GIFs; manifests record all settings and hashes, `--check` byte-verifies regeneration, three focused tests cover layout, source immutability, transparency/palette constraints, GIF timing, invalid rows, and change detection, and the full suite passes with 201 tests.

2026-08-21: Added the reference-guided `PF_Run_ForwardLean_HeadDown` action as a reversible derivative of the untouched Run, retaining the slight distributed torso lean while pivoting the neck nine degrees forward. Rendered full-cycle front/side comparisons and regenerated the provisional four-direction Run sheet from the selected posture without changing Walk, leg motion, foot contacts, or timing.

2026-08-21: Implemented the first reproducible headless Blender character pipeline for the supplied `elf_bald_female` Meshy exports. Verified identical 100,029-vertex meshes and 24-bone rigs across Bind/Walk/Run, rebuilt and packed the PBR material, produced a reusable master `.blend`, rendered motion diagnostics, generated provisional eight-frame four-direction 64x64 Walk and Run sheets, and baked a reversible slight-forward-lean Run variant for visual comparison; the full regression suite passes with 198 tests.

2026-08-20: Produced a marked-up Meshy rigging reference that places anatomical chin/neck, shoulder, elbow, wrist, pelvis, knee, and ankle targets over the supplied setup screenshot, with a skeletal centerline guide and emphasized humeral-head placement; the reference is retained under `output/imagegen/`.

2026-08-20: Prepared a male Meshy modeling reference by deterministically removing the redundant three-quarter figure from the supplied four-view render, then using a guarded `gpt-image-2` wardrobe edit to replace ornate lower-body armor with a plain opaque athletic base outfit. The visually reviewed three-view result and separate Front, Side, and Back crops are retained under `output/imagegen/`.

2026-08-20: Generated and visually reviewed a high-quality three-view Meshy reference from the supplied adult elf turnaround using the `gpt-image-2` edit API. The new opaque narrow-strap athletic base outfit removes shoulder, armpit, forearm, leg, and foot obstructions while preserving consistent Front, Side, and Back views; the PNG is retained under `output/imagegen/` for local 3D-model iteration.

2026-08-20: Fetched and pruned every remote branch and tag. `main` remains exactly aligned with `origin/main` at `c7f31a3`; the newly published five-commit `origin/agent/publish-processing-palette-assets` line is now available through a matching local tracking branch at `27c2c53`, and the existing local ignore/rollback notes were preserved.

2026-08-19: Reverted the unsuccessful semantic Run-base experiment in full, restoring the prior authoritative mixed-length Run artwork, playback metadata, generator, tests, and documentation byte-for-byte. The purchased `assets/Top-Down Asset Pack/` remains intentionally ignored and untracked as a local-only reference; the discarded generated experiment was moved to a recoverable temporary backup outside the repository.

2026-08-19: Added the user-supplied `hk-between-essence-32x.png` and `ludpiratepalette64-32x.png` RGBA palette strips to tracked project assets; both files were format- and geometry-validated before publication on `agent/add-palette-assets`.

2026-08-19: Synchronized this checkout with `origin/main` at `dbe72d3`, bringing in the merged animation/editor workflow plus the subsequent animation-preview fixes and cluster-aware image cleanup; metadata-only local state note, with the pulled code otherwise matching the remote.

2026-08-19: Added Cluster Cleanup to the live Preview Process workflow with a 1–32 pixel threshold, array-backed exact-RGBA component labeling, deterministic boundary-first merging, conservative same-alpha transparency handling, reusable public Lab color helpers, focused processing documentation, and regression coverage; a 1448x1086 quantized-style benchmark completes in about 0.23 seconds and the full suite passes with 198 tests.

2026-08-19: Fixed Animation Studio onion-skin compositing so neighboring frames render above the transparency checker, added a one-shot Drag Select Colors palette workflow that restores the prior tool, and lifted Preview output controls to each selected region's native dimensions for resize-free filtering; the full suite passes with 189 tests.

2026-08-19: Fast-forwarded `main` from `37512c8` to `beb9fe5`, integrating and publishing `agent/upgrade-animation-and-editor-workflows`.

2026-08-19: Prepared the complete Animation Studio, Floating Palette, independent-window, and authoritative Character Forge movement update for publication on `agent/upgrade-animation-and-editor-workflows`. All new source art, manifests, deterministic builders, metadata, documentation, and regression coverage are included; the full suite passes with 186 tests and the component pipeline validates 3 animations, 35 ideas, and 30 production components.

2026-08-19: Promoted the latest supplied Walk and four Run direction strips as Character Forge's authoritative animation sources. Walk is now an exact all-row passthrough with four normal forward loops. Run is rebuilt pixel-exactly as a 512x256 mixed-length sheet with six Front, eight Back, six Right, and six Left frames; Character Forge and the component pipeline now support per-direction counts, Right `6,5,4,3,2,1,2,3,4,5` and Left `1,2,3,4,5,6,5,4,3,2` ping-pong preview cycles, and normal Front/Back loops. Canonical pipeline validation passes and the full suite passes with 186 tests.

2026-08-19: Added explicit animated-GIF import to Animation Studio. Imported GIF frames become a horizontal linked-sheet track that is immediately available in Source Sheet, Frame Editor, timeline, and playback views; original and edited pixels plus fitted variable timing round-trip through `.pfa`. GIF loop metadata maps to Loop or Once, the current palette is retained, and the full suite passes with 185 tests.

2026-08-18: Added the main Pixel Editor's compact Floating Palette with current-color/transparent initialization, explicit right-click sending from the project palette, custom RGBA additions, removable local swatches, per-editor session retention, and editor-relative always-on-top behavior. Decoupled every persistent editor/tool launch route from Qt parent-window minimization while retaining modal ownership, added comprehensive offscreen coverage, and fixed deterministic Character Forge JSON line endings for Windows checkouts; the full suite passes with 181 tests.

2026-08-18: Merged the Animation Studio feature branch into `main`, brought all remote branches into local tracking, and integrated the user's new `walk_double_pauldrons_working.png` as an exact authored Front + Back Walk overlay. Right/Left continue to fall back to the base; the generator, manifest coverage, provenance, workbench indexes, documentation, and tests were updated for multi-direction authored starter sheets, and the full suite passes with 172 tests.

2026-08-18: Prepared the complete authored Character Forge component update for publication, including the Frost Blue Hair and revised Double Pauldrons source art, regenerated runtime/workbench assets, reusable hood-driven hair alpha occlusion, documentation, and regression coverage; the full suite passes with 155 tests.

2026-08-17: Refreshed the authored Double Pauldrons Front Walk overlay from the user's revised `walk_double_pauldrons.png`, updating the runtime sheet, provenance hash, and workbench previews while preserving exact source bytes and front-only coverage.

2026-08-17: Integrated the user's authored six-frame Double Pauldrons sheet as the durable `workbench-double-leaf-pauldrons` Front Walk overlay. Character Forge uses the supplied pixels exactly, preserves base-only fallback outside Front Walk, records source provenance, and protects the artwork from semantic-starter regeneration.

2026-08-17: Added reusable, manifest-driven component alpha occlusion through `alphaOccludedByTags`. The authored Frost Hair now opts into the `hooded_cloak` tag, causing every selected hooded cloak's actual animation alpha to mask the hair behind hood fabric while preserving visible bangs through transparent face openings.

2026-08-17: Integrated the user's authored six-frame Frost Blue Hair sheet as the durable `workbench-messy-frost-hair` Front Walk overlay. Character Forge now renders the supplied pixels exactly in all six Front frames, retains base-only fallback for other directions and animations, records authored-source provenance, and protects the artwork from semantic-starter regeneration.

2026-08-17: Fast-forwarded local `main` from `cb41d6f` to `7131c7a`, bringing it fully in sync with `origin/main`; refreshed the local virtual environment from `requirements.txt`, regenerated deterministic metadata after Windows checkout line-ending conversion, and verified the full suite passes with 154 tests.

2026-08-18: Brought the complete project worktree under version control for publication, including the Animation Studio, gesture-level Undo/Redo, the final Character Forge Walk correction and dependent cloak assets, the saved `.pfa` project, and the full 2,461-file art-generation/review pipeline archive. Local environments, caches, and secret-bearing `.env` files remain ignored; the full suite passes with 171 tests.

2026-08-17: Promoted the supplied final Walk sheet into Character Forge with one deliberately narrow transform: Front, Back, Right, and the three transparent bottom rows remain pixel-identical, while only Left is reattached in exact frame order `6,5,4,3,2,1`. Rebaselined the canonical runtime checksum, updated source provenance, and regenerated all ten full-direction semantic cloaks into the matching same-phase Right/Left order; component validation reports three animations, 35 ideas, and 30 production components, and the full suite passes with 171 tests.

2026-08-17: Rebuilt the non-launching Animation Editor as a two-pane linked-sheet Animation Studio with pixel-aligned source selection, signed X/Y frame strides, named direction tracks, overlap-aware editing, core pixel tools, onion skinning, timeline playback and timing, frame-difference analysis, global sheet Undo/Redo, original/working-sheet `.pfa` archives, and PNG/GIF/JSON export. Playback now offers persisted Once, Loop, and Ping Pong modes; Ping Pong reverses through the selected range without duplicated turnaround frames and exports the matching GIF sequence. Both the regular Pixel Editor and Animation Studio now expose Undo Last Action controls and Ctrl+Z, with each brush drag, shape, stamp, or moved selection recorded as one action; no-op gestures preserve Redo. The canonical 384x259 Walk sheet passes the four-direction six-frame acceptance workflow without modifying its extra bottom rows, and the full suite passes with 171 tests.

2026-08-17: Prepared and staged the complete verified Pixel Forge worktree for repository publication, including editor workflow improvements, corrected character Walk timing, deterministic component tooling, all current generated and authored art plus source archives, and the eleven-item silhouette workbench. The root `.env` and local virtual environment remain ignored; the full suite passes with 154 tests and the component pipeline validates 30 registered components.

2026-08-17: Built an overnight component-silhouette workbench from the user's eleven requested concepts: messy hair, one pauldron, gloves, eyepatch, double pauldrons, mage hat/vestments, leather armor, ratty shawl, headband, orcish armor, and a horned cult mask. Each starter has six aligned Front Walk frames, an exact-color editable `regions.png`, a stable preview, manifest provenance, Character Forge wiring, fallback behavior, visual indexes, and a pickup guide; the AI-generated board is retained as reference only and contributes no pixels to production overlays, and the full suite passes with 154 tests.

2026-08-16: Corrected both side-view Walk cycles after diagnosing reversed contact-foot motion rather than a missing boomerang playback mode. The repaired authored sheet (including the user's four-pixel Left artifact removal) is preserved by hash; Right now plays `1,2,3,6,5,4`, Left is rebuilt as a same-phase per-frame mirror with its original `-1,-1` alignment, all ten full-direction cloak overlays follow the identical order/offset, the canonical Walk checksum was intentionally rebaselined, and the full suite passes with 151 tests.

2026-08-16: Preserved the supplied two-region `walk_warlock_robe.png` semantic source byte-for-byte and generated four stable six-frame Front Walk Outerwear treatments—Void Amethyst, Blood Ritual, Necrotic Jade, and Astral Midnight. All four retain the exact robe/trim silhouette, record source/output hashes, regenerate byte-identically, appear in Character Forge without reserving Headwear or Neck, fall back exactly outside Walk/Front, and pass the full suite with 149 tests.

2026-08-16: Promoted the supplied `walk_hooded_cloak.png` into the durable canonical semantic Walk source: preserved the authored file byte-for-byte, retained Front/Back/Right, created Left as an exact per-frame horizontal mirror of Right, added the authored hood-panel region, regenerated all six existing cloaks across every Walk direction, and added Royal Amethyst, Midnight Raven, Desert Sand + Teal, and Ivory + Crimson variants. All ten are wired into Character Forge with source/output hashes and reproducible manifests; the superseded Front-only semantic source is archived, and the full suite passes with 146 tests.

2026-08-16: Migrated the remaining larger-hood Pointed, Burgundy, and Winter Gray cloak selections to the complete six-frame semantic model. The runtime Outerwear catalog now contains only six small-hood semantic cloaks; the three legacy source/manifests are hash-preserved under `legacy_sources/old-model-cloaks/`, Pointed Green and Winter Gray gained stable semantic presets, Burgundy was relabeled as its semantic replacement, and the full suite passes with 145 tests.

2026-08-16: Removed the superseded three-frame Semantic Forest cloak and the non-semantic Muddy Field Boots from Character Forge, then regenerated Winter Gray and Blackened Iron as stable palette-only treatments with all seeded light-blue edge speckles and toe glints removed. Visual inspection confirms clean frame-to-frame color behavior, removed IDs are regression-tested as absent, and the full suite passes with 144 tests.

2026-08-16: Processed the completed six-frame `color_regions_test_2.png` semantic cloak source into four full Walk/Front Character Forge components—Forest Wool, Burgundy Velvet, Storm Blue & Silver, and Autumn Russet—using a shared locked 1,246-pixel semantic mask, five-step material palettes, stable directional shading, continuous trim, and clasp-relative folds. All four outputs reproduce byte-identically, alter every authored Front frame, fall back exactly for unsupported directions and animations, and pass visual composition review; the full suite passes with 146 tests.

2026-08-16: Implemented the first semantic-region Silhouette Finisher prototype from the supplied `color_regions_test.png`: exact marker extraction removed all exposed base pixels, locked the combined 638-pixel silhouette across Walk/Front frames 1, 2, and 4, and produced a selectable forest-wool cloak using separate outer-fabric, lining, gold-trim, and bronze-hardware palettes with stable lighting and clasp-anchored folds. The stored regions and output reproduce byte-identically, unsupported frames/directions fall back to the base, and the full suite passes with 143 tests.

2026-08-16: Added a reproducible non-destructive component-variant generator and exposed six derived Front Walk examples in Character Forge: crimson and cream/indigo shirts, blackened-iron and mud-weathered boots, and burgundy/gold-trim and snow-dusted winter cloaks. Every output preserves its source silhouette, records source/output hashes and fixed seeds, falls back exactly outside Walk/Front, passes visual composition review, and reproduces byte-identically under `--check`; the full suite passes with 140 tests.

2026-08-16: Registered the supplied pointed hooded cloak as an incomplete Outerwear component covering all six Walk/Front frames, preserved its source pixels with only the canonical three transparent Walk rows appended, reserved Headwear and Neck while equipped, visually verified it both alone and over the default shirt, and confirmed exact base fallback for all unsupported directions and animations; the full suite passes with 137 tests.

2026-08-16: Added a visible Right-click Transparent Pixel Editor option that gives right-click the transparent-color behavior of brush dragging, Clean Stroke, mirror, Shift-fill, line, and ellipse gestures without changing the selected left-click color or non-paint right-click actions; the full suite passes with 136 tests.

2026-08-16: Hardened Pixel Editor layers with a persistent high-contrast editing-layer banner, bold active-row treatment, visibility checkboxes that no longer change the edit target, automatic stale-selection clearing on layer switches, named confirmation before active-layer deletion, blocked canvas edits on hidden active layers, compact layer-management controls, and coordinate-preserving Move/Copy Selection actions targeting any existing layer with atomic cross-layer Undo/Redo; the full suite passes with 133 tests.

2026-08-16: Replaced the generic component-generation prompt with an immutable-raster paper-doll specification containing slot-specific fit contracts, exact direction-row mapping, design consistency rules, pixel-art constraints, and a preserve-original fail-safe; generated ten new one-candidate Idle tests through `gpt-image-2`, with ten API successes, complete frame coverage, zero reserved-blue leaks, and no promotion-ready result because every candidate still fails palette complexity. Visual review identified the short wool travel coat and quilted gambeson as the strongest cleanup candidates; the full suite passes with 125 tests.

2026-08-16: Integrated the latest `main` Clean Stroke painting and selection resize work with the complete Character Forge and component-production branch while preserving both pixel-canvas workflows.

2026-08-16: Validated and prepared the complete Pixel Forge worktree for integration, including Character Forge, the component pipeline and review tooling, palette and shade-ramp improvements, UI refinements, documentation, tests, and all current art under `assets/`; the full suite passes with 124 tests.

2026-08-16: Added the manually authored Leather Boots as an incomplete Feet component covering all six Walk/Front frames, stripped the lower-row base references from its production overlay, and verified unsupported directions and animations fall back exactly to the authoritative base.

2026-08-16: Added root-level `HANDOFF.md` for post-reboot continuity, recording the dirty-worktree warning, paused generation state, manual/hybrid component direction, pending Jewelry and Eye / Face slot decisions, shade-ramp verification, concept references, and safe next steps; documentation-only with no runtime change.

2026-08-16: Replaced the Pixel Editor's clipped four-stop fixed-offset shade ramp with a visually audited six-stop ramp containing three adaptive cool shadows, the exact selected base, and two adaptive warm lights; added neutral-color temperature handling, compact six-swatch UI coverage, updated the ramp reference, and verified the full suite passes with 123 tests.

2026-08-16: Completed a visual audit of all 63 pilot candidates across model output, extraction, and reconstruction; found zero production-ready candidates and zero coherent three-animation components, documented per-category verdicts and the recommendation to pivot to hybrid hand-authored topology families in `COMPONENT_FACTORY_FINDINGS.md`, and kept the remaining generation queue paused.

2026-08-16: Added the root-level `COMPONENT_FACTORY_FINDINGS.md` reference documenting pilot failures and proposed remediation for fuchsia contamination, mask-fill boxes, foreign/redrawn mannequins, reversed heads, palette and frame failures, contextual cleanup, and review-tab zoom; this was documentation-only and did not change runtime behavior.

2026-08-16: Added the reversible reserved-blue mannequin generation ramp, position-aware canonical reversal, border-background cleanup, processing provenance, and resumable permanent-error handling; completed the seven-component pilot with 63/63 API responses, zero moderation failures, zero blue leaks, and all candidates safely held for palette/coverage cleanup; the full suite passes with 111 tests.

2026-08-16: Implemented the Pip & Pyre Component Factory and manifest-driven Character Forge runtime, rebuilt Run from all four authoritative strips, migrated the shirt to the `torso`/Tops slot, queued 105 credential-free bootstrap jobs, and verified the full suite passes with 103 tests.

2026-08-15: Disabled hover tooltips application-wide across Pixel Forge and all editor/tool windows while retaining visible labels and other status UI; the full suite passes with 92 tests.

2026-08-15: Promoted the authoritative six-frame Run Front/Left/Right strips into a 384x256 combined sheet with a clearly provisional repeated legacy Back row, and added recipe-persisted main-color selection that remaps the walking shirt's exact nine-shade ramp while preserving outlines; the full suite passes with 91 tests.

2026-08-15: Resynced Character Forge to the final authoritative corrected Walk base revision (`a1841bea…`) while preserving its native transparency, dimensions, direction layout, and 48 opaque white eye pixels; verification remains green.

2026-08-15: Made Character Forge base-matte handling animation-specific so the corrected transparent Walk sheet preserves all 48 opaque white eye pixels while legacy Idle/Run sheets still clear their white mattes; the full suite passes with 89 tests.

2026-08-15: Replaced Character Forge's walking base with the corrected authoritative transparent sheet, rebuilt the shirt overlay directly from its authored front row, and updated byte-provenance coverage; the full suite passes with 88 tests.

2026-08-15: Registered the first manually authored Character Forge shirt as a walk-only Top part, removed accidentally exported base-reference pixels, retained all six authored front-facing cells, and verified unsupported directions/animations fall back exactly to the base; the full suite passes with 88 tests.

2026-08-15: Removed all generated Character Forge placeholder parts and their generator, returning the library and default recipe to base-only while preserving the slot, persistence, rendering, and export infrastructure for manually authored assets; the full suite passes with 88 tests.

2026-08-15: Added Character Forge with locked supplied base sheets, all seven modular slots, aligned starter overlays, integer-zoom directional animation preview, seeded randomization, local JSON recipe save/load, exact-size PNG/JSON export, Pixel Forge part-sheet editing handoff, and focused regression coverage; the full suite passes with 88 tests.

2026-08-08: Replaced the destructive, grid-scaled Import Sprite underlay with a native-resolution floating stamp that preserves existing pixels, follows the cursor, and commits only on a canvas click; the full suite passes with 81 tests.

2026-08-08: Added compact 2×–16× integer downscale presets beside the preview W/H controls, driven by the selected source region and setting both output dimensions plus Fit in one action; the full suite passes with 80 tests.

2026-08-08: Made main-preview and pixel-editor palette extraction/import load every distinct visible RGBA color by default, with the existing perceptual reduction explicitly opt-in in both surfaces; the full suite passes with 78 tests.

2026-08-08: Compacted the main-view Output and Palette & Quantization panels by merging resize and post-process controls, removing redundant preview-size and quantization-status labels, reducing palette actions to two rows, and default-collapsing advanced extraction controls; the full suite passes with 74 tests.

2026-08-08: Collapsed palette-sampling posterize settings into a compact, clearly labeled activation row that hides all detail controls when inactive while retaining manual collapse when active; the full suite passes with 73 tests.

2026-08-08: Added a Select All control beside Drop that detects the imported image resolution, fills the rectangle W/H controls, and replaces partial regions with a full-image selection; the full suite passes with 72 tests.

2026-08-08: Added a header-toggleable, non-destructive pixel-distance measurement overlay with click-move-click placement, precise Euclidean labels, right-click clearing, and focused UI/canvas tests; the full suite passes with 70 tests.

2026-08-07: Committed the complete image-processing, transparency, palette-consolidation, and test changes on `agent/image-processing-palette-workflow` and prepared the branch for remote publication.

2026-08-07: Added alpha-aware Area and Lanczos 3 resizing, denoise/despeckle processing, redo-capable history, and consolidated palette generation plus explicit quantization/dithering into one active-palette workflow; removed the automatic Limit Colors and palette-debug panes, with 67 tests passing.

2026-06-26: Committed Clean Stroke paint dragging, selection resize handles, and Command Center sync notes for remote push.

2026-06-26: Prepared Clean Stroke paint dragging and selection resize handles for commit and remote push after syncing home changes from `origin/main`.

2026-06-26: Pulled `origin/main` to `1cbf604`, reapplied local editor changes after resolving one signal-setup conflict, dropped the temporary stash, and verified focused pixel-canvas tests pass.

2026-06-26: Prepared isometric guide overlay controls, stamp flip actions, related canvas tests, and removal of a root ballista asset for commit and remote push.

2026-06-19: Added collapsible multi-column pixel-map tooling, ellipse-drag pixel-canvas drawing with tests, new palette family PNGs, and a root ballista asset.

2026-06-17: Pulled `origin/main` to `296bb15`, reapplied local pixel-canvas ellipse-drag work after one conflict, cleared the temporary stash, and verified the test suite passes.

2026-06-17: Implemented tunable palette posterize/debug tooling, art-direction-aware palette families, and draw-selection perimeter fill for the pixel editor.

2026-06-15: Prepared pixel-canvas line drawing, assembly-grid tilesheet export, a tile-layout test, and the `brushwood_wall` palette asset for commit and remote push.

2026-06-07: Prepared all Command Center setup files and `palettes/` PNG assets for commit and remote push.

2026-06-07: Metadata-only Command Center setup added provisional project manifest, current-state document, and AI-agent guidance.

Recent git history includes selection copy workflows, transparency keying, palette sampling, and texture generator updates.

## Service Notes
No long-running services, backend processes, health URLs, or service suites were found. The app launch command is `python main.py`. The live semantic Character Forge asset builder is `python tools/build_semantic_character_forge.py --force`; it is deterministic and does not use an external image service. The retired 64px component-generation CLI is archived and is not an active service or supported runtime route.
