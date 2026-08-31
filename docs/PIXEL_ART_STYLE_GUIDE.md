# Pixel Forge Heroic JRPG Style Guide

Status: Proposed canonical style policy
Profile ID: `pixel_forge_heroic_jrpg_v1`
Companion machine profile: `docs/PIXEL_ART_STYLE_PROFILE_V1.json`

## Purpose

This guide defines the intended final appearance of Pixel Forge character sprites. It synthesizes the strongest shared qualities of the seven approved inspiration images without copying any one artist, character, costume, or palette.

The style is named **Pixel Forge Heroic JRPG**. It should read as deliberately authored pixel art: expressive, readable, colorful, and game-ready at 128x128. Blender establishes pose, proportions, camera, semantic regions, and motion. It is not the final authority on every contour or pixel cluster.

The reference images are inspiration only and must not be redistributed as project assets or treated as literal generation targets.

## The Style in One Paragraph

Pixel Forge Heroic JRPG sprites have bold class-specific silhouettes, heroic but varied proportions, large readable hands, feet, heads, hair, and equipment, compact intentional pixel clusters, selective dark contours, and broad material planes with limited shading. They favor clarity and character over anatomical literalism. A mage may be narrow and flowing, a dwarf broad and compressed, and a warrior massive and armored, yet all belong to the same world through shared contour logic, palette discipline, lighting, cluster scale, and animation rules.

## The Seven Style Pillars

1. **Silhouette before surface.** The character, pose, class, held item, and facing direction must read from the outer shape alone.
2. **Archetype before uniform proportion.** Body type and class remain distinct; the style does not force every character into one template.
3. **Deliberate clusters, never reduction noise.** Every visible pixel belongs to a useful shape, edge, highlight, or texture decision.
4. **Readable exaggeration.** Heads, hands, feet, weapons, hair, and loose clothing may exceed the literal 3D footprint when that improves the sprite.
5. **Material clarity with few tones.** Skin, cloth, leather, metal, hair, horn, and magical effects should be distinguishable without gradients or excessive colors.
6. **Stable motion.** Contours, palette roles, equipment, anatomy, and layering remain coherent through the complete animation.
7. **One world, many silhouettes.** Shared construction rules create cohesion; costume, build, color accents, and equipment create individuality.

## Canonical Technical Target

- Canvas: 128x128 pixels per frame.
- Alpha: binary transparency only. No semi-transparent edge pixels.
- Sampling: nearest-neighbor only after pixel construction.
- Anti-aliasing: prohibited.
- Blur and automatic smoothing: prohibited.
- Dithering: off by default; allowed only as an explicitly authored, temporally stable material treatment.
- Export background: transparent. Ground lines and review backgrounds are review aids, not character pixels.
- Final composite palette: target 24 colors, hard maximum 32 colors excluding transparency.
- Individual component ramp: normally 3-5 colors, including its darkest contour/shadow color.
- Canvas occupancy: preserve the approved per-character and per-camera framing. No frame may resize the character independently.
- Safe margin: at least 4 transparent pixels around all non-effect character pixels. Declared effects may use a separate envelope.

The existing deterministic 16-color render may remain a useful source and fallback. The final dressed sprite may use more colors because multiple readable materials and accents are part of this style.

## Proportion Language

The style uses **heroic compression**, not a universal chibi scale.

- Enlarge the head enough to support a recognizable face, hairline, horns, and headgear.
- Make hands and feet large enough to survive animation and communicate gesture and contact.
- Shorten and simplify thin limb segments when literal anatomy creates noisy or fragile one-pixel bridges.
- Enlarge signature weapons and tools until their type and orientation are immediately legible.
- Preserve the character's archetype:
  - Dwarves are short, broad, dense, and grounded.
  - Heavy warriors are wide through torso, shoulder, hands, and equipment.
  - Elves and agile characters are leaner, with longer gesture lines and lighter visual mass.
  - Casters may use tall headwear, flowing cloth, long staves, and asymmetrical silhouettes.
  - Humans retain readable build differences rather than converging on a single average body.
