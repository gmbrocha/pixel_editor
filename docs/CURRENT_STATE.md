# Current State

Last updated: 2026-08-29

## Summary
PixelForge is a PySide6 desktop pixel-art and tileset utility. Source-grounded tools include image import and preview extraction, palette handling, pixel editing, animation editing, modular Character Forge assembly/export, tile layout, tileset processing, tileset template generation, and procedural texture generation.

## Current Status
The Animation Editor is a functional two-pane Animation Studio with signed-stride direction tracks, linked sheet editing, pixel tools, onion skinning, Once/Loop/Ping Pong playback, analysis, Undo/Redo, `.pfa` persistence, GIF import, and PNG/GIF/JSON export. Pixel editing includes gesture-level Undo/Redo, Clean Stroke, selection resizing, optional Right-click Transparent painting, layer safeguards, cross-layer selection copy/move, and an editor-owned Floating Palette.

The main Pixel Editor now provides an editor-owned, session-local Floating Palette with explicit color sending, custom RGBA additions, removable swatches, and permanent transparency. Persistent editor and utility windows launch independently, so minimizing or closing their launcher does not minimize or close the work window; the Floating Palette deliberately remains attached to its Pixel Editor.

Animation Studio now imports animated GIFs directly. It composites each frame onto the GIF's full logical canvas, builds an editable horizontal original/working source sheet and track, and fits GIF delays into the shared FPS plus per-frame duration model.

Character Forge now exposes four approved 128px bases: Elf female, Tiefling female, Dwarf male, and muscular Human male. Each has Idle, Walk, and Run in Front, Back, Right, Left rows. Idle uses 14 sampled runtime columns at 6 FPS: both weight shifts play consecutively at normal speed, then runtime frame 13 holds for 1500 ms before the loop restarts; its 26-frame Blender action remains intact. Walk and Run use eight frames at 10 FPS. The catalog contains the five original elf starters, 25 new component families fitted independently to all four bases, plus incomplete user-authored Tiefling Low Run hair and blindfold components, for 107 selectable entries total. The hair preserves authoritative Front, Back, and Right artwork, derives Left by mirroring the complete Right composite, and remaps all five authored shades through Main Color. It uses the canonical two-layer contract: `hair_back` behind body/clothing and `hair_front` above them, with explicit show/clip/hide policies on headwear. The blindfold preserves all four authored directions and renders on `face_accessory_under_hair`, so its pixels remain visible only where the selected hair alpha does not cover them. The Tiefling Ankle Boots, Cap-Sleeve Field Shirt, and Cropped Training Top also use approved Run overrides with exact Front, Back, and Right art plus a complete-composite Right-to-Left mirror. The less-muscular Human remains excluded. Retired 64px runtime assets, the old component catalog/workbench, reserved-blue prototypes, and factory sources/tests have been removed from the repository.

Character Forge camera height is now a canonical recipe and UI dimension. Every approved base and motion has exactly three orthographic views: Near Top-Down at 70 degrees, Three-Quarter at 45 degrees, and Low at 28 degrees. The camera choice is independent of the Front, Back, Left, and Right direction choice. All current components have Low-view coverage only and are gated by both camera and fitted base.

The user-facing elf label is `Elf Female Base`. Its Low view is normalized from a 99px median figure height to 79px, matching the Tiefling and Human Low framing while retaining semantic regions and components. The Dwarf uses a 1.12 framing multiplier at all three heights, producing approximately 71px Low and 61px Three-Quarter median heights versus 79px and 67px for the full-height models.

The main Preview Process workflow now includes Cluster Cleanup, a deterministic four-connected component pass that absorbs exact-color islands at or below a configurable threshold into structurally adjacent same-alpha regions. It preserves dimensions, transparency boundaries, hard pixel edges, and the input RGBA palette while using shared boundary, Lab similarity, neighbor area, and row-major order for stable merge selection.

