# Current State

Last updated: 2026-08-18

## Summary
PixelForge is a PySide6 desktop pixel-art and tileset utility. Source-grounded tools include image import and preview extraction, palette handling, pixel editing, animation editing, modular Character Forge assembly/export, tile layout, tileset processing, tileset template generation, and procedural texture generation.

## Current Status
The Animation Editor is now a functional two-pane Animation Studio with drag-defined signed-stride direction tracks, linked in-memory sheet editing, core pixel tools, onion skinning, Once/Loop/Ping Pong playback and timing controls, frame analysis, gesture-level Undo/Redo, versioned `.pfa` persistence, and PNG/GIF/JSON exports. Active development is also indicated by the operational Pip & Pyre Component Factory: authoritative Idle/Walk/Run geometry, manifest-driven Character Forge composition, recipe schema 2, resumable GPT Image jobs, deterministic normalization/extraction/QA, review and Pixel Editor cleanup, guarded production promotion, reproducible non-destructive component variants, and a semantic-region Silhouette Finisher are implemented. The final canonical Walk base preserves the supplied authored sheet separately, copies Front, Back, and Right without alteration, and reverses only the six Left-row cells as `6,5,4,3,2,1`; this places Left in the same phase as its corresponding Right mirror. Three earlier derivatives demonstrate palette remapping, coordinate-masked two-tone materials, and stable material ramps. The semantic finisher isolates exact authoring colors, locks their combined alpha mask, and applies region-specific five-step palettes, fixed lighting, colored boundary shading, and clasp-anchored folds without frame-local noise. Its canonical hooded-cloak Walk source preserves authored Front, Back, and Right rows and deterministically mirrors Right into same-phase Left with matching alignment, producing ten visually reviewed four-direction treatments: Forest Wool, Burgundy + Gold Trim, Storm Blue & Silver, Autumn Russet, Pointed Hood Green, Winter Gray, Royal Amethyst + Gold, Midnight Raven, Desert Sand + Teal, and Ivory + Crimson. A separate two-region Warlock Robe source produces four visually reviewed Front Walk treatments: Void Amethyst, Blood Ritual, Necrotic Jade, and Astral Midnight. An overnight workbench adds eleven rough-but-editable six-frame Front Walk semantic starters across Hair, Shoulder / Chest, Hands, Face, Outerwear, Neck, and Headwear, backed by a visual index, exact marker masks, deterministic previews, manifests, and a focused pickup guide. Pixel editing includes gesture-level Undo/Redo for painting, shapes, stamps, and moved selections, Clean Stroke painting, selection resize handling, an optional Right-click Transparent paint binding that preserves the left-click color across brush and shape operations, and a hardened layer workflow with an explicit editing-layer banner, independent visibility controls, stale-selection clearing on layer switches, confirmed layer deletion, hidden-layer paint protection, and direct copy/move of selected pixels into existing layers with atomic Undo/Redo. A generation-only reserved-blue mannequin ramp avoids false nudity moderation. The original seven-component pilot completed 21 animation jobs and 63 candidates with zero API failures but no production-ready candidates. A subsequent ten-component, Idle-only experiment used a stricter immutable-raster paper-doll prompt and produced ten of ten review candidates with full frame coverage, zero reserved-blue leaks, and near-zero reconstruction error; the short wool travel coat and quilted gambeson are the strongest visual hits, but all ten still fail palette complexity and several retain colored fringe or anatomy contamination. The existing walking shirt remains available as an incomplete, recolorable Tops component.

## Blockers
None. The ten immutable-prompt Idle candidates are available for human review and cleanup; the broader bootstrap queue remains intentionally held.

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

Character Forge currently has two manually authored runtime test components, three non-semantic deterministic derivatives, ten complete four-direction semantic-finish Walk cloak variants, four Front Walk semantic Warlock Robe variants, and eleven workbench silhouette starters. The workbench set is intentionally rough and should be treated as tracing/editing material, not approved art. Double Leaf Pauldrons cover Front and Back Walk; the other workbench starters remain Front-only. The obsolete three-frame semantic cloak and non-semantic Muddy Field Boots remain removed. The three larger-hood legacy cloak entries—Pointed Hood, Burgundy, and Winter Gray—are archived outside runtime discovery and replaced by small-hood semantic components. Blackened Iron boots use a stable palette-only treatment with seeded edge accents removed. Shirts, boots, and Warlock Robes still cover Walk/Front only; hooded cloaks cover every Walk direction but still need Idle and Run overlays. Hooded cloaks reserve Headwear and Neck while selected; component-specific workbench conflicts are recorded in their manifests and pickup guide. All 63 original pilot candidates fail automated QA: 59 exceed the 48-color palette hard limit and seven have missing frame coverage, with overlap between those groups. The ten immutable-prompt Idle candidates also all fail palette complexity, ranging from 67 to 1,413 colors; visual review found better cross-direction design consistency but persistent magenta/cyan fringe and occasional anatomy contamination. The short wool travel coat and quilted gambeson merit cleanup experiments, not direct promotion. No generated candidate is approved or promoted.

## Next Actions
Review the `category`, `status`, and `priorityRank` values when registering the project in Command Center.

Update this document after commits or other git state changes made during agent sessions.

Review `assets/character-forge/workbench/component-silhouette-starters-all-frames.png`, choose the strongest starter, and edit its linked `regions.png` using the exact semantic markers. The pickup guide recommends beginning with Hair, either Pauldron set, Ratty Shawl, Orcish Armor, or Cult Mask. Pivot component production toward reusable hand-authored topology families with authoritative-base underlays, animation-aware editing, linked ramps, and deterministic variants. Retain generated candidates as optional concept/reference material. Clean and palette-reduce the short wool travel coat and quilted gambeson Idle candidates against the authoritative base before deciding whether either design warrants controlled Walk and Run follow-up jobs. Do not run the full remaining bootstrap queue yet.

## Recent Activity
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
No long-running services, backend processes, health URLs, or service suites were found. The app launch command is `python main.py`; component tooling is available through `python component_pipeline.py --help`. GPT Image generation is an explicit command-line action and does not run in the background.

The component pipeline's `OPENAI_API_KEY` is stored in the ignored root-level `.env` file and is loaded automatically. Always check it through `openai_api_available()` before reporting that credentials are unavailable; never display or copy the secret itself.
