# Elf Run Redo Transfer Project

## Open on another machine

1. Clone or pull the repository.
2. Run `git lfs pull` so the Blender binary is downloaded rather than left as an LFS pointer.
3. Open `run_redo_v1.blend` with Blender 5.1 or newer.
4. Use **File > Save As** and create a personal iteration such as `run_redo_work_01.blend` before editing.

`run_redo_v1.blend` is self-contained. Its model, rig, materials, actions, quickstart text, and editing UI are stored in the file; it has no required external images or linked Blender libraries. `run_redo_v1.json` records its source frames, SHA-256, actions, portability check, and Blender version.

## Actions

- `PF_Run_Redo_Edit` is selected when the file opens. It is the editable eight-pose copy of the currently installed forward-lean/head-down Run.
- `PF_Run_Meshy_Edit` is an editable eight-pose copy of the original untouched Meshy Run and can be used as a clean fallback.
- `PF_Run_ForwardLean_HeadDown` is the protected full action behind the current installed Run.
- `PF_Run` is the protected untouched full Meshy source action.

Edit frames 1 through 8 at 10 FPS. Frame 9 is the loop-closure copy of frame 1. Stay in Pose Mode, use `R` to rotate bones, and generally use `G` only on `Hips`. After changing a pose, press `I` to update the existing Location/Rotation/Scale key. If frame 1 changes, frame 9 must ultimately match it; the finalizer can rebuild that closure later.

The embedded Blender text `PIXEL_FORGE_RUN_REDO_QUICKSTART` contains the same essential instructions.

Nothing in this starter changes Character Forge until a revised action is explicitly finalized, rendered, reviewed, and promoted.
