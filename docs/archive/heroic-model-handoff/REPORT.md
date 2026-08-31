# Heroic JRPG Proportion Authoring - Review Report

Package: `pixel_forge_heroic_jrpg_style_v1_claude_handoff`
Blender: 5.1.2 (matches `PACKAGE_MANIFEST.json`)
Status: **review candidates only - not approved, not canonical**

---

## 1. Headline: the brief contained a conflict, and it was resolved in favour of the references

`CLAUDE_PROMPT.md` specified proportion bands of 4.5-5.0 (Elf), 4.25-4.75 (Tiefling),
4.0-4.5 (Human) and 3.25-3.75 (Dwarf). The seven reference images were supplied later and
measured as follows (figure isolated by largest connected component against a keyed
background, normalised to common height, chin read against a heads-tall grid):

| Reference | Heads tall | Sprite height |
|---|---:|---:|
| Barbarian | ~6.8 | ~74 logical px |
| Bard | ~6.5-7.0 | ~76 px |
| Warlock | ~7.0 | ~60 px |
| Warrior | ~6.0-6.5 | ~67 px (grid 6) |
| Player sprite | ~6.0 | ~64 px (grid 8) |
| Four-character lineup | ~6.0 | - |
| Cleric (dwarf) | ~3.5 | ~55 px |

Six of seven references sit at 6-7 heads - roughly two head-heights taller than the
written bands. The single exception is the bearded dwarf, whose ~3.5 matches its band
almost exactly. Both options were built and rendered under an identical camera
(`previews/PROPORTION_DECISION_A_vs_B.png`).

**Art direction chose the reference-matched option (B)**, then requested two amendments:
the Dwarf was too short, and the arms were too heavy. Both were applied. The delivered
models therefore sit at reference proportions, with the Dwarf raised from 3.55 to 4.30
heads and all added arm girth reduced or removed.

Consequence to note: because the sources were already 5.8-7.9 heads, reference-matched
proportions mean the Elf, Tiefling and Human changed only moderately in stature. The
substantive change for those three is head, hand and foot enlargement plus neck
shortening, not overall compression. The Dwarf changed substantially.

---

## 2. Method

Rest-proportion retarget with linear-blend-skin re-bind - the method demonstrated by
`reference/prior_success/chibify.py`, generalised and corrected. Script:
`heroic_retarget.py` (shipped in `outputs/scripts/`).

1. Per bone, `S_b = diag(gx, len, gz)` in **bone-local** space.
2. Hierarchy walked parents-first; a child's rest offset is carried through `S_parent`,
   so shortening a thigh drags shin and foot with it.
3. Localised cranium/jaw/depth shaping applied in the **original** head-bone basis.
4. Every vertex moved by the weight-blended delta `D_b = M'_b @ S_b @ M_b^-1`.
5. Re-ground to z = 0.
6. Bone-parented `PF_ATTACH_*` empties re-solved through the same delta.
7. Approved actions duplicated, never edited.

### Deliberate deviations from `chibify.py`

| Change | Why |
|---|---|
| Anisotropic girth (`gx` lateral vs `gz` depth) instead of one isotropic value | Torso can widen for the front silhouette without gaining depth the ortho camera never sees |
| Head shaping moved *before* the LBS delta | chibify applied it after, in the stale pre-retarget basis; composing it first is geometrically correct |
| `use_connect` flags restored after the edit-bone pass | chibify left every bone disconnected. Residuals measured 1e-5 cm or less, so the original rig structure is preserved exactly |
| Bone-parented empties re-solved | chibify did not handle them; the Elf's 17 attach points would otherwise drift off their anatomy |
| **Approved actions never written** | chibify's motion-scale loop iterates `bpy.data.actions` and would have edited `PF_*_Approved` in place, which the brief forbids |
| Sizes solved, not dialled | Cranium height, hand ratio and foot ratio are secant-solved against targets rather than hand-tuned scale factors |
| numpy vectorised deformation | ~100k verts x 24 bones per evaluation, needed for the solver to converge in-session |