- Exaggeration must not change the character's identity, direction, action, or equipment loadout.

Exact ratios are intentionally calibrated from approved hero sprites rather than imposed before the golden set exists.

## Silhouette and Pose

At native size, the viewer must be able to identify:

- facing direction;
- action and phase of motion;
- planted versus airborne foot;
- leading arm and leg;
- major garment shapes;
- held weapon or prop;
- hair, horns, hat, hood, or other major head silhouette.

Use deliberate negative space between limbs, torso, weapons, and hanging cloth. It is acceptable to simplify a limb gap, shift a contour by one or two final pixels, or enlarge a hand or foot when this prevents forms from visually merging.

Do not create:

- detached accidental islands;
- isolated one-pixel stems or spikes;
- ambiguous merged hands and torsos;
- limbs that reverse apparent direction between frames;
- thin noisy contours inherited from downsampled geometry;
- silhouette changes that imply an undeclared item or altered anatomy.

## Pixel Cluster Construction

Pixels are composed as clusters, not sprinkled as detail.

- Prefer compact blocks, stepped diagonals, and clean directional runs.
- Remove isolated pixels unless they serve a specific readable purpose such as an eye, buckle glint, or magical spark.
- A one-pixel accent must have a stable semantic role and remain stable when the animation requires it.
- Avoid staircase edges that alternate irregularly without describing curvature.
- Avoid internal single-pixel holes inside otherwise solid components.
- Join tiny same-material fragments when separation does not improve readability.
- Use the fewest clusters necessary to describe the form at 1x.

Every sprite must be reviewed at both native 1x and nearest-neighbor enlarged view. Enlarged inspection finds defects; native inspection decides whether the art reads.

## Contour Policy

Contours are selective and chromatic.

- Use deep navy, plum, umber, or another hue-related dark instead of outlining everything in pure black.
- The normal outer contour is one final pixel thick.
- Two-pixel masses are allowed only where the dark area is also a cast shadow, deep overlap, or intentional material plane.
- Do not apply a uniform border around every component.
- Internal boundaries should be lighter or omitted when value contrast already separates the forms.
- Break or brighten the contour on strongly lit upper-left edges.
- Strengthen the contour at contact points, overlaps, underside planes, and important silhouette turns.
- Component outlines must merge into the final character's contour system; stacked components must not accumulate concentric borders.

## Palette and Value Structure

Each character uses one coherent final palette across all animations and directions.

- Organize color by functional ramps: skin, hair/horn, primary cloth, secondary cloth, leather, metal, and accent/effect.
- Most material ramps contain a contour/deep-shadow, shadow, local color, and highlight. A fifth color is optional for focal materials.
- Reserve the darkest values for silhouette, deep overlaps, and focal separation.
- Reserve the brightest values for face, metal glints, magical effects, and other intentional focal points.
- Use one dominant color family, one supporting family, and one or two restrained saturated accents.
- Avoid assigning a unique ramp to every small object.
- Avoid near-duplicate colors that add palette count without creating visible structure.
- Palette swaps must remap the complete ramp while preserving value order and color-role relationships.

## Lighting and Shading

The canonical light comes from the upper-left/front of the character relative to the rendered view.

- Shade with connected planes, not soft gradients.
- Use highlights to explain planes and materials, not to trace every edge.
- Place deeper shadow under hair, chin, arms crossing the torso, belts, cloaks, and overlapping armor.
- Keep light direction stable in every frame and direction.
- Material response:
  - Cloth: broad quiet planes, restrained highlights.
  - Leather: warm shadows, selective edge or crease highlights.
  - Metal: stronger value jumps and small controlled glints.
  - Skin: softer value progression than metal, with readable face and joint planes.
  - Hair and fur: grouped locks or masses, never strand-level noise.
  - Horn, bone, and wood: distinct ramps with simple directional banding.

Ambient occlusion may support overlaps, but it must not muddy the silhouette or become a dark halo around every part.

## Faces, Hair, and Headgear

Faces are minimal but expressive.

