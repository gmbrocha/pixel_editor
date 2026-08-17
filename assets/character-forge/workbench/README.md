# Component silhouette starter workbench

These are deliberately rough, editable **Front Walk** starting points—not finished
production art. Each starter is aligned to all six authoritative 64x64 Front Walk
frames and is already selectable in Character Forge.

## Start here tomorrow

1. Open `component-silhouette-starters-all-frames.png` for the complete visual index.
2. Pick a design and open its `regions.png` from the path listed below in Pixel Editor.
3. Change the silhouette or semantic blocks using only the exact marker colors.
4. Run `python tools/generate_component_silhouette_starters.py` to refresh previews.
5. Run the same command with `--check` when the generated files should be current.

The marker colors are main `#FF4040`, lining/secondary `#40FF80`, trim
`#FFD840`, hardware/accent `#7A40A8`, and special material `#083EFF`.

## Starters

| # | Character Forge choice | Slot | Editable semantic mask |
|---|---|---|---|
| 1 | Messy Frost Hair | Hair | `parts/hair/workbench-messy-frost-hair/regions.png` |
| 2 | One-Shoulder Pauldron | Shoulder / Chest | `parts/shoulder_chest/workbench-one-shoulder-pauldron/regions.png` |
| 3 | Leather Gloves | Hands | `parts/hands/workbench-leather-gloves/regions.png` |
| 4 | Eye Patch | Face | `parts/face/workbench-eye-patch/regions.png` |
| 5 | Double Leaf Pauldrons | Shoulder / Chest | `parts/shoulder_chest/workbench-double-leaf-pauldrons/regions.png` |
| 6 | Crooked Mage Hat + Vestments | Outerwear | `parts/outerwear/workbench-crooked-mage-vestments/regions.png` |
| 7 | Rugged Leather Armor | Outerwear | `parts/outerwear/workbench-rugged-leather-armor/regions.png` |
| 8 | Ratty Shawl | Neck | `parts/neck/workbench-ratty-shawl/regions.png` |
| 9 | Cloth Headband | Headwear | `parts/headwear/workbench-cloth-headband/regions.png` |
| 10 | Orcish Spiked Armor | Outerwear | `parts/outerwear/workbench-orcish-spiked-armor/regions.png` |
| 11 | Horned Cult Mask | Face | `parts/face/workbench-horned-cult-mask/regions.png` |

## Useful caveats

- The Hair starter is currently one Front layer. Longer hairstyles will eventually
  need separate rear-hair and fringe/crown layers.
- Gloves trace the moving hand silhouettes closely; refine their cuffs first.
- The combined Mage starter reserves Headwear and Neck. It can later be split into
  independent hat and vestment components.
- Orcish Armor reserves Shoulder / Chest so it cannot collide with the pauldron
  starters.
- The Cult Mask reserves Headwear. Its exaggerated horns are intentional tracing
  material and easy to shorten in the semantic mask.
- Unsupported directions and Idle/Run intentionally fall back to the base.

`starter-component-concept-board.png` is an AI-generated shape-language reference
only. No generated mannequin pixels were copied into any production overlay; every
actual starter is a deterministic semantic mask built over the authoritative base.
