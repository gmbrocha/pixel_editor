# 3D-Guided Pixel Animation and Component Factory Plan

Last updated: 2026-08-20

Status: Foundation implemented; real-FBX Blender verification pending

Initial target: One humanoid, one eight-frame Run animation, four directions, 64x64 cells

## Implementation Progress

As of 2026-08-20, the parts that do not require a local Blender installation are
implemented:

- Versioned `pixel-forge-3d-animation` package schema and strict loader.
- Contained-path, frame/direction, image-size, exact-region-color, silhouette,
  anchor, optional depth, and SHA-256 validation.
- Command-line package validator at
  `tools/validate_3d_animation_package.py`.
- Animation Studio **Import 3D Package** action.
- Conversion of package directions into linked-sheet tracks.
- Conversion of floating-point package anchors onto Animation Studio's current
  integer anchor grid.
- Experimental Blender FBX exporter at
  `tools/blender/export_pixel_animation.py`.
- Focused automated tests for valid import, structural validation, path safety,
  and the Animation Studio route.

Blender is not installed on the development machine at the time of this update.
The exporter compiles and its command-line contract is available, but it has not
yet been executed inside Blender or validated against a real Meshy FBX. Treat its
render, material, bone-name, and FBX assumptions as experimental until the Phase 1
pilot succeeds.

The authoritative package contract is documented in
`docs/3D_ANIMATION_PACKAGE.md`.

## Purpose

This document is the durable handoff for building a 3D-to-pixel animation pipeline
for Pixel Forge and Character Forge. It is intended to be readable without the
conversation that produced it.

The goal is not to make polished 3D artwork. The goal is to use a consistently
rigged 3D character as a motion, proportion, region, depth, and attachment scaffold.
Blender will turn that scaffold into synchronized, machine-readable animation
frames. Pixel Forge will pixelate and clean those frames, and Component Creator will
use the structural maps to fit clothing, equipment, hair, and other modular parts.

The central idea is:

```text
Meshy character and animation
            |
            v
Standardized Blender scene and rig
            |
            +--> visible character render
            +--> semantic body-region map
            +--> silhouette/alpha map
            +--> depth and occlusion data
            +--> projected joint/attachment anchors
            |
            v
Pixel Forge animation package
            |
            +--> pixel-art base animation
            +--> component fitting constraints
            +--> palette and cleanup processing
            |
            v
Character Forge spritesheet and reusable components
```

## Why This Direction

The existing image-generation experiments proved that an image model can invent
interesting component concepts but does not reliably preserve exact anatomy,
silhouette, direction, palette, or frame registration across a complete animation.
A 3D rig solves those consistency problems before pixel-art generation begins.

The 3D model can be visually rough. These properties matter much more than attractive
textures or dense geometry:

- The skeleton deforms consistently.
- The limbs are separated and readable in motion.
- The feet have a stable contact point.
- The character remains centered and at a fixed scale.
- Body regions can be identified from bones or explicit mesh assignments.
- The same animation can be sampled from exact camera directions.

This will not eliminate all manual art. It should eliminate repeatedly redrawing the
same anatomy and manually guessing registration across dozens of frames. Human work
should move toward art direction, silhouette correction, component design, and the
small number of pixels that require judgment.

## Division of Responsibilities

### What the project owner needs to provide

The owner will select and prepare the source models and choose the motions worth
supporting. The detailed intake checklist appears later in this document.

In brief, the owner should:

1. Choose one pilot humanoid rather than downloading a large collection immediately.
2. Confirm that its use is allowed for this project and retain its source/license
   information.
3. Prefer a clean T-pose or A-pose with separated limbs and recognizable hands and
   feet.
4. Auto-rig it in Meshy or provide a compatible rigged model.
5. Apply one uncomplicated Run animation for the first test.
6. Export the model and animation as FBX, retaining the original model and textures.
7. Supply a brief description of the intended pixel character and any nonstandard
   anatomy.

### What Codex/project implementation will provide later

Implementation work should provide:

- A repeatable Blender scene and headless export script.
- Rig inspection, scale normalization, camera setup, action sampling, and output
  validation.
- Automatic body-region classification seeded from armature weights.
- Exact region-ID, silhouette, depth, and visible render passes.
- Projected anchor export as JSON.
- A versioned interchange package that Pixel Forge can import.
- Pixel Forge processing and spritesheet assembly.
- Component-to-region rules, anchor-aware placement, and occlusion handling.
- Tests proving deterministic, aligned output.

## Source Model Requirements

