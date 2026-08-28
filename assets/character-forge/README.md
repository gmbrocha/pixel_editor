# Character Forge assets

Character Forge now uses the 128×128 semantic elf pipeline exclusively. The old
64px human base, generated candidates, reserved-blue mannequin output, workbench,
component sources, and retired factory code/tests remain recoverable under
`legacy_sources/pre-semantic-elf-20260821/` but are outside runtime discovery.

## Runtime base

`sheet_specs.json` registers `elf-01` (`Semantic Elf Base`) with four rows in
Front, Back, Right, Left order:

- Idle: 26 frames per direction at 12 FPS, 3328×512 sheet.
- Walk: 8 frames per direction at 10 FPS, 1024×512 sheet.
- Run: 8 frames per direction at 10 FPS, 1024×512 sheet.

The sheets live under `bases/elf-01/`. They are ordinary indexed-palette pixel
art with binary transparency and 128×128 cells. Idle is derived non-destructively
from 13 manually authored poses by placing those poses on alternating frames and
using Blender's keyed-transform interpolation for the in-betweens. Run uses the
approved forward-lean/head-down action.

## Semantic packages

`semantic/elf-01/<animation>/` contains the complete durable package for each
animation:

- ordinary art sheet and native-speed direction GIFs;
- exact 8-bit per-pixel anatomical region IDs;
- color-coded region inspection sheet;
- individual art, ID, and preview frames;
- all 13 component-slot masks and all 13 body-hide masks;
- direction strips, palette, hashes, source-frame mapping, and manifest.

Every opaque art pixel has exactly one region ID, and transparent pixels have ID
zero. `tools/build_semantic_sprite_package.py --check` recreates a package and
byte-compares it.

## Starter components

The live `parts/` tree contains only five simple, approved, region-derived items:

- Basic Linen Shirt (`torso`)
- Simple Work Vest (`outerwear`)
- Basic Trousers (`legwear`)
- Plain Leather Gloves (`hands`)
- Tall Work Boots (`feet`)

Each covers Idle, Walk, and Run in all four directions. Each manifest declares a
five-color material ramp, so Character Forge's existing color picker can produce
arbitrary color variants without duplicating component entries. These are basic
pipeline proofs intended for later pixel cleanup, not final costume design.

Review contact sheets for the base and every starter item are under `review/`.

## Regeneration

After building the three semantic animation packages, reinstall the runtime and
starter components with:

```powershell
python tools/build_semantic_character_forge.py `
  --asset-root assets/character-forge `
  --idle-package animation_images_models/elf_bald_female/working/idle_26f_128_semantic `
  --walk-package animation_images_models/elf_bald_female/working/walk_manual_v1_128_semantic `
  --run-package animation_images_models/elf_bald_female/working/run_128_semantic `
  --force
```

Runtime discovery reads only manifests beneath the live `parts/` directory; it
does not scan `legacy_sources/`.