### What was solved vs. chosen

Cross-character **common** decisions (cohesion): one cranium height, one hand ratio, one
foot ratio, one neck policy, one head-shaping policy. Per-archetype **tuned** decisions:
leg-to-torso ratio, lateral girth, shoulder width, stature. No global scale factor is used
to differentiate any character.

---

## 3. Before / after, per model

All figures in armature units (cm; armature object scale is 0.01, unchanged).
`heads_tall` is measured against the **cranium**, excluding thin appendages - see 3.1.

| Model | Height before | Height after | Cranium before | Cranium after | Heads before | Heads after |
|---|---:|---:|---:|---:|---:|---:|
| Elf bald female | 164.0 | 166.4 | 22.6 | 26.0 | 7.27 | **6.40** |
| Tiefling bald female | 169.0 | 158.6 | 21.5 | 26.0 | 7.87 | **6.10** |
| Human bald male | 165.0 | 156.0 | 23.3 | 26.0 | 7.09 | **6.00** |
| Dwarf bald male | 164.0 | 120.4 | 28.4 | 28.0 | 5.78 | **4.30** |

| Model | Width x | Depth y | Shoulder half-width | Hand / height | Foot / height |
|---|---:|---:|---:|---:|---:|
| Elf bald female | 99.5 | 33.9 | 17.5 | 0.146 | 0.186 |
| Tiefling bald female | 64.1 | 32.9 | 17.0 | 0.145 | 0.185 |
| Human bald male | 109.0 | 37.9 | 28.0 | 0.145 | 0.185 |
| Dwarf bald male | 113.4 | 38.4 | 30.9 | 0.155 | 0.194 |

### 3.1 Horn caveat on the Tiefling

The Tiefling's horns rise above the skull, so a naive `total / (top - chin)` ratio counts
horn as head and understates the body proportion. Horns are thin in **depth** while
staying wide in x, so the cranium metric separates them with a depth-and-population test.
Both numbers are reported:

- cranium-based (used for targeting): **6.10** heads
- horn-inclusive: **5.01** heads

Targeting the horn-inclusive figure would have made the Tiefling the tallest character in
the cast, contradicting 'slightly more compact than the Elf'. The cranium reading is used
throughout. **This is a judgement call and wants human confirmation.**

---

## 4. Per-model bone decisions

Solved scalars (secant, converged in-session):

| Model | head_scale | hand_scale | foot_scale | compress | Hips motion scale |
|---|---:|---:|---:|---:|---:|
| Elf bald female | 1.1481 | 1.4995 | 1.5045 | 1.0180 | 1.0314 |
| Tiefling bald female | 1.2169 | 1.4456 | 1.2564 | 0.9194 | 0.9092 |
| Human bald male | 1.1178 | 1.1471 | 1.1835 | 0.9435 | 0.9222 |
| Dwarf bald male | 0.9964 | 0.6557 | 0.5748 | 0.7620 | 0.6082 |

`compress` multiplies the length of the vertical chain (both legs, Spine/Spine01/Spine02)
only. Leg-to-torso ratio - the thing that actually makes a dwarf read as a dwarf - is set
by the per-archetype base table and is *not* touched by the solver.

### Elf bald female - bone lengths

| Bone | Before | After | Factor |
|---|---:|---:|---:|
| Hips | 11.58 | 11.58 | x1.000 |
| Spine02 | 12.10 | 11.95 | x0.987 |
| Spine01 | 12.10 | 11.95 | x0.987 |
| Spine | 3.51 | 3.50 | x0.998 |
| neck | 12.19 | 7.56 | x0.620 |
| Head | 14.58 | 16.74 | x1.148 |
| LeftShoulder | 11.13 | 11.13 | x1.000 |
| LeftArm | 23.31 | 22.14 | x0.950 |
| LeftForeArm | 22.59 | 21.23 | x0.940 |
| LeftHand | 22.59 | 33.87 | x1.500 |
| LeftUpLeg | 33.76 | 32.65 | x0.967 |
| LeftLeg | 38.49 | 36.83 | x0.957 |
| LeftFoot | 11.29 | 16.99 | x1.505 |
| LeftToeBase | 11.29 | 16.99 | x1.505 |