### Strongly preferred

- Humanoid proportions, even if stylized.
- Neutral T-pose or A-pose before rigging.
- Arms visibly separated from the torso.
- Legs visibly separated from each other.
- Hands separated from hips, clothing, weapons, and props.
- Feet with clear bottoms that can be aligned to a ground plane.
- One continuous character at a sensible scale near the scene origin.
- Clean deformation around shoulders, elbows, hips, and knees.
- A standard humanoid armature and conventional bone names.
- A model that still reads clearly as a silhouette at small size.

### Acceptable for the first pilot

- Imperfect topology if the animation deforms cleanly.
- Low-detail or unattractive textures.
- Separate meshes for body, hair, eyes, or clothing.
- A moderate amount of clipping that does not affect the visible silhouette.
- A model whose colors will be completely replaced during pixel processing.

### Avoid for the first pilot

- Fused legs or arms fused into the torso.
- A robe or skirt that permanently hides both legs.
- Wings, tails, extra arms, digitigrade legs, or other nonstandard anatomy.
- Long coats, capes, dangling straps, or simulated cloth.
- A weapon permanently merged into the hand.
- Extreme body proportions.
- Dense accessories that obscure the base anatomy.
- Poor skin weights that collapse elbows, knees, shoulders, or hips.
- Models with uncertain ownership or licensing.

Those more difficult models can be supported later. The first pilot should establish
the pipeline with the least ambiguous humanoid possible.

## Meshy Preparation Checklist

Meshy's current workflow supports uploading or generating a model, humanoid
auto-rigging, applying animation presets, and exporting rigged animation. Its help
documentation recommends a clean T-pose or A-pose and FBX for animated characters:

- https://help.meshy.ai/en/articles/16231707-how-to-create-3d-animation-with-auto-rigging
- https://help.meshy.ai/en/articles/9991884-what-3d-file-formats-does-meshy-support-full-export-list

For the pilot:

1. Select or generate one ordinary humanoid.
2. Save the model's Meshy project URL or model identifier in a text file.
3. Record the model prompt if it was generated.
4. Save a screenshot of the unposed model from the front and side.
5. If Meshy reports poor topology or fused geometry, remesh before rigging.
6. Put the model in a neutral T-pose or A-pose.
7. Run humanoid auto-rigging.
8. Inspect shoulders, elbows, wrists, hips, knees, and ankles during motion.
9. Apply a simple looping Run animation with limited acrobatics or body rotation.
10. Preview the entire loop and reject it if feet, knees, or arms collapse visibly.
11. Export the animated result as FBX.
12. If available, also export an unanimated GLB or BLEND copy as a recovery source.
13. Retain all texture files even though the first renderer may use flat materials.

Do not collect hundreds of production candidates yet. Once the pilot establishes
which skeleton conventions, topology, and export settings work, collection can be
performed against a validated intake standard.

## Pilot Package the Owner Should Assemble

Create a folder similar to this. Names do not need to be exact, but the contents
should be recognizable.

```text
pilot_humanoid_run/
  README.txt
  license-and-source.txt
  model-neutral.fbx              # if available
  model-run-animated.fbx         # required pilot input
  model-source.glb               # optional recovery source
  textures/                      # retain original textures
  references/
    front.png
    side.png
    desired-pixel-style.png      # optional but useful
    desired-run-timing.gif       # optional if Meshy motion is not the timing target
```

`README.txt` should answer:

- What is the character supposed to be?
- Is this a base mannequin or a finished character design?
- Does it have any nonstandard anatomy?
- Which animation preset/action was used?
- Should the final sprite be 64x64?
- Should it match the current `human-01` proportions or establish a new base family?
- Are there features that must remain visible at pixel scale?

`license-and-source.txt` should record:

- Meshy project/model identifier or source URL.
- Date acquired or generated.
- Account/plan or license terms under which it was obtained.
- Whether the model may be modified and used commercially.
- Whether redistribution of the raw model is permitted.
- The original creator, if it is a community or third-party model.

This is asset provenance, not legal advice. Keeping it beside the source prevents a
future library of anonymous models whose permitted uses are unknown.

## Blender Pipeline

### Standard scene

The Blender project should contain:

- A world origin and ground plane convention.
- A normalized character-height convention.
- An armature/action inspection step.
- Four orthographic cameras named `Front`, `Back`, `Right`, and `Left`.
- A transparent background.
- A flat visible-render material setup.
- Exact semantic region-ID materials.
- A scriptable animation sampling and export configuration.

