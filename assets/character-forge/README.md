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
  extra transparent bottom pixels are preserved.
- `run-front.png`, `run-back.png`, `run-right.png`, and `run-left.png`: authoritative
  384x64 six-frame strips.
- `run.png`: derived 384x256 sheet assembled pixel-identically in Front, Back,
  Right, Left rows by `tools/build_character_forge_run_sheet.py`.

Generation and promotion refuse changed canonical checksums. Accept an intentional
same-geometry revision only with:

```powershell
python component_pipeline.py rebaseline --confirm human-01
```

## Production components

Every component lives beneath `parts/<slot>/<component-id>/` with a versioned
`manifest.json` and canonical-size transparent animation overlays. Runtime discovery
uses manifests; rejected/raw pipeline candidates never belong here.

`walking-shirt-test` is an incomplete `torso` component (displayed as **Tops**).
It covers all six Front Walk frames, falls back to the base elsewhere, and preserves
its exact nine-shade recolorable blue ramp with `#2C4267` as the main color.

Normal component discovery exposes only `approved` manifests. Character Forge is a
developer picker and also exposes `incomplete` components for visual inspection.
