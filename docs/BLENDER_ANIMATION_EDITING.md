# Editing Pixel Forge Animations in Blender

This guide assumes you have never used Blender. Follow it in order the first time. The separate [Blender Basic Controls](BLENDER_BASIC_CONTROLS.md) page is a compact reference for navigation and shortcuts.

## What you are opening

Open this file:

`animation_images_models/elf_bald_female/working/original_motion_edit_session.blend`

It contains the character model, skeleton, texture, semantic component regions, and six animation actions.

The three actions intended for editing are:

| Action | Contents |
| --- | --- |
| `PF_Idle_Edit` | Our restrained Pixel Forge Idle. |
| `PF_Walk_Meshy_Edit` | The original Meshy Walk. |
| `PF_Run_Meshy_Edit` | The original untouched Meshy Run. |

The full source actions are also present as `PF_Idle`, `PF_Walk`, and `PF_Run`. Treat those as references and recovery copies. Do your work in actions ending in `_Edit`.

Each editable action contains eight poses:

- Frames 1 through 8 are the poses that will become sprite frames.
- Frame 9 is a hidden working closure that duplicates frame 1.
- Playback is set to frames 1 through 8 at 10 FPS.
- Auto Key starts disabled so Blender does not silently create unwanted keys.
- The file initially opens on `PF_Walk_Meshy_Edit`, frame 1, in Pose Mode.

Saving this `.blend` does not update Character Forge. Promotion is a separate process performed only after the animations are approved.

## 1. Open the file

1. Start Blender.
2. If Blender shows a splash screen, click anywhere outside it to dismiss it.
3. At the upper-left, click **File**, then **Open**.
4. Browse to the Pixel Forge repository and select `animation_images_models/elf_bald_female/working/original_motion_edit_session.blend`.
5. Click **Open Blender File**.
6. If Blender warns that the current unsaved startup scene will be discarded, confirm the open operation. The startup cube is disposable.

Blender may open the file in the **Layout** workspace. That is normal.

## 2. Understand the screen

Blender divides the window into rectangular editors. The important ones for this task are:

- **3D Viewport:** the large area showing the character and bones.
- **Timeline:** the strip with frame numbers and playback controls.
- **Dope Sheet / Action Editor:** the panel that shows animation keys and lets you choose an action.
- **Outliner:** usually at the upper-right; it lists objects in the file.
- **Properties:** usually at the lower-right; it contains detailed settings. You will rarely need it for basic pose editing.

Shortcuts apply to the editor underneath your mouse pointer. Before pressing a viewport shortcut, move the pointer over the 3D Viewport.

## 3. Switch to the Animation workspace

1. Look at the workspace tabs across the top of Blender: **Layout**, **Modeling**, **Sculpting**, and so on.
2. Click **Animation**.
3. If **Animation** is not visible, scroll the workspace tabs horizontally or click the small `+` at the right end, then choose **General**, **Animation**.

The Animation workspace rearranges the same file into panels that are more useful for posing and playback. It does not change the animation.

## 4. Select the skeleton and enter Pose Mode

You animate the skeleton, called an armature, rather than dragging the character mesh.

1. Move the mouse over the 3D Viewport.
2. Click one of the visible bones. The selected bone should change color.
3. Look at the mode selector in the upper-left corner of the 3D Viewport. It should say **Pose Mode**.
4. If it says **Object Mode**, click the character skeleton once, open the mode selector, and choose **Pose Mode**. With the armature selected, `Ctrl+Tab` also opens the mode-selection pie.

Do not animate in **Edit Mode**. Edit Mode changes the permanent construction and rest position of the skeleton. If the mode selector says Edit Mode, immediately change it back to Pose Mode.

If no bones are visible or selectable:

1. Find `PF_Elf_Bald_Female_Rig` in the Outliner.
2. Click it once.
3. Move the pointer back over the 3D Viewport.
4. Press `Ctrl+Tab` and choose **Pose Mode**.

The teaching file sets the rig to display in front of the character, so bones should remain visible through the model.

## 5. Open the Action Editor

The Action Editor is where you choose Idle, Walk, or Run.

