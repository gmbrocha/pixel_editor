# PixelForge — Shade Ramp Generator Cursor Prompt

```
Add a "Shade Ramp Generator" feature to PixelForge.

## Behavior
When the user selects any color in the palette, a button or panel appears
that generates a 4-shade ramp from that base color using HSB math.

## The Math
Given a base color in HSB (H: 0-360, S: 0-100, B: 0-100), generate 4 swatches:

Shadow:    H +12, S +15, B -40  (clamp all values to valid range)
Base:      unchanged
Midlight:  H -6,  S -12, B +22
Highlight: H -12, S -30, B +45

All values clamp: H wraps 0-360, S and B clamp 0-100.

## Output
Display the 4 swatches as a horizontal row, labeled Shadow / Base / Midlight / Highlight.
Each swatch should be clickable to set it as the active drawing color.
Add an "Add all to palette" button that drops all 4 into the current palette.

## Tech notes
- Convert the existing active color to HSB before applying the math
- If the app currently stores colors as HEX or RGB, convert to HSB,
  apply offsets, then convert back to HEX/RGB for rendering
- The conversion functions for RGB↔HSB should be self-contained utilities

## UI placement
Put it in the palette panel area, triggered when a color is selected.
Keep it minimal — 4 swatches in a row is the entire UI.
```

---

# PixelForge — Mirror Mode Cursor Prompt

```
Add a "Mirror Mode" toggle to PixelForge, active in both the regular pixel
editor and the animation frame editor.

## Behavior
When mirror mode is on, every pixel placed by the user is simultaneously
mirrored to the horizontally symmetrical position on the opposite side of
the canvas center axis.

- Axis = canvas width / 2
- If canvas is 64px wide, axis is at x=32
- A pixel placed at x=10 auto-places one at x=54 (64 - 10)
- A pixel placed at x=32 (on the axis) places only one pixel
- Erasing mirrors the same way — erase left, erase right

## UI
- A simple toggle button in the toolbar, labeled "Mirror" with an icon
  (two triangles facing each other, or just an M)
- When active, show a faint vertical line down the center of the canvas
  indicating the axis
- Toggle persists per session but does not save with the file

## Scope
- Applies to freehand drawing, eraser, and single pixel placement
- Does not apply to fill/bucket tool (would cause unintended full fills)
- Works identically in the animation editor on whichever frame is active

## Tech notes
- On every pixel write operation, calculate the mirror x as:
  mirrorX = canvasWidth - 1 - originalX
- Apply the same color/erase operation at (mirrorX, y)
- No change to the underlying data model — just intercept the draw call
```

---

# Other PixelForge Automations to Build

## High Priority

**Palette extractor from image**
Drag any image (Midjourney output, reference photo) onto PixelForge and it
extracts the N most dominant colors into a palette row automatically.
Huge for keeping your sprite consistent with your reference art.

**Palette lock / restrict drawing to palette**
Toggle that prevents you from drawing any color not in your current palette.
Enforces discipline, prevents accidental color creep across a sprite.

**Onion skinning**
When animating, show the previous frame as a ghost (low opacity) underneath
the current frame. Standard in every sprite tool, essential for smooth animation.

**Per-frame palette view**
Shows which colors are actually used in the current frame. Lets you see if
you accidentally introduced a stray color that shouldn't be there.

---

## Medium Priority

**Hue shift preview**
Hover over any palette color and see a live preview of what the full 4-shade
ramp would look like before committing. Non-destructive, just a tooltip/popup.

**Mirror drawing mode**
Paint on the left half, it mirrors to the right simultaneously.
Essential for symmetrical creatures like the corrupted warden.

**Color swap**
Select any color on the canvas, replace all instances of it with another color
in one click. Useful when you decide a shade is wrong after painting.

**Export sprite sheet**
Take all animation frames and export them as a single horizontal or grid PNG,
properly spaced, ready to drop into Godot.

---

## Nice to Have

**Grid overlay toggle**
Show/hide a tile grid overlay (e.g. 16x16 or 64x64 guides) so you can see
your sprite boundaries while painting.

**Zoom to fit**
One button that snaps zoom level so the entire canvas fills the screen.
Obvious but easy to forget to build.

**Undo history panel**
Visual list of last N actions so you can jump back to a specific state,
not just step backward one at a time.

---

# Pixel Art Tips Reference

## The Big Ones

**Hue shifting**
Don't just go darker/lighter within the same hue. Shadows shift slightly
cooler (toward blue/purple), highlights shift warmer (toward yellow).
Pure grey shadows look flat and dead. This is the single biggest upgrade.

