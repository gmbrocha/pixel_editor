# Pixel Forge 3D Production Assets

This tree separates reproducible production assets from local acquisition and working data.

- `elf_bald_female/canonical/` is the tracked semantic mannequin, contract, debug texture, and inspection set.
- Raw FBXs, ZIP archives, extracted packages, working blends, diagnostics, and Blender backups are ignored.

The canonical blend is self-contained and does not require the ignored Meshy files for inspection, rendering, or use of its existing actions. Full regeneration still requires the corresponding local source whose SHA-256 is recorded in its manifest.

See `docs/BLENDER_CHARACTER_PIPELINE.md` for rebuild, validation, staging, review, and promotion commands.
