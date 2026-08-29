# Pixel Forge 3D Production Assets

This tree separates reproducible production assets from local acquisition and working data.

- `elf_bald_female/canonical/` is the tracked semantic mannequin, contract, debug texture, and inspection set.
- `elf_bald_female/editable/` contains portable tracked Blender editing starters. These `.blend` files are self-contained Git LFS assets intended to move between machines.
- Raw FBXs, ZIP archives, extracted packages, working blends, diagnostics, and Blender backups are ignored.

The canonical blend is self-contained and does not require the ignored Meshy files for inspection, rendering, or use of its existing actions. Full regeneration still requires the corresponding local source whose SHA-256 is recorded in its manifest.

See `docs/BLENDER_CHARACTER_PIPELINE.md` for rebuild, validation, staging, review, and promotion commands.

## Portable Run redo

After cloning, run `git lfs pull`, then open:

`elf_bald_female/editable/run_redo_v1.blend`

The file opens on `PF_Run_Redo_Edit`, an eight-pose editable copy of the currently installed Run. `PF_Run_Meshy_Edit` is included as an editable copy of the untouched Meshy Run. The complete `PF_Run_ForwardLean_HeadDown` and `PF_Run` actions remain protected comparison/recovery sources. The project has packed assets and requires no external FBX, ZIP, texture, or linked Blender library to open.

See `elf_bald_female/editable/README.md` for editing and save guidance.

## Approved motion transfer

The canonical elf mannequin retains the protected Meshy actions and also stores
the exact user-approved `PF_Idle_Approved`, `PF_Walk_Approved`, and
`PF_Run_Approved` actions. `motion_transfer_targets.json` maps the ignored local
Meshy bind, Walk, Run, and texture packages for the Tiefling female, Dwarf male,
and muscular Human male.

Build review-only candidates and all four-direction 128px GIFs with:

```powershell
python tools/build_motion_transfer_candidates.py --target all --force
python tools/build_motion_transfer_candidates.py --target all --check
```

The Tiefling female, Dwarf male, and muscular Human male have now been approved.
Their packed canonical blends and hash manifests live under each model's tracked
`canonical/` directory. Meshy Idle is not used: the approved elf Idle transfers
from the bind pose. The less-muscular Human remains outside the configuration.

All four approved Idles use the shared timing contract in
`approved_motion_timing.json`: preserves the 26-frame/12 FPS authored Idle action and defines its 14-frame/6 FPS Character Forge sampling. Runtime frames 6 and 13 each display for 1500 ms.
Rebuild or verify the promoted target Blender files and Character Forge bases
with:

```powershell
python tools/promote_motion_transfer_bases.py --target all --force
python tools/promote_motion_transfer_bases.py --target all --check
```

Ignored candidate blends, extracted FBXs, source renders, and pixel previews
remain under each target's `working/` tree as reproducible intermediate data.

## Component cleanup review bundle

`component_cleanup_v2/` contains 300 editable, component-only sprite sheets for
the 25 generated families fitted to all four approved bases. The sheets remain
review-only and are not promoted into Character Forge. They receive one
conservative preprocessing pass that removes tiny detached islands, chamfers
solid one-pixel outline corners, and fills only enclosed one- or two-pixel
transparent holes. Gloves, boots, open vests, and hooded pieces preserve their
two largest intentional pieces.

Use `component_cleanup_v2/index.csv` to locate a family and model. Each family
folder contains Idle, Walk, Run, and a hash-linked cleanup manifest; twelve
first-frame composite boards are under `component_cleanup_v2/review/`.

Rebuild or byte-verify the complete review bundle with:

```powershell
python tools/build_component_cleanup_bundle.py --force
python tools/build_component_cleanup_bundle.py --check
```

The superseded cleanup-v1 and transitional 14-frame migration bundles have
been removed. `component_cleanup_v2/` is the sole editable mirror of the
promoted component-family baseline.