Right-side bones use identical factors; the source rig's slight L/R asymmetry
(e.g. LeftShoulder vs RightShoulder) is preserved because factors are ratios.

### Tiefling bald female - bone lengths

| Bone | Before | After | Factor |
|---|---:|---:|---:|
| Hips | 11.48 | 11.59 | x1.010 |
| Spine02 | 11.52 | 10.17 | x0.883 |
| Spine01 | 11.52 | 10.17 | x0.883 |
| Spine | 3.72 | 3.31 | x0.892 |
| neck | 13.27 | 7.96 | x0.600 |
| Head | 15.24 | 18.54 | x1.217 |
| LeftShoulder | 11.45 | 11.68 | x1.020 |
| LeftArm | 23.24 | 21.61 | x0.930 |
| LeftForeArm | 21.42 | 19.70 | x0.920 |
| LeftHand | 21.42 | 30.96 | x1.446 |
| LeftUpLeg | 35.69 | 30.52 | x0.855 |
| LeftLeg | 40.55 | 34.30 | x0.846 |
| LeftFoot | 11.45 | 14.39 | x1.256 |
| LeftToeBase | 11.45 | 14.39 | x1.256 |

Right-side bones use identical factors; the source rig's slight L/R asymmetry
(e.g. LeftShoulder vs RightShoulder) is preserved because factors are ratios.

### Human bald male - bone lengths

| Bone | Before | After | Factor |
|---|---:|---:|---:|
| Hips | 12.05 | 12.30 | x1.020 |
| Spine02 | 12.25 | 10.98 | x0.896 |
| Spine01 | 12.25 | 10.98 | x0.896 |
| Spine | 7.46 | 6.82 | x0.915 |
| neck | 6.63 | 3.85 | x0.580 |
| Head | 16.38 | 18.31 | x1.118 |
| LeftShoulder | 17.69 | 21.58 | x1.220 |
| LeftArm | 24.03 | 22.11 | x0.920 |
| LeftForeArm | 21.43 | 19.50 | x0.910 |
| LeftHand | 21.43 | 24.58 | x1.147 |
| LeftUpLeg | 33.10 | 29.04 | x0.877 |
| LeftLeg | 39.93 | 34.66 | x0.868 |
| LeftFoot | 12.12 | 14.35 | x1.184 |
| LeftToeBase | 12.12 | 14.35 | x1.184 |

Right-side bones use identical factors; the source rig's slight L/R asymmetry
(e.g. LeftShoulder vs RightShoulder) is preserved because factors are ratios.

### Dwarf bald male - bone lengths

| Bone | Before | After | Factor |
|---|---:|---:|---:|
| Hips | 12.12 | 12.61 | x1.040 |
| Spine02 | 11.49 | 8.76 | x0.762 |
| Spine01 | 11.49 | 8.76 | x0.762 |
| Spine | 8.40 | 6.40 | x0.762 |
| neck | 6.57 | 3.29 | x0.500 |
| Head | 20.96 | 20.88 | x0.996 |
| LeftShoulder | 21.86 | 21.42 | x0.980 |
| LeftArm | 23.25 | 21.62 | x0.930 |
| LeftForeArm | 24.96 | 22.71 | x0.910 |
| LeftHand | 24.96 | 16.37 | x0.656 |
| LeftUpLeg | 35.31 | 19.91 | x0.564 |
| LeftLeg | 31.64 | 17.36 | x0.549 |
| LeftFoot | 15.83 | 9.10 | x0.575 |
| LeftToeBase | 15.83 | 9.10 | x0.575 |

Right-side bones use identical factors; the source rig's slight L/R asymmetry
(e.g. LeftShoulder vs RightShoulder) is preserved because factors are ratios.

Girth is specified per bone as `[length, girth_x, girth_z]`; the full tables are in
`outputs/scripts/presets/*.json`. Summary of intent:

