# Pip & Pyre Component Factory: Pilot Findings

Last updated: 2026-08-16

## Purpose

This document records the findings from visually reviewing the first generated
Character Forge component pilot. It is the working reference for the next factory
revision while the remaining candidates are inspected.

This is a findings and design-direction document, not a claim that the proposed
changes below have already been implemented. The current production Character
Forge assets and canonical base sprites remain unchanged.

## Current pilot state

- The seven-component pilot covers a captain's cap, spectacles, neckerchief,
  belt, vest, gloves, and boots.
- It completed 21 animation jobs and produced 63 of 63 requested candidates.
- The reserved-blue mannequin eliminated the earlier false-nudity moderation
  failures. The pilot completed with no API failures and no reserved-blue leaks.
- No generated pilot candidate has been approved or promoted.
- All 63 candidates currently fail at least one automated QA rule. Fifty-nine
  exceed the 48-color palette limit, and seven have one or more missing frames;
  those groups overlap.
- There are useful *design references* among the results, especially some boots,
  caps, belts, and vests. That does not mean their extracted overlays are usable.
  The completed visual audit below found no production-ready candidate and no
  coherent component spanning all three animations.

## Full 63-candidate visual audit

The complete pilot was reviewed across the downsampled model response, extracted
transparent overlay, and reconstruction over the authoritative base. This exposed
failures that the existing technical score does not measure adequately.

### Bottom line

- **Production-ready candidates: 0 of 63.**
- **Coherent components covering Idle, Walk, and Run: 0 of 7.**
- **Candidates that are clean enough to promote after minor palette reduction:
  0 of 63.**
- Some individual images contain useful hat, belt, vest, or boot concepts, but
  turning them into exact overlays would require substantial redraw and cleanup.
- Spectacles, neckerchiefs, and gloves are especially poor fits for the current
  generation method.
- The remaining 28 bootstrap ideas should not be generated with the current
  pipeline.

The main failure is not the current QA hard failure for palette complexity. It is
loss of identity between the authoritative sprite and the generated sprite. The
model repeatedly changes anatomy, proportions, silhouette, pose details, or
directional interpretation inside the editable region. The resulting component
pixels literally do not fit the canonical character.

### Quantitative context

- The extracted overlays contain a median of 1,357 unique RGBA colors. The range
  is 0 for an empty/missing result through 5,190 colors.
- Sixty-one of 63 candidates register silhouette growth.
- Seven candidates contain at least one missing required frame.
- Despite these results, the current technical scores range from 69.28 to 88.02,
  with a median of 81.35. Those apparently healthy numbers are misleading because
  the score does not sufficiently penalize anatomy replacement, body-outline
  contamination, inconsistent design identity, or mask-shaped background fills.

### Component-by-component verdict

| Component | Visual audit | Verdict |
| --- | --- | --- |
| Weathered captain's cap | All nine sheets contain recognizable hats, but the cuts, brims, crowns, colors, and apparent facing vary between jobs. Blue/magenta body and head-edge residue survives extraction. Some frames contain large black mask fills in the model response. | Useful concept reference; no coherent three-animation cap and no cleanup-ready overlay. |
| Round spectacles | Several jobs generate black rectangles over entire head regions. Other results redraw faces, eyes, skull outlines, or head direction. Extracted sheets contain replacement head pixels and scattered light/dark fragments rather than isolated eyewear. | Failed for production. Hand authoring is likely faster than repairing any result. |
| Linen neckerchief | Four of nine sheets have missing frames. Several masked jobs contain black rectangles; surviving extractions are tiny, fragmented, inconsistent, or include neck/head residue. | Failed for production. A small authored neck overlay would be faster and more controllable. |
| Wide leather belt | Belts are visually recognizable, but many extractions contain changed body outlines, legs, arms, and scattered blue/magenta pixels throughout the slot region. Belt width, buckle, color, and placement do not remain one design across animations. | Some design reference value; overlays require major redraw and do not form one component. |
| Leather work vest | The strongest conceptual category, with several readable vest designs. Nevertheless, extracted sheets include cyan body borders, magenta fringe, limb/torso replacement pixels, and radically different vest construction between independent animation jobs. Some model results also place each sprite inside a black rectangle. | Best reference material in the pilot, but still not a production overlay set. Manual tracing/redraw may reuse the idea only. |
| Plain leather gloves | The generous Hands mask lets the model reinterpret arms and adjacent body pixels. Extractions contain large amounts of body-outline contamination and inconsistent glove size/placement; some raw frames are boxed in black. | Failed for production. Hand authoring against the exact hands is more efficient. |
| Ankle work boots | Several individual boot shapes are readable, especially in Run, but many raw jobs add black ground rectangles and many extractions retain magenta/blue residue. Shoe height, sole, cuff, and perspective vary across animation jobs. | Useful concept reference; no consistent complete boot component. A few frames might be traced, but not promoted as-is. |