Orthographic projection is required because apparent size does not change with
distance from the camera. Blender documents orthographic cameras here:

- https://docs.blender.org/manual/en/latest/render/cameras.html

Workbench rendering is a strong candidate for the visible pilot render because it
supports material colors and simple shadows/cavity without a complex photorealistic
material system:

- https://docs.blender.org/manual/en/latest/render/workbench/index.html

Eevee or a custom flat shader remains an option if Workbench does not provide enough
control over exact output colors or transparency.

### Direction convention

The script must explicitly define which model axis is forward and verify it with a
labeled preview. Never infer directions from filenames alone.

The intended output labels are:

- `Front`: character facing the viewer.
- `Back`: character facing away from the viewer.
- `Right`: character facing screen-right.
- `Left`: character facing screen-left.

Whether Blender rotates the model or switches between cameras is an implementation
detail. Fixed cameras are easier to inspect; rotating a normalized rig may simplify
automation. Either method must produce identical scale and ground alignment.

### Animation sampling

The source action may run at 24, 30, or another frame rate. Pixel animation should
not blindly export every 3D frame. Instead, it should sample normalized phases across
one clean loop.

For an eight-frame pilot:

```text
0/8, 1/8, 2/8, 3/8, 4/8, 5/8, 6/8, 7/8
```

The final endpoint is not duplicated because it should match the first frame of the
next loop. The script should record the sampled source times in the package manifest.

Animation actions may later declare different counts. The current Character Forge
assets already demonstrate that direction-specific counts and playback sequences can
exist, so the interchange format must not assume every row has the same count.

### Registration

Every frame must use:

- One fixed cell size.
- One fixed orthographic camera scale.
- One common ground-line coordinate.
- One common horizontal center convention.
- No automatic per-frame crop or recentering.

The root/pelvis can move during the animation, but the exported cell cannot chase the
character from frame to frame. Foot sliding and root motion need to be handled as an
explicit motion policy rather than hidden by cropping.

### Proposed render resolution

The pilot should render each frame at 256x256 and process it down to 64x64. This gives
Pixel Forge enough information to choose a controlled silhouette and palette. Direct
64x64 rendering can also be tested, but it tends to make 3D rasterization decisions
become irreversible before Pixel Forge can clean them.

The semantic ID pass must never be smoothly resampled. It must use exact colors and
nearest-neighbor reduction if it is rendered above the final resolution.

## Machine-Readable Outputs

Each direction and frame should produce synchronized files.

### 1. Visible or beauty render

Purpose: source imagery for the eventual pixel-art base.

- Transparent RGBA PNG.
- Flat, controlled lighting.
- No depth-of-field, motion blur, bloom, or film grain.
- Minimal or disabled anti-aliasing should be tested against high-resolution
  rendering plus controlled reduction.

### 2. Semantic body-region map

Purpose: identify which anatomical region owns every visible pixel.

Each region uses an exact, reserved RGB identifier. Example labels include:

```text
background
head
neck
torso
pelvis
upper_arm_left
lower_arm_left
hand_left
upper_arm_right
lower_arm_right
hand_right
thigh_left
shin_left
foot_left
thigh_right
shin_right
foot_right
```

The actual numeric colors will be stored in a versioned schema. Consumer code must
read the schema rather than treating the colors as art colors.

Initial region assignment can be generated from armature vertex weights:

1. Inspect the deform bones affecting each vertex.
2. Assign the vertex to the strongest relevant bone or mapped semantic group.
3. Convert bone-specific groups into the stable semantic vocabulary.
4. Allow manual corrections for ambiguous boundaries.
5. Render those assignments with emission/unlit ID materials.

The region render must disable lighting, color management changes, interpolation,
dithering, and anti-aliasing that invents colors. Every pixel must decode to either a
known region ID or transparent background.

### 3. Silhouette/alpha map

Purpose: provide the exact visible body occupancy separately from color and region
classification.

- Transparent or zero outside the body.
- Fully occupied inside the visible character.
- May later include separate layers for body, hair, and permanent accessories.

### 4. Depth pass

Purpose: resolve what is in front when components overlap the body or each other.

The raw depth pass can be retained at higher precision. Pixel Forge may also derive a
simpler ordinal layer map such as:

```text
behind body
rear limb
torso plane
front limb
front accessory
```

Depth alone does not understand garment logic, but it provides the physical ordering
needed to decide whether a hand crosses in front of an apron or an arm passes behind
the torso.

### 5. Normal pass (optional for the pilot)