- **Elf** - lowest girth of the set, longest limb segments, longest gesture lines.
- **Tiefling** - marginally more girth and slightly shorter segments than the Elf.
- **Human** - power silhouette. Width comes from `LeftShoulder`/`RightShoulder` *length*
  1.22 (which pushes the arm root outboard) plus torso lateral girth 1.12-1.14, not from
  inflating the arm tubes. Shoulder half-width 28.0 vs the Elf's 17.5.
- **Dwarf** - shortest and broadest. Legs 0.74/0.72 against a torso held at 1.00, so the
  short-leg/strong-torso ratio is structural. **Arm girth is 1.00/0.99 - no thickening at
  all** - because the source dwarf is already heavy-limbed and any added girth compounded
  into an ogre read.

---

## 5. Localised mesh changes

Applied within the sanctioned list (cranium shaping, jaw simplification, hand/foot volume,
shoulder/torso mass). All are weighted by the Head vertex group and applied in the
original head-bone basis, so they blend smoothly into the neck.

| Pass | Value | Purpose |
|---|---|---|
| `jaw_squash` | 0.94 (Elf/Tief/Human), 0.94 (Dwarf) | Simplify the jaw into one pixel cluster |
| `cranium_bulge` | 1.05 | Room for hairline, horns and headgear at Character Forge stage |
| `head_depth` | 0.97 | Flatter skull reads better under an orthographic camera |
| `head_lift` | 1.0-1.2 | Closes the neck gap opened by the enlarged cranium |

**Not done, deliberately:** no eye-scaling pass. `chibify.py` includes one, and the
textures are packed so it would have run. It was skipped because eye geometry is closer to
facial identity than to proportion, and the brief assigns face treatment to Character
Forge. Flagged as an option if the 128px face reads weakly - see section 9.

No hair, clothing, armour, weapons or props were added. The painted clothing visible in
the previews is baked into the supplied `PF_BaseColor` texture and is untouched.

---

## 6. Animation

### Derivative actions were necessary

Yes, for two reasons: the hip height changed on every model (motion scale 0.61-1.03), and
Required Technical Method #8 requires grounded feet.

Created, with fake user set:

- `PF_Idle_HeroicJRPG`
- `PF_Walk_HeroicJRPG`
- `PF_Run_HeroicJRPG`

### Exactly what changed in them

**Only the three `pose.bones["Hips"].location` f-curves.** Two constant operations:

1. **Proportion scale** - all keyframe values and Bezier handles multiplied by the
   hip-height ratio, so the vertical bob and lateral sway stay proportionate to the new
   leg length.
2. **Grounding offset** - a single constant translation, expressed in the Hips rest basis,
   sized so the lowest mesh point over the *complete* loop lands on z = 0.

| Model | Idle lift | Walk lift | Run lift |
|---|---:|---:|---:|
| Elf | 4.34 cm | 1.50 cm | 5.12 cm |
| Tiefling | 4.36 cm | 1.21 cm | 4.26 cm |
| Human | 3.80 cm | 2.35 cm | 4.77 cm |
| Dwarf | 2.46 cm | 2.67 cm | 2.48 cm |

No rotation channel was touched on any bone. No timing, interpolation or keyframe count
was altered. No resampling, smoothing or redesign was performed. Rotations, scales and all
non-Hips location channels are byte-identical to the approved originals.

### Approved actions are intact

`PF_Idle_Approved`, `PF_Walk_Approved` and `PF_Run_Approved` are present and unedited in
all four files, with their original 240 f-curves and frame ranges (Idle 1-27, Walk 1-9,
Run 1-9). The retarget script writes only to the duplicates; it never iterates
`bpy.data.actions` for editing. The other pre-existing actions (`PF_BindPose`, `PF_Run`,
`PF_Walk`, `PF_Idle`, the `_Transfer` variants, `PF_Run_ForwardLean*`) are also untouched.

### Full-loop validation

