"""Procedural textures for the Texture Generator subsystem.

This module is intentionally self-contained from `shade_ramp` and the
main editor's palette code: the texture generator is documented as a
standalone subsystem, so its colour math lives here. The `unique_colors`
extractor is also kept simple (no quantisation) because the spec asks for
*every* unique colour from the imported PNG.
"""

from __future__ import annotations

import colorsys
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np
from PIL import Image


Color = tuple[int, int, int, int]  # (r, g, b, a) all 0-255


# -- Colour helpers ---------------------------------------------------------


def _rgb_to_hsb(c: Color) -> tuple[float, float, float, int]:
    """Return (H 0-360, S 0-100, B 0-100, alpha)."""
    r, g, b, a = c
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return h * 360.0, s * 100.0, v * 100.0, a


def _hsb_to_rgb(h: float, s: float, b: float, alpha: int) -> Color:
    h_norm = (h % 360.0) / 360.0
    s_norm = max(0.0, min(1.0, s / 100.0))
    b_norm = max(0.0, min(1.0, b / 100.0))
    r, g, bl = colorsys.hsv_to_rgb(h_norm, s_norm, b_norm)
    return (int(round(r * 255)), int(round(g * 255)), int(round(bl * 255)), alpha)


def _nearest_cool_hue(h: float) -> float:
    """Return the cool-side hue closest to `h`. Cool hues taken to be the
    blue/cyan/teal arc (180-260 deg). The dark stop's hue gets nudged ~10
    deg toward this anchor, giving the shadow a slightly cooler cast which
    looks more natural than just darkening in place."""
    cool_anchors = (180.0, 210.0, 240.0, 260.0)
    return min(cool_anchors, key=lambda anchor: min(
        abs(anchor - h),
        360.0 - abs(anchor - h),
    ))


def _nudge_hue_toward(h: float, target: float, max_step: float) -> float:
    """Move `h` at most `max_step` degrees along the shorter arc toward
    `target`. Wraps at 360."""
    diff = (target - h + 540.0) % 360.0 - 180.0  # signed shortest arc
    step = max(-max_step, min(max_step, diff))
    return (h + step) % 360.0


# -- Ramp -------------------------------------------------------------------


# Ramp ordering throughout the texture generator: index 0 is the LIGHTEST
# stop and index n-1 is the DARKEST. The brick algorithm assumes this
# ordering when it picks "lightest" and "darkest" for mortar and bevel.
RAMP_MIN_STOPS = 3
RAMP_MAX_STOPS = 8


def generate_ramp(base_color: Color, n_stops: int) -> list[Color]:
    """Derive a `n_stops` light-to-dark ramp from a base colour using HSB.

    Anchors per spec:
      * lightest stop  : S * 0.6, B + 30  (toward white)
      * centre stop    : the base colour
      * darkest stop   : S + 20, B / 2, hue nudged ~10 deg toward cool
    Intermediate stops: linearly interpolated in HSB between these anchors.
    """
    if n_stops < RAMP_MIN_STOPS or n_stops > RAMP_MAX_STOPS:
        raise ValueError(
            f"n_stops must be in [{RAMP_MIN_STOPS}, {RAMP_MAX_STOPS}], got {n_stops}"
        )
    h, s, b, alpha = _rgb_to_hsb(base_color)
    cool_target = _nearest_cool_hue(h)

    # Anchor HSB triples (light, base, dark).
    light_h, light_s, light_b = h, s * 0.6, min(100.0, b + 30.0)
    base_h, base_s, base_b = h, s, b
    dark_h = _nudge_hue_toward(h, cool_target, max_step=10.0)
    dark_s = min(100.0, s + 20.0)
    dark_b = max(0.0, b * 0.5)

    centre = (n_stops - 1) // 2  # for an even count this puts base just
                                 # left of true centre, which is fine -
                                 # the ramp still spans light -> dark.
    stops: list[Color] = []
    for i in range(n_stops):
        if i == 0:
            triple = (light_h, light_s, light_b)
        elif i == n_stops - 1:
            triple = (dark_h, dark_s, dark_b)
        elif i == centre:
            triple = (base_h, base_s, base_b)
        elif i < centre:
            # interpolate light -> base
            denom = max(1, centre)
            t = i / denom
            triple = (
                _interp_hue(light_h, base_h, t),
                light_s + (base_s - light_s) * t,
                light_b + (base_b - light_b) * t,
            )
        else:
            denom = max(1, n_stops - 1 - centre)
            t = (i - centre) / denom
            triple = (
                _interp_hue(base_h, dark_h, t),
                base_s + (dark_s - base_s) * t,
                base_b + (dark_b - base_b) * t,
            )
        stops.append(_hsb_to_rgb(*triple, alpha=alpha))
    return stops


def _interp_hue(h0: float, h1: float, t: float) -> float:
    """Interpolate hues along the shorter arc."""
    diff = (h1 - h0 + 540.0) % 360.0 - 180.0
    return (h0 + diff * t) % 360.0


# -- Palette extraction -----------------------------------------------------


def unique_colors_from_image(source: str | Path | Image.Image) -> list[Color]:
    """Return every unique RGBA colour in `source` (no quantisation, no
    cap). The texture generator's palette panel scrolls when there are
    many colours so we don't need to limit here."""
    if isinstance(source, Image.Image):
        img = source.convert("RGBA")
    else:
        img = Image.open(source).convert("RGBA")
    arr = np.asarray(img).reshape(-1, 4)
    # `np.unique` over packed uint32 is much faster than per-tuple set
    # work for typical PNG sizes.
    packed = arr.view(np.uint32).reshape(-1)
    uniq = np.unique(packed)
    raw = uniq.view(np.uint8).reshape(-1, 4)
    return [(int(r), int(g), int(b), int(a)) for r, g, b, a in raw]


# -- Vegetation (shared by Brick and Blocks) -------------------------------


# Style identifiers for the Vegetation pass. Lowercased to match the
# UI's stored data values without an extra translation layer.
VEGETATION_STYLE_MOSS: str = "moss"
VEGETATION_STYLE_GRASS: str = "grass"
VEGETATION_STYLE_BOTH: str = "both"
VEGETATION_STYLES: tuple[str, ...] = (
    VEGETATION_STYLE_MOSS,
    VEGETATION_STYLE_GRASS,
    VEGETATION_STYLE_BOTH,
)


@dataclass
class VegetationParams:
    """Optional vegetation pass for Brick and Blocks textures.

    A 3-stop ramp is derived automatically from `color` at render time
    (see `_vegetation_ramp`); the user never sees or tweaks the ramp.
    `coverage` is the raw 0..1 placement probability per eligible pixel
    for moss; the grass pass internally scales this by 0.6 so the
    slider feels consistent across both styles.
    """

    style: str = VEGETATION_STYLE_BOTH
    coverage: float = 0.30
    color: Color = (0x4a, 0x7a, 0x3a, 0xff)

    def clamped(self) -> "VegetationParams":
        s = (self.style or "").lower()
        if s not in VEGETATION_STYLES:
            s = VEGETATION_STYLE_BOTH
        r, g, b, a = self.color
        return VegetationParams(
            style=s,
            coverage=max(0.0, min(1.0, float(self.coverage))),
            color=(
                max(0, min(255, int(r))),
                max(0, min(255, int(g))),
                max(0, min(255, int(b))),
                max(0, min(255, int(a))),
            ),
        )


# -- Brick texture ----------------------------------------------------------


@dataclass
class BrickParams:
    """Parameters for `generate_brick_texture`. See spec for ranges."""

    brick_width: int = 6        # px, range 2..canvas_w
    brick_height: int = 3       # px, range 1..canvas_h
    mortar: int = 1             # px, range 1..3
    row_offset: float = 0.5     # 0.0..1.0, fraction of brick width
    color_variance: int = 2     # 0..4, how many ramp stops to wander
    bevel: bool = True          # 1px highlight/shadow on brick interior
    # Percent of the top / left edge (in face pixels) that the bevel
    # highlight covers. 100 = full edge (legacy behaviour). 50 (default)
    # stops the highlight halfway. The top-left corner pixel is always
    # lit when bevel is on, regardless of this value.
    highlight_length: int = 50  # range 10..100, percent
    # Repaint the interior pixel(s) of every 4-way mortar intersection
    # with stop 1 instead of stop 0, breaking the harsh 90deg cross
    # where four blocks meet.
    soft_corners: bool = False
    # Final-pass moss/grass overlay. None = pass is skipped entirely
    # (preserves pre-vegetation output byte-for-byte).
    vegetation: VegetationParams | None = None

    def clamped(self, canvas_w: int, canvas_h: int) -> "BrickParams":
        """Return a copy with values clamped to legal ranges given the
        canvas size. Used at generation time to be defensive against UI
        races (e.g. canvas resized while spinboxes still show old maxima)."""
        return BrickParams(
            brick_width=max(2, min(self.brick_width, canvas_w)),
            brick_height=max(1, min(self.brick_height, canvas_h)),
            mortar=max(1, min(self.mortar, 3)),
            row_offset=max(0.0, min(self.row_offset, 1.0)),
            color_variance=max(0, min(self.color_variance, 4)),
            bevel=bool(self.bevel),
            highlight_length=max(10, min(int(self.highlight_length), 100)),
            soft_corners=bool(self.soft_corners),
            vegetation=self.vegetation.clamped() if self.vegetation else None,
        )


def _brick_hash(seed: int, col: int, row: int) -> int:
    """Stable 32-bit mixer for per-brick colour variance.

    A self-contained mulberry32-flavoured mixer so the output is bit-stable
    no matter what numpy version is installed.
    """
    h = (seed & 0xFFFFFFFF)
    h ^= (col + 0x9E3779B9) & 0xFFFFFFFF
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= (h >> 13)
    h ^= (row + 0xC2B2AE35) & 0xFFFFFFFF
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= (h >> 16)
    return h & 0xFFFFFFFF


def _wrap_blit(
    pixels: np.ndarray,
    rect_x: int,
    rect_y: int,
    rect_w: int,
    rect_h: int,
    color: np.ndarray,
) -> None:
    """Fill a `rect_w x rect_h` rectangle starting at (rect_x, rect_y),
    wrapping at the canvas edges (so the texture tiles seamlessly).

    Implements modulo-wrapping by splitting the rect into up to 4 axis-
    aligned sub-rects.
    """
    h, w = pixels.shape[:2]
    if rect_w <= 0 or rect_h <= 0:
        return
    x0 = rect_x % w
    y0 = rect_y % h
    # Horizontal split if the rect crosses the right edge.
    x_segments: list[tuple[int, int]] = []  # (start_x, length)
    rem = rect_w
    cx = x0
    while rem > 0:
        seg = min(rem, w - cx)
        x_segments.append((cx, seg))
        cx = (cx + seg) % w
        rem -= seg
    # And vertical similarly.
    y_segments: list[tuple[int, int]] = []
    rem = rect_h
    cy = y0
    while rem > 0:
        seg = min(rem, h - cy)
        y_segments.append((cy, seg))
        cy = (cy + seg) % h
        rem -= seg
    for sy, lh in y_segments:
        for sx, lw in x_segments:
            pixels[sy:sy + lh, sx:sx + lw] = color