Purpose: provide stable surface direction for controlled shading. This could help
apply one palette ramp consistently across directions without copying noisy 3D
lighting.

It is not required to prove region mapping and may be postponed.

### 6. Anchor JSON

Purpose: export projected bone/joint and equipment attachment locations into the same
pixel coordinate system as the frames.

Example:

```json
{
  "schemaVersion": 1,
  "animation": "run",
  "direction": "right",
  "frame": 3,
  "sourceTime": 0.375,
  "cellSize": [64, 64],
  "anchors": {
    "head": [31.2, 8.6],
    "neck": [31.0, 16.8],
    "shoulder_left": [28.3, 19.7],
    "elbow_left": [35.1, 28.2],
    "hand_left": [39.4, 36.7],
    "hip_center": [31.0, 38.9],
    "knee_left": [24.8, 49.1],
    "foot_left": [22.7, 61.0],
    "weapon_grip_right": [37.5, 35.4]
  }
}
```

Coordinates should remain floating point in the interchange data. Pixel placement
can round them according to a documented deterministic rule.

### 7. Package manifest

The manifest should record:

- Schema version.
- Source model identifier and hash.
- Source animation/action and hash.
- Blender version and exporter version.
- Cell size and render size.
- Direction definitions.
- Frame counts and sampled source times.
- Camera settings.
- Ground line and character bounds.
- Region vocabulary and ID colors.
- Paths and checksums for every output.
- Any manual region corrections.

## Proposed Export Package Layout

```text
exports/humanoid-001/run/
  manifest.json
  preview-sheet.png
  visible/
    front/000.png ... 007.png
    back/000.png  ... 007.png
    right/000.png ... 007.png
    left/000.png  ... 007.png
  regions/
    front/000.png ... 007.png
    ...
  silhouettes/
    ...
  depth/
    ...
  anchors/
    front/000.json ... 007.json
    ...
  diagnostics/
    camera-contact-sheet.png
    region-contact-sheet.png
    alignment-overlay.png
```

The package should be self-describing. Pixel Forge should not need the original FBX
or Blender file to consume it.

## Pixel Forge Processing

The visible render should pass through a reproducible pipeline:

1. Validate package schema and checksums.
2. Validate cell dimensions, directions, frames, region IDs, and anchors.
3. Resize the visible render to the final cell size.
4. Convert it to the selected base palette.
5. Optionally apply edge-preserving denoise before hard quantization.
6. Apply Cluster Cleanup to remove isolated exact-color fragments.
7. Optionally apply 2x2 Macro Pixels when that is the chosen art scale.
8. Enforce transparency and silhouette policy.
9. Assemble the directional spritesheet without per-frame recropping.
10. Preview animation loops and direction changes.
11. Export the base sheet plus structural sidecar data.

The exact order must be visually tested. In particular, 2x2 Macro Pixels may be
appropriate for some styles but too destructive for faces, hands, or thin equipment.
It should remain a style decision rather than an unconditional step.

## Component Creator Integration

### Component description becomes a structured recipe

A description such as:

> Brown leather blacksmith apron covering the torso and upper thighs, worn over a
> cream shirt with rolled sleeves.

should be translated into explicit rules rather than independently regenerated for
every frame:

```text
Cream shirt:
  regions: torso, upper_arm_left, upper_arm_right
  layer policy: replace/cover base surface

Rolled sleeves:
  anchors: shoulder to elbow on each arm
  coverage: lower portion of each upper-arm region

Leather apron:
  anchors: waist_left, waist_right, knee_left, knee_right
  regions: torso_lower, pelvis, upper_thighs
  silhouette extension: allowed below and beside pelvis
  layer policy: torso-front, behind hands when depth requires

Apron straps:
  anchors: shoulders to waist
  layer policy: front of shirt, behind arms
```

The region map constrains placement; anchors define structure; depth resolves moving
occlusion; the component's own authoring data defines allowed silhouette growth.

### Component classes

Different parts need different fitting strategies.

#### Surface-following components

Examples: shirts, gloves, boots, tight pants, face paint.

These can primarily use body regions plus palette/shading rules. They are the easiest
initial components.

#### Anchored silhouette components

Examples: hair, hats, pauldrons, belts, aprons, backpacks, weapons.

These need anchors and a reusable 2D topology or shape template. The body map gives
registration but the component is allowed to extend beyond the body silhouette.

#### Volume or cloth components

Examples: long coats, skirts, robes, cloaks, capes, dangling straps.