A headless Blender 5.1 pipeline maintains the canonical semantic elf mannequin and tracked approved target mannequins. The Tiefling artist save is preserved untouched; its evaluated frames 1–26 were consolidated into a clean approved action without the stray frame-0 keys. Tiefling female, Dwarf male, and muscular Human male canonical blends each retain protected source/transfer actions beside separate approved Idle, Walk, and Run actions. Their runtime sheets, exact-timing GIFs, hashes, palettes, and reproducible promotion manifests are tracked.

## Blockers
None. All four configured models, their three motions, and the 25 four-base Low-view component families are promoted. The canonical preprocessing pass is part of the live family generator, approved manual replacements are hash-linked overrides, and all 300 live animation sheets are byte-identical to the editable `component_cleanup_v2` mirror. Generated garments without overrides remain editable first-pass pixel assets rather than final hand-cleaned costume art.

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

Elevated Character Forge camera views do not yet have semantic region maps or angle-specific component sheets. All current component entries are intentionally available only at Low.

The base pixel art remains a deterministic reduction of 3D renders and will benefit from deliberate face/silhouette cleanup. Generated garments follow each model's rig-derived anatomy and therefore read more like fitted base clothing than authored loose geometry. The target models have fitting-region sheets but not the elf's complete per-frame semantic packages, slot/hide masks, or elevated-view regions. Hair, facial details, loose authored silhouettes, and elevated component variants remain future work.

The superseded cleanup-v1 and transitional 14-frame component bundles have been removed. `component_cleanup_v2` is the sole editable mirror of the promoted 100-family-variant baseline; approved manual edits must also be registered in the canonical component-override manifest so regeneration preserves them.

## Next Actions
Use the four live Character Forge bases and all three camera heights for runtime review. Continue manual edits from the 300 live mirrors indexed by `animation_images_models/component_cleanup_v2/index.csv`; every Idle sheet has 14 columns. Register later approved hand edits in `animation_images_models/component_override_sources.json` and promote them before rebuilding the family catalog and cleanup mirror. Add elevated-view semantic/component sheets only as a later approved phase. Component experiments can use the tracked elf semantic guides and target fitting-region sheets indexed in `assets/character-forge/AUTHORING.md`.

Review the `category`, `status`, and `priorityRank` values when registering the project in Command Center.

Update this document after commits or other git state changes made during agent sessions.

Use `tools/build_semantic_character_forge.py` to regenerate the live elf base and five starters after semantic-package changes; it preserves independently generated families. Use `tools/build_character_component_families.py` to rebuild or verify the 25 four-base families, and `tools/build_component_cleanup_bundle.py` to rebuild or verify their editable mirrors. The retired factory and its archives are no longer active repository content.

## Recent Activity
2026-08-29: Created a verified checkpoint of the approved Standard-style Character Forge before beginning the separate chibi pipeline. The checkpoint includes revised Idle timing, three-height cameras, wheel zoom, two-layer Tiefling hair, the under-hair blindfold, the three approved Tiefling Run garment overrides, their deterministic promotion tools, and a green 203-test suite with three optional transfer tests skipped.

2026-08-29: Promoted the approved Tiefling Cropped Training Top Run edit as the third canonical family override. Preserved Front, Back, and Right exactly, generated Left from Right, and enabled the same final-composite mirror contract used by the approved hair, boots, and shirt so every equipped layer stays aligned. Refreshed the live Forge family and cleanup-v2 mirror with hash-linked provenance; all three deterministic builders, 30 focused tests, and the complete suite pass with 203 tests and three optional motion-transfer tests skipped.

2026-08-29: Installed the hand-authored four-direction Tiefling Low Run blindfold as an incomplete, recolorable Face component. It preserves the supplied pixels exactly and uses the dedicated under-hair accessory layer, allowing the selected hair's actual alpha to cover the blindfold while every exposed pixel remains unchanged. Added a deterministic installer, source/hash provenance, catalog/UI gating, exact-art and overlap tests, and regeneration documentation; the complete suite passes with 203 tests and three optional motion-transfer tests skipped.