### Cross-animation identity failure

Idle, Walk, and Run are generated as independent jobs. Candidate IDs are local to
those jobs; `candidate-001` in Idle is not a continuation of `candidate-001` in
Walk or Run. The visual audit confirms that no candidate-number grouping preserves
one garment design across animations. For example, the captain's cap changes its
crown, brim, coloring, and overall construction between animation jobs.

This means selecting the least-bad candidate from each animation still does not
produce one believable Character Forge component. A design lock or reference
could improve similarity, but it would not solve the more fundamental exact-fit
problem demonstrated by the pilot.

### Extraction contamination

Position-aware mannequin reversal restores pixels that remain close enough to the
reserved cyan ramp. When the model reshades or redraws the mannequin more heavily,
those pixels no longer match the reversible ramp and are treated as new component
art. This is why many extracted overlays contain cyan/dark-blue outlines around
the torso, arms, legs, feet, or head.

The reconstruction can consequently look more plausible than the overlay deserves:
contaminated body-shaped pixels are being placed back over roughly corresponding
canonical body pixels. At pixel scale, the colors, edges, and silhouettes do not
match and would corrupt layered character combinations.

White backgrounds and tighter masks would reduce fuchsia and black-box artifacts,
but they would not guarantee preservation of exact body geometry or cross-frame
design identity. Those changes are workflow improvements, not a complete remedy
for the production-fit failure.

## Recommendation after the audit

Do not abandon Character Forge or the component asset system. Do abandon the
assumption that a general image-generation edit will produce production-ready,
frame-registered pixel overlays for these sprites.

The manifest catalog, slot/layer composition, recipes, recoloring, canonical
validation, previews, cleanup editor, QA, and guarded promotion remain useful.
The generation stage should be demoted to optional concept/reference creation.

### Recommended hybrid production workflow

1. Use generated images, sketches, or descriptions only to choose the garment's
   silhouette, materials, details, and color ramp.
2. Hand author the exact overlay on the authoritative base with a locked base
   underlay and animation playback.
3. Build reusable authored topology families: sleeveless torso, short sleeve,
   long sleeve, coat, narrow belt, wide belt, short boot, tall boot, and similar
   foundational shapes.
4. Derive many catalog items deterministically from those fitted families through
   ramp swaps, trim, buckles, patches, emblems, cuff changes, and a small number of
   deliberate pixel edits.
5. Add editor assistance for copying a component between related frames, onion
   skinning, linked palette ramps, frame/direction navigation, and base-relative
   cleanup. These tools reduce authoring time without surrendering registration.

The expensive work is fitting a garment topology to the 52 canonical frames:
four Idle views, 24 Walk frames, and 24 Run frames. That work should be reused.
Once one reliable topology exists, recolors and detail variants can create many
items without redrawing all 52 frames.

If another API experiment is performed, it should be a deliberately small
single-component test, not the remaining bootstrap queue. A white background,
tight silhouette mask, one direction at a time, and a locked design reference can
test the upper bound of the approach. It should be judged on exact pixel fit—not
general visual appeal—and should be stopped if it still redraws canonical anatomy.