- Prioritize head shape, hairline, brow/eye cluster, nose plane, and jaw or beard shape.
- A face does not require two fully rendered eyes in every direction.
- Facial pixels must not flicker between unrelated placements from frame to frame.
- Hair is designed as major locks and outer masses with a 3-5 color ramp.
- Hair may extend beyond the Blender silhouette within its declared semantic envelope.
- Front hair, back hair, face accessories, horns, hats, hoods, and cowls use explicit layer ownership.
- A hood or cowl may occlude back hair where the recipe declares coverage; exposed hair remains visible according to the coverage mask.

## Clothing, Armor, Props, and Effects

- Fitted clothing follows the anatomy closely but may clean or strengthen its contour.
- Loose shirts, skirts, coats, robes, and cloaks may create broader readable silhouettes.
- Armor uses large plates and clear overlaps; avoid tracing every 3D panel seam.
- Belts, buckles, straps, and trim are accents, not fields of noise.
- Props and weapons may be exaggerated for recognition but must preserve their declared type and grip.
- Held objects must remain connected to the correct hand unless the animation explicitly releases them.
- Effects use a separate, declared semantic layer and a small high-saturation ramp. They are not allowed to hide animation errors.

## Controlled Silhouette Envelopes

The Blender alpha is the **authoritative core**, not an absolute artistic prison. Final pixels may leave that core only within a declared semantic envelope.

Initial final-pixel budgets, to be calibrated against the golden hero set:

| Semantic class | Typical excursion from core | Intent |
| --- | ---: | --- |
| Torso/limb anatomy | 1 px | Clean a contour, close fragile gaps |
| Hands and feet | 2 px | Improve gesture, grip, and ground contact |
| Fitted clothing/armor | 1 px | Strengthen silhouette without changing build |
| Hair, beard, fur | 3 px | Form readable locks and masses |
| Skirt, coat, robe, cloak | 4 px | Support flowing secondary silhouettes |
| Rigid weapon or prop | 2 px | Improve legibility while preserving geometry |
| Declared magical effect | 6 px | Permit effect shapes in their own semantic layer |

These budgets are local allowances, not permission to inflate the whole sprite. Any excursion must:

1. remain connected to its legal semantic region unless it is a declared particle/effect;
2. maintain high overlap with the authoritative core;
3. avoid invading a protected foreground region;
4. remain temporally coherent;
5. preserve identity, proportions, action, and equipment.

Hard clipping to the Blender silhouette remains available as a conservative fallback and catastrophic-failure safeguard.

## Semantic Occlusion and Layer Ownership

The final composite must be depth-aware. A component is not allowed to win merely because it was drawn later.

Canonical conceptual order:

1. back effects and back equipment;
2. back hair and back loose garments;
3. background anatomy;
4. torso and leg garments;
5. visible foreground anatomy;
6. gloves, boots, and foreground equipment according to ownership;
7. face accessories and front headwear;
8. front hair and declared foreground effects.

Required ownership rules:

- A torso garment must not cover a hand or foreground forearm crossing the torso.
- Pants, skirts, and belts must not cover a foreground hand or weapon.
- Gloves replace the owned hand pixels but remain below a held weapon where the grip requires it.
- Boots replace the owned foot/lower-leg region and respect overlying pants, skirts, or armor.
- Front hair may cover a blindfold or face accessory where the hair mask says it passes in front.
- Back hair remains behind the body and may be hidden by a hood, cowl, armor, or cloak coverage mask.
- Component contour expansion must never erase protected foreground anatomy.

When depth is ambiguous, the recipe must declare ownership; the compositor must not infer it from component file order.

## Directional Authoring

- Front, back, and right are authored directional truths.
- Left may be produced by mirroring the **complete right-facing composite** only when the entire recipe is declared mirror-safe.
- Asymmetrical hair, scars, horns, shoulder armor, weapon hands, pouches, symbols, and directional lighting require an explicit left treatment or mirror metadata.
- Never mirror only one layer after compositing has established directional overlaps.
- Every direction must preserve recognizable materials, proportions, and equipment ownership.