2026-08-29: Promoted the user-approved Tiefling Ankle Boots and Cap-Sleeve Field Shirt Run edits as canonical Character Forge component overrides. Front, Back, and Right rows remain byte-exact to the editable sources; Left is derived from Right and requests a final-composite mirror so the body, both garments, hair, and other selected layers stay aligned. Added hash-linked override sources and normalized outputs, made forced family regeneration preserve the approved art, refreshed cleanup-v2 as an exact live mirror, and verified all three deterministic builders, 24 focused tests, and the complete suite with 202 passed and three optional motion-transfer tests skipped.

2026-08-29: Promoted the newly approved Tiefling Low Run hair with its authoritative Front, Back, and Right rows. Added a manifest-driven final-composite direction mirror so Left is an exact horizontal flip of the fully assembled Right view rather than a potentially misaligned hair-only overlay. Expanded Run coverage to all four directions and derived the recolor ramp from all five authored opaque colors, making Main Color shift every hair shade together while retaining the two-layer hair contract for later front/back separation. The deterministic installer and 12 focused Forge tests pass; the remaining suite reports 200 passed, three optional transfer tests skipped, and the unrelated manually edited Tiefling ankle-boots cleanup sheet deselected because its manifest hash is currently stale.

2026-08-29: Added mouse-wheel zoom directly over the Character Forge preview pane while preserving and synchronizing the existing 1x/2x/4x/8x Preview Zoom selector. Wheel-up advances one zoom level, wheel-down retreats one level, and nearest-neighbor pixel scaling remains unchanged.

2026-08-29: Revised the shared Idle timing contract across Elf, Tiefling, Dwarf, and muscular Human so both weight shifts play consecutively at the normal cadence and only the completed sequence pauses. Removed the former mid-sequence hold, retained a single 1500 ms hold on runtime frame 13/authored frame 24, updated timing metadata inside all four canonical Blender files, and regenerated all 48 three-height/four-direction Idle GIFs without changing any poses or sprite-sheet pixels. Added a deterministic apply/check utility; the full suite passes with 200 tests and three optional transfer tests skipped.

2026-08-29: Consolidated the repository around the approved four-base Character Forge and canonical Blender pipeline. Removed the 2,592-file/142 MB retired Character Forge archive, obsolete cleanup-v1 and transitional 14-frame bundles, their one-shot reducer/audit, temporary component previews, approximately 2.2 GB of regenerable ignored working/extracted outputs, and 221 MB of Blender backup files. Preserved raw Meshy packages, canonical/editable Blender sources, model references, promoted runtime assets, cleanup-v2, and hand-authored component sources. Deterministic component, cleanup-mirror, and hair checks pass; the active suite reports 200 passed and three optional motion-transfer tests skipped because their ignored extracted/candidate caches were removed.

2026-08-29: Promoted all 300 preprocessed cleanup-v2 Idle/Walk/Run sheets into the 100 live four-base Character Forge component variants. Moved the one-time cleanup into the canonical family generator so forced rebuilds reproduce rather than revert the promoted art, and converted cleanup-v2 into a byte-identical editable mirror that never preprocesses a second time. All 300 live/mirror sheet comparisons match exactly; both deterministic generators and the full 204-test suite pass.

2026-08-29: Added a conservative attached-spur cleanup pass after review of the animated Tiefling ankle boots. It removes only one-pixel-wide terminal silhouette stems up to two pixels long when their attachment edge has opaque support on both sides, preserving unsupported narrow straps, toes, and fingers. Rebuilt all 300 staged editable sheets; the pass removed 13,800 spurs/13,842 pixels across 12,000 frames, including the reported ankle-boot protrusions. Deterministic regeneration passes and the full suite passes with 204 tests.

2026-08-29: Promoted the user-approved third Tiefling long-hair edit over the prior prototype while preserving its component ID and exact Front/Low Run pixels. Added the canonical two-layer hair contract (`hair_back`/`hair_front`), an under-hair face-accessory layer, and manifest-driven headwear policies: headbands show, caps/coifs clip, and guard helms hide hair. Rebuilt all family manifests and the 300-sheet cleanup bundle deterministically; all generator checks and the full 202-test suite pass.