## Non-negotiable fit requirement

A component is only useful when it is registered to the authoritative Pixel
Forge body in every frame. The model may add a garment around the supplied
mannequin, but it may not invent a different mannequin, replace anatomy, change a
pose, move a limb or head, reverse a facing direction, or alter frame spacing.

Some pilot results contain visually appealing art fitted to bodies that are not
our base sprites. Those results are not production-compatible overlays. A design
may still be useful as visual reference, but its pixels cannot be promoted unless
the component is refitted to the exact canonical frames during cleanup or
regenerated correctly.

The canonical Idle, Walk, and Run sheets must always remain pristine. Mannequin
recoloring and generation backgrounds are temporary generation-only transforms.

## Finding 1: the fuchsia generation matte is counterproductive

The solid `#FF00FF` matte was chosen because it is easy to distinguish from most
component colors. In practice, the image model does not preserve it as one exact
flat color. It creates related pink, purple, dark-magenta, antialiased, and shaded
pixels around component and mask boundaries. Exact color removal cannot eliminate
all of those shades safely, while a broad magenta tolerance risks deleting real
component colors.

The fuchsia matte also dominates the raw and reconstruction views, making visual
review more tiring and making subtle fringe contamination harder to judge.

### Working direction

Use an opaque white generation canvas for subsequent jobs. White is visually
neutral and more likely to produce a clean, conventional product-art background.
Background removal must be connectivity-aware rather than a global white color
key:

- Remove white and near-white regions only when connected to the image or
  editable-mask boundary.
- Never globally erase every white pixel. Eyes, highlights, spectacles, pale
  fabrics, and intentionally white components must survive.
- Preserve the reserved-blue mannequin transform and its exact position-aware
  reversal to canonical pixels.
- Continue clamping all pixels outside the editable region to the canonical base.
- Record the generation background and cleanup thresholds in job provenance so
  old fuchsia jobs and new white jobs remain reproducible.

Existing fuchsia candidates should not be destructively rewritten merely to match
the new policy. Promising candidates can be cleaned individually; new generation
jobs should use the revised white-background preparation.

## Finding 2: the black boxes are generated mask-fill artifacts

The black rectangles visible across faces and other regions are not intentional UI
overlays. The model has interpreted the broad rectangular editable mask as an area
it is free to fill and has painted a dark background or occlusion into it. An
Image API edit mask is guidance about where editing may occur; it does not compel
the model to produce transparency or to modify only the desired garment pixels.

Interpretation depends on the review tab:

- In **Raw**, a black box is useful failure evidence from the model response.
- In **Normalized**, it means preprocessing has retained that generated fill.
- In **Extracted** or **Reconstruction**, it means the background artifact was
  classified as component art and the candidate is not usable without cleanup.

### Working direction

- Replace the fuchsia canvas with white as described above.
- Use tighter, silhouette-aware editable masks instead of only generous slot
  rectangles where possible.
- Remove only background regions connected to mask boundaries; do not erase
  isolated dark component details.
- Add QA for large, low-variation rectangular fills and unusually high coverage
  of an editable region.
- Treat any surviving mask-shaped block in extraction or reconstruction as a hard
  promotion failure.

## Finding 3: some generated heads face the wrong direction

The authoritative sheet direction order is not the cause of the observed backward
heads. In affected candidates, the model redrew a head or major head pixels inside
the editable Face region and interpreted the directional row incorrectly. The
extractor then saw those changed head pixels as component pixels. Reconstruction
correctly exposes the result by placing that extracted replacement head over the
canonical body.

This is especially obvious with spectacles: a valid spectacles overlay should add
small accessory pixels around the eyes or side profile, not contain a replacement
head silhouette.

### Working direction

- State the exact row/direction mapping prominently in generation prompts and
  generation reference material.
- Consider generating one direction at a time for direction-sensitive components,
  then reassemble the authoritative sheet deterministically.
