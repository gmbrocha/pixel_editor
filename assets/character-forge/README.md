# Character Forge assets

`sheet_specs.json` is the shared authority for runtime composition and the Pip &
Pyre component factory. It records frame geometry, direction ordering, timing,
matte handling, generation transforms, the generation-only reversible reserved-blue
mannequin ramp, slot regions, layers, and canonical SHA-256 checksums. Canonical
runtime sheets are never recolored.

## Canonical base

- `idle.png`: 64x256 RGBA; one 64x64 frame in Front, Left, Right, Back rows. Its
  exact `#FFFFFF` source matte is cleared at runtime; the off-white eye pixels are
  preserved.
- `walk.png`: 384x259 RGBA; six frames in Front, Back, Right, Left rows. Its three
  extra transparent bottom pixels are preserved. The corrected authored sheet is
  retained at `base_sources/human-01/walk-authored.png`. Runtime rows 1–3 are
  preserved exactly, and only the Left row is reversed as frames
  `6, 5, 4, 3, 2, 1`. The resulting Left frames are the authored `-1, -1` aligned
  mirrors of the corresponding Right frames.
- `run-front.png`, `run-back.png`, `run-right.png`, and `run-left.png`: authoritative
  384x64 six-frame strips.
- `run.png`: derived 384x256 sheet assembled pixel-identically in Front, Back,
  Right, Left rows by `tools/build_character_forge_run_sheet.py`.

Generation and promotion refuse changed canonical checksums. Accept an intentional
same-geometry revision only with:

```powershell
python component_pipeline.py rebaseline --confirm human-01
```

Regenerate or byte-verify the corrected Walk runtime sheet with:

```powershell
python tools/build_character_forge_walk_sheet.py
python tools/build_character_forge_walk_sheet.py --check
```

## Production components

Every component lives beneath `parts/<slot>/<component-id>/` with a versioned
`manifest.json` and canonical-size transparent animation overlays. Runtime discovery
uses manifests; rejected/raw pipeline candidates never belong here.

`walking-shirt-test` is an incomplete `torso` component (displayed as **Tops**).
It covers all six Front Walk frames, falls back to the base elsewhere, and preserves
its exact nine-shade recolorable blue ramp with `#2C4267` as the main color.

`leather-boots-front-test` is an incomplete Front Walk component for **Feet**.
The original larger-hood cloak and its two derived treatments are preserved under
`legacy_sources/old-model-cloaks/` but are intentionally excluded from runtime
discovery. All selectable cloaks now use the complete semantic-region source,
cover all six Walk frames in Front, Back, Right, and Left, reserve Headwear and
Neck, and fall back exactly for unsupported animations.

## Deterministic variants

`tools/generate_character_component_variants.py` derives three non-destructive
examples from the shirt and boots: palette-remapped crimson cloth,
coordinate-masked cream/indigo cloth, and stable blackened iron. Cloak treatments
have moved entirely to semantic-region finishing. The earlier seeded Muddy Field
Boots experiment is intentionally excluded until a semantic-region source is
authored. Every transform preserves the source alpha mask and records its source
hash, output hash, and method in the derived manifest.

Regenerate or verify the committed examples with:

```powershell
python tools/generate_character_component_variants.py
python tools/generate_character_component_variants.py --check
```

## Semantic-region cloak finishing

`tools/finish_component_regions.py` accepts a base composite or transparent mask
containing five exact opaque authoring colors: main `#FF4040`, lining `#40FF80`,
trim `#FFD840`, hardware `#7A40A8`, and hood panel `#083EFF`. It strips every
non-marker pixel, locks the resulting alpha silhouette, and applies five-step
material ramps, fixed top-left lighting, colored boundary shading, and
clasp-anchored folds without frame-local random noise.

The supplied `walk_hooded_cloak.png` is preserved byte-for-byte at
`semantic_sources/hooded-cloak-walk/authored-regions.png`. It contains authored
Front, Back, and Right rows. `tools/complete_cloak_walk_regions.py` creates the
canonical 384x259 `semantic-regions.png`, applies the same `1, 2, 3, 6, 5, 4`
side-view phase correction as the character base, and fills Left with a per-frame
Right mirror plus the matching `-1, -1` alignment offset. The source manifest
records both hashes, direction provenance, marker counts, frame geometry, and the completion algorithm. The
superseded Front-only source remains recoverable under
`legacy_sources/semantic-cloak-front-walk/`.

Ten full-direction Walk components are derived from the canonical source:
Forest Wool, Burgundy + Gold Trim, Storm Blue & Silver, Autumn Russet, Pointed
Hood Green, Winter Gray, Royal Amethyst + Gold, Midnight Raven, Desert Sand +
Teal, and Ivory + Crimson. Regenerate or byte-verify the source, every finished
sheet, and every component manifest with:

```powershell
python tools/generate_cloak_walk_variants.py
python tools/generate_cloak_walk_variants.py --check
```

### Warlock Robe variants

The supplied two-region `walk_warlock_robe.png` is preserved byte-for-byte at
`semantic_sources/warlock-robe-front-walk/authored-regions.png`. Its six Front
Walk frames use main fabric `#FF4040` and trim `#FFD840`; the deterministic
finisher normalizes the sheet to 384x259 without altering its authored pixels.
Four Front Walk treatments are registered as Outerwear: Void Amethyst, Blood
Ritual, Necrotic Jade, and Astral Midnight. They do not reserve Headwear or Neck.

Regenerate or verify the source, outputs, and manifests with:

```powershell
python tools/generate_warlock_robe_variants.py
python tools/generate_warlock_robe_variants.py --check
```

## Editable silhouette starter workbench

`workbench/` contains eleven deliberately rough Front Walk component starters for
the next manual-art pass: messy hair, one pauldron, gloves, eyepatch, double
pauldrons, mage hat/vestments, leather armor, ratty shawl, headband, orcish armor,
and a horned cult mask. Each is registered in Character Forge, has all six Front
Walk frames, includes a directly editable exact-color `regions.png`, and falls
back to the base outside Walk/Front.

Open `workbench/component-silhouette-starters-all-frames.png` for the visual
index and `workbench/README.md` for the direct mask paths and component-specific
caveats. Regenerate or verify the complete set with:

```powershell
python tools/generate_component_silhouette_starters.py
python tools/generate_component_silhouette_starters.py --check
```

Normal component discovery exposes only `approved` manifests. Character Forge is a
developer picker and also exposes `incomplete` components for visual inspection.
