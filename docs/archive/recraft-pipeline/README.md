# Retired Recraft Sprite Pipeline

Archived: 2026-09-01

This directory is an inert snapshot of the rejected Recraft-based Heroic
component experiment. It is retained for historical reference only and is not
part of the active Pixel Forge runtime, toolchain, dependencies, or test suite.
The archived files preserve their former repository layout beneath this
directory so the experiment can be understood or restored deliberately.

## Included

- `animation_images_models/`: provider configuration and the provisional,
  uncalibrated validation profile.
- `docs/`: the former operating guide.
- `src/core/`: the implementation.
- `tools/`: the offline lab and guarded production-runner launchers.
- `tests/`: the former focused test module. Its `.py.txt` suffix keeps the
  archived test from being collected by the active test suite.
- `working/recraft/`: the local offline calibration job and the two labeled
  regression jobs, including their source, normalized, review, and extraction
  artifacts.

The archived source still contains its original root-relative paths and should
not be run in place. Restoring it would require moving the files back to those
paths, restoring `httpx` to `requirements.txt`, and reassessing the provider
contract before any network submission.

## Deliberately Not Archived

The Heroic assets are independent of Recraft and remain active in their
original locations:

- the four canonical authored Heroic `.blend` models and render blends;
- the authored Idle, Walk, and Run actions;
- promoted Heroic base sheets, directional GIFs, palettes, and manifests;
- Heroic semantic-region sheets and previews;
- the Heroic build/check tooling and provider-neutral style references.

No paid Recraft request was made and no Recraft-derived component was promoted
to Character Forge.
