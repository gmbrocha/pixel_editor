# Palette Workflows

PixelForge has several palette surfaces with deliberately different lifetimes.

## Active preview palette

The main window's **Active palette** is the palette used by **Quantize Preview**.
Loading or generating it does not alter the image immediately. The workflow is:

1. Generate **Palette From Preview** or choose **Load Palette**.
2. Inspect or edit the active swatches.
3. Choose **Quantize Preview** to map the unquantized preview to those colors.
4. Optionally choose **Apply To Source** to commit that mapping with source undo.

Changing the palette or dithering restores the unquantized preview so a result
from an older palette cannot accidentally be applied. Newly opened Pixel Editor,
Animation Studio, Reference Mapper, and Tile Layout windows receive a copy of the
current active palette.

Palette mapping compares RGB colors perceptually and preserves each source
pixel's alpha. Fully transparent source pixels remain transparent.

## Saved colors (persistent)

The **Saved colors** palette is a cross-session color shelf stored at
`~/.pixelforge/palette.json`. Main-window eyedropper picks are saved here and are
also added to the active palette and any currently open Pixel Editors.

Clicking a saved swatch selects that color for the main transparency-key tools,
adds it to the active palette, and sends it to open Pixel Editors. **Use for
Preview** replaces the active preview palette with the complete saved list.
Importing into Saved colors merges colors without duplicates; it does not replace
the active preview palette until **Use for Preview** is chosen.

## Pixel Editor and Floating Palette

Each Pixel Editor has its own project palette. It starts with a copy of the main
active palette when opened, but later project-palette edits remain local to that
editor. The editor can replace or merge its palette from any supported palette
file.

The Floating Palette is a session-local quick-access shelf owned by one Pixel
Editor. Custom Floating Palette colors do not change the project palette unless
they are explicitly sent or added through a project-palette action.

Animation Studio stores its palette in the `.pfa` project and updates it from
Pick Color or the one-shot Drag Select Colors workflow.

## Supported imports

The main active palette, Saved colors importer, and Pixel Editor accept:

- PixelForge or common JSON palettes (`.json`)
- hex lists (`.hex`, `.txt`)
- JASC palettes (`.pal`)
- GIMP palettes (`.gpl`)
- palette images (`.png`, `.bmp`, `.gif`, `.jpg`, `.jpeg`, `.webp`)

With **Reduce colors** off, file order and every unique color are preserved.
Fully transparent pixels in palette images are ignored. With reduction on,
palette images use the configured size and sampling settings; ordered JSON and
text palettes keep their listed colors unchanged but stop at the configured
size.

### JSON structures

The compact `colors` structure is supported:

```json
{
  "name": "Blacksmith",
  "colors": [
    "#101010",
    "#F09030",
    "#20304080"
  ]
}
```

`#RRGGBB` defaults alpha to 255; `#RRGGBBAA` includes alpha.

PixelForge exports a versioned, backward-compatible structure:

```json
{
  "format": "pixelforge-palette",
  "version": 1,
  "name": "Blacksmith",
  "palette": [
    {
      "hex": "#101010FF",
      "rgba": [16, 16, 16, 255]
    }
  ]
}
```

A bare JSON array is also accepted. Entries may be hex strings, `[R, G, B]` or
`[R, G, B, A]` arrays, or objects using `hex`, `rgb`, `rgba`, `color`, or
`r`/`g`/`b`/optional `a`. Channels must be integers from 0 through 255. Duplicate
colors are removed while preserving first appearance. Conflicting fields and
empty or malformed palettes produce an explicit validation error.

## Exports

Main-window and Pixel Editor palettes can export as:

- PNG palette strip (`.png`)
- versioned PixelForge JSON (`.json`)
- one-color-per-line hex (`.hex` or `.txt`)
- JASC-PAL (`.pal`)
- GIMP Palette (`.gpl`)

JSON and hex preserve alpha. JASC and GIMP palette formats contain RGB only, so
their exported colors reload as fully opaque. Pixel Editor Palette Grid export
remains PNG because its empty cells and two-dimensional arrangement are visual
layout data rather than a simple ordered color list.
