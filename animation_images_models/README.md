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