1. Find a panel showing frame numbers and rows of animation data. In the Animation workspace, it is commonly at the lower-left.
2. At that panel's upper-left, look for a dropdown that may say **Dope Sheet**.
3. Open that dropdown and choose **Action Editor**.
4. Near the middle of the Action Editor header, find the action-name dropdown. It initially shows `PF_Walk_Meshy_Edit`.
5. Click the dropdown to switch between:
   - `PF_Idle_Edit`
   - `PF_Walk_Meshy_Edit`
   - `PF_Run_Meshy_Edit`

Avoid choosing `PF_Idle`, `PF_Walk`, or `PF_Run` when making edits. Those are the full reference actions.

If you cannot find a Dope Sheet panel, you can change any panel into one:

1. Click the **Editor Type** icon at the extreme upper-left corner of that panel.
2. Choose **Dope Sheet**.
3. In the new Dope Sheet header, change **Dope Sheet** to **Action Editor**.

## 6. Move around the character

With the pointer over the 3D Viewport:

- Hold the middle mouse button and drag to orbit around the character.
- Hold `Shift` plus the middle mouse button and drag to pan.
- Scroll the wheel to zoom.
- Press Numpad `1` for Front view.
- Press Numpad `3` for Right view.
- Press Numpad `7` for Top view.
- Hold `Ctrl` with those numpad keys for the opposite view.
- Select a bone or the armature and press Numpad `.` to center the view on it.
- If you become lost, press `Home` while the pointer is over the viewport to frame everything.

If your keyboard has no numpad, use the labeled axis gizmo in the upper-right corner of the 3D Viewport. Click `X`, `Y`, or `Z` to snap to an aligned view.

## 7. Choose a frame

1. Look at the Timeline or Action Editor.
2. Click frame 1, 2, 3, and so on to inspect the eight poses.
3. You can also press the Left or Right Arrow key to move one frame at a time.
4. The current frame number appears near the playback controls.

The Walk action uses these phases:

| Frame | Pose |
| --- | --- |
| 1 | Left Contact |
| 2 | Left Down |
| 3 | Left Passing |
| 4 | Left Up |
| 5 | Right Contact |
| 6 | Right Down |
| 7 | Right Passing |
| 8 | Right Up |

The Idle and Run actions also contain eight evenly selected poses. Action-specific markers appear when their editable action is selected.

## 8. Make one safe practice edit

Start with a very small rotation so you can learn the workflow without damaging the pose.

1. Select `PF_Walk_Meshy_Edit` in the Action Editor.
2. Click frame 3 in the Timeline.
3. Confirm the 3D Viewport says **Pose Mode**.
4. Click the `Head` or `neck` bone.
5. Press `R` once. Move the mouse slightly. The bone and attached character geometry should rotate.
6. Left-click or press `Enter` to confirm. Press `Esc` or right-click instead if you want to cancel the rotation.
7. With the bone still selected, right-click the bone in the 3D Viewport.
8. In the context menu, click **Insert Keyframe with Keying Set...**.
9. Click **Location, Rotation & Scale**.

That last step records the bone's new location, rotation, and scale on the current frame. Blender calls that stored value a **keyframe**.

The teaching actions already contain keyframes on every editable pose, so you may not see a new diamond appear. You are updating the value stored in a diamond that was already present. To confirm it worked, move to the next frame and then return to the edited frame. The bone should return to your edited position.

In Blender 5.1, pressing `I` in the 3D Viewport normally inserts a keyframe immediately and silently. It does not necessarily open a menu. After you understand the explicit right-click method above, you can use `I` as the faster shortcut. If you move a bone but do not insert or update its keyframe, the change may disappear when you switch frames or actions.

To undo the practice edit, press `Ctrl+Z`. To redo it, press `Shift+Ctrl+Z`.

## 9. Rotate on a specific axis

Plain `R` rotates freely relative to the current view. For controlled editing:

- `R`, then `X` constrains rotation to the global X axis.
- `R`, then `X`, then `X` constrains rotation to the bone's local X axis.
- The same pattern works with `Y` and `Z`.
- Type a number after choosing an axis to enter an exact angle, such as `R`, `X`, `X`, `5`, `Enter`.

Local axes are usually more useful for bones because they follow the bone's orientation.

Blender bones use their local Y axis along the bone's visible head-to-tail length:

- To twist around the bone's own length, press `R`, `Y`, `Y`.
- To bend around one of the bone's perpendicular local axes, press `R`, `X`, `X` or `R`, `Z`, `Z`.
- To rotate around the bone's own pivot without constraining an axis, press `R`. In Pose Mode, the default pivot is the selected bone's head; Blender is not rotating it around the world origin.