- Add direction-specific masks or attachment zones for Face, Headwear, and other
  sensitive slots.
- Reject generated skin, head, or mannequin pixels from Face accessory overlays.
- Add a component-pixel budget and a maximum canonical-head replacement ratio.
- Hard-fail candidates whose overlay replaces a significant part of the head or
  creates a new head silhouette.
- Apply direction-aware expectations: front eyewear crosses the eye area, side
  eyewear follows the profile, and back views normally contain little or no face
  accessory art unless the design visibly wraps around the head.

## Finding 4: broad masks encourage replacement art instead of fitted overlays

The initial anatomical regions are intentionally generous, but the pilot shows
that generous rectangles give the model too much freedom. It sometimes redraws a
body region, invents a new mannequin, or changes the silhouette far beyond the
requested component. This explains how an attractive component can still be
fitted to the wrong sprite.

### Working direction

- Derive masks from both the declared slot region and the actual canonical sprite
  silhouette, with a small component-appropriate expansion allowance.
- Use different expansion rules per slot: spectacles need very little space;
  outerwear and headwear legitimately need more silhouette growth.
- Permit explicit direction-specific overrides in component metadata.
- Preserve enough room for accessories that extend beyond the body while making
  canonical anatomy read-only wherever practical.
- Add QA that compares overlay location and silhouette growth against the
  canonical body on a per-frame basis, not just at whole-sheet level.

## Finding 5: the model is producing too many colors

Fifty-nine of the 63 pilot candidates exceed the current 48-color hard limit.
The excess is not merely a numerical inconvenience: it often represents
anti-aliasing, background contamination, soft gradients, and multiple nearly
identical shades that do not belong in the established pixel-art style.

Automated reduction can help expose a design, but it should not silently decide
the final palette. A clean component needs a small intentional ramp, preserved
outlines, and readable highlights/shadows consistent across frames and directions.

### Working direction

- Keep palette complexity as a hard promotion guard.
- Add a review-assisted ramp reduction step that clusters near-duplicate shades
  while protecting authored outline and highlight colors.
- Show the candidate palette beside the target component ramp during cleanup.
- Prefer a consistent component ramp across Idle, Walk, and Run.
- Require human inspection after reduction; passing the numeric threshold alone
  does not establish acceptable art direction.

## Finding 6: missing frames must remain a hard failure

Seven candidates omit the requested component in at least one frame. A component
that disappears during an animation cannot be promoted as complete coverage.
Some directionally hidden pixels can be legitimate, but that exception must be
declared by the component's expected directional coverage rather than inferred
from an accidental blank frame.

### Working direction

- Keep per-frame zero coverage as a hard failure for required frames.
- Let manifests explicitly declare legitimate directional absence.
- Show missing frames prominently in the reviewer and jump directly to them.
- Prefer regenerating or manually drawing a missing frame rather than copying a
  neighboring pose without checking registration.

## Finding 7: reconstruction is doing its job

The reconstruction view is not causing the backward heads or foreign bodies. It
composites the extracted overlay over the pristine canonical base and therefore
reveals what promotion would actually do. A bizarre reconstruction generally
means extraction contains replacement anatomy or background artifacts.

Raw, normalized, extracted, and reconstruction views answer different questions
and should all remain available:

- **Raw:** what the image model returned.
- **Normalized:** what survived downsampling and background processing.
- **Extracted:** what the pipeline currently believes is the transparent
  component.
- **Reconstruction:** how that component fits the canonical body.

Promotion decisions should be based primarily on extraction and reconstruction,
not on an attractive raw candidate.

## Finding 8: cleanup needs the authoritative base as visual context

Editing a transparent component by itself is not sufficient. Registration,
occlusion, pose correspondence, and directional errors can only be judged against
the exact base animation that the component will cover.

### Required cleanup behavior

- Open the exact authoritative base animation and direction associated with the
  candidate as a locked, visual-only underlay.