2026-08-29: Installed the second hand-authored Tiefling long-hair edit as an incomplete Character Forge component. It is available only for Tiefling/Low, contains the authored eight-frame Front Run row, and supplies transparent Back/Left/Right Run plus Idle/Walk sheets so no missing artwork is invented. Added a deterministic installer/check and tests proving catalog/UI gating and frame-level composition coverage; the full suite passes with 201 tests.

2026-08-29: Composited the first hand-authored Tiefling long-hair Front/Low Run strip over the live base and generated native and 4x eight-frame review GIFs without promotion. Added a reusable aligned-overlay preview tool, and designated `component_cleanup_v2/new_hand_authored/` as user-owned so deterministic cleanup-bundle checks ignore it and forced rebuilds preserve its files byte-for-byte.

2026-08-29: Removed the final unconditional two-piece exemption from cleanup handwear and footwear after visual examples showed tiny remote dots being retained as the nominal second glove/boot. Second pieces now survive only when substantial or both proportionally and spatially plausible. The rebuilt bundle removes 4,203 detached clusters/34,068 pixels—340 clusters/3,374 pixels beyond the prior pass—and a fresh audit of all 12,000 frames finds zero residual clusters matching the artifact rule.

2026-08-29: Added twelve exact Low-view base sprite references to the staged component cleanup bundle—Idle, Walk, and Run for Elf, Tiefling, Dwarf, and muscular Human—under `base_sprites/` for scratch clothing, hair, and accessory authoring. The copies are hash-linked to the live Character Forge sheets and are now reproduced and verified by the bundle builder; deterministic bundle verification and the full 200-test suite pass.

2026-08-29: Tightened the component cleanup bundle's detached-artifact pass across all 12,000 component frames. Small clusters up to 16 pixels are now removed when they are under 20% of the main piece or more than six pixels away; unconditional two-piece protection is limited to actual hand/foot pairs rather than vests and hoods. A post-chamfer island-only sweep catches newly exposed specks without thinning outlines twice. Regeneration removed 3,863 clusters/30,694 pixels, the residual audit found zero matching outliers, and the full suite passes with 200 tests.

2026-08-29: Reduced canonical Character Forge Idle output from 26 to 14 exact sampled poses across all four bases, three camera heights, four directions, semantic guides, region maps, 105 components, GIFs, and the 300-sheet cleanup bundle. Runtime remains approximately five seconds through 6 FPS timing and 1500 ms holds on frames 6 and 13, while every 26-frame Blender action stays untouched. Preserved the user's original cleanup sheets and created a non-destructive 14-frame editable derivative; added a reusable runtime-timing contract and migration verifier. The full suite passes with 197 tests.

2026-08-29: Built a non-destructive component cleanup preprocessor and a separate 300-sheet editable review bundle for all 25 families and four fitted bases. The single conservative pass removes tiny detached four-connected islands, preserves intentional paired pieces, chamfers only solid one-pixel outline corners, fills only enclosed one-/two-pixel holes from the declared palette, clears hidden RGB, and records frame-level hashes and changes. Added twelve visual boards and an audit of the 15 older elf cleanup sheets; the audit preserves user files and flags the edited linen-shirt Idle's fully transparent extra 512px canvas. Bundle regeneration is byte-identical and the full suite passes with 195 tests.

2026-08-28: Added 25 recolorable Low-view component families—four tops, four outerwear pieces, six legwear cuts, three handwear styles, four footwear heights, and four headwear styles—with separate fitted variants for Elf, Tiefling, Dwarf, and muscular Human. Derived exact 32-region target fitting sheets from each canonical 24-bone rig, generated 100 variants/300 animation sheets and twelve review boards, preserved one-pixel outlines and model/camera gating, made family and region builds byte-deterministic, and verified the full suite passes with 188 tests.