Every complete loop was evaluated through the depsgraph - Idle 1-27, Walk 1-9, Run 1-9 -
measuring skinned-mesh minimum z, planted-foot travel, and frame-1-vs-closure vertex RMS.

| Metric | Result |
|---|---|
| Ground penetration, derivative actions | 0.00 cm on all 12 loops |
| Loop closure RMS (frame 1 vs closure frame) | 0.000 mm on all 12 loops |
| Ground penetration, approved actions | 1.8-5.8 cm - **pre-existing in the sources** |

---

## 7. Preservation confirmations

| Item | Status |
|---|---|
| Input files | Untouched. All four SHA-256 hashes re-verified against the manifest; `inputs/` and `reference/` set read-only before any work began |
| Mesh and armature object names | Preserved exactly, per manifest |
| Bone names | All 24 preserved |
| Bone parent hierarchy | Preserved |
| Bone `use_connect` flags | Preserved exactly (residual <= 1e-5 cm) |
| Bone local orientations / rolls | Preserved to float precision. Only the translation component of each rest offset is scaled; the 3x3 basis is copied verbatim. Independently verified: max element-wise deviation of `matrix_local.to_3x3()` across all 24 bones x 4 models = **4.83e-06**. Existing quaternion animation therefore remains valid |
| Vertex group names and semantics | All 22 preserved, weights untouched |
| Topology | Unchanged - vertex, polygon and loop counts identical; only coordinates moved |
| Approved-action f-curve content | Verified by SHA-256 over every (data_path, array_index, keyframe) tuple: **identical to source** in all four files |
| UVs | Unchanged, including the Elf's second `PF_SemanticUV` layer |
| Materials and textures | Unchanged; all four 2048x2048 maps remain packed |
| Shape keys | None existed on any input; none added |
| Modifiers | Armature modifier intact and still bound |
| `PF_ATTACH_*` empties (Elf, 17) | Re-solved through the deformation delta so each stays on its original anatomy |
| Object scale | Unchanged. The pre-existing uniform 0.01 armature scale is untouched; **no non-uniform object scale was introduced** |
| Camera framing | Not used to achieve any proportion. Preview cameras are diagnostic only |

---

## 8. Cross-character cohesion

| Model | Height | Heads | Shoulder half-width | Shoulder / height | Leg length / height |
|---|---:|---:|---:|---:|---:|
| Elf bald female | 166.4 | 6.40 | 17.5 | 0.105 | 0.418 |
| Tiefling bald female | 158.6 | 6.10 | 17.0 | 0.107 | 0.409 |
| Human bald male | 156.0 | 6.00 | 28.0 | 0.179 | 0.408 |
| Dwarf bald male | 120.4 | 4.30 | 30.9 | 0.257 | 0.310 |

- **Dwarf reads as a Dwarf structurally**, not by global scaling: leg length is 0.163 of
  height against the Elf's 0.418, and shoulder-to-height is 0.257 against the Elf's 0.105.
- **Human is the power silhouette**: widest shoulders in absolute terms (28.0) and the
  heaviest torso girth of the three tall characters.
- **Elf is the lightest, most elongated gesture**: tallest, longest legs, lowest girth.
- **Tiefling stays distinct from the Elf**: shorter, slightly heavier, and carrying its
  existing horn and ear anatomy unchanged.
- Cranium height is 26.0 for the three tall characters and 28.0 for the Dwarf, so faces
  occupy a comparable pixel budget across the cast.

---

## 9. Open concerns for human review

1. **Foot slide in Walk and Run is large and inherited.** Planted-foot travel measures
   16-70 cm depending on model. It is present in the approved sources at the same
   magnitude (Elf walk: 69.78 cm approved vs 69.84 cm derivative), so the retarget did not
   introduce it - these are in-place cycles authored for root-motion-driven playback. If
   they are ever played without root motion, the slide will be visible. Out of scope here
   because it would require editing approved rotations.
2. **Approved actions still penetrate the ground by 1.8-5.8 cm.** Left as found, since they
   are protected. Only the derivative actions are grounded. Worth deciding whether the
   canonical files should be corrected upstream.