You can also use the rotation gizmo. Choose **Local** from the Transform Orientation dropdown in the 3D Viewport header, activate the Rotate tool, and drag the colored ring for the desired local axis. Red is X, green is Y, and blue is Z.

Normally rotate limbs with `R`. Do not move individual knees, elbows, hands, or feet using `G`; that can visually detach joints because this rig uses forward kinematics. Translation with `G` is normally reserved for the `Hips` bone when adjusting the whole body's height or weight shift.

### Why the Hips bone looks off-center

The horizontal bone visible across the left side of the pelvis is `Hips`. Meshy exported its bone head at the body center but pointed its display tail toward the character's left. Blender draws the full line from head to tail, making the bone look misplaced even though its transform pivot is centered.

In the canonical rig, the Hips head is approximately `X=0.35`, while its tail reaches approximately `X=11.71`. The head is the meaningful pivot. The tail mainly defines the bone's visible direction and local axes.

This is inherited FBX rest-rig data, not asymmetrical pelvis weighting. Do not try to center it in Edit Mode: changing the rest bone could invalidate the imported Walk and Run actions and complicate skinning. Use Pose Mode for animation. If a centered visual control becomes desirable, it should be added as a separate non-deforming control rather than changing this source bone.

## 10. Select and key several bones

You can change several bones on one pose before keying them.

1. Adjust the first bone and confirm the transform.
2. Hold `Shift` while clicking another bone to add it to the selection.
3. Adjust that bone.
4. Continue until the pose looks right.
5. Right-click a selected bone, choose **Insert Keyframe with Keying Set...**, then choose **Location, Rotation & Scale**. After learning this route, pressing `I` is the faster silent shortcut.

For maximum safety as a beginner, key each changed bone immediately after adjusting it.

Press `A` in Pose Mode to select all bones. Press `Alt+A` to deselect all bones.

## 11. Keep the first frame and closure frame identical

In the original eight-pose teaching actions, frame 9 exists only to close the animation loop. It starts as an exact copy of frame 1. If you change frame 1, you must update frame 9 too.

After finishing changes to frame 1:

1. Stay on frame 1 in Pose Mode.
2. Press `A` to select all bones.
3. Press `Ctrl+C` and choose **Copy Pose** if Blender opens a copy menu.
4. Move to frame 9 by typing `9` into the current-frame field or clicking frame 9 in the Action Editor.
5. Press `Ctrl+V` to paste the pose.
6. Right-click a selected bone, choose **Insert Keyframe with Keying Set...**, then choose **Location, Rotation & Scale**.
7. Return the Timeline end to frame 8 if you temporarily changed it. Normal preview should play frames 1 through 8 only.

Do not independently design frame 9. It must remain the same pose as frame 1.

If you extend an action, the same rule moves with the end of the animation: `N` visible poses use frame `N+1` as the closure. The current `idle_more_frames.blend` uses visible frames 1–13 and closure frame 14. Set the Timeline end to 13 while previewing. The finalizer can rebuild frame 14 automatically in a separate pipeline copy, so do not sacrifice an intended visible pose just to make room for the closure.

## 12. Preview the animation

1. Confirm the Timeline start is `1` and end is `8`.
2. Move the pointer over the 3D Viewport.
3. Press `Space` to play.
4. Press `Space` again to pause.
5. Rotate to a side view and play again.
6. Rotate to a front view and play again.

Always inspect both side and front views. A leg pose that looks correct from the side can cross or spread too far when viewed from the front.

## 13. Recommended editing order

Do not try to perfect everything at once.

For Walk:

1. Edit contact frames 1 and 5. Establish heel/toe contact and stride length.
2. Edit passing frames 3 and 7. Bring the free foot past the planted leg.
3. Edit down frames 2 and 6. Lower `Hips` slightly and let the planted knee absorb weight.
4. Edit up frames 4 and 8. Raise `Hips` slightly and prepare the next contact.
5. Correct torso balance.
6. Correct arm counter-swing.
7. Adjust neck and head last.
8. After changing frame 1, copy it to frame 9.

For Run:

1. Correct foot contacts and airborne silhouettes first.
2. Correct knees and stride shape.
3. Adjust `Hips` height and forward lean.
4. Adjust arms, torso, neck, and head.
5. Check that the character does not appear to freeze at the loop seam.

For Idle:

1. Keep both feet planted.
2. Use very small rotations on the spine, neck, and head.
3. Avoid large hip translations or arm swings.
4. Preview at 10 FPS; subtle motion can look much larger after pixelization.

## 14. Useful bones

| Body area | Bone | What it controls |
| --- | --- | --- |
| Whole body | `Hips` | Body height, overall weight shift, and root placement. Usually the only bone translated with `G`. |
| Lower torso | `Spine02` | Lower torso bend and twist. |
| Middle torso | `Spine01` | Middle torso bend and twist. |
| Upper torso | `Spine` | Chest and upper-torso direction. |
| Neck | `neck` | Neck angle and part of the head posture. |
| Head | `Head` | Head rotation and gaze. |
| Shoulders | `LeftShoulder`, `RightShoulder` | Shoulder base position. Use small changes. |
| Upper arms | `LeftArm`, `RightArm` | Shoulder swing. |
| Forearms | `LeftForeArm`, `RightForeArm` | Elbow bend. |
| Hands | `LeftHand`, `RightHand` | Wrist and hand angle. |
| Thighs | `LeftUpLeg`, `RightUpLeg` | Hip swing, stride, and thigh direction. |
| Shins | `LeftLeg`, `RightLeg` | Knee bend. |
| Feet | `LeftFoot`, `RightFoot` | Ankle angle and foot plant. |
| Toes | `LeftToeBase`, `RightToeBase` | Toe roll and toe-off. |

## 15. Save without losing the starting file

The first time you save your work:

1. Click **File**, then **Save As**.
2. Choose the same `working` directory or another personal work directory.
3. Give the file a new name, such as `original_motion_edit_session_greg_01.blend`.
4. Click **Save As Blender File**.
5. If Blender asks whether to confirm the filename, confirm it.

After that, `Ctrl+S` saves the current working copy.

Keeping the generated starting file unchanged makes it easy to recover from experiments. The full source actions inside the file provide another recovery path, but a separate filename is still strongly recommended.

## 16. Common problems

### I cannot select bones

- Make sure the armature is selected in the Outliner.
- Make sure the 3D Viewport mode says **Pose Mode**.
- Make sure you are clicking a bone rather than only the character mesh.

### The whole model has an orange outline

You probably selected the mesh instead of a bone. Select `PF_Elf_Bald_Female_Rig` in the Outliner, then enter Pose Mode.

### My change disappears on another frame

You probably did not insert a keyframe. Return to the intended frame, make the adjustment, right-click the selected bone, choose **Insert Keyframe with Keying Set...**, and then choose **Location, Rotation & Scale**.

### The character changes when I select another action

That is expected; every action contains different poses. Confirm that the action name ends in `_Edit` before making changes.

### I accidentally entered Edit Mode

Do not continue editing. Use the mode selector to return to Pose Mode. If you changed the skeleton in Edit Mode, press `Ctrl+Z` until the rest skeleton returns to its prior shape.

### The animation pops between frames 8 and 1

Check the frame-1/frame-9 closure. Copy the complete pose from frame 1 to frame 9 again using the instructions above.

For an extended action, compare frame 1 with its `N+1` closure instead. For the current 13-pose Idle, that means frame 14.

The artist file remains a 13-pose loop. The approved Blender derivative inserts one evaluated in-between after each authored pose, so its protected action has 26 visible frames at 12 FPS and exact closure on frame 27. Character Forge does not duplicate those in-betweens: it samples 14 exact action poses at 6 FPS, including authored frames 1,3,5,7,9,11,13,15,17,19,21,23,24,25.

### The camera view is lost

Select a bone and press Numpad `.`. If that does not help, press `Home` to frame everything.

### Playback is too fast or slow

The prepared editing actions are intended to preview at 10 FPS. Check **Output Properties**, **Frame Rate**, or the Timeline playback settings if that value changes.

### Pressing a shortcut affects the wrong panel

Move the mouse pointer over the 3D Viewport before using pose or view shortcuts. Blender shortcuts are context-sensitive.

## 17. What not to do yet

- Do not delete or rename bones.
- Do not change the skeleton in Edit Mode.
- Do not apply transforms to the armature or mesh.
- Do not edit the source actions unless you intentionally want to replace the recovery copy.
- Do not overwrite the canonical mannequin `.blend`.
- Do not promote anything to Character Forge until the animation has been reviewed from all four sprite directions.