2026-08-28: Created a separate editable elf-component cleanup bundle containing exact RGBA copies of all 15 current component sheets: five components across Idle, Walk, and Run. The bundle preserves canonical 128px cells, Front/Back/Right/Left row order, transparency, dimensions, and live bytes, and includes an editing index so stray pixels can be removed without modifying runtime assets directly.

2026-08-28: Reduced the five elf starter components to the one-pixel pixel-art outline minimum across Idle, Walk, and Run. Four formerly dilated components now color only their outside contour instead of the roughly three-pixel expanded-through-eroded band; the already-one-pixel vest remains at the minimum. Interior luminance shading, silhouettes, animation timing, palettes, semantic packages, and all non-component assets remain unchanged; the full suite passes with 183 tests.

2026-08-28: Renamed the user-facing semantic elf selection to `Elf Female Base`, rebuilt its formerly oversized Low beauty/semantic packages at normalized orthographic framing, and regenerated all aligned region maps, masks, components, sheets, and timed GIFs. Added a tracked per-model framing multiplier and rebuilt every Dwarf camera/animation/direction variant at 1.12 scale, making it visibly but conservatively shorter than the other bases without changing its rig or motions. Semantic, camera, target-promotion, and full-suite verification pass with 183 tests.

2026-08-28: Made camera height a canonical Character Forge recipe and UI dimension alongside base, animation, and direction. Added orthographic Near Top-Down (70 degrees), Three-Quarter (45 degrees), and existing Low (28 degrees) variants for all four approved bases and all three motions, promoted 144 timed direction GIFs plus runtime sheets under a hash-linked manifest, preserved Low assets and Low-only elf component gating, added deterministic Blender/pixel regeneration and promotion-safe metadata retention, and verified the full suite passes with 183 tests.

2026-08-28: Preserved the user's Tiefling Idle artist file and non-destructively consolidated its edited frames into a clean tracked canonical action, removing frame-0 spill only in the derived copy. Added exact per-frame timing so every approved model holds Idle frames 11 and 24 for 1500 ms, generalized Character Forge to four fit-safe bases, promoted Elf female, Tiefling female, Dwarf male, and muscular Human male Idle/Walk/Run sheets and GIFs, and retained elf-only semantic components. Target and legacy candidate regeneration checks pass, and the full suite passes with 182 tests.

2026-08-28: Promoted the user-approved revised elf Run into the live 128px semantic `elf-01` base and regenerated all five region-derived starters. Consolidated exact approved Idle, Walk, and Run actions into the tracked canonical mannequin beside protected Meshy sources, added a hash-linked self-checking motion profile and reusable three-target transfer pipeline, and generated deterministic Tiefling female, Dwarf male, and muscular Human male review candidates with 36 native-size GIFs. All candidates preserve source actions, remain ignored pending visual approval, pass timing, palette, closure, clipping, contact-cap, hash, semantic-mannequin, altered-rest-axis, and regeneration checks, and the full suite passes with 176 tests.

2026-08-28: Finalized the newly saved `PF_Run_Redo_Edit` non-destructively into a working pipeline copy, preserving all eight authored poses and rebuilding frame 9 as the exact loop closure. Rendered synchronized four-direction beauty/semantic passes and generated deterministic 128px, 16-color, eight-frame 10 FPS review GIFs; verified package regeneration, timing, looping, and safe canvas margins. Character Forge remains unchanged pending visual approval.

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
No long-running services, backend processes, health URLs, or service suites were found. The app launch command is `python main.py`. The live semantic Character Forge asset builder is `python tools/build_semantic_character_forge.py --force`; canonical camera views use `python tools/build_character_camera_views.py --force`, followed by `--check`. Both are deterministic and do not use an external image service. Motion-transfer reviews use `python tools/build_motion_transfer_candidates.py --target all --force`, followed by `--check`; raw sources and outputs remain ignored until approval. Editable component cleanup reviews use `python tools/build_component_cleanup_bundle.py --force`, followed by `--check`, and remain unpromoted until user approval. The retired 64px component-generation CLI is archived and is not an active service or supported runtime route.