3. **Tiefling horn measurement convention** (section 3.1) needs sign-off.
4. **Face readability at 128px was not evaluated by a pixel artist.** The eye pass was
   deliberately skipped. If faces read weakly in the sprite previews, a mild eye scale
   (~1.10) is available as a one-line preset change.
5. **Dwarf stature is now art-directed, not reference-derived.** Its cleric reference reads
   ~3.5 heads; the delivered Dwarf is 4.30 following the 'too short' note. It is therefore
   the one model that intentionally departs from its reference.
6. **Elf grew slightly taller** (164.0 -> 166.4) because enlarged feet raise the ankle. If
   absolute stature is constrained elsewhere in the pipeline, say so and it can be pinned.
7. **Self-intersection was not exhaustively tested.** Checks covered ground contact, foot
   travel, gross volume and loop closure - not per-triangle interpenetration in deep
   elbow/knee flexion.
8. **Renders are Cycles, anti-aliased.** They are 3D diagnostics, not final pixel art. The
   style profile's binary-alpha and no-AA rules apply to the Character Forge output stage;
   binary-alpha variants of the sprite previews are supplied for envelope checking.

---

## 10. Files produced

### Models (`outputs/`)

- `elf_bald_female_heroic_jrpg_v1.blend`
- `tiefling_bald_female_heroic_jrpg_v1.blend`
- `human_bald_male_heroic_jrpg_v1.blend`
- `dwarf_bald_male_heroic_jrpg_v1.blend`

### Report

- `outputs/REPORT.md` (this file)

### Scripts (`outputs/scripts/`)

- `heroic_retarget.py` - the retarget, solver and measurement
- `ground.py` - derivative-action grounding pass
- `validate.py` - full-loop deformation and animation validation
- `preview.py` - diagnostic render driver
- `postprocess.py` - contact sheet, GIF and comparison assembly
- `make_presets.py` - archetype preset generator
- `presets/*.json` - the four solved preset tables

### Review renders (`outputs/previews/`)

- `PROPORTION_DECISION_A_vs_B.png` - the bands-vs-references comparison
- `LINEUP_same_scale_front.png`, `LINEUP_same_scale_right.png`
- `turnaround_{elf,tief,human,dwarf}.png` - front/right/back rest, common scale
- `beforeafter_{...}.png` - identical camera and scale
- `sprite128_{...}_native.png`, `_binary_alpha.png`, `_binary_alpha_4x.png`
- `run_contactsheet_{...}_{front,right}.png` and `_2x.png` - complete 8 frames
- `run_{...}_{front,right}.gif` - animated, complete loop
- `walk_contactsheet_{...}_front.png`, `walk_{...}_front.gif` - complete 8 frames
- `idle_contactsheet_{...}_front.png`, `idle_{...}_front.gif` - complete 26 frames
- `loopclosure_run_{...}.png` - frame 1 against closure frame 9
- `raw/` - all 248 source frames

Annotated measurement sheets derived from the seven reference images were kept in the
working directory and deliberately **not** written into `outputs/`, per
`reference_policy.redistribute_reference_images: false` in the style profile.

---

## 11. Independent verification

A separate script (`scripts/verify.py` behaviour, run post-save) re-opened every source and
every output and compared: vertex/polygon/loop counts, UV layer names, material names,
vertex-group name sets, bone name sets, parent map, `use_connect` map, object scales, shape
keys, modifiers, packed image inventory, and a SHA-256 signature of all approved-action
f-curve keyframe data. Every invariant matched. The only differences between source and
output are the intended ones: moved vertex coordinates, moved bone rest transforms,
re-solved attach empties, and three added `*_HeroicJRPG` actions.

Input SHA-256 hashes were re-verified after all work completed and still match the manifest.

---

## 12. Stop condition

Stopped after the four `.blend` files, the previews and this report. No Pixel Forge code,
canonical file, Character Forge asset, component sheet or rendering-pipeline file was
modified. Nothing under `inputs/` or `reference/` was written.