## Animation Policy

The complete approved animation is the unit of authorship and approval.

- Run: all 8 canonical frames at the approved timing.
- Walk: all 8 canonical frames at the approved timing.
- Idle: all 14 runtime frames with the approved pause timing represented as playback duration, not duplicate editing frames.
- Four-frame sampling or propagation is not an accepted production shortcut.
- Frame 1 and loop closure must be visually continuous under native playback.

Temporal requirements:

- No contour crawling unrelated to motion.
- No palette-role changes or material flicker.
- No detached pixel islands appearing for a single frame.
- No accessory popping, unexplained side switching, or grip changes.
- No accidental duplicate poses.
- Arms and legs must preserve the intended phase and may not appear to reverse.
- Hair and loose clothing follow the primary motion with controlled secondary overlap, not independent floating.
- Planted feet remain visually planted unless the source motion lifts them.
- Pixel clusters may deform between frames, but their semantic identity and volume must remain coherent.

Approval requires viewing the full loop at native scale. Attractive isolated poses are necessary but insufficient.

## Authoritative Source Contract

For any generated or assisted finishing pass:

- Blender owns camera, action, pose, facing, body identity, equipment identity, and semantic source maps.
- The approved deterministic render owns the composition core and fallback output.
- The style finisher may simplify, cluster, recolor within declared ramps, improve contours, exaggerate within envelopes, and resolve approved semantic overlaps.
- The style finisher may not invent or remove anatomy, change the action, change facing, replace equipment, alter costume semantics, or move the character outside approved framing.
- Final output is a flattened recipe result plus the metadata required to reproduce its layers and validation.

## Hard Rejection Rules

Reject a frame or loop when any of the following occurs:

- wrong canvas, frame count, direction, timing, or alpha mode;
- anti-aliased or semi-transparent character edges;
- palette exceeds 32 colors without an approved exception;
- missing, doubled, detached, or invented anatomy;
- changed character identity, action, facing, or equipment;
- protected foreground anatomy covered by an underlying component;
- detached non-effect pixels or unexplained internal transparent holes;
- major silhouette change outside declared envelopes;
- clipping against the canvas safe margin;
- temporal reversal, popping, flicker, or broken loop continuity;
- left mirroring that reverses an asymmetrical design incorrectly.

## Review Judgments

The following require human review rather than automatic rejection in isolation:

- exact contour-break placement;
- whether an exaggeration improves readability;
- ideal cluster size for a face or material;
- saturation and accent balance;
- whether a legal loose-cloth or hair excursion feels excessive;
- whether asymmetry strengthens the pose without changing identity.

## Golden Anchor Set

Before this profile becomes locked canonical policy, create and approve a small golden set:

1. Tiefling female Run, front, all 8 frames, fully dressed with hair and at least three overlapping components.
2. The same Run, back and right, with the declared mirror-safe left result.
3. One Dwarf frame demonstrating compact proportions, beard/hair, armor or clothing, and a large prop.
4. One muscular Human frame demonstrating broad anatomy, material separation, and readable hands.
5. One caster or loose-garment frame demonstrating cloth, hair, effect, and silhouette-envelope behavior.

The golden set should establish exact contour density, palette scale, face construction, proportion ranges, and envelope calibration. It becomes the provider-neutral visual test target.

## Frame Review Checklist

- Does the silhouette communicate class, direction, and action at 1x?
- Are leading limbs, planted feet, hands, and held items unambiguous?
- Are pixels organized into purposeful clusters?
- Are contours selective, chromatic, and normally one pixel thick?
- Do materials read through value structure rather than texture noise?
- Is the face readable without over-detail?
- Are hair and loose garments expressive but semantically attached?
- Did every foreground body part survive component compositing?
- Are all silhouette excursions legal for their semantic regions?
- Is the palette coherent and within budget?
- Does the complete native-speed loop remain stable?
- Do all directions look like the same character and recipe?

## North Star

The finished sprite should feel as though a skilled pixel artist used the Blender render as animation reference—not as though a 3D render was merely reduced, outlined, or filtered.
