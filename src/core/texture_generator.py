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


def _iter_brick_lattice(
    width: int, height: int, params: BrickParams,
) -> Iterator[tuple[int, int, int, int]]:
    """Yield `(col_idx, row_idx, brick_x, brick_y)` for every brick that
    touches the `width x height` canvas, including one row/column of
    overshoot on each side so bricks crossing the canvas edge can be
    rendered with `_wrap_blit` and continue seamlessly from the opposite
    side. The brick width and height are constant across the lattice and
    can be read from `params`.

    Both the brick generator and the blocks generator iterate the lattice
    in lockstep, so detail passes can correlate brick coordinates with
    the same per-brick PRNG keys the brick fill used.
    """
    p = params.clamped(width, height)
    row_stride = p.brick_height + p.mortar
    col_stride = p.brick_width + p.mortar
    first_row = -1
    last_row = (height // row_stride) + 2
    for row_idx in range(first_row, last_row):
        row_y = row_idx * row_stride
        offset_px = int(round(row_idx * p.brick_width * p.row_offset)) % p.brick_width
        first_col = -1
        last_col = (width // col_stride) + 2
        for col_idx in range(first_col, last_col):
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
    lightest = np.array(ramp_colors[0], dtype=np.uint8)
    darkest = np.array(ramp_colors[-1], dtype=np.uint8)
    centre_idx = (n - 1) // 2

    # Step 1: mortar pass - flood the canvas with the darkest stop.
    pixels = np.empty((height, width, 4), dtype=np.uint8)
    pixels[..., :] = darkest

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

        # Step 4: bevel pass. Top + left = lightest, bottom + right =
        # darkest. Draw bottom & right first so the lightest top & left
        # wins on corner conflicts (per spec).
        if p.bevel and interior_w >= 2 and interior_h >= 2:
            _wrap_blit(pixels, brick_x, brick_y + interior_h - 1, interior_w, 1, darkest)
            _wrap_blit(pixels, brick_x + interior_w - 1, brick_y, 1, interior_h, darkest)
            _wrap_blit(pixels, brick_x, brick_y, interior_w, 1, lightest)
            _wrap_blit(pixels, brick_x, brick_y, 1, interior_h, lightest)

    return Image.fromarray(pixels, mode="RGBA")


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
    cracks: bool = False        # detail pass B

    def clamped(self, canvas_w: int, canvas_h: int) -> "BlocksParams":
        return BlocksParams(
            brick_width=max(4, min(self.brick_width, canvas_w)),
            brick_height=max(3, min(self.brick_height, canvas_h)),
            mortar=max(1, min(self.mortar, 3)),
            row_offset=max(0.0, min(self.row_offset, 1.0)),
            color_variance=max(0, min(self.color_variance, 4)),
            bevel=bool(self.bevel),
            surface_dings=bool(self.surface_dings),
            cracks=bool(self.cracks),
        )

    def to_brick_params(self) -> BrickParams:
        """Strip the Blocks-only fields so the brick generator can run as
        the base pass."""
        return BrickParams(
            brick_width=self.brick_width,
            brick_height=self.brick_height,
            mortar=self.mortar,
            row_offset=self.row_offset,
            color_variance=self.color_variance,
            bevel=self.bevel,
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


def _apply_dings(
    pixels: np.ndarray,
    bx: int, by: int, bw: int, bh: int,
    seed: int, col: int, row: int,
    darkest: np.ndarray, second_darkest: np.ndarray,
) -> None:
    """Detail pass A from the Blocks spec.

    Ding zone is the brick interior inset by 1 px on every side - i.e. the
    region that's inside the bevel - so dings never overwrite the bevel.
    """
    rng = _block_rng(seed, col, row, _SALT_DING)
    if rng.random() >= 0.40:
        return
    n_dings = rng.randint(1, 3)
    zone_x0 = bx + 1
    zone_y0 = by + 1
    zone_w = bw - 2
    zone_h = bh - 2
    if zone_w <= 0 or zone_h <= 0:
        return
    for _ in range(n_dings):
        ax = zone_x0 + rng.randrange(zone_w)
        ay = zone_y0 + rng.randrange(zone_h)
        # Alternate (seeded) between darkest and one stop lighter.
        color = darkest if rng.random() < 0.5 else second_darkest
        _wrap_set_pixel(pixels, ax, ay, color)
        placed = 1
        n_extras = rng.randint(0, 2)
        if n_extras == 0:
            continue
        neighbours = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        rng.shuffle(neighbours)
        for dx, dy in neighbours:
            if placed >= 3 or n_extras <= 0:
                break
            nx = ax + dx
            ny = ay + dy
            # Must remain in the ding zone (no mortar, no bevel).
            if not (zone_x0 <= nx < zone_x0 + zone_w):
                continue
            if not (zone_y0 <= ny < zone_y0 + zone_h):
                continue
            _wrap_set_pixel(pixels, nx, ny, color)
            placed += 1
            n_extras -= 1


def _apply_crack(
    pixels: np.ndarray,
    bx: int, by: int, bw: int, bh: int,
    seed: int, col: int, row: int,
    darkest: np.ndarray,
) -> None:
    """Detail pass B from the Blocks spec.

    A crack originates on either the top or left bevel pixel of the brick
    interior and walks inward via a biased random walk (80% primary, 20%
    perpendicular jitter). Length 2-6 px. After placement, 20% chance of a
    single Y-branch from a non-tip point.
    """
    rng = _block_rng(seed, col, row, _SALT_CRACK)
    if rng.random() >= 0.25:
        return
    if bw < 3 or bh < 3:
        return  # nothing to fracture inside

    edge = rng.choice(("top", "left"))
    if edge == "top":
        ox = bx + rng.randrange(bw)
        oy = by
        primary = (0, 1)
    else:
        ox = bx
        oy = by + rng.randrange(bh)
        primary = (1, 0)

    length = rng.randint(2, 6)
    crack_pixels: list[tuple[int, int]] = [(ox, oy)]
    _wrap_set_pixel(pixels, ox, oy, darkest)
    cx, cy = ox, oy
    for _ in range(length - 1):
        if rng.random() < 0.80:
            dx, dy = primary
        else:
            # Perpendicular jitter only - never reverse the primary axis.
            if primary[0] == 0:
                dx, dy = (rng.choice((-1, 1)), 0)
            else:
                dx, dy = (0, rng.choice((-1, 1)))
        nx, ny = cx + dx, cy + dy
        # Stop if we'd leave the brick interior or hit the opposite bevel.
        if not (bx <= nx <= bx + bw - 1) or not (by <= ny <= by + bh - 1):
            break
        if edge == "top" and ny == by + bh - 1:
            break
        if edge == "left" and nx == bx + bw - 1:
            break
        cx, cy = nx, ny
        crack_pixels.append((cx, cy))
        _wrap_set_pixel(pixels, cx, cy, darkest)

    # Branch: 20% chance, max one per crack, originating from a non-tip point.
    if len(crack_pixels) >= 2 and rng.random() < 0.20:
        bp_idx = rng.randrange(0, len(crack_pixels) - 1)
        bx0, by0 = crack_pixels[bp_idx]
        if primary[0] == 0:
            branch_primary = (rng.choice((-1, 1)), 0)
        else:
            branch_primary = (0, rng.choice((-1, 1)))
        branch_len = rng.randint(1, 3)
        cx, cy = bx0, by0
        for _ in range(branch_len):
            if rng.random() < 0.80:
                dx, dy = branch_primary
            else:
                # Jitter perpendicular to the branch axis.
                if branch_primary[0] == 0:
                    dx, dy = (rng.choice((-1, 1)), 0)
                else:
                    dx, dy = (0, rng.choice((-1, 1)))
            nx, ny = cx + dx, cy + dy
            if not (bx <= nx <= bx + bw - 1) or not (by <= ny <= by + bh - 1):
                break
            cx, cy = nx, ny
            _wrap_set_pixel(pixels, cx, cy, darkest)


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
    # Skip the detail passes entirely if neither toggle is on - saves both
    # the np.array round-trip and the lattice walk.
    if not p.surface_dings and not p.cracks:
        return base

    pixels = np.array(base)
    n = len(ramp_colors)
    darkest = np.array(ramp_colors[-1], dtype=np.uint8)
    second_darkest = np.array(ramp_colors[max(0, n - 2)], dtype=np.uint8)

    bw = p.brick_width
    bh = p.brick_height
    for col_idx, row_idx, brick_x, brick_y in _iter_brick_lattice(width, height, p.to_brick_params()):
        if p.surface_dings:
            _apply_dings(
                pixels, brick_x, brick_y, bw, bh,
                seed, col_idx, row_idx, darkest, second_darkest,
            )
        if p.cracks:
            _apply_crack(
                pixels, brick_x, brick_y, bw, bh,
                seed, col_idx, row_idx, darkest,
            )

    return Image.fromarray(pixels, mode="RGBA")


# -- Texture-type registry --------------------------------------------------


# Order matters: it sets the dropdown order in the UI. "Blocks Cracked"
# is a separate entry from "Blocks" per the user's preference - both use
# the Blocks algorithm with different default params.
TEXTURE_TYPES: tuple[str, ...] = ("Brick", "Blocks", "Blocks Cracked")


# Canvases below this size will surface a non-blocking warning when cracks
# are enabled (per spec). Exposed so the UI can read the same threshold.
BLOCKS_CRACK_MIN_CANVAS: int = 32


def texture_type_default_filename(texture_type: str, width: int, height: int) -> str:
    safe = texture_type.lower().replace(" ", "_")
    return f"texture_{safe}_{width}x{height}.png"
