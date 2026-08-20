# Pixel Forge 3D Animation Package

Schema version 1 is the interchange boundary between Blender renders and Pixel
Forge. A package is a directory containing `manifest.json` plus synchronized
visible, semantic-region, silhouette, anchor, and optional depth assets.

Validate a package without opening the UI:

```powershell
python tools/validate_3d_animation_package.py C:\path\to\package
```

Import a valid package in **Animation Studio → Import 3D Package**. The Studio
creates one linked-sheet track per direction and imports projected anchors into
their matching frames. Structural passes are validated on import and retained in
the source package for the future Component Creator integration.

## Manifest

```json
{
  "kind": "pixel-forge-3d-animation",
  "schemaVersion": 1,
  "name": "pilot-human",
  "animation": "run",
  "frameSize": [64, 64],
  "fps": 8,
  "playbackMode": "loop",
  "regions": {
    "background": [0, 0, 0, 0],
    "head": [255, 224, 64, 255],
    "torso": [224, 48, 48, 255]
  },
  "directions": [
    {
      "id": "front",
      "name": "Front",
      "frames": [
        {
          "index": 0,
          "sourceTime": 0.0,
          "visible": "visible/front/000.png",
          "regions": "regions/front/000.png",
          "silhouette": "silhouettes/front/000.png",
          "anchors": "anchors/front/000.json",
          "depth": "depth/front/000.exr"
        }
      ]
    }
  ],
  "checksums": {
    "visible/front/000.png": "64-lowercase-hexadecimal-sha256"
  }
}
```

`checksums` and each frame's `depth` are optional. When checksums are present,
every listed digest is verified and unused checksum entries are rejected.

## Required invariants

- Every referenced asset stays beneath the package root and uses a canonical
  forward-slash relative path.
- Direction IDs and animation/region/anchor identifiers use lowercase letters,
  digits, underscores, or hyphens and start with a letter.
- Direction IDs and display names are unique.
- Frame indexes are consecutive from zero within every direction.
- Every visible, region, silhouette, and optional depth image has exactly
  `frameSize` dimensions.
- Every region-map pixel is an exact RGBA value declared by `regions`.
- `background` is required and must be fully transparent.
- Silhouette alpha occupancy matches region-map background/non-background
  occupancy exactly.
- Anchor coordinates are finite. They may extend one frame beyond an edge to
  support attached equipment but implausibly distant coordinates are rejected.
- Reusing the same asset path for multiple frames is rejected.

Region maps are data, not artwork. They must not use anti-aliasing, interpolated
resizing, color correction, dithering, or lighting. If generated above the final
frame size, reduce them only with nearest-neighbor sampling.

## Anchor files

Each anchor file is JSON with floating-point pixel coordinates in the matching
frame's coordinate system:

```json
{
  "anchors": {
    "head": [31.25, 8.5],
    "hip_center": [31.0, 38.75],
    "foot_left": [23.5, 61.0],
    "weapon_grip_right": [38.125, 35.25]
  }
}
```

Animation Studio currently rounds imported floating-point anchors to its integer
pixel grid using half-away-from-zero rounding. The package retains the precise
values for future component mapping.

## Current implementation boundary

Implemented now:

- Strict package parsing and path containment.
- Visible/region/silhouette/depth dimension checks.
- Exact region-color and silhouette-occupancy validation.
- Optional SHA-256 validation.
- Anchor validation.
- Conversion to Animation Studio's linked-sheet, direction-track model.
- A command-line validator and Animation Studio import action.

Not implemented yet:

- Blender render/export execution on a real FBX.
- Region/depth/silhouette viewing inside Animation Studio.
- Persisting structural passes inside `.pfa` archives.
- Component fitting from regions, anchors, and depth.
- Automatic palette reduction and pixel cleanup across the imported package.

Those boundaries are explicit so a valid v1 package remains usable while later
features are added without silently changing the contract.