**Pillow shading (avoid this)**
Classic beginner trap — shading around the outline of a shape like it's a pillow.
Light has a source direction. Always ask "where is the light coming from"
and shade accordingly, not just around the edge.

**Clusters not noise**
When adding texture, group same-colored pixels into small deliberate clusters
of 2-3+. Single scattered pixels read as noise. Even 2 pixels together reads
as intentional.

**Outline variation**
Instead of a uniform dark outline, make the outline slightly lighter on the
top/lit side and darker on the bottom/shadow side. Massive depth for free.

**Anti-aliasing by hand**
On curved edges, manually place a single pixel of mid-tone between the shape
edge and the background. Makes curves read as smooth without blurring.

**Limit your palette ruthlessly**
3-4 shades per color region max. The constraint forces clarity and readability.
More shades = muddier, not better.

## The HSB Shade Ramp Table

For warm/neutral colors (skin, grey, horns):

| Shade     | H   | S   | B   |
|-----------|-----|-----|-----|
| Shadow    | +12 | +15 | −40 |
| Base      |  0  |  0  |  0  |
| Midlight  |  −6 | −12 | +22 |
| Highlight | −12 | −30 | +45 |

For greens:

| Shade     | H   | S   | B   |
|-----------|-----|-----|-----|
| Shadow    | +15 | +15 | −40 |
| Base      |  0  |  0  |  0  |
| Midlight  |  −8 | −10 | +22 |
| Highlight | −15 | −25 | +45 |

For pink/purple:

| Shade     | H   | S   | B   |
|-----------|-----|-----|-----|
| Shadow    | −12 | +15 | −40 |
| Base      |  0  |  0  |  0  |
| Midlight  |  +6 | −10 | +22 |
| Highlight | +12 | −30 | +45 |

**Rule to memorize:**
- Shadows: S up, B way down, hue toward nearest cool color
- Highlights: S way down, B way up, hue toward yellow/warm
- Midlight: half values, opposite hue direction from shadow

---

# Sprite Painting Order

**1. Silhouette first**
Fill the entire character shape with a single flat mid-tone. No detail, no shading. Just the shape. If the silhouette doesn't read as your character at this stage, no amount of detail will fix it.

**2. Color blocking**
Still no shading. Fill each region with its flat base color only. Skin one color, horns one color, loincloth one color, runes one color. Confirm your color palette works together before going further.

**3. Base shading**
Add just your shadow tone — one shade darker per region. Pick a light source direction and commit to it for the whole sprite. Never change it. Everything facing away from the light gets shadow tone now.

**4. Highlight pass**
Add your highlight tone — one shade lighter. Only surfaces directly facing the light source. At this point you have 3 tones per region and the sprite should look solid.

**5. Midlight refinement**
Add the subtle mid tone between base and highlight where needed. This is where forms start to feel round rather than flat. Don't overdo it — most areas won't need it.

**6. Details and texture**
Runes, fine markings, texture clusters. Only now. Doing this earlier means repainting over it constantly.

**7. Outline pass**
Full silhouette outline first, then go back and selectively thin or remove it — tips of horns, lit edges, thin shapes get no outline or shadow-side only.

**8. Anti-aliasing**
Very last. Only on the outer silhouette, only on the largest curves, one pixel deep only.

**Golden rule throughout:** zoom out constantly. Make a decision at 8x, check it at 2x. If it doesn't read at 2x it doesn't exist.

---

# PixelForge — Zoom Step Feature Cursor Prompt

```
Improve the zoom control in PixelForge's pixel editor and animation editor.

## Current behavior
Zoom changes one value at a time via clicking up/down controls.

## New behavior
Keep the existing single-step controls as-is. Add fast zoom preset buttons
alongside them that jump directly to common zoom levels in one click.

## Zoom presets
Add buttons for: 1x, 2x, 4x, 8x, 16x

## UI
- Display preset buttons as a small horizontal row of labeled buttons
  next to or below the existing zoom control
- Highlight/mark whichever preset matches the current zoom level if applicable
- If the user is on a non-preset zoom (e.g. 3x from single stepping),
  no preset is highlighted — that's fine, don't force snap
- Keyboard shortcuts if feasible: hold Shift + scroll wheel to jump by 4x
  increments instead of 1x

## Scope
- Applies to both the regular pixel editor and the animation frame editor
- Does not change any other zoom behavior — purely additive
```
