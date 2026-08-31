# Component Cleanup V2 Review Bundle

This folder contains 300 editable, component-only PNG
sprite sheets: 25 families fitted to four bases across Idle, Walk, and Run.
These files are exact editable mirrors of the preprocessed sheets currently
promoted in Character Forge, except registered approved-edit sources: those
preserve the user-authored direction rows while the live sheet may also contain
a generated mirrored direction. Later manual edits here still require promotion.

For a registered single-component edit, use
`python tools/promote_component_edit.py --component <component-id> --sequence run`.
It updates only the affected Forge variant and this bundle's related metadata;
the exhaustive family and cleanup builders remain checkpoint operations.

## Layout

- Cell size: 128 x 128 pixels.
- Rows: Front, Back, Right, Left.
- Idle: 14 columns, 1792 x 512 (sampled from authored frames 1, 3, 5, 7,
  9, 11, 13, 15, 17, 19, 21, 23, 24, and 25).
- Walk and Run: 8 columns, 1024 x 512.
- Files: `<base-id>/<family-id>/idle.png`, `walk.png`, and `run.png`.
- Exact Low-view body references: `base_sprites/<base-id>/idle.png`,
  `walk.png`, and `run.png`. These are convenient scratch-authoring bases for
  new clothing, hair, or accessories; they are not cleanup candidates.

## Canonical preprocessing applied once

1. Remove detached four-connected islands no larger than 16 pixels when they
   are either smaller than 20% of the frame's largest component or more than
   six pixels away from it. A second hand/foot must pass the same size,
   proportion, and distance checks; no disconnected piece is reserved merely
   because it is second-largest.
2. Chamfer one-pixel outline corners only when the pixel is the removable corner
   of a solid 2x2 turn. Then repeat only the detached-island sweep to catch
   specks exposed by the chamfer; the outline itself is never thinned twice.
3. Fill only fully enclosed one- or two-pixel transparent holes, using the most
   common neighboring color from the component's declared palette.
4. Remove one-pixel-wide terminal silhouette spurs up to two pixels long only
   when they attach to an edge with opaque support on both sides. This catches
   stray stems without shortening unsupported narrow straps, toes, or fingers.

The live Character Forge family builder applies this pass once. This mirror
copies those canonical results byte-for-byte and never preprocesses them again.

The pass removed 4175 detached islands
(33779 pixels), chamfered
279718 outline pixels, and filled
582 tiny holes (753 pixels).
It also removed 13705 terminal spurs
(13747 pixels).

Use `index.csv` to navigate the 100 variants. Every component folder contains a
`cleanup_manifest.json` with source/output hashes and per-frame changes.
The twelve PNGs under `review/` composite the first Front frame over each model
for a quick whole-catalog sanity check; edit the component-only animation sheets,
not these flattened review boards.
