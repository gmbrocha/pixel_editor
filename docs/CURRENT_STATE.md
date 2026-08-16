# Current State

Last updated: 2026-08-16

## Summary
PixelForge is a PySide6 desktop pixel-art and tileset utility. Source-grounded tools include image import and preview extraction, palette handling, pixel editing, animation editing, modular Character Forge assembly/export, tile layout, tileset processing, tileset template generation, and procedural texture generation.

## Current Status
Active development is indicated by the operational Pip & Pyre Component Factory: authoritative Idle/Walk/Run geometry, manifest-driven Character Forge composition, recipe schema 2, resumable GPT Image jobs, deterministic normalization/extraction/QA, review and Pixel Editor cleanup, and guarded production promotion are implemented. Pixel editing also includes Clean Stroke painting and selection resize handling from the latest `main` work. A generation-only reserved-blue mannequin ramp avoids false nudity moderation. The seven-component pilot completed 21 animation jobs and 63 candidates with zero API failures, but a full visual audit found zero production-ready candidates and zero coherent components spanning Idle, Walk, and Run because generated pixels do not reliably preserve the authoritative sprite geometry or design identity. The remaining 28 ideas stay queued and should not be generated with the current workflow. The existing walking shirt remains available as an incomplete, recolorable Tops component.

## Blockers
None. The pilot is complete and the remaining bootstrap queue is intentionally held for human review of the pilot.

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

Character Forge currently has two manually authored test components: a shirt and leather boots, each covering the six front-facing Walk frames only. Their remaining directions and Idle/Run overlays still need authoring. All 63 pilot candidates fail automated QA: 59 exceed the 48-color palette hard limit and seven have missing frame coverage, with overlap between those groups. More importantly, visual audit found body-outline contamination, altered anatomy or registration, black mask fills, directional errors, and inconsistent designs across independent animation jobs. No generated candidate is approved or promoted, and none should be treated as cleanup-ready production art.

## Next Actions
Review the `category`, `status`, and `priorityRank` values when registering the project in Command Center.

Update this document after commits or other git state changes made during agent sessions.

Pivot component production toward reusable hand-authored topology families with authoritative-base underlays, animation-aware editing, linked ramps, and deterministic variants. Retain the pilot as optional concept/reference material. Do not run `python component_pipeline.py generate --bootstrap --remaining` with the current generation workflow; only reconsider API generation after a tightly controlled single-component exact-fit experiment succeeds.

## Recent Activity
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