These cannot be reliably inferred from a body-region map alone. They will require one
or more of:

- Simple proxy geometry attached to the 3D rig.
- A dedicated 2D animation topology family.
- Direction- and animation-specific silhouette authoring.
- Limited procedural cloth behavior with manual correction.

The current hooded-cloak semantic topology is an example of a reusable 2D family.
The new pipeline should preserve that concept rather than assume region maps magically
solve loose cloth.

### Occlusion rules

Components need both physical and semantic ordering. Examples:

- A rear hand can disappear behind the torso.
- A front hand should cross in front of an apron.
- Hair can be hidden by a hood while bangs remain visible.
- A weapon grip follows the hand, while the blade may cross several depth layers.

The system should combine:

- Per-pixel model depth.
- Semantic region identity.
- Component slot/layer metadata.
- Explicit overrides for special components.

Existing Character Forge occlusion tags can remain part of the final rule system.

## Implementation Phases

### Phase 0: Input inspection and conventions

- Inspect the pilot FBX in Blender.
- Identify its forward axis, scale, armature, action, frame range, and bone names.
- Confirm that the animation loops and deforms acceptably.
- Choose fixed camera scale, ground line, and body-height convention.
- Create a bone-to-semantic-region mapping table.

Exit condition: the pilot can be opened reproducibly and all required joints can be
identified.

### Phase 1: Manual Blender proof

- Set up four orthographic cameras.
- Sample eight Run phases.
- Render visible and region-ID contact sheets.
- Export a small hand-authored anchor JSON sample.
- Reduce visible frames to 64x64 through existing Pixel Forge tools.

Exit condition: all 32 frames are correctly directed, aligned, readable, and paired
with valid region maps.

This phase should happen before building a generalized exporter. It establishes
whether the art direction is viable.

### Phase 2: Automated Blender exporter

- Add deterministic scene setup and cleanup.
- Normalize model scale and origin.
- Discover or configure armature/action data.
- Create cameras and render settings.
- Generate semantic region assignments from weights.
- Export visible, region, silhouette, depth, and anchor data.
- Write manifest and checksums.
- Support headless execution from a command line.

Exit condition: two identical runs from the same inputs produce byte-identical or
semantically identical validated packages.

### Phase 3: Pixel Forge package importer

- Add package validation and diagnostics.
- Display visible, region, silhouette, and depth views.
- Assemble tracks for all directions.
- Apply saved processing recipes consistently to every frame.
- Export a canonical linked sheet without changing frame registration.

Exit condition: the pilot package becomes a previewable and editable Pixel Forge
animation project.

### Phase 4: First mapped component

- Begin with a fitted shirt, gloves, or boots.
- Define its region coverage and palette ramps.
- Propagate it across all pilot frames.
- Use depth to handle front/rear limbs.
- Compare component-only and composite animation views.
- Permit per-frame manual correction while preserving the reusable recipe.

Exit condition: one component definition covers all 32 pilot frames with only minor
corrections and no anatomy contamination.

### Phase 5: Anchored component

- Test an apron, hat, pauldron, or handheld object.
- Define anchor and silhouette-extension rules.
- Validate motion, occlusion, and direction behavior.

Exit condition: the component remains attached and visually coherent across the full
loop.

### Phase 6: Generalization

- Add Idle and Walk actions.
- Test a second compatible humanoid.
- Retarget established motion where possible.
- Formalize body families and nonstandard-rig intake rules.
- Add batch processing only after individual inspection remains reliable.

Exit condition: the same toolchain can process a second model without code changes or
manual scene reconstruction.

## Pilot Acceptance Criteria

The pilot is successful when:

- One source action produces Front, Back, Right, and Left outputs.
- Each direction contains the intended eight unique Run phases.
- The feet remain on the defined ground line except when the animation intentionally
  lifts them.
- Character scale and cell registration never change between frames.
- No camera uses perspective projection.
- Every region-map pixel decodes to a documented region or background.
- Region maps align exactly with the corresponding visible silhouettes.
- Anchor coordinates land on the expected joints in every frame.
- The final 64x64 animation is readable in motion.
- Processing is reproducible from recorded settings.
- A simple component can cover all 32 frames without independent image generation.
- Re-running the pipeline does not reorder directions or phases.

## Quality Diagnostics

The exporter/importer should eventually generate automated checks for:

- Missing frames or directions.
- Duplicate or near-duplicate sampled phases.
- Unexpected silhouette-area spikes.
- Foot-position jumps.
- Frame-to-frame center drift.
- Unknown region-ID colors.
- Region pixels outside the silhouette.
- Missing bones or anchors.
- Direction labels that appear mirrored or reversed.
- Palette counts above the selected limit.
- Components disappearing from required frames.
- Unreasonable component silhouette growth.

Contact sheets and animated previews remain mandatory. Passing numeric checks does not
prove that an animation looks good.

## Known Risks and Boundaries

### Region maps are structural constraints, not completed clothing

A torso region tells the system where the torso is. It does not automatically invent
a good coat silhouette, lapel construction, folds, or hem motion. Reusable component
topologies and art rules are still necessary.

### Poor rigging will become poor pixel animation

Pixel reduction may hide fine defects, but it cannot repair a collapsing knee or a
hand passing through the torso. Bad deformation should be rejected before export.

### A beautiful 3D model may make a bad sprite

Fine textures, fingers, facial details, and thin straps may disappear at 64x64. Strong
silhouette and readable proportions matter more than realistic detail.

### Automated left/right mirroring has limits

Mirroring is useful for symmetrical bodies and components. It is not correct for
asymmetrical hair, one-sided armor, weapon hands, scars, bags, or handed animation.
Direction-specific source data must remain supported.

### Root motion requires an explicit policy

Some 3D actions move the character through world space. The exporter must decide
whether to preserve that travel, convert it to an in-place loop, or record motion
separately. The default game-sprite pilot should use an in-place animation.

### Hundreds of models require intake discipline

Batch scale is useful only after the accepted rig, axis, scale, naming, provenance,
and QA standards are known. The factory should reject incompatible inputs rather than
silently producing corrupted sheets.

## Decisions Deliberately Deferred

The pilot should inform these choices:

- Workbench versus Eevee/custom flat rendering.
- Render directly at 64x64 versus render at 256x256 and reduce.
- Exact base palette and number of shade steps.
- Whether normal maps materially improve pixel shading.
- Whether regions should be assigned per vertex, per face, or through a corrected
  transfer mesh.
- Whether the model rotates or four cameras surround it.
- How much root/pelvis motion is preserved.
- Which anchors belong in schema version 1.
- How component descriptions become editable structured recipes.
- Whether Blender is launched from Pixel Forge or run as an external preparation
  command.
- Whether 3D source assets are tracked in Git, stored through large-file tooling, or
  kept outside the repository with checksummed manifests.

## Immediate Next Actions for the Owner

Nothing needs to be implemented or installed today. When ready:

1. Choose one plain humanoid with clear limbs and an uncomplicated silhouette.
2. Verify its permitted use and make `license-and-source.txt`.
3. Rig it as a humanoid in Meshy.
4. Apply one simple in-place Run animation.
5. Reject or repair it if joints collapse or the feet visibly slide incorrectly.
6. Export the animated character as FBX.
7. If possible, also export the neutral model as GLB, FBX, or BLEND.
8. Save front and side screenshots.
9. Place everything into one pilot folder using the earlier layout.
10. Copy that folder to the Pixel Forge machine or attach it in a future Codex
    session.

Do not spend time choosing the perfect final hero model. A plain, readable test body
is more useful for proving cameras, region maps, anchors, and component fitting.

## Immediate Next Actions for the Project

When the pilot assets are available:

1. Inspect the FBX and animation without modifying Pixel Forge.
2. Produce the Phase 1 manual Blender proof and contact sheets.
3. Review the 64x64 result with the owner.
4. Adjust scale, camera, timing, palette, and shading until the motion reads well.
5. Only then create the generalized Blender exporter and Pixel Forge importer.

## Re-entry Instructions

From another machine or a future session, use this prompt:

> Read `3D_ANIMATION_FACTORY_PLAN.md` at the Pixel Forge repository root. I have the
> pilot model package ready. Inspect it and begin Phase 0 and Phase 1 only; do not
> generalize the pipeline until we have reviewed the first four-direction contact
> sheet and 64x64 animation preview.

That instruction deliberately forces an inexpensive visual proof before a large
implementation.

## Intended End State

The completed system should allow the owner to select a compatible 3D humanoid and
motion, generate structurally mapped pixel animation frames, describe or select
components, and receive a Character Forge-compatible result with stable direction,
registration, palette, anatomy, and occlusion.

The resulting factory is not merely a 3D screenshot converter. Its valuable product
is a synchronized animation package in which every pixel frame is accompanied by
body ownership, silhouette, depth, and attachment information. That is what allows
component work to be reused instead of redrawn independently for every frame.