def get_divisors(n: int) -> list[int]:
    """Return every positive integer divisor of `n` in ascending order.

    Shared by the brick / blocks parameter panels: each axis snaps the
    brick dimension to a value `(divisor - mortar)` so that
    `(brick + mortar)` divides the canvas size evenly and the texture
    tiles seamlessly across the seam."""
    if n <= 0:
        return []
    divisors: list[int] = []
    i = 1
    while i * i <= n:
        if n % i == 0:
            divisors.append(i)
            if i != n // i:
                divisors.append(n // i)
        i += 1
    divisors.sort()
    return divisors


def valid_brick_dimensions(canvas_size: int, mortar: int, minimum: int) -> list[int]:
    """Return brick dimensions (width *or* height) that tile cleanly into
    `canvas_size` with `mortar`-pixel gaps between bricks.

    A dimension `d` is valid iff `(d + mortar)` divides `canvas_size`
    evenly *and* `d >= minimum` (the per-parameter floor enforced by the
    spinbox). Result is sorted ascending and may be empty - callers
    should treat an empty list as "no clean fit possible at this mortar
    size for this canvas"."""
    m = max(0, int(mortar))
    floor = max(0, int(minimum))
    return [d - m for d in get_divisors(int(canvas_size)) if d - m >= floor]


def brick_tile_remainder(
    canvas_w: int, canvas_h: int, brick_width: int, brick_height: int, mortar: int,
) -> tuple[int, int]:
    """Return the (x, y) leftover mortar band, in pixels, that the brick
    lattice can't fill with another brick before the canvas edge. Both
    zero = the texture tiles seamlessly. Non-zero on either axis = that
    edge will carry a strip of pure mortar that won't continue into a
    brick on wrap. Surfaced in the UI as a non-blocking hint."""
    bw = max(1, int(brick_width))
    bh = max(1, int(brick_height))
    m = max(1, int(mortar))
    col_stride = bw + m
    row_stride = bh + m
    if col_stride <= 0 or row_stride <= 0:
        return (0, 0)
    return (max(0, int(canvas_w)) % col_stride, max(0, int(canvas_h)) % row_stride)


def _lattice_counts(width: int, height: int, params: BrickParams) -> tuple[int, int]:
    """Return `(n_cols, n_rows)` - the number of canonical bricks the
    lattice fits across `width` x `height`. Exposed alongside the
    iterator so the UI can warn when the canvas / brick params don't
    divide cleanly (the seam will then carry a leftover mortar band
    that can't be made to tile)."""
    p = params.clamped(width, height)
    row_stride = p.brick_height + p.mortar
    col_stride = p.brick_width + p.mortar
    n_rows = max(1, height // row_stride)
    n_cols = max(1, width // col_stride)
    return n_cols, n_rows


def _iter_brick_lattice(
    width: int, height: int, params: BrickParams,
) -> Iterator[tuple[int, int, int, int]]:
    """Yield `(col_idx, row_idx, brick_x, brick_y)` for every canonical
    brick on the `width x height` canvas. `col_idx` and `row_idx` are
    always in `[0, n_cols)` x `[0, n_rows)`; bricks shifted across the
    canvas seam by `row_offset` are still painted in full because
    `_wrap_blit` splits the rect at the canvas edge.

    No "overshoot" rows or cols are emitted - earlier revisions iterated
    one or two extra cells past each edge to chase seam-crossing bricks,
    but those phantom bricks ended up overpainting both canonical brick
    interiors (with a different per-brick hash) and, when the canvas
    wasn't a multiple of the stride, mortar pixels themselves. The wrap
    is fully handled by `_wrap_blit` instead.

    Both the brick generator and the blocks generator iterate the lattice
    in lockstep, so detail passes can correlate brick coordinates with
    the same per-brick PRNG keys the brick fill used.
    """
    p = params.clamped(width, height)
    row_stride = p.brick_height + p.mortar
    col_stride = p.brick_width + p.mortar
    n_cols, n_rows = _lattice_counts(width, height, p)
    for row_idx in range(n_rows):
        row_y = row_idx * row_stride
        offset_px = int(round(row_idx * p.brick_width * p.row_offset)) % p.brick_width
        for col_idx in range(n_cols):
            brick_x = col_idx * col_stride - offset_px
            yield col_idx, row_idx, brick_x, row_y


def generate_brick_texture(
    *,
    width: int,
    height: int,
    ramp_colors: list[Color],
    params: BrickParams,
    seed: int,
) -> Image.Image:
    """Render a tileable brick texture sized `width x height` using the
    light-to-dark `ramp_colors` (lightest first, darkest last)."""
    if width <= 0 or height <= 0:
        raise ValueError(f"canvas size must be positive, got {width}x{height}")
    if len(ramp_colors) < 2:
        raise ValueError("ramp must have at least 2 colours")

    p = params.clamped(width, height)
    n = len(ramp_colors)
    centre_idx = (n - 1) // 2

    # Mortar / bevel colour hierarchy. `ramp_colors` is documented as
    # lightest-first, darkest-last, so the spec's "stop 0 (darkest)" maps
    # to `ramp_colors[-1]`, "stop 1" to `ramp_colors[-2]`, and the
    # spec's "stop N-2 (one below lightest)" to `ramp_colors[1]`.
    #
    # Mortar must always be deeper than the bevel shadow so blocks read
    # as having depth - the previous code reused `darkest` for both,
    # which collapsed the gap and shadow into the same colour.
    #
    # Collapse rules when the ramp is smaller than the 4 stops the full
    # hierarchy expects (silent - no warning per spec):
    #   * n >= 4: full hierarchy.
    #   * n == 3: face and bevel shadow share the middle stop;
    #             bevel highlight uses the lightest stop.
    #   * n == 2: only mortar vs everything-else; bevel disabled.
    mortar_color = np.array(ramp_colors[-1], dtype=np.uint8)
    if n >= 4:
        bevel_shadow_color = np.array(ramp_colors[-2], dtype=np.uint8)
        bevel_highlight_color = np.array(ramp_colors[1], dtype=np.uint8)
        bevel_active = p.bevel
    elif n == 3:
        bevel_shadow_color = np.array(ramp_colors[1], dtype=np.uint8)
        bevel_highlight_color = np.array(ramp_colors[0], dtype=np.uint8)
        bevel_active = p.bevel
    else:  # n == 2
        bevel_shadow_color = np.array(ramp_colors[0], dtype=np.uint8)
        bevel_highlight_color = bevel_shadow_color
        bevel_active = False

    # Step 1: mortar pass - flood the canvas with the mortar stop.
    pixels = np.empty((height, width, 4), dtype=np.uint8)
    pixels[..., :] = mortar_color

    # Steps 2-4: lay out and fill bricks via the shared lattice iterator.
    for col_idx, row_idx, brick_x, brick_y in _iter_brick_lattice(width, height, p):
        interior_w = p.brick_width
        interior_h = p.brick_height
        if p.color_variance == 0:
            ramp_idx = centre_idx
        else:
            window = 2 * p.color_variance + 1
            offset = (_brick_hash(seed, col_idx, row_idx) % window) - p.color_variance
            ramp_idx = max(0, min(n - 1, centre_idx + offset))
        brick_color = np.array(ramp_colors[ramp_idx], dtype=np.uint8)
        _wrap_blit(pixels, brick_x, brick_y, interior_w, interior_h, brick_color)

        # Step 4: bevel pass. Top + left = highlight, bottom + right =
        # shadow. Draw bottom & right first so the highlight top & left
        # wins on corner conflicts (per spec).
        #
        # `highlight_length` (10..100, percent) shortens the top and
        # left runs only. Pixels past the cutoff revert to the brick
        # face colour that was already painted above. The top-left
        # corner pixel is always lit when bevel is on (max(1, ...) on
        # both runs guarantees this even at 10% on tiny bricks). The
        # bottom and right shadow runs are unaffected per spec.
        if bevel_active and interior_w >= 2 and interior_h >= 2:
            _wrap_blit(pixels, brick_x, brick_y + interior_h - 1, interior_w, 1, bevel_shadow_color)
            _wrap_blit(pixels, brick_x + interior_w - 1, brick_y, 1, interior_h, bevel_shadow_color)
            top_len = max(1, (interior_w * p.highlight_length) // 100)
            left_len = max(1, (interior_h * p.highlight_length) // 100)
            _wrap_blit(pixels, brick_x, brick_y, top_len, 1, bevel_highlight_color)
            _wrap_blit(pixels, brick_x, brick_y, 1, left_len, bevel_highlight_color)

    if p.soft_corners:
        _apply_corner_softening(pixels, p, ramp_colors)

    if p.vegetation is not None:
        _apply_vegetation(pixels, p, p.vegetation, seed)

    return Image.fromarray(pixels, mode="RGBA")


def _apply_corner_softening(
    pixels: np.ndarray,
    params: BrickParams,
    ramp_colors: list[Color],
) -> None:
    """Soften block corners in two deterministic passes after the bevel
    pass. Both passes share a single pixel-type map (face / highlight /
    shadow / mortar) built up-front from the brick lattice so they
    correctly reflect `highlight_length` truncation.

    Pass 1 - T-junction armpit fix: at every T-shape mortar junction
    the two bevel-highlight pixels in the "armpits" - immediately
    flanking the end of the perpendicular mortar stub where it meets
    the wide cross-axis gap - are repainted to mortar so the mortar
    wins the corner. Only currently-highlight pixels are touched; if
    the armpit happens to already be face (highlight_length truncated
    it off) or shadow, it stays.

    Pass 2 - Corner gradient: for each block face corner, the corner
    pixel and the two bevel pixels approaching it (one along each
    incident edge) are repainted with intermediate ramp values so the
    harsh 90deg highlight/shadow/mortar transition reads as slightly
    rounded. Skipped per-block when the face is smaller than 3x3, and
    skipped wholesale when the ramp has fewer than 4 stops (the spec's
    hierarchy needs N>=4 to express the gradient stops).

    Pass 3 - Inner face softening: the first face pixel diagonally
    inside each softened corner is darkened two ramp stops relative to
    that block face, clamped to the bevel-shadow stop. This extends the
    rounding illusion one pixel into the block body, especially around
    T-junctions where bevel-only softening still reads too angular.

    Pass 1 runs before Pass 2 so the gradient sees already-fixed
    armpits at the boundary - if a pixel happens to be both an armpit
    and a corner-approach, the gradient (Pass 2) wins. Pass 3 runs
    last and only touches face pixels."""
    h, w = pixels.shape[:2]
    n = len(ramp_colors)
    if h <= 0 or w <= 0 or n < 2:
        return
    p = params.clamped(w, h)
    if not p.bevel:
        return  # No bevel pixels to soften and no armpits to fix.

    is_face, is_hi, is_sh, is_mortar = _classify_brick_pixels_split(w, h, p)
    mortar_color = np.array(ramp_colors[-1], dtype=np.uint8)

    # ---- Pass 1: T-junction armpit fix ----
    #
    # A vertical mortar stub's "endpoint" is a mortar pixel where the
    # cross-axis (above/below) opens into the wide horizontal gap (i.e.
    # mortar AND the perpendicular wide gap is mortar three-wide there)
    # while the in-axis (left/right) has narrowed back into the brick
    # interior. The armpits are the two pixels flanking that endpoint.
    M = is_mortar
    M_above = np.roll(M, 1, axis=0)
    M_below = np.roll(M, -1, axis=0)
    M_left = np.roll(M, 1, axis=1)
    M_right = np.roll(M, -1, axis=1)

    # Wide-gap detection: at the row/column ABOVE/BELOW/LEFT/RIGHT of
    # the candidate, the perpendicular line is at least 3 mortar pixels
    # wide (so it's the cross-axis gap, not just another stub).
    wide_above = M_above & np.roll(M_above, 1, axis=1) & np.roll(M_above, -1, axis=1)
    wide_below = M_below & np.roll(M_below, 1, axis=1) & np.roll(M_below, -1, axis=1)
    wide_left = M_left & np.roll(M_left, 1, axis=0) & np.roll(M_left, -1, axis=0)
    wide_right = M_right & np.roll(M_right, 1, axis=0) & np.roll(M_right, -1, axis=0)

    # A true T-junction has narrowed back into brick on BOTH flanks of
    # the stub endpoint. Using OR here over-matches plus-junctions and
    # paints non-armpit bevel pixels to mortar.
    vstub_top = M & wide_above & (~M_left) & (~M_right)
    vstub_bot = M & wide_below & (~M_left) & (~M_right)
    hstub_left = M & wide_left & (~M_above) & (~M_below)
    hstub_right = M & wide_right & (~M_above) & (~M_below)

    arm_h = (
        np.roll(vstub_top, -1, axis=1) | np.roll(vstub_top, 1, axis=1)
        | np.roll(vstub_bot, -1, axis=1) | np.roll(vstub_bot, 1, axis=1)
    )
    arm_v = (
        np.roll(hstub_left, -1, axis=0) | np.roll(hstub_left, 1, axis=0)
        | np.roll(hstub_right, -1, axis=0) | np.roll(hstub_right, 1, axis=0)
    )
    # A T-end corner must collapse fully into mortar regardless of
    # whether the bevel pixel there belongs to the highlight side or
    # the shadow side of the adjacent block.
    armpits = (arm_h | arm_v) & (is_hi | is_sh)
    if armpits.any():
        pixels[armpits] = mortar_color
        is_hi[armpits] = False
        is_sh[armpits] = False
        is_mortar[armpits] = True

    # ---- Pass 2: Corner gradient ----
    if n < 4 or p.brick_width < 3 or p.brick_height < 3:
        return

    # Spec uses darkest-first stop indices; code arrays are
    # lightest-first, so spec K -> code (n-1-K). Stops needed:
    #   spec 2     = lightened shadow      -> code n-3
    #   spec N-3   = darkened highlight    -> code 2
    #   midpoint   = floor((1 + (N-2))/2)  -> code n-1-mid_spec
    hi_dark_color = np.array(ramp_colors[2], dtype=np.uint8)
    sh_light_color = np.array(ramp_colors[n - 3], dtype=np.uint8)
    mid_spec = (1 + (n - 2)) // 2
    mid_color = np.array(ramp_colors[n - 1 - mid_spec], dtype=np.uint8)
    is_bevel = is_hi | is_sh
    color_to_idx = {
        tuple(int(v) for v in color): idx for idx, color in enumerate(ramp_colors)
    }

    def _paint_if_bevel(x: int, y: int, color: np.ndarray) -> None:
        wy = y % h
        wx = x % w
        if is_bevel[wy, wx]:
            pixels[wy, wx] = color

    def _paint_if_face_softened(x: int, y: int) -> None:
        wy = y % h
        wx = x % w
        if not is_face[wy, wx]:
            return
        face_key = tuple(int(v) for v in pixels[wy, wx])
        base_idx = color_to_idx.get(face_key)
        if base_idx is None:
            return
        softened_idx = min(n - 2, base_idx + 2)
        pixels[wy, wx] = np.array(ramp_colors[softened_idx], dtype=np.uint8)

    bw, bh = p.brick_width, p.brick_height
    for _col_idx, _row_idx, bx, by in _iter_brick_lattice(w, h, p):
        # Only repaint actual bevel pixels. If a shortened highlight left
        # a would-be corner approach as face, leave the face intact.

        # TL: top highlight meets left highlight - all three darkened.
        _paint_if_bevel(bx, by, hi_dark_color)
        _paint_if_bevel(bx + 1, by, hi_dark_color)
        _paint_if_bevel(bx, by + 1, hi_dark_color)

        # TR: top highlight meets right shadow - mixed; corner = midpoint.
        tr_x, tr_y = bx + bw - 1, by
        _paint_if_bevel(tr_x - 1, tr_y, hi_dark_color)
        _paint_if_bevel(tr_x, tr_y + 1, sh_light_color)
        _paint_if_bevel(tr_x, tr_y, mid_color)

        # BL: per spec, both approaching pixels and corner = sh_light.
        bl_x, bl_y = bx, by + bh - 1
        _paint_if_bevel(bl_x, bl_y - 1, sh_light_color)
        _paint_if_bevel(bl_x + 1, bl_y, sh_light_color)
        _paint_if_bevel(bl_x, bl_y, sh_light_color)

        # BR: bottom shadow meets right shadow - all sh_light.
        br_x, br_y = bx + bw - 1, by + bh - 1
        _paint_if_bevel(br_x - 1, br_y, sh_light_color)
        _paint_if_bevel(br_x, br_y - 1, sh_light_color)
        _paint_if_bevel(br_x, br_y, sh_light_color)

        # Extend the soft-corner gradient one face pixel inward.
        _paint_if_face_softened(bx + 1, by + 1)
        _paint_if_face_softened(tr_x - 1, tr_y + 1)
        _paint_if_face_softened(bl_x + 1, bl_y - 1)
        _paint_if_face_softened(br_x - 1, br_y - 1)


def _classify_brick_pixels_split(
    width: int, height: int, params: BrickParams,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Variant of `_classify_brick_pixels` that splits the bevel mask
    into highlight (top + left, truncated by `highlight_length`) and
    shadow (bottom + right, full length). Returns
    `(is_face, is_hi, is_sh, is_mortar)`.

    Mirrors the paint order of the bevel pass in `generate_brick_texture`
    so the masks reflect the pixel that was actually painted, including
    the highlight-length truncation (the rightmost portion of the top
    edge stays face, not highlight, when `highlight_length < 100`)."""
    p = params.clamped(width, height)
    is_face = np.zeros((height, width), dtype=bool)
    is_hi = np.zeros((height, width), dtype=bool)
    is_sh = np.zeros((height, width), dtype=bool)

    bw_ = p.brick_width
    bh_ = p.brick_height

    for _col_idx, _row_idx, bx, by in _iter_brick_lattice(width, height, p):
        for dy in range(bh_):
            yy = (by + dy) % height
            for dx in range(bw_):
                xx = (bx + dx) % width
                is_face[yy, xx] = True
                is_hi[yy, xx] = False
                is_sh[yy, xx] = False
        if p.bevel and bw_ >= 2 and bh_ >= 2:
            yy = (by + bh_ - 1) % height
            for dx in range(bw_):
                xx = (bx + dx) % width
                is_sh[yy, xx] = True
                is_face[yy, xx] = False
                is_hi[yy, xx] = False
            xx = (bx + bw_ - 1) % width
            for dy in range(bh_):
                yy = (by + dy) % height
                is_sh[yy, xx] = True
                is_face[yy, xx] = False
                is_hi[yy, xx] = False
            top_len = max(1, (bw_ * p.highlight_length) // 100)
            yy = by % height
            for dx in range(top_len):
                xx = (bx + dx) % width
                is_hi[yy, xx] = True
                is_sh[yy, xx] = False
                is_face[yy, xx] = False
            left_len = max(1, (bh_ * p.highlight_length) // 100)
            xx = bx % width
            for dy in range(left_len):
                yy = (by + dy) % height
                is_hi[yy, xx] = True
                is_sh[yy, xx] = False
                is_face[yy, xx] = False

    is_mortar = ~(is_face | is_hi | is_sh)
    return is_face, is_hi, is_sh, is_mortar


# -- Blocks texture (Brick base + dings + cracks) --------------------------


# Per-block PRNG salts. Mixed into the block's seed-hash so the dings and
# cracks streams are independent of (and from) the brick colour-variance
# stream while remaining bit-stable for any given (master seed, col, row).
_SALT_DING = 0xDEADBEEF
_SALT_CRACK = 0xCAFEBABE


@dataclass
class BlocksParams(BrickParams):
    """Brick parameters plus the two Blocks-only detail toggles."""

    # Defaults overridden vs BrickParams: bigger blocks with a 1px mortar.
    brick_width: int = 8        # range 4..canvas_w
    brick_height: int = 6       # range 3..canvas_h

    surface_dings: bool = True  # detail pass A
    ding_amount: int = 50       # 0..100
    cracks: bool = False        # detail pass B
    crack_amount: int = 40      # 0..100

    def clamped(self, canvas_w: int, canvas_h: int) -> "BlocksParams":
        return BlocksParams(
            brick_width=max(4, min(self.brick_width, canvas_w)),
            brick_height=max(3, min(self.brick_height, canvas_h)),
            mortar=max(1, min(self.mortar, 3)),
            row_offset=max(0.0, min(self.row_offset, 1.0)),
            color_variance=max(0, min(self.color_variance, 4)),
            bevel=bool(self.bevel),
            highlight_length=max(10, min(int(self.highlight_length), 100)),
            soft_corners=bool(self.soft_corners),
            surface_dings=bool(self.surface_dings),
            ding_amount=max(0, min(int(self.ding_amount), 100)),
            cracks=bool(self.cracks),
            crack_amount=max(0, min(int(self.crack_amount), 100)),
            vegetation=self.vegetation.clamped() if self.vegetation else None,
        )

    def to_brick_params(self) -> BrickParams:
        """Strip the Blocks-only fields so the brick generator can run as
        the base pass. Vegetation is also stripped here - Blocks applies
        it itself after dings + cracks so the order matches the spec
        (vegetation is the final pass).

        `soft_corners` and `highlight_length` *are* forwarded so the
        corner-softening pass and the truncated-highlight bevel run as
        part of the brick base, matching their specified slots in the
        pipeline."""
        return BrickParams(
            brick_width=self.brick_width,
            brick_height=self.brick_height,
            mortar=self.mortar,
            row_offset=self.row_offset,
            color_variance=self.color_variance,
            bevel=self.bevel,
            highlight_length=self.highlight_length,
            soft_corners=self.soft_corners,
            vegetation=None,
        )


def _block_rng(seed: int, col: int, row: int, salt: int) -> random.Random:
    """Return a deterministic Python `random.Random` keyed on
    (master seed, brick col, brick row, salt). Different salts give
    independent streams so dings and cracks for the same block don't
    correlate."""
    base = _brick_hash(seed, col, row) ^ (salt & 0xFFFFFFFF)
    return random.Random(base)


def _wrap_set_pixel(pixels: np.ndarray, x: int, y: int, color: np.ndarray) -> None:
    """Paint one pixel at canvas coords (x, y) with wrap-around, so detail
    passes that walk past the canvas edge tile cleanly."""
    h, w = pixels.shape[:2]
    pixels[y % h, x % w] = color


_DING_SIZE_WEIGHTS: tuple[tuple[int, int], ...] = (
    (2, 1),
    (3, 3),
    (4, 4),
    (5, 3),
    (6, 1),
)

_DING_SHAPES: dict[int, tuple[tuple[tuple[int, int], ...], ...]] = {
    2: (
        ((0, 0), (1, 0)),
        ((0, 0), (0, 1)),
    ),
    3: (
        ((0, 0), (1, 0), (0, 1)),
        ((0, 0), (1, 0), (1, 1)),
        ((0, 0), (1, 0), (2, 0)),
    ),
    4: (
        ((0, 0), (1, 0), (0, 1), (1, 1)),
        ((0, 0), (1, 0), (2, 0), (1, 1)),
        ((0, 0), (1, 0), (0, 1), (-1, 1)),
    ),
    5: (
        ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1)),
        ((0, 0), (1, 0), (0, 1), (1, 1), (2, 1)),
        ((0, 0), (1, 0), (2, 0), (1, 1), (1, -1)),
    ),
    6: (
        ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)),
        ((0, 0), (1, 0), (2, 0), (1, -1), (1, 1), (2, 1)),
        ((0, 0), (1, 0), (1, 1), (2, 1), (1, 2), (2, 2)),
    ),
}

_DING_TRANSFORMS: tuple[tuple[int, int, bool], ...] = (
    (1, 1, False),
    (-1, 1, False),
    (1, -1, False),
    (-1, -1, False),
    (1, 1, True),
    (-1, 1, True),
    (1, -1, True),
    (-1, -1, True),
)

_MAX_DING_BLOCK_PROBABILITY: float = 0.70
_MAX_CRACK_PROBABILITY: float = 0.50
_THROUGH_CRACK_GAP_CHANCE: float = 0.18


def _weighted_choice(rng: random.Random, weighted_values: tuple[tuple[int, int], ...]) -> int:
    total = sum(weight for _value, weight in weighted_values)
    roll = rng.randrange(total)
    upto = 0
    for value, weight in weighted_values:
        upto += weight
        if roll < upto:
            return value
    return weighted_values[-1][0]


def _transform_offsets(
    offsets: tuple[tuple[int, int], ...],
    *,
    sx: int,
    sy: int,
    swap: bool,
) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for ox, oy in offsets:
        tx, ty = (oy, ox) if swap else (ox, oy)
        out.append((tx * sx, ty * sy))
    return out


def _nearest_face_idx(y: int, x: int, face_idx_map: np.ndarray) -> int:
    """Return the nearest valid face ramp index around `(y, x)`, searching
    the pixel itself first and then a small cardinal/diagonal neighbourhood."""
    h_, w_ = face_idx_map.shape
    base_idx = int(face_idx_map[y % h_, x % w_])
    if base_idx >= 0:
        return base_idx
    for radius in (1, 2):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) + abs(dy) > radius:
                    continue
                idx = int(face_idx_map[(y + dy) % h_, (x + dx) % w_])
                if idx >= 0:
                    return idx
    return -1


def _paint_ding_blob(
    pixels: np.ndarray,
    positions: list[tuple[int, int]],
    *,
    base_idx: int,
    ramp_colors: list[Color],
) -> None:
    if not positions:
        return
    n = len(ramp_colors)
    if n <= 1:
        return

    centroid_y = sum(y for y, _x in positions) / len(positions)
    centroid_x = sum(x for _y, x in positions) / len(positions)
    core_count = 1 if len(positions) <= 4 else 2
    ordered = sorted(
        positions,
        key=lambda pos: (
            abs(pos[0] - centroid_y) + abs(pos[1] - centroid_x),
            pos[0],
            pos[1],
        ),
    )
    core = ordered[:core_count]

    light_idx = min(n - 2, base_idx + 1)
    mid_idx = min(n - 2, base_idx + 2)
    dark_idx = min(n - 2, base_idx + 3)

    max_dist = 0
    dists: dict[tuple[int, int], int] = {}
    for pos in positions:
        dist = min(abs(pos[0] - cy) + abs(pos[1] - cx) for cy, cx in core)
        dists[pos] = dist
        max_dist = max(max_dist, dist)

    for y, x in positions:
        dist = dists[(y, x)]
        if max_dist <= 0:
            idx = dark_idx
        elif max_dist == 1:
            idx = dark_idx if dist == 0 else mid_idx
        else:
            idx = dark_idx if dist == 0 else (mid_idx if dist == 1 else light_idx)
        pixels[y, x] = np.array(ramp_colors[idx], dtype=np.uint8)


def _plan_crack_gaps(
    rng: random.Random,
    spine: list[tuple[int, int]],
    *,
    face_idx_map: np.ndarray,
    ramp_colors: list[Color],
) -> tuple[
    dict[tuple[int, int], np.ndarray],
    dict[tuple[int, int], np.ndarray],
    set[tuple[int, int]],
]:
    """Return overlay maps for optional gaps inside a through-crack spine.

    `gap_fill` repaints selected centre pixels back to their face colour.
    `gap_edge` lightly softens the crack pixels immediately before/after
    each gap so the interruption reads intentional instead of abrupt."""
    if len(spine) < 6 or rng.random() >= _THROUGH_CRACK_GAP_CHANCE:
        return {}, {}, set()

    h_, w_ = face_idx_map.shape
    gap_fill: dict[tuple[int, int], np.ndarray] = {}
    gap_edge: dict[tuple[int, int], np.ndarray] = {}
    gap_pixels: set[tuple[int, int]] = set()

    target_gap_count = 1 if rng.random() < 0.65 else 2
    centre = len(spine) // 2
    candidate_indices = list(range(max(2, centre - 3), min(len(spine) - 2, centre + 4)))
    rng.shuffle(candidate_indices)

    accepted_gap_count = 0
    blocked: set[int] = set()
    for start_idx in candidate_indices:
        if accepted_gap_count >= target_gap_count:
            break
        if start_idx in blocked:
            continue
        gap_len = rng.randint(1, 2)
        gap_indices = list(range(start_idx, min(start_idx + gap_len, len(spine) - 1)))
        if any(idx in blocked for idx in gap_indices):
            continue

        base_idx = _nearest_face_idx(spine[start_idx][0], spine[start_idx][1], face_idx_map)
        if base_idx < 0:
            continue

        face_color = np.array(ramp_colors[base_idx], dtype=np.uint8)
        edge_idx = min(len(ramp_colors) - 2, base_idx + 2)
        edge_color = np.array(ramp_colors[edge_idx], dtype=np.uint8)

        for idx in gap_indices:
            gy, gx = spine[idx]
            key = (gy % h_, gx % w_)
            gap_fill[key] = face_color
            gap_pixels.add(key)
            blocked.update({idx - 1, idx, idx + 1, idx + 2})

        left_idx = gap_indices[0] - 1
        right_idx = gap_indices[-1] + 1
        if 0 <= left_idx < len(spine):
            ey, ex = spine[left_idx]
            key = (ey % h_, ex % w_)
            if key not in gap_pixels:
                gap_edge[key] = edge_color
        if 0 <= right_idx < len(spine):
            ey, ex = spine[right_idx]
            key = (ey % h_, ex % w_)
            if key not in gap_pixels:
                gap_edge[key] = edge_color
        accepted_gap_count += 1

    if not gap_pixels:
        return {}, {}, set()
    return gap_fill, gap_edge, gap_pixels


def _apply_dings(
    pixels: np.ndarray,
    bx: int, by: int, bw: int, bh: int,
    seed: int, col: int, row: int,
    ramp_colors: list[Color],
    face_idx_map: np.ndarray,
    ding_amount: int,
) -> None:
    """Detail pass A from the Blocks spec.

    Dings may only land on block-face pixels. `face_idx_map` is the shared
    per-pixel face classifier built once for the whole render; using it here
    means dings naturally avoid mortar and bevel regardless of whether bevel
    is enabled.
    """
    amount_norm = max(0.0, min(float(ding_amount), 100.0)) / 100.0
    if amount_norm <= 0.0:
        return

    rng = _block_rng(seed, col, row, _SALT_DING)
    block_probability = 0.10 + (_MAX_DING_BLOCK_PROBABILITY - 0.10) * amount_norm
    if rng.random() >= block_probability:
        return

    h_, w_ = pixels.shape[:2]
    valid_face: dict[tuple[int, int], int] = {}
    for yy in range(by, by + bh):
        wy = yy % h_
        for xx in range(bx, bx + bw):
            wx = xx % w_
            face_idx = int(face_idx_map[wy, wx])
            if face_idx >= 0:
                valid_face[(wy, wx)] = face_idx
    if not valid_face:
        return

    ding_count = 1
    if rng.random() < 0.30 + 0.45 * amount_norm:
        ding_count += 1
    if rng.random() < max(0.0, amount_norm - 0.10):
        ding_count += 1

    claimed: set[tuple[int, int]] = set()
    all_sizes = [size for size, _weight in _DING_SIZE_WEIGHTS]
    anchors = sorted(valid_face)
    for _ in range(ding_count):
        preferred_size = _weighted_choice(rng, _DING_SIZE_WEIGHTS)
        size_order = [preferred_size] + [
            size
            for size in sorted(all_sizes, key=lambda value: abs(value - preferred_size))
            if size != preferred_size
        ]

        placed = False
        for size in size_order:
            variants: list[list[tuple[int, int]]] = []
            for offsets in _DING_SHAPES[size]:
                for sx, sy, swap in _DING_TRANSFORMS:
                    variants.append(
                        _transform_offsets(offsets, sx=sx, sy=sy, swap=swap)
                    )
            rng.shuffle(variants)

            anchor_order = anchors[:]
            rng.shuffle(anchor_order)
            for ay, ax in anchor_order:
                if (ay, ax) in claimed:
                    continue
                for offsets in variants:
                    positions: list[tuple[int, int]] = []
                    for dx, dy in offsets:
                        key = ((ay + dy) % h_, (ax + dx) % w_)
                        if key not in valid_face or key in claimed:
                            positions = []
                            break
                        positions.append(key)
                    if not positions:
                        continue

                    base_idx = round(
                        sum(valid_face[pos] for pos in positions) / len(positions)
                    )
                    _paint_ding_blob(
                        pixels,
                        positions,
                        base_idx=max(0, min(len(ramp_colors) - 2, base_idx)),
                        ramp_colors=ramp_colors,
                    )
                    claimed.update(positions)
                    placed = True
                    break
                if placed:
                    break
            if placed:
                break


def _build_face_idx_map(
    width: int, height: int, params: BrickParams, seed: int, n_stops: int,
) -> np.ndarray:
    """Return an `(height, width)` int16 map of per-pixel block face ramp
    indices. `-1` marks a pixel that's not block face (mortar or bevel).

    Mirrors `generate_brick_texture`'s per-block ramp_idx computation
    so the crack pass's shadow-fringe darkening picks up the actual
    rendered face colour - including per-block colour variance offsets.
    """
    p = params.clamped(width, height)
    centre_idx = (n_stops - 1) // 2
    out = np.full((height, width), -1, dtype=np.int16)
    bw_, bh_ = p.brick_width, p.brick_height
    has_bevel = p.bevel and bw_ >= 2 and bh_ >= 2

    for col_idx, row_idx, bx, by in _iter_brick_lattice(width, height, p):
        if p.color_variance == 0:
            ramp_idx = centre_idx
        else:
            window = 2 * p.color_variance + 1
            offset = (
                _brick_hash(seed, col_idx, row_idx) % window
            ) - p.color_variance
            ramp_idx = max(0, min(n_stops - 1, centre_idx + offset))

        if has_bevel:
            x_lo, x_hi = bx + 1, bx + bw_ - 2
            y_lo, y_hi = by + 1, by + bh_ - 2
        else:
            x_lo, x_hi = bx, bx + bw_ - 1
            y_lo, y_hi = by, by + bh_ - 1
        if x_lo > x_hi or y_lo > y_hi:
            continue
        for yy in range(y_lo, y_hi + 1):
            wy = yy % height
            for xx in range(x_lo, x_hi + 1):
                out[wy, xx % width] = ramp_idx
    return out


def _apply_crack(
    pixels: np.ndarray,
    bx: int, by: int, bw: int, bh: int,
    seed: int, col: int, row: int,
    ramp_colors: list[Color],
    crack_amount: int,
    *,
    bevel: bool,
    is_mortar: np.ndarray,
    face_idx_map: np.ndarray,
    crack_record: set[tuple[int, int]] | None = None,
    gap_record: set[tuple[int, int]] | None = None,
) -> None:
    """Detail pass B from the Blocks spec - structured stress fracture.

    A crack starts on the top or bottom mortar seam of the block body and
    travels inward in a Manhattan-style
    stepped path (1..4 px primary runs separated by 1 px perpendicular
    pivots), tapers from a 2 px-wide stroke to a 1 px stroke after at most
    2 px of crack progression, remains primarily vertical, and may die out
    before it reaches the far seam. Every crack is anchored to at least one
    mortar seam and must span at least 25% of the block height. A 1 px shadow
    fringe of block-face colour darkened by 2 ramp stops is painted on
    either side of the crack centre to read as the stone face sinking into
    the fissure.

    All coordinates wrap modulo the canvas, so cracks placed near the
    seam continue cleanly on the opposite edge.

    Crack placement is amount-driven: the user-facing slider scales the
    per-block probability up to `_MAX_CRACK_PROBABILITY` and modestly
    stretches the nominal crack length.

    `crack_record` (optional) collects every painted crack centre pixel
    as a canvas-space (y, x) tuple. Used by the vegetation pass so moss
    can grow on cracks without colour-matching against the mortar shade
    (which would also flag legitimately darkest-coloured block faces).
    """
    amount_norm = max(0.0, min(float(crack_amount), 100.0)) / 100.0
    if amount_norm <= 0.0:
        return

    rng = _block_rng(seed, col, row, _SALT_CRACK)
    if rng.random() >= _MAX_CRACK_PROBABILITY * amount_norm:
        return

    h_, w_ = pixels.shape[:2]
    n = len(ramp_colors)

    # Crack centres may travel across bevel pixels so the fissure visibly
    # meets its origin mortar seam. Only the fringe stays restricted to
    # true face pixels.
    body_x_lo, body_x_hi = bx, bx + bw - 1  # inclusive
    body_y_lo, body_y_hi = by, by + bh - 1
    if body_x_lo > body_x_hi or body_y_lo > body_y_hi:
        return

    # Step 2: pick an origin along the top or bottom seam, inset from the
    # corners so the crack starts in the body rather than in the corner
    # blends.
    x_min, x_max = body_x_lo + 2, body_x_hi - 2
    if x_min > x_max:
        return
    ox = rng.randint(x_min, x_max)
    if rng.random() < 0.5:
        oy = body_y_lo
        primary = (0, 1)
    else:
        oy = body_y_hi
        primary = (0, -1)
    min_vertical_span = max(2, (bh + 3) // 4)

    # Keep lateral pivots inside an inner corridor so the crack can't
    # run out into the side seams and read as a horizontal fracture.
    lateral_lo = body_x_lo + 1 if bw >= 3 else body_x_lo
    lateral_hi = body_x_hi - 1 if bw >= 3 else body_x_hi

    # Step 4: build the structured step path. Force at least one pivot so
    # the crack visibly tapers from its 2 px origin into a 1 px fracture.
    # The walk is not forced to hit the far seam, but it does need enough
    # vertical travel to read as a proper stress line.
    nominal_total = rng.randint(
        3 + round(2 * amount_norm),
        6 + round(5 * amount_norm),
    )
    path: list[tuple[tuple[int, int], int]] = []
    first_primary_len = rng.randint(2, 4 if amount_norm >= 0.35 else 3)
    path.append((primary, first_primary_len))
    total_steps = first_primary_len
    primary_progress = first_primary_len
    while total_steps < nominal_total or primary_progress < min_vertical_span:
        pivot = (rng.choice((-1, 1)), 0)
        pivot_len = 1
        path.append((pivot, pivot_len))
        total_steps += pivot_len
        primary_len = rng.randint(1, 4)
        path.append((primary, primary_len))
        total_steps += primary_len
        primary_progress += primary_len

    # Step 5: walk the path. Crack centres are collected first into a
    # set so the fringe pass can look up "is this pixel a centre?" in
    # O(1) and never overwrite a centre. The 2 px-wide phase is capped to
    # the first two progression steps so the crack quickly narrows into
    # a mostly 1 px seam.
    centres: set[tuple[int, int]] = set()
    centre_dirs: dict[tuple[int, int], tuple[int, int]] = {}
    spine: list[tuple[int, int]] = []
    raw_x_min: int | None = None
    raw_x_max: int | None = None
    raw_y_min: int | None = None
    raw_y_max: int | None = None

    def _add_centre(px: int, py: int, direction: tuple[int, int]) -> None:
        nonlocal raw_x_min, raw_x_max, raw_y_min, raw_y_max
        key = (py % h_, px % w_)
        centres.add(key)
        # Keep the direction the centre was first painted with so the
        # fringe pass picks the right perpendicular axis even if a later
        # segment re-visits the same pixel from a different heading.
        centre_dirs.setdefault(key, direction)
        raw_x_min = px if raw_x_min is None else min(raw_x_min, px)
        raw_x_max = px if raw_x_max is None else max(raw_x_max, px)
        raw_y_min = py if raw_y_min is None else min(raw_y_min, py)
        raw_y_max = py if raw_y_max is None else max(raw_y_max, py)

    cx, cy = ox, oy
    two_px_phase = True
    pivoted = False
    two_px_budget = 2
    terminated = False
    for seg_idx, (direction, step_len) in enumerate(path):
        # The 2 px stroke ends at the first direction change in the
        # path - i.e. the moment we paint into the first pivot segment.
        if seg_idx > 0 and not pivoted:
            two_px_phase = False
            pivoted = True
        for _ in range(step_len):
            wy, wx = cy % h_, cx % w_
            # Crack centres run until the first mortar pixel; bevel is a
            # valid part of the route so the fissure visibly meets the seam.
            if is_mortar[wy, wx]:
                terminated = True
                break
            _add_centre(cx, cy, direction)
            key = (cy % h_, cx % w_)
            if not spine or spine[-1] != key:
                spine.append(key)
            if two_px_phase:
                # Companion pixel: vertical travel widens horizontally,
                # horizontal travel widens downward.
                if direction[0] == 0:
                    if not is_mortar[cy % h_, (cx + 1) % w_]:
                        _add_centre(cx + 1, cy, direction)
                else:
                    if not is_mortar[(cy + 1) % h_, cx % w_]:
                        _add_centre(cx, cy + 1, direction)
                two_px_budget -= 1
                if two_px_budget <= 0:
                    two_px_phase = False
            next_x = cx + direction[0]
            if next_x < lateral_lo or next_x > lateral_hi:
                terminated = True
                break
            cx += direction[0]
            cy += direction[1]
        if terminated:
            break

    if (
        not centres
        or not spine
        or raw_x_min is None
        or raw_x_max is None
        or raw_y_min is None
        or raw_y_max is None
    ):
        return
    vertical_span = raw_y_max - raw_y_min + 1
    horizontal_span = raw_x_max - raw_x_min + 1
    if vertical_span < min_vertical_span:
        return
    if horizontal_span > vertical_span:
        return

    through_crack = raw_y_min == body_y_lo and raw_y_max == body_y_hi
    gap_fill: dict[tuple[int, int], np.ndarray] = {}
    gap_edge: dict[tuple[int, int], np.ndarray] = {}
    gap_pixels: set[tuple[int, int]] = set()
    if through_crack:
        gap_fill, gap_edge, gap_pixels = _plan_crack_gaps(
            rng,
            spine,
            face_idx_map=face_idx_map,
            ramp_colors=ramp_colors,
        )

    active_centres = centres.difference(gap_pixels)
    if not active_centres:
        return

    # Step 5C: paint crack centres. Darkest ramp stop, same as mortar -
    # so cracks read as fissures opening into the same dark void as the
    # mortar gaps between blocks.
    darkest = np.array(ramp_colors[-1], dtype=np.uint8)
    for cy_p, cx_p in active_centres:
        pixels[cy_p, cx_p] = darkest
        if crack_record is not None:
            crack_record.add((cy_p, cx_p))

    # Step 5D: paint shadow fringe. For every centre, look at the two
    # neighbours perpendicular to that centre's travel direction. If
    # the neighbour is a block-face pixel (face_idx_map >= 0) and not
    # itself a centre, darken it 2 ramp stops below the *block's* base
    # colour - this is what sells "the stone face is sinking into the
    # crack".
    #
    # During the 2 px phase the two centres at (px, py) and (px+1, py)
    # together cover the inner pair (px, py) and (px+1, py), so the
    # outer fringe at (px-1, py) and (px+2, py) is what the spec asks
    # for - falls out naturally from skipping centre pixels.
    for (cy_p, cx_p), direction in centre_dirs.items():
        if (cy_p, cx_p) not in active_centres:
            continue
        if direction[0] == 0:
            neighbours = ((cy_p, (cx_p - 1) % w_), (cy_p, (cx_p + 1) % w_))
        else:
            neighbours = (((cy_p - 1) % h_, cx_p), ((cy_p + 1) % h_, cx_p))
        for ny, nx in neighbours:
            if (ny, nx) in active_centres:
                continue
            base_idx = int(face_idx_map[ny, nx])
            if base_idx < 0:
                continue  # mortar or bevel - leave alone
            darkened = min(n - 2, base_idx + 2)
            pixels[ny, nx] = np.array(ramp_colors[darkened], dtype=np.uint8)

    for key, color in gap_edge.items():
        pixels[key] = color
    for key, color in gap_fill.items():
        pixels[key] = color
        if gap_record is not None:
            gap_record.add(key)


# -- Vegetation pass (final pass, applied after every other detail) -------


# Per-pixel PRNG salts for the moss and grass streams. Keep these
# distinct from the per-brick salts so vegetation rolls don't correlate
# with ding / crack rolls at any given location.
_SALT_VEG_MOSS = 0xA00BA000
_SALT_VEG_GRASS = 0xA00BA001


def _vegetation_ramp(base: Color) -> tuple[Color, Color, Color]:
    """3-stop dark/mid/light ramp derived from `base` per the spec:
      * dark  = base, S +15, B -35
      * mid   = base
      * light = base, S -25, B +25
    HSB ops, clamped to legal ranges. Recomputed per render - cheap.
    """
    h, s, b, a = _rgb_to_hsb(base)
    dark = _hsb_to_rgb(h, min(100.0, s + 15.0), max(0.0, b - 35.0), a)
    mid = _hsb_to_rgb(h, s, b, a)
    light = _hsb_to_rgb(h, max(0.0, s - 25.0), min(100.0, b + 25.0), a)
    return dark, mid, light


def _classify_brick_pixels(
    width: int, height: int, params: BrickParams,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (is_face, is_bevel, is_mortar) bool masks.

    The iteration mirrors `generate_brick_texture`'s paint order
    (face fill, then bevel overrides) so the classification matches the
    pixel that actually got painted - crucial for the vegetation pass
    to correctly identify mortar vs bevel vs face territory at the
    seam-wrap boundaries where multiple virtual bricks overlap.
    """
    p = params.clamped(width, height)
    is_face = np.zeros((height, width), dtype=bool)
    is_bevel = np.zeros((height, width), dtype=bool)

    bw_ = p.brick_width
    bh_ = p.brick_height

    for _col_idx, _row_idx, bx, by in _iter_brick_lattice(width, height, p):
        for dy in range(bh_):
            yy = (by + dy) % height
            for dx in range(bw_):
                xx = (bx + dx) % width
                is_face[yy, xx] = True
                is_bevel[yy, xx] = False
        if p.bevel and bw_ >= 2 and bh_ >= 2:
            yy = (by + bh_ - 1) % height
            for dx in range(bw_):
                xx = (bx + dx) % width
                is_bevel[yy, xx] = True
                is_face[yy, xx] = False
            xx = (bx + bw_ - 1) % width
            for dy in range(bh_):
                yy = (by + dy) % height
                is_bevel[yy, xx] = True
                is_face[yy, xx] = False
            yy = by % height
            for dx in range(bw_):
                xx = (bx + dx) % width
                is_bevel[yy, xx] = True
                is_face[yy, xx] = False
            xx = bx % width
            for dy in range(bh_):
                yy = (by + dy) % height
                is_bevel[yy, xx] = True
                is_face[yy, xx] = False

    is_mortar = ~(is_face | is_bevel)
    return is_face, is_bevel, is_mortar


def _pixel_rng(seed: int, x: int, y: int, salt: int) -> random.Random:
    """Per-pixel deterministic PRNG keyed on (master seed, x, y, salt).

    Used by the vegetation pass so each candidate pixel's placement
    decision is order-independent (same result whether the pass scans
    row-major or sweeps eligible pixels in any other order)."""
    base = _brick_hash(seed, x, y) ^ (salt & 0xFFFFFFFF)
    return random.Random(base)


def _apply_vegetation(
    pixels: np.ndarray,
    brick_params: BrickParams,
    veg: VegetationParams,
    seed: int,
    *,
    crack_pixels: set[tuple[int, int]] | None = None,
) -> None:
    """Final pass: paint moss clusters and/or grass tufts in the mortar
    seams. Mutates `pixels` in place. Safe to call on either Brick or
    Blocks output - `crack_pixels` is None for Brick and a set of
    canvas-space (y, x) crack pixels for Blocks (when cracks were
    enabled)."""
    p = veg.clamped()
    if p.coverage <= 0.0:
        return

    h_, w_ = pixels.shape[:2]
    is_face, is_bevel, is_mortar = _classify_brick_pixels(w_, h_, brick_params)

    is_crack = np.zeros_like(is_face)
    if crack_pixels:
        for cy, cx in crack_pixels:
            # Defensive modulo - the crack recorder already wraps but
            # being explicit means callers can pass un-wrapped coords.
            is_crack[cy % h_, cx % w_] = True

    moss_eligible = is_mortar | is_crack

    dark, mid, light = _vegetation_ramp(p.color)
    dark_arr = np.array(dark, dtype=np.uint8)
    mid_arr = np.array(mid, dtype=np.uint8)
    light_arr = np.array(light, dtype=np.uint8)

    do_moss = p.style in (VEGETATION_STYLE_MOSS, VEGETATION_STYLE_BOTH)
    do_grass = p.style in (VEGETATION_STYLE_GRASS, VEGETATION_STYLE_BOTH)

    # Moss clusters can't share pixels - one global "claimed" set
    # tracks every cluster pixel placed so far.
    claimed: set[tuple[int, int]] = set()

    if do_moss:
        # argwhere returns (y, x) in row-major order, which gives a
        # deterministic iteration sequence across runs.
        for yx in np.argwhere(moss_eligible):
            y = int(yx[0])
            x = int(yx[1])
            if (y, x) in claimed:
                continue
            rng = _pixel_rng(seed, x, y, _SALT_VEG_MOSS)
            if rng.random() >= p.coverage:
                continue

            cluster_size = rng.randint(1, 3)
            cluster_pixels: list[tuple[int, int]] = [(y, x)]
            if cluster_size > 1:
                # Spec: only cardinal neighbours, only eligible ones,
                # never face / bevel / out-of-bounds. Wrap-around for
                # seamless tiling.
                neighbours = [
                    ((y - 1) % h_, x),
                    ((y + 1) % h_, x),
                    (y, (x - 1) % w_),
                    (y, (x + 1) % w_),
                ]
                eligible_neighbours = [
                    (ny, nx) for ny, nx in neighbours
                    if moss_eligible[ny, nx] and (ny, nx) not in claimed
                ]
                rng.shuffle(eligible_neighbours)
                for n_pos in eligible_neighbours:
                    if len(cluster_pixels) >= cluster_size:
                        break
                    cluster_pixels.append(n_pos)

            anchor_is_light = rng.random() < 0.25
            for i, (cy, cx) in enumerate(cluster_pixels):
                if i == 0:
                    color = light_arr if anchor_is_light else mid_arr
                else:
                    color = dark_arr if rng.random() < 0.60 else mid_arr
                pixels[cy, cx] = color
                claimed.add((cy, cx))

    if do_grass:
        # Eligible grass anchor: mortar pixel where the pixel directly
        # above is brick (face OR bevel) - i.e. tuft can push upward
        # into the brick body.
        is_brick_above = np.zeros_like(is_mortar)
        is_brick_above[1:] = is_face[:-1] | is_bevel[:-1]
        is_brick_above[0] = is_face[h_ - 1] | is_bevel[h_ - 1]
        grass_eligible = is_mortar & is_brick_above

        # Grass coverage is internally scaled so the slider feels
        # consistent with moss despite grass naturally being sparser.
        effective_p = p.coverage * 0.6

        for y in range(h_):
            blocked: set[int] = set()
            for x in range(w_):
                if not grass_eligible[y, x]:
                    continue
                if x in blocked:
                    continue
                rng = _pixel_rng(seed, x, y, _SALT_VEG_GRASS)
                if rng.random() >= effective_p:
                    continue

                requested_h = rng.randint(2, 3)
                lean = rng.choice([-1, 0, 1])

                # Walk upward from base, stopping at the first bevel.
                # final_h = 1 (base only) up to requested_h.
                upward_count = 0
                for step in range(1, requested_h):
                    next_y = (y - step) % h_
                    if is_bevel[next_y, x]:
                        break
                    upward_count += 1
                final_h = 1 + upward_count
                if final_h <= 0:
                    continue

                # Paint base (always in mortar).
                pixels[y, x] = dark_arr
                if final_h >= 2:
                    tip_y = (y - (final_h - 1)) % h_
                    tip_x = (x + lean) % w_
                    # Drop lean if the offset pixel is mortar / bevel
                    # (don't grow into a different mortar gap; don't
                    # overwrite bevel either).
                    if is_mortar[tip_y, tip_x] or is_bevel[tip_y, tip_x]:
                        tip_x = x
                    if final_h == 2:
                        pixels[tip_y, tip_x] = light_arr
                    else:  # final_h == 3
                        mid_y = (y - 1) % h_
                        pixels[mid_y, x] = mid_arr
                        pixels[tip_y, tip_x] = light_arr

                # Reserve X-2..X+2 on this mortar line so tufts don't
                # clump. Wrap so a tuft near the canvas edge still
                # blocks its symmetric neighbour after the seam.
                for offset in range(-2, 3):
                    blocked.add((x + offset) % w_)


def generate_blocks_texture(
    *,
    width: int,
    height: int,
    ramp_colors: list[Color],
    params: BlocksParams,
    seed: int,
) -> Image.Image:
    """Render a Blocks texture: brick base + bevel + optional dings + cracks.

    Reuses `generate_brick_texture` for steps 1-4 (mortar, layout, fill,
    bevel) and walks the same lattice (via `_iter_brick_lattice`) for the
    detail passes so per-block PRNG keys line up with the brick fill.
    Vegetation, when enabled, runs as the final pass after dings / cracks.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"canvas size must be positive, got {width}x{height}")
    if len(ramp_colors) < 2:
        raise ValueError("ramp must have at least 2 colours")

    p = params.clamped(width, height)
    base = generate_brick_texture(
        width=width, height=height,
        ramp_colors=ramp_colors,
        params=p.to_brick_params(),
        seed=seed,
    )
    do_dings = p.surface_dings and p.ding_amount > 0
    do_cracks = p.cracks and p.crack_amount > 0

    # Skip the detail passes entirely if neither toggle is on AND no
    # vegetation - saves both the np.array round-trip and the lattice walk.
    if not do_dings and not do_cracks and p.vegetation is None:
        return base

    pixels = np.array(base)
    n = len(ramp_colors)

    # Capture crack pixels iff we'll need them for vegetation; skipping
    # the recorder for plain Blocks keeps the detail pass allocation-free.
    crack_record: set[tuple[int, int]] | None = (
        set() if (do_cracks and p.vegetation is not None) else None
    )

    # Detail-pass prerequisites. Per spec these are built once before the
    # per-block loop, not recomputed per block:
    #   * face_idx_map - per-pixel block ramp index; dings use it as the
    #                    valid face mask and cracks use it for both face-
    #                    only placement and shadow-fringe darkening.
    #   * is_mortar - crack termination check when the walk reaches a
    #                 mortar seam rather than just the bevel boundary.
    is_mortar_mask: np.ndarray | None = None
    face_idx_map: np.ndarray | None = None
    if do_dings or do_cracks:
        face_idx_map = _build_face_idx_map(
            width, height, p.to_brick_params(), seed, n
        )
    if do_cracks:
        _, _, is_mortar_mask = _classify_brick_pixels(
            width, height, p.to_brick_params()
        )

    bw = p.brick_width
    bh = p.brick_height
    for col_idx, row_idx, brick_x, brick_y in _iter_brick_lattice(width, height, p.to_brick_params()):
        if do_dings:
            assert face_idx_map is not None
            _apply_dings(
                pixels, brick_x, brick_y, bw, bh,
                seed, col_idx, row_idx,
                ramp_colors,
                face_idx_map,
                p.ding_amount,
            )
        if do_cracks:
            assert is_mortar_mask is not None and face_idx_map is not None
            _apply_crack(
                pixels, brick_x, brick_y, bw, bh,
                seed, col_idx, row_idx,
                ramp_colors,
                p.crack_amount,
                bevel=p.bevel,
                is_mortar=is_mortar_mask,
                face_idx_map=face_idx_map,
                crack_record=crack_record,
            )

    if p.vegetation is not None:
        _apply_vegetation(
            pixels, p.to_brick_params(), p.vegetation, seed,
            crack_pixels=crack_record,
        )

    return Image.fromarray(pixels, mode="RGBA")


# -- Boards texture ---------------------------------------------------------


# Per-pass salts so the boards algorithm pulls each random stream from an
# independent series even though they all share the master seed (mirrors
# the _SALT_DING / _SALT_CRACK pattern above).
_SALT_BOARDS_WOBBLE = 0xB0A4D000
_SALT_BOARDS_COLOR = 0xB0A4D001
_SALT_BOARDS_GRAIN = 0xB0A4D002
_SALT_BOARDS_GRAIN_STUB = 0xB0A4D003
_SALT_BOARDS_KNOT_POS = 0xB0A4D004
_SALT_BOARDS_KNOT_HALO = 0xB0A4D005


# When the canvas dimension perpendicular to plank length is below this,
# knots may not render well. The UI surfaces a non-blocking warning rather
# than disabling the toggle (per spec).
BOARDS_KNOT_MIN_CANVAS: int = 24


@dataclass
class BoardsParams:
    """Parameters for `generate_boards_texture`. Plank Width is the
    *thickness* of each plank (perpendicular to plank length); Orientation
    flips the algorithm's axis at the boundary so the same code path
    handles both directions."""

    plank_width: int = 6        # 3..canvas dim perpendicular to length
    orientation: str = "horizontal"  # "horizontal" or "vertical"
    gap: int = 1                # 1..2 px
    color_variance: int = 2     # 0..4 ramp stops
    edge_wobble: int = 2        # 0..4 px
    grain_density: int = 3      # 1..6 lines per plank
    grain_waviness: int = 2     # 0..4 px sine amplitude
    bevel: bool = True
    knots: bool = True
    knots_per_sheet: int = 2    # 0..6

    def clamped(self, canvas_w: int, canvas_h: int) -> "BoardsParams":
        orient = (
            "vertical"
            if str(self.orientation).lower().startswith("v")
            else "horizontal"
        )
        # Plank width is bounded by the canvas dimension perpendicular to
        # the plank length axis.
        width_axis = canvas_h if orient == "horizontal" else canvas_w
        return BoardsParams(
            plank_width=max(3, min(self.plank_width, max(3, int(width_axis)))),
            orientation=orient,
            gap=max(1, min(self.gap, 2)),
            color_variance=max(0, min(self.color_variance, 4)),
            edge_wobble=max(0, min(self.edge_wobble, 4)),
            grain_density=max(1, min(self.grain_density, 6)),
            grain_waviness=max(0, min(self.grain_waviness, 4)),
            bevel=bool(self.bevel),
            knots=bool(self.knots),
            knots_per_sheet=max(0, min(self.knots_per_sheet, 6)),
        )


def _gap_color_from_darkest(darkest: Color) -> Color:
    """Push the darkest ramp stop ~20% toward black (clamped). This is
    the colour that fills the gap between planks and acts as the base for
    knot halos."""
    r, g, b, a = darkest
    return (
        max(0, int(round(r * 0.8))),
        max(0, int(round(g * 0.8))),
        max(0, int(round(b * 0.8))),
        a,
    )


def _wobble_walk(
    seed: int, boundary_idx: int, length: int, max_wobble: int,
) -> np.ndarray:
    """Per-pixel boundary offset for one plank gap, biased random walk
    clamped to ±max_wobble. The tail is linearly blended back to
    `offsets[0]` so the wobble tiles seamlessly across the wrap seam.
    """
    if length <= 0:
        return np.zeros(0, dtype=np.int32)
    if max_wobble <= 0:
        return np.zeros(length, dtype=np.int32)
    rng = _block_rng(seed, boundary_idx, 0, _SALT_BOARDS_WOBBLE)
    offsets = np.zeros(length, dtype=np.int32)
    cur = 0
    for x in range(length):
        r = rng.random()
        if r < 0.20:
            cur -= 1
        elif r < 0.40:
            cur += 1
        cur = max(-max_wobble, min(max_wobble, cur))
        offsets[x] = cur
    blend = min(length // 4, max(1, max_wobble * 4 + 1))
    if blend > 1 and length > blend:
        end_val = int(offsets[length - blend])
        target = int(offsets[0])
        for i in range(blend):
            t = i / max(1, blend - 1)
            offsets[length - blend + i] = int(
                round(end_val * (1 - t) + target * t)
            )
    return offsets


def _ellipse_inside(dx: int, dy: int, rx: int, ry: int) -> bool:
    """Integer-safe test for (dx, dy) inside an axis-aligned ellipse of
    radii (rx, ry). Used for the knot halo / ring / core shells."""
    if rx <= 0 or ry <= 0:
        return False
    return (dx * dx) * (ry * ry) + (dy * dy) * (rx * rx) <= (rx * rx) * (ry * ry)


def _generate_boards_canonical(
    *,
    width: int,            # along plank length axis
    height: int,           # perpendicular to plank length axis
    ramp_colors: list[Color],
    params: BoardsParams,
    seed: int,
) -> np.ndarray:
    """Render boards in the canonical horizontal frame (planks running
    left-right, plank width = vertical dimension). Vertical orientation
    is implemented as a coordinate transform on the result rather than
    duplicating algorithm logic."""
    n = len(ramp_colors)
    lightest = np.array(ramp_colors[0], dtype=np.uint8)
    darkest = np.array(ramp_colors[-1], dtype=np.uint8)
    second_darkest = np.array(ramp_colors[max(0, n - 2)], dtype=np.uint8)
    centre_idx = (n - 1) // 2

    W = max(1, params.plank_width)
    G = max(1, params.gap)
    S = W + G
    n_planks = max(1, height // S)

    # Step 1: gap pass - fill the canvas with the gap colour.
    gap_rgb = _gap_color_from_darkest(
        tuple(int(v) for v in ramp_colors[-1])  # type: ignore[arg-type]
    )
    gap_color = np.array(gap_rgb, dtype=np.uint8)
    pixels = np.empty((height, width, 4), dtype=np.uint8)
    pixels[..., :] = gap_color

    # Step 2: per-boundary wobble offsets. `gap_offset[i]` is the per-x
    # shift of the gap *below* plank i (which is also the top boundary of
    # plank (i + 1) % n_planks). The whole gap moves as a unit.
    gap_offset = np.zeros((n_planks, width), dtype=np.int32)
    for i in range(n_planks):
        gap_offset[i] = _wobble_walk(seed, i, width, params.edge_wobble)

    # Step 3: derive per-plank top / bot from the wobble of bordering
    # gaps, then fill. plank_top / plank_bot are the wobble-aware edge
    # map every later pass references.
    plank_top = np.zeros((n_planks, width), dtype=np.int32)
    plank_bot = np.zeros((n_planks, width), dtype=np.int32)
    plank_color_idx = np.zeros(n_planks, dtype=np.int32)

    for i in range(n_planks):
        prev_i = (i - 1) % n_planks
        nominal_top = i * S
        nominal_bot = i * S + W
        top_arr = nominal_top + gap_offset[prev_i]
        bot_arr = nominal_bot + gap_offset[i]
        # Defensive thickness clamp - prevents 0-px planks if the wobble
        # streams of adjacent boundaries happen to converge. With default
        # ranges this is essentially impossible but cheap to guarantee.
        thick = bot_arr - top_arr
        bot_arr = np.where(thick < 1, top_arr + 1, bot_arr)
        plank_top[i] = top_arr
        plank_bot[i] = bot_arr

        if params.color_variance == 0:
            ramp_idx = centre_idx
        else:
            rng = _block_rng(seed, i, 0, _SALT_BOARDS_COLOR)
            offset = rng.randint(-params.color_variance, params.color_variance)
            ramp_idx = max(0, min(n - 1, centre_idx + offset))
        plank_color_idx[i] = ramp_idx
        plank_color = np.array(ramp_colors[ramp_idx], dtype=np.uint8)

        for x in range(width):
            t = int(plank_top[i, x])
            b = int(plank_bot[i, x])
            for y_off in range(b - t):
                pixels[(t + y_off) % height, x] = plank_color

    # Step 4: bevel - one row inside the wobbled edge map, top = light,
    # bottom = dark. Skip planks that are too thin for both.
    if params.bevel:
        for i in range(n_planks):
            for x in range(width):
                t = int(plank_top[i, x])
                b = int(plank_bot[i, x])
                if b - t < 2:
                    continue
                pixels[t % height, x] = lightest
                pixels[(b - 1) % height, x] = darkest

    # Step 6 (positioning only): pick knot centres before the grain pass
    # so grain can curve around them without a second pass (per spec
    # implementation note).
    knots: list[tuple[int, int, int, int, int]] = []  # (cx, cy, rx, ry, plank_idx)
    if params.knots and params.knots_per_sheet > 0 and width >= 9 and height >= 9:
        rng_kp = _block_rng(seed, 0, 0, _SALT_BOARDS_KNOT_POS)
        max_attempts = max(50, params.knots_per_sheet * 100)
        for _ in range(max_attempts):
            if len(knots) >= params.knots_per_sheet:
                break
            cx = rng_kp.randint(4, width - 5)
            cy = rng_kp.randint(4, height - 5)
            r = rng_kp.randint(2, 4)
            rx = max(1, rng_kp.randint(r - 1, r + 1))
            ry = max(1, rng_kp.randint(r - 1, r + 1))
            if any(
                (cx - ox) ** 2 + (cy - oy) ** 2 < 36
                for ox, oy, _, _, _ in knots
            ):
                continue
            plank_idx = (cy // S) % n_planks
            t = int(plank_top[plank_idx, cx])
            b = int(plank_bot[plank_idx, cx])
            if not (t <= cy < b):
                continue  # centre fell into a wobbled gap - skip and retry
            knots.append((cx, cy, rx, ry, plank_idx))

    # Step 5: grain pass. For each plank lay grain_density lines parallel
    # to plank length, with sine waviness, partial spans, and termination
    # stubs. Knot distortion is applied in-line so grain bends around
    # nearby knots without needing a second pass.
    if params.grain_density > 0:
        bevel_active = params.bevel
        for i in range(n_planks):
            nominal_top = i * S
            nominal_bot = i * S + W
            interior_top = nominal_top + (1 if bevel_active else 0)
            interior_bot = nominal_bot - (1 if bevel_active else 0)
            if interior_bot - interior_top < 1:
                continue
            for g_idx in range(params.grain_density):
                rng = _block_rng(seed, i, g_idx, _SALT_BOARDS_GRAIN)
                base_y = (
                    interior_top
                    + (g_idx + 0.5)
                    * (interior_bot - interior_top)
                    / params.grain_density
                )
                jitter = rng.randint(-1, 1)
                y_anchor = max(
                    interior_top,
                    min(interior_bot - 1, int(round(base_y)) + jitter),
                )

                # Colour: 1-2 stops darker than this plank's base, capped
                # at the darkest ramp stop.
                darkness_step = rng.choice([1, 2])
                grain_idx = min(n - 1, int(plank_color_idx[i]) + darkness_step)
                grain_color = np.array(ramp_colors[grain_idx], dtype=np.uint8)

                length_frac = rng.uniform(0.5, 1.0)
                grain_len = max(1, int(round(width * length_frac)))
                x_start = rng.randint(0, max(0, width - 1))
                freq = rng.uniform(0.2, 0.8)
                phase = rng.uniform(0.0, 6.283185307179586)

                last_pixel: tuple[int, int] | None = None
                for off in range(grain_len):
                    x = (x_start + off) % width
                    disp = 0
                    if params.grain_waviness > 0:
                        disp = int(
                            round(
                                np.sin(off * freq + phase)
                                * params.grain_waviness
                            )
                        )
                    y = y_anchor + disp

                    # Knot distortion: push grain pixel away from any
                    # knot centre within 3 px (max ±2 px right at the
                    # knot, fading to 0 at distance 3).
                    for cx_k, cy_k, _, _, _ in knots:
                        dx_signed = (
                            (x - cx_k + width // 2) % width
                        ) - width // 2
                        dy_diff = y - cy_k
                        d2 = dx_signed * dx_signed + dy_diff * dy_diff
                        if d2 < 9:
                            dist = d2 ** 0.5
                            if dist < 3.0:
                                push = 2.0 * (1.0 - dist / 3.0)
                                sign = 1 if dy_diff >= 0 else -1
                                y += int(round(push * sign))

                    # Clamp to this column's plank interior (excluding
                    # bevel pixels if bevel is active and there is room).
                    t = int(plank_top[i, x])
                    b = int(plank_bot[i, x])
                    if bevel_active and (b - t) >= 3:
                        t += 1
                        b -= 1
                    if b - t < 1:
                        continue
                    y = max(t, min(b - 1, y))
                    pixels[y % height, x] = grain_color
                    last_pixel = (x, y)

                if last_pixel is not None:
                    rng_stub = _block_rng(
                        seed, i, g_idx, _SALT_BOARDS_GRAIN_STUB
                    )
                    if rng_stub.random() < 0.30:
                        stub_len = rng_stub.randint(1, 2)
                        stub_dir = rng_stub.choice([-1, 1])
                        lx, ly = last_pixel
                        t = int(plank_top[i, lx])
                        b = int(plank_bot[i, lx])
                        if bevel_active and (b - t) >= 3:
                            t += 1
                            b -= 1
                        for s in range(1, stub_len + 1):
                            sy = ly + s * stub_dir
                            if t <= sy < b:
                                pixels[sy % height, lx] = grain_color

    # Step 6 (painting): halo, ring, core, then SE shadow. Painted
    # outward-in so the inner rings win on shell conflicts at the edges
    # of the ellipse.
    if params.knots and knots:
        for k_idx, (cx, cy, rx, ry, plank_idx) in enumerate(knots):
            rng_halo = _block_rng(seed, k_idx, 0, _SALT_BOARDS_KNOT_HALO)
            halo_skip_rate = rng_halo.uniform(0.10, 0.20)
            shadow_color = np.array(
                (
                    int(round((int(darkest[0]) + int(second_darkest[0])) / 2)),
                    int(round((int(darkest[1]) + int(second_darkest[1])) / 2)),
                    int(round((int(darkest[2]) + int(second_darkest[2])) / 2)),
                    int(darkest[3]),
                ),
                dtype=np.uint8,
            )
            for dy in range(-(ry + 1), ry + 2):
                for dx in range(-(rx + 1), rx + 2):
                    nx = (cx + dx) % width
                    ny = cy + dy
                    if ny < 0 or ny >= height:
                        continue
                    # Knots respect the wobble-aware plank boundary: any
                    # pixel that would fall in a gap is skipped.
                    t = int(plank_top[plank_idx, nx])
                    b = int(plank_bot[plank_idx, nx])
                    if not (t <= ny < b):
                        continue
                    in_core = _ellipse_inside(dx, dy, max(1, rx - 1), max(1, ry - 1))
                    in_ring = _ellipse_inside(dx, dy, rx, ry)
                    in_halo = _ellipse_inside(dx, dy, rx + 1, ry + 1)
                    if in_core:
                        pixels[ny, nx] = darkest
                    elif in_ring:
                        pixels[ny, nx] = second_darkest
                    elif in_halo:
                        if rng_halo.random() >= halo_skip_rate:
                            pixels[ny, nx] = darkest
            # Shadow: 1-px crescent on the bottom-right quadrant just
            # outside the halo. "Darkest blended slightly lighter" is
            # implemented as the average of darkest and second-darkest.
            for dy in range(0, ry + 3):
                for dx in range(0, rx + 3):
                    if _ellipse_inside(dx, dy, rx + 1, ry + 1):
                        continue
                    if not _ellipse_inside(dx, dy, rx + 2, ry + 2):
                        continue
                    nx = (cx + dx) % width
                    ny = cy + dy
                    if ny < 0 or ny >= height:
                        continue
                    t = int(plank_top[plank_idx, nx])
                    b = int(plank_bot[plank_idx, nx])
                    if not (t <= ny < b):
                        continue
                    pixels[ny, nx] = shadow_color

    return pixels


def generate_boards_texture(
    *,
    width: int,
    height: int,
    ramp_colors: list[Color],
    params: BoardsParams,
    seed: int,
) -> Image.Image:
    """Render a tileable wood-boards texture using the light-to-dark
    `ramp_colors` (lightest first). Vertical orientation re-uses the
    horizontal generator on a transposed canvas and rotates the result;
    this keeps the algorithm single-sourced."""
    if width <= 0 or height <= 0:
        raise ValueError(f"canvas size must be positive, got {width}x{height}")
    if len(ramp_colors) < 2:
        raise ValueError("ramp must have at least 2 colours")

    p = params.clamped(width, height)
    if p.orientation == "vertical":
        pixels = _generate_boards_canonical(
            width=height,
            height=width,
            ramp_colors=ramp_colors,
            params=p,
            seed=seed,
        )
        pixels = np.ascontiguousarray(pixels.transpose((1, 0, 2)))
    else:
        pixels = _generate_boards_canonical(
            width=width,
            height=height,
            ramp_colors=ramp_colors,
            params=p,
            seed=seed,
        )
    return Image.fromarray(pixels, mode="RGBA")


# -- Texture-type registry --------------------------------------------------


# Order matters: it sets the dropdown order in the UI.
TEXTURE_TYPES: tuple[str, ...] = ("Brick", "Blocks", "Boards")


# Canvases below this size will surface a non-blocking warning when cracks
# are enabled (per spec). Exposed so the UI can read the same threshold.
BLOCKS_CRACK_MIN_CANVAS: int = 32


def texture_type_default_filename(texture_type: str, width: int, height: int) -> str:
    safe = texture_type.lower().replace(" ", "_")
    return f"texture_{safe}_{width}x{height}.png"
