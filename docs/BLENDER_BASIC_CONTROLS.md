# Blender Basic Controls

This is a compact cheat sheet for the Pixel Forge animation-editing file. The full task walkthrough is in [Editing Pixel Forge Animations in Blender](BLENDER_ANIMATION_EDITING.md).

## The most important rule

Blender shortcuts affect the panel underneath the mouse pointer. Put the pointer over the 3D Viewport before using view, selection, pose, or transform shortcuts.

## Mouse and viewport navigation

| Action | Control |
| --- | --- |
| Select a bone or object | Left-click |
| Add another item to selection | `Shift` + left-click |
| Orbit around the character | Hold middle mouse and drag |
| Pan the view | `Shift` + middle mouse drag |
| Zoom | Mouse wheel |
| Frame selected item | Numpad `.` |
| Frame everything | `Home` |
| Front view | Numpad `1` |
| Back view | `Ctrl+Numpad 1` |
| Right view | Numpad `3` |
| Left view | `Ctrl+Numpad 3` |
| Top view | Numpad `7` |
| Bottom view | `Ctrl+Numpad 7` |
| Toggle perspective/orthographic | Numpad `5` |

Without a numpad, click the X, Y, or Z axis on the navigation gizmo in the upper-right corner of the 3D Viewport.

## Modes

| Action | Control |
| --- | --- |
| Open the mode-selection pie | `Ctrl+Tab` |
| Return from an accidentally entered Edit Mode | Use the upper-left mode dropdown and choose **Pose Mode** |

For animation work, use **Pose Mode**. Avoid **Edit Mode**, which changes the permanent skeleton.

## Selecting bones

| Action | Control |
| --- | --- |
| Select one bone | Left-click the bone |
| Add/remove a bone from selection | `Shift` + left-click |
| Select all bones | `A` |
| Deselect all bones | `Alt+A` |
| Hide selected bone | `H` |
| Show hidden bones | `Alt+H` |

## Transforming a pose

| Action | Control |
| --- | --- |
| Move | `G` |
| Rotate | `R` |
| Scale | `S` |
| Constrain to global axis | Press `X`, `Y`, or `Z` once after `G`, `R`, or `S` |
| Constrain to local axis | Press the axis twice, such as `R`, `X`, `X` |
| Confirm transform | Left-click or `Enter` |
| Cancel transform | Right-click or `Esc` |
| Enter an exact value | Type the number before confirming, such as `R`, `X`, `X`, `5`, `Enter` |

For this rig, rotate most bones with `R`. Normally use `G` only on `Hips`; moving individual limb bones can detach joints visually.

For a Blender bone, local Y runs along its visible head-to-tail length. Use `R`, `Y`, `Y` to twist around that length. Use `R`, `X`, `X` or `R`, `Z`, `Z` to bend on the bone's other local axes. Plain `R` already rotates around the selected bone's own pivot in Pose Mode.

## Animation and timeline

| Action | Control |
| --- | --- |
| Insert a keyframe quickly | `I`; Blender 5.1 normally inserts it silently |
| Insert with an explicit menu | Right-click the selected bone, choose **Insert Keyframe with Keying Set...**, then **Location, Rotation & Scale** |
| Play or pause | `Space` |
| Previous/next frame | Left/Right Arrow |
| Previous/next keyframe | Up/Down Arrow |
| Jump to a frame | Click the current-frame number and type a value |
| Copy the selected pose | `Ctrl+C` in Pose Mode |
| Paste the copied pose | `Ctrl+V` in Pose Mode |

The Pixel Forge edit actions use frames 1 through 8. Frame 9 must remain a copy of frame 1 for loop closure.

## Files and mistakes

| Action | Control |
| --- | --- |
| Save | `Ctrl+S` |
| Save As | `Shift+Ctrl+S` |
| Undo | `Ctrl+Z` |
| Redo | `Shift+Ctrl+Z` |

Use **Save As** before your first real edit and give the experiment a new filename.

## Useful interface toggles

| Action | Control |
| --- | --- |
| Show/hide right sidebar in the current editor | `N` |
| Show/hide left toolbar in the 3D Viewport | `T` |
| Maximize the panel under the mouse | `Ctrl+Space` |

If the interface seems to disappear after `Ctrl+Space`, press `Ctrl+Space` again to restore all panels.

## Safe beginner sequence

For every pose adjustment:

1. Verify **Pose Mode**.
2. Verify the action name ends in `_Edit`.
3. Select the correct frame.
4. Select a bone.
5. Rotate it with `R`.
6. Confirm with left-click or `Enter`.
7. Right-click the bone, choose **Insert Keyframe with Keying Set...**, then **Location, Rotation & Scale**. Later, use `I` as the faster silent shortcut.
8. Preview with `Space`.
9. Undo with `Ctrl+Z` if necessary.
