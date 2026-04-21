from __future__ import annotations

import colorsys

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
from skimage.morphology import medial_axis

Color = tuple[int, int, int, int]


# Minimum normalized distance for any filled pixel in radial shading.
# Clamping the floor keeps 1-pixel tips, thin vines, and edges from collapsing
# to ramp[0] (the darkest shadow), which would make them visually disappear or
# look like black noise. Exposed so it can be tuned later without touching
# call sites.
APPLY_SHADING_MIN_NORM: float = 0.15

# Default light direction for directional shading. 135 degrees in standard
# math convention is "top-left", which corresponds to the spec's normalized
# (-1, -1) in image (x, y) coordinates (image y grows downward, so a math-up
# direction of +y becomes image-up of -y).
DIRECTIONAL_SHADING_DEFAULT_ANGLE_DEG: float = 135.0


def rgb_to_hsb(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert RGB (0-255 each) to HSB where H 0-360, S 0-100, B 0-100."""
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return h * 360.0, s * 100.0, v * 100.0


def hsb_to_rgb(h: float, s: float, b: float) -> tuple[int, int, int]:
    """Convert HSB (H 0-360, S 0-100, B 0-100) to RGB (0-255 each)."""
    h_norm = (h % 360.0) / 360.0
    s_norm = max(0.0, min(1.0, s / 100.0))
    b_norm = max(0.0, min(1.0, b / 100.0))
    r, g, bv = colorsys.hsv_to_rgb(h_norm, s_norm, b_norm)
    return int(round(r * 255)), int(round(g * 255)), int(round(bv * 255))


def _apply_offset(h: float, s: float, b: float, dh: float, ds: float, db: float) -> tuple[float, float, float]:
    return (h + dh) % 360.0, max(0.0, min(100.0, s + ds)), max(0.0, min(100.0, b + db))


def shade_ramp(color: Color) -> list[tuple[str, Color]]:
    """Return [(label, rgba), ...] for shadow / base / midlight / highlight."""
    r, g, b = color[0], color[1], color[2]
    a = color[3]
    h, s, bv = rgb_to_hsb(r, g, b)

    offsets = [
        ("Shadow",    +12, +15, -40),
        ("Base",        0,   0,   0),
        ("Midlight",   -6, -12, +22),
        ("Highlight", -12, -30, +45),
    ]
    ramp: list[tuple[str, Color]] = []
    for label, dh, ds, db in offsets:
        nh, ns, nb = _apply_offset(h, s, bv, dh, ds, db)
        nr, ng, nbl = hsb_to_rgb(nh, ns, nb)
        ramp.append((label, (nr, ng, nbl, a)))
    return ramp


def _sample_ramp_into_rgb(t: np.ndarray, ramp_colors: list[Color]) -> np.ndarray:
    """Sample `ramp_colors` (shadow -> highlight) at per-pixel positions
    `t` in [0, 1] with linear interpolation in RGB space.

    Returns a float32 (H, W, 3) array of RGB values in [0, 255].
    """
    palette = np.array([(c[0], c[1], c[2]) for c in ramp_colors], dtype=np.float32)
    n_stops = palette.shape[0]
    if n_stops == 1:
        return np.broadcast_to(palette[0], (t.shape[0], t.shape[1], 3)).copy()

    scaled = t * (n_stops - 1)
    lower_idx = np.floor(scaled).astype(np.int32)
    upper_idx = np.minimum(lower_idx + 1, n_stops - 1)
    frac = (scaled - lower_idx)[..., None]
    return (1.0 - frac) * palette[lower_idx] + frac * palette[upper_idx]


def _write_back_rgb_preserving_alpha(
    arr: np.ndarray, rgb_lookup: np.ndarray, filled_mask: np.ndarray
) -> Image.Image:
    """Build a new RGBA image where filled pixels' RGB comes from
    `rgb_lookup` and alpha (and untouched pixels) come from `arr`."""
    new_arr = arr.copy()
    rgb_uint8 = np.clip(np.rint(rgb_lookup), 0, 255).astype(np.uint8)
    new_arr[filled_mask, 0] = rgb_uint8[filled_mask, 0]
    new_arr[filled_mask, 1] = rgb_uint8[filled_mask, 1]
    new_arr[filled_mask, 2] = rgb_uint8[filled_mask, 2]
    return Image.fromarray(new_arr, mode="RGBA")


def apply_radial_shading(
    image: Image.Image,
    ramp_colors: list[Color],
    *,
    min_norm: float = APPLY_SHADING_MIN_NORM,
) -> tuple[Image.Image, int]:
    """Recolor every filled pixel of `image` along `ramp_colors` based on its
    Euclidean distance to the nearest transparent pixel.

    `ramp_colors` is ordered shadow -> highlight (low brightness -> high).
    Edge pixels (distance ~ 0) map toward `ramp_colors[0]`. Center pixels
    (max distance) map toward `ramp_colors[-1]`. Values between ramp entries
    are linearly interpolated in RGB space.

    Alpha is preserved exactly per pixel; only RGB is replaced. Fully
    transparent pixels (alpha == 0) are untouched.

    `min_norm` clamps the minimum normalized distance so 1-pixel tips and thin
    vine segments stay near the shadow end of the ramp instead of collapsing
    onto the darkest entry alone.

    Returns the new image and the number of filled pixels recolored.
    """
    base = image.convert("RGBA").copy()
    if not ramp_colors:
        return base, 0

    arr = np.array(base)
    alpha = arr[..., 3]
    filled_mask = alpha > 0
    filled_count = int(filled_mask.sum())
    if filled_count == 0:
        return base, 0

    distances = distance_transform_edt(filled_mask)

    # If the entire canvas is filled (no empty pixels at all) the EDT returns
    # +inf everywhere. Treat that as a uniform mid-ramp shade so we don't
    # divide by inf or NaN out below.
    finite_mask = filled_mask & np.isfinite(distances)
    if not finite_mask.any():
        normalized = np.full(distances.shape, 0.5, dtype=np.float32)
    else:
        max_dist = float(distances[finite_mask].max())
        if max_dist <= 0.0:
            normalized = np.full(distances.shape, min_norm, dtype=np.float32)
        else:
            normalized = (distances / max_dist).astype(np.float32)

    floor = float(max(0.0, min(1.0, min_norm)))
    normalized = np.clip(normalized, floor, 1.0)

    rgb_lookup = _sample_ramp_into_rgb(normalized, ramp_colors)
    return _write_back_rgb_preserving_alpha(arr, rgb_lookup, filled_mask), filled_count


def apply_directional_shading(
    image: Image.Image,
    ramp_colors: list[Color],
    *,
    light_angle_degrees: float = DIRECTIONAL_SHADING_DEFAULT_ANGLE_DEG,
) -> tuple[Image.Image, int]:
    """Recolor every filled pixel based on which side of the shape's medial
    axis (centerline) it lies on, relative to a configurable light direction.

    Steps:
        1. Build the filled/empty alpha mask.
        2. Compute the medial-axis skeleton with `skimage.morphology.medial_axis`.
        3. For each filled pixel, look up its nearest skeleton pixel using
           `scipy.ndimage.distance_transform_edt(..., return_indices=True)`.
        4. Take the offset vector from skeleton point to current pixel.
        5. Dot it (after normalizing) against the light direction.
        6. Remap dot from [-1, +1] to [0, 1] and sample `ramp_colors`. Pixels
           on the skeleton itself have a zero offset and land at exactly 0.5
           (midtone), as required.

    `light_angle_degrees` follows the standard math convention: 0 deg = light
    from the right, 90 deg = light from above (visually up), 135 deg = light
    from the top-left (the default), counter-clockwise positive. Internally
    this is converted to image-coordinate vector (cos a, -sin a) so the y-down
    nature of image arrays is handled correctly.

    Alpha is preserved exactly per pixel; only RGB is replaced. Returns the
    new image and the number of filled pixels recolored.
    """
    base = image.convert("RGBA").copy()
    if not ramp_colors:
        return base, 0

    arr = np.array(base)
    filled_mask = arr[..., 3] > 0
    filled_count = int(filled_mask.sum())
    if filled_count == 0:
        return base, 0

    # Medial-axis skeleton of the filled silhouette. For very small shapes
    # (e.g. a 1px line) the skeleton coincides with the shape itself.
    skeleton = medial_axis(filled_mask)
    if not skeleton.any():
        skeleton = filled_mask

    # `distance_transform_edt(~skel, return_indices=True)` returns, for every
    # cell, the (y, x) coordinates of its nearest True cell in `skel` -- i.e.
    # the closest skeleton pixel for every pixel in the canvas.
    _, indices = distance_transform_edt(~skeleton, return_indices=True)
    nearest_y = indices[0]
    nearest_x = indices[1]

    yy, xx = np.indices(arr.shape[:2])
    vy = (yy - nearest_y).astype(np.float32)
    vx = (xx - nearest_x).astype(np.float32)
    vec_len = np.sqrt(vx * vx + vy * vy)

    # Light direction in image (x, y) space. Math angle theta -> (cos t, -sin t)
    # because image y grows downward; this makes 90 deg point visually upward
    # and 135 deg point to the visually-upper-left (the default).
    theta = np.deg2rad(float(light_angle_degrees))
    light_x = float(np.cos(theta))
    light_y = float(-np.sin(theta))

    # Per-pixel dot product of the unit offset-from-skeleton vector with the
    # light direction. Pixels exactly on the skeleton (vec_len == 0) keep
    # dot == 0, which maps to t = 0.5 = midtone, matching the spec.
    dot = np.zeros_like(vec_len)
    nonzero = vec_len > 1e-6
    dot[nonzero] = (vx[nonzero] * light_x + vy[nonzero] * light_y) / vec_len[nonzero]

    t = np.clip((dot + 1.0) * 0.5, 0.0, 1.0).astype(np.float32)

    rgb_lookup = _sample_ramp_into_rgb(t, ramp_colors)
    return _write_back_rgb_preserving_alpha(arr, rgb_lookup, filled_mask), filled_count


# Back-compat alias for the previous `apply_shading` name.
apply_shading = apply_radial_shading