- Default to an **On Base** composite view, with a **Component Only** checkerboard
  option.
- Provide base visibility and opacity controls.
- Provide animation playback and direct frame/direction navigation.
- Provide a difference or component-highlight view for subtle overlay pixels.
- Edit only the transparent component layer. Erasing component pixels must reveal
  the base, never alter it.
- Keep **Restore Source** scoped to the original extracted overlay. It must not
  copy base pixels into the saved component.
- Save only the transparent overlay at exact canonical sheet dimensions; the
  underlay is never included in the artifact.

## Finding 9: all review image tabs need mouse-wheel zoom

The review tabs contain pixel-scale evidence that cannot be assessed reliably at
one fixed display size. Raw, normalized, extracted, and reconstruction views all
need the same predictable navigation behavior.

### Required zoom behavior

- Mouse-wheel zoom on every image tab.
- Zoom centered on the cursor so the inspected pixel remains under the pointer.
- Nearest-neighbor rendering at every scale.
- A practical range around 25% to 3200%, plus **Fit** and **1:1** actions.
- Scrollbars and middle-mouse panning when the image exceeds the viewport.
- Retain zoom and pan independently per tab and candidate where practical.
- Do not allow wheel zoom to change the selected candidate or animation
  direction accidentally.

## Disposition of the existing 63 candidates

The completed API work should be preserved. No automatic bulk promotion or bulk
deletion is appropriate.

Suggested triage labels:

1. **Salvage:** design fits the canonical mannequin and needs palette/fringe
   cleanup only.
2. **Reference only:** good design idea, but fitted to altered anatomy or the wrong
   mannequin; use as a visual reference for redraw or regeneration.
3. **Regenerate:** requested component is missing, directionally wrong, or damaged
   beyond efficient cleanup.
4. **Reject:** mask fill, unrelated imagery, or no useful component design.

Old fuchsia candidates must retain their original raw files and recorded request
metadata even if a corrected sibling job is generated with the white-background
pipeline.

## Recommended implementation order

1. Keep the remaining 28-component generation queue paused.
2. Add authoritative-base underlays and component-only/composite controls to
   cleanup.
3. Add consistent wheel zoom, Fit, 1:1, and panning across all review image tabs.
4. Add authoring accelerators: onion skinning, frame/direction navigation,
   base-relative copy/propagation, and linked palette ramps.
5. Define the first reusable hand-authored garment topology family and use it to
   prove deterministic variants.
6. If generation remains available, change new preparation from fuchsia to white
   with connected-boundary
   background removal and provenance versioning.
7. Tighten masks using canonical silhouettes and slot-specific growth allowances.
8. Add QA for rectangular mask fills, anatomy replacement, excessive head
   coverage, and direction-sensitive attachment.
9. Add per-direction generation support for Face and other sensitive categories
   only if the small controlled test justifies continued API work.
10. Retain the existing pilot as concept/reference material; do not spend time
    cleaning every candidate merely because it already exists.

The background, mask, or processing revision must create a new request fingerprint
or explicit processing version. Existing jobs must remain resumable and auditable.

## Acceptance criteria for the next generation pass

A candidate is ready for human approval only when:

- Every required frame contains the requested component.
- The canonical body pose, proportions, facing direction, registration, and frame
  spacing are unchanged.
- Extraction contains no mannequin skin/body replacement, reserved-blue pixels,
  white canvas, fuchsia fringe, black mask boxes, or other generated background.
- The transparent overlay reconstructs cleanly over the exact canonical base.
- Directional appearance is plausible for every covered view.
- Palette complexity is intentional and within the configured limit.
- Silhouette growth is appropriate for the component slot.
- The reviewer can inspect it at pixel scale and the cleanup editor can compare it
  directly with its locked base underlay.

Promotion remains a separate, explicit action after QA and human approval.

## Open review notes

The owner is still inspecting the pilot. Add newly observed failure modes and good
examples to this document before changing generation policy, so the next pipeline
revision responds to the full review rather than only the first few candidates.
