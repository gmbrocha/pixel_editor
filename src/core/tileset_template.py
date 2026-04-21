"""Procedural 8x6 = 47-tile tileset template generator.

Each tile is a flat silhouette of two regions: Region A (the "wall" / solid
side) and Region B (the "floor" / open side). The 47 tile arrangement
covers all visually distinct combinations of N/S/E/W edge walls and the
four "inner corner" wall nubs that tile-set authors typically need.

The tile silhouettes are deterministic for a given seed, with subtle
seeded edge wobble, optional outer-corner chamfering, and occasional
1-deep notches on long straight edges. Region fill is either a flat
RGBA colour or a tile-sized texture tiled across the sheet so adjacent
tiles of the same region remain visually continuous.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw


Color = tuple[int, int, int, int]


# -- Sheet layout -----------------------------------------------------------

SHEET_COLS: int = 8
SHEET_ROWS: int = 6
TOTAL_TILES: int = 47  # last slot (col 7, row 5) is intentionally empty


# Each tile role is a list of "wall components" that get unioned into the
# wall mask. The final mask = True for Region A (wall), False for Region B
# (floor). Components:
#   'N','S','E','W'         -- ts/4 strip on that edge
#   'INNER_NE/NW/SE/SW'     -- ts/4 x ts/4 wall nub in that corner
#   'FULL'                  -- entire tile is wall (FULL_WALL)
#   'ISOLATED'              -- single small wall blob in centre
# (FULL_FLOOR is the empty list.)
TILE_ROLES: list[list[str]] = [
    # Row 0
    [],                                     # 0 FULL_FLOOR
    ['N'],                                  # 1 WALL_N
    ['S'],                                  # 2 WALL_S
    ['E'],                                  # 3 WALL_E
    ['W'],                                  # 4 WALL_W
    ['N', 'S'],                             # 5 WALL_NS  (vertical corridor)
    ['E', 'W'],                             # 6 WALL_EW  (horizontal corridor)
    ['N', 'E'],                             # 7 WALL_NE_OUTER_CORNER
    # Row 1
    ['N', 'W'],                             # 8 WALL_NW_OUTER
    ['S', 'E'],                             # 9 WALL_SE_OUTER
    ['S', 'W'],                             # 10 WALL_SW_OUTER
    ['N', 'S', 'E'],                        # 11 WALL_NSE  (T, open W)
    ['N', 'S', 'W'],                        # 12 WALL_NSW  (T, open E)
    ['N', 'E', 'W'],                        # 13 WALL_NEW  (T, open S)
    ['S', 'E', 'W'],                        # 14 WALL_SEW  (T, open N)
    ['N', 'S', 'E', 'W'],                   # 15 WALL_NSEW (cross / +)
    # Row 2
    ['INNER_NE'],                           # 16
    ['INNER_NW'],                           # 17
    ['INNER_SE'],                           # 18
    ['INNER_SW'],                           # 19
    ['N', 'INNER_SE'],                      # 20
    ['N', 'INNER_SW'],                      # 21
    ['S', 'INNER_NE'],                      # 22
    ['S', 'INNER_NW'],                      # 23
    # Row 3
    ['E', 'INNER_NW'],                      # 24
    ['E', 'INNER_SW'],                      # 25
    ['W', 'INNER_NE'],                      # 26
    ['W', 'INNER_SE'],                      # 27
    ['N', 'E', 'INNER_SW'],                 # 28
    ['N', 'W', 'INNER_SE'],                 # 29
    ['S', 'E', 'INNER_NW'],                 # 30
    ['S', 'W', 'INNER_NE'],                 # 31
    # Row 4
    ['N', 'INNER_SE', 'INNER_SW'],          # 32
    ['S', 'INNER_NE', 'INNER_NW'],          # 33
    ['E', 'INNER_NW', 'INNER_SW'],          # 34
    ['W', 'INNER_NE', 'INNER_SE'],          # 35
    ['INNER_NE', 'INNER_SW'],               # 36 DOUBLE_INNER_NE_SW
    ['INNER_NW', 'INNER_SE'],               # 37 DOUBLE_INNER_NW_SE
    ['FULL'],                               # 38 FULL_WALL
    ['ISOLATED'],                           # 39 ISOLATED_WALL
    # Row 5
    ['N', 'S', 'INNER_NE'],                 # 40
    ['N', 'S', 'INNER_NW'],                 # 41
    ['N', 'S', 'INNER_SE'],                 # 42
    ['N', 'S', 'INNER_SW'],                 # 43
    ['E', 'W', 'INNER_NE'],                 # 44
    ['E', 'W', 'INNER_NW'],                 # 45
    ['E', 'W', 'INNER_SE'],                 # 46
    # slot (7, 5) = empty
]
assert len(TILE_ROLES) == TOTAL_TILES, (
    f"expected {TOTAL_TILES} tile roles, got {len(TILE_ROLES)}"
)


SUPPORTED_TILE_SIZES: tuple[int, ...] = (16, 32, 48, 64)


# Built-in two-region presets. Wall is region A, Floor is region B.
QUICK_PRESETS: list[tuple[str, str, Color, str, Color]] = [
    # (preset_label, wall_name, wall_color, floor_name, floor_color)
    ("Dirt / Stone",         "Stone",    (0x4a, 0x4a, 0x52, 0xff), "Dirt",    (0x7a, 0x5c, 0x3a, 0xff)),
    ("Brick / Mortar",       "Brick",    (0x7a, 0x3a, 0x2a, 0xff), "Mortar",  (0xc8, 0xaa, 0x72, 0xff)),
    ("Grass / Earth",        "Grass",    (0x5a, 0x8a, 0x4a, 0xff), "Earth",   (0x7a, 0x5c, 0x3a, 0xff)),
    ("Water / Sand",         "Water",    (0x2a, 0x4a, 0x7a, 0xff), "Sand",    (0xc8, 0xaa, 0x72, 0xff)),
    ("Obsidian / Crystal",   "Obsidian", (0x1a, 0x1a, 0x2a, 0xff), "Crystal", (0x3a, 0x2a, 0x5a, 0xff)),
]


# -- Public data classes ----------------------------------------------------


@dataclass
class RegionSpec:
    """One region's fill specification.

    `texture` (when not None) is composited into this region's silhouette
    mask, sampled at (px % tile_size, py % tile_size) so it tiles across
    the whole sheet rather than restarting per tile. `color` is used when
    `texture` is None.
    """

    name: str
    color: Color = (0, 0, 0, 255)
    texture: Image.Image | None = None

    @property
    def fill_mode(self) -> str:
        return "texture" if self.texture is not None else "color"


# Transition style identifiers for Region C (kept lowercase to match the
# UI dropdown's stored data values).
TRANSITION_STYLE_NONE: str = "none"
TRANSITION_STYLE_HARD_BORDER: str = "hard_border"
TRANSITION_STYLE_STONE_LIP: str = "stone_lip"
TRANSITION_STYLES: tuple[str, ...] = (
    TRANSITION_STYLE_NONE,
    TRANSITION_STYLE_HARD_BORDER,
    TRANSITION_STYLE_STONE_LIP,
)


@dataclass
class RegionCSpec:
    """Optional transition region painted into edge / corner tiles only.

    Region C overlays Region B at the silhouette boundary, eating inward
    by `depth` (or a wobbled depth, for Stone Lip). It never overwrites
    Region A. The `style` field selects the lip shaping algorithm; only
    the parameters relevant to the chosen style are read at render time,
    so the others can carry any default the UI sees fit to keep around.
    """

    name: str = "Transition"
    color: Color = (0xc8, 0xaa, 0x72, 0xff)
    texture: Image.Image | None = None
    style: str = TRANSITION_STYLE_STONE_LIP

    # None / Hard Border: single depth value (1-4 / 1-3 respectively).
    depth: int = 2

    # Stone Lip parameters.
    min_depth: int = 1
    max_depth: int = 3
    wobble_rate: int = 3
    follow_pattern: bool = True

    @property
    def fill_mode(self) -> str:
        return "texture" if self.texture is not None else "color"

    def effective_max_depth(self) -> int:
        """Maximum number of pixels the lip can extend into Region B at any
        point. Used to bound the BFS expansion so we don't scan further
        than necessary."""
        if self.style == TRANSITION_STYLE_STONE_LIP:
            return max(1, self.max_depth)
        return max(1, self.depth)


# -- Mask building & variation ---------------------------------------------


def _build_base_wall_mask(role: list[str], ts: int) -> np.ndarray:
    """Return a (ts, ts) bool mask: True where Region A (wall) covers."""
    mask = np.zeros((ts, ts), dtype=bool)
    if "FULL" in role:
        mask[:] = True
        return mask
    if "ISOLATED" in role:
        # Small centred wall blob, ~ts/4 across (min 2px).
        blob = max(2, ts // 4)
        cy = cx = ts // 2
        half = blob // 2
        mask[cy - half:cy - half + blob, cx - half:cx - half + blob] = True
        return mask

    # ts/4 wall thickness on edge strips; ts/4 size for inner-corner nubs.
    w = max(1, ts // 4)
    if "N" in role:
        mask[0:w, :] = True
    if "S" in role:
        mask[ts - w:ts, :] = True
    if "E" in role:
        mask[:, ts - w:ts] = True
    if "W" in role:
        mask[:, 0:w] = True
    if "INNER_NE" in role:
        mask[0:w, ts - w:ts] = True
    if "INNER_NW" in role:
        mask[0:w, 0:w] = True
    if "INNER_SE" in role:
        mask[ts - w:ts, ts - w:ts] = True
    if "INNER_SW" in role:
        mask[ts - w:ts, 0:w] = True
    return mask


def _stable_per_tile_seed(seed: int, tile_index: int) -> int:
    """Mix the master seed and tile index into a 32-bit value so each tile
    has its own deterministic PRNG stream that doesn't depend on the order
    other tiles were generated in."""
    mixed = ((seed & 0xFFFFFFFF) * 2654435761) ^ ((tile_index + 1) * 0x9E3779B9)
    return mixed & 0xFFFFFFFF


def _apply_edge_wobble(mask: np.ndarray, rng: np.random.Generator) -> None:
    """Shift wall/floor boundary cells by +-1 px with ~20% probability.

    Vectorised: each call to `rng.random(shape)` is deterministic for a
    given seeded `rng`, so the seed -> sheet relationship stays
    reproducible even though we no longer step pixel-by-pixel.
    Operates on a working copy so the wobble decision for one boundary
    cell can't immediately influence its neighbour.
    """
    ts = mask.shape[0]
    new_mask = mask.copy()

    # Skip wobble entirely on tiles that are too small to have an
    # "interior" boundary not touching the tile edge.
    if ts >= 4:
        # --- Horizontal boundaries: between row y and row y+1, for
        #     y in 1..ts-3 (skip border-adjacent rows for clean tile edges).
        upper = mask[1:ts - 2]   # shape (ts-3, ts), rows 1..ts-3
        lower = mask[2:ts - 1]   # shape (ts-3, ts), rows 2..ts-2
        is_boundary = upper != lower
        should_wobble = rng.random(is_boundary.shape) < 0.20
        extend_out = rng.random(is_boundary.shape) < 0.5
        active = is_boundary & should_wobble
        wall_above = active & upper       # wall on row y, floor on row y+1
        wall_below = active & lower       # floor on row y, wall on row y+1

        # extend_out grows the wall by 1px outward; otherwise we retract.
        upper_set_floor = np.zeros_like(mask)
        lower_set_wall = np.zeros_like(mask)
        upper_set_wall = np.zeros_like(mask)
        lower_set_floor = np.zeros_like(mask)
        upper_set_floor[1:ts - 2] = wall_above & ~extend_out  # retract: clear wall row
        lower_set_wall[2:ts - 1] = wall_above & extend_out    # extend: fill floor row
        lower_set_floor[2:ts - 1] = wall_below & ~extend_out
        upper_set_wall[1:ts - 2] = wall_below & extend_out
        new_mask[upper_set_floor] = False
        new_mask[lower_set_wall] = True
        new_mask[lower_set_floor] = False
        new_mask[upper_set_wall] = True

        # --- Vertical boundaries: between col x and col x+1.
        left = mask[:, 1:ts - 2]
        right = mask[:, 2:ts - 1]
        is_b = left != right
        should = rng.random(is_b.shape) < 0.20
        ext = rng.random(is_b.shape) < 0.5
        active = is_b & should
        wall_left = active & left
        wall_right = active & right
        left_clear = np.zeros_like(mask)
        right_set = np.zeros_like(mask)
        right_clear = np.zeros_like(mask)
        left_set = np.zeros_like(mask)
        left_clear[:, 1:ts - 2] = wall_left & ~ext
        right_set[:, 2:ts - 1] = wall_left & ext
        right_clear[:, 2:ts - 1] = wall_right & ~ext
        left_set[:, 1:ts - 2] = wall_right & ext
        new_mask[left_clear] = False
        new_mask[right_set] = True
        new_mask[right_clear] = False
        new_mask[left_set] = True

    _kill_isolated_pixels(new_mask)
    mask[:] = new_mask


def _kill_isolated_pixels(mask: np.ndarray) -> None:
    """Flip any cell whose 4 axis-aligned neighbours all disagree with it.

    Run once; this is enough to remove the rare single-pixel islands that
    edge-wobble can produce when both sides of a 1-pixel-thick edge happen
    to flip the same column.
    """
    ts = mask.shape[0]
    pad = np.pad(mask, 1, constant_values=False)
    same = (
        (pad[0:ts, 1:ts + 1] == mask).astype(np.int8)
        + (pad[2:ts + 2, 1:ts + 1] == mask).astype(np.int8)
        + (pad[1:ts + 1, 0:ts] == mask).astype(np.int8)
        + (pad[1:ts + 1, 2:ts + 2] == mask).astype(np.int8)
    )
    isolated = same == 0
    mask[isolated] = ~mask[isolated]


def _round_outer_corners(mask: np.ndarray, rng: np.random.Generator) -> None:
    """For each convex outer wall corner (a wall pixel with exactly one N/S
    and one E/W wall neighbour, plus the diagonal-out neighbour also wall),
    remove it with 50% probability to chamfer the corner."""
    ts = mask.shape[0]
    if ts < 3:
        return
    # Shifted neighbour boards (False outside the grid).
    n = np.zeros_like(mask); n[1:, :] = mask[:-1, :]
    s = np.zeros_like(mask); s[:-1, :] = mask[1:, :]
    e = np.zeros_like(mask); e[:, :-1] = mask[:, 1:]
    w = np.zeros_like(mask); w[:, 1:] = mask[:, :-1]
    ne = np.zeros_like(mask); ne[1:, :-1] = mask[:-1, 1:]
    nw = np.zeros_like(mask); nw[1:, 1:] = mask[:-1, :-1]
    se = np.zeros_like(mask); se[:-1, :-1] = mask[1:, 1:]
    sw = np.zeros_like(mask); sw[:-1, 1:] = mask[1:, :-1]

    interior = np.zeros_like(mask)
    interior[1:-1, 1:-1] = True

    nn_count = n.astype(np.int8) + s.astype(np.int8) + e.astype(np.int8) + w.astype(np.int8)
    base = mask & interior & (nn_count == 2)
    # Convex corner = exactly one N/S neighbour AND one E/W neighbour AND
    # the diagonal "outside" pixel is also wall (so we sit on the outer
    # rim of a wall block and can chamfer it).
    candidate = base & (
        (n & e & ne) | (n & w & nw) | (s & e & se) | (s & w & sw)
    )
    rolls = rng.random(mask.shape) < 0.5
    mask[candidate & rolls] = False


def _maybe_add_notches(mask: np.ndarray, rng: np.random.Generator) -> None:
    """For each straight wall edge longer than 4 px, with 30% probability
    cut a single 1-deep x 2-wide indent into the wall side."""
    ts = mask.shape[0]
    if ts < 8:
        return
    _try_notch_horizontal(mask, rng, top_is_wall=True)
    _try_notch_horizontal(mask, rng, top_is_wall=False)
    _try_notch_vertical(mask, rng, left_is_wall=True)
    _try_notch_vertical(mask, rng, left_is_wall=False)


def _scan_runs_horizontal(mask: np.ndarray, y: int, top_is_wall: bool) -> list[tuple[int, int]]:
    ts = mask.shape[0]
    runs: list[tuple[int, int]] = []
    run_start: int | None = None
    for x in range(ts):
        is_edge = (mask[y, x] and not mask[y + 1, x]) if top_is_wall else (
            (not mask[y, x]) and mask[y + 1, x]
        )
        if is_edge:
            if run_start is None:
                run_start = x
        elif run_start is not None:
            runs.append((run_start, x - 1))
            run_start = None
    if run_start is not None:
        runs.append((run_start, ts - 1))
    return runs


def _try_notch_horizontal(mask: np.ndarray, rng: np.random.Generator, top_is_wall: bool) -> None:
    ts = mask.shape[0]
    for y in range(ts - 1):
        for x0, x1 in _scan_runs_horizontal(mask, y, top_is_wall):
            length = x1 - x0 + 1
            if length <= 4:
                continue
            if rng.random() >= 0.30:
                continue
            lo = x0 + 1
            hi = x1 - 2
            if hi <= lo:
                continue
            sx = int(rng.integers(lo, hi + 1))
            wall_y = y if top_is_wall else y + 1
            mask[wall_y, sx] = False
            mask[wall_y, sx + 1] = False


def _scan_runs_vertical(mask: np.ndarray, x: int, left_is_wall: bool) -> list[tuple[int, int]]:
    ts = mask.shape[0]
    runs: list[tuple[int, int]] = []
    run_start: int | None = None
    for y in range(ts):
        is_edge = (mask[y, x] and not mask[y, x + 1]) if left_is_wall else (
            (not mask[y, x]) and mask[y, x + 1]
        )
        if is_edge:
            if run_start is None:
                run_start = y
        elif run_start is not None:
            runs.append((run_start, y - 1))
            run_start = None
    if run_start is not None:
        runs.append((run_start, ts - 1))
    return runs


def _try_notch_vertical(mask: np.ndarray, rng: np.random.Generator, left_is_wall: bool) -> None:
    ts = mask.shape[0]
    for x in range(ts - 1):
        for y0, y1 in _scan_runs_vertical(mask, x, left_is_wall):
            length = y1 - y0 + 1
            if length <= 4:
                continue
            if rng.random() >= 0.30:
                continue
            lo = y0 + 1
            hi = y1 - 2
            if hi <= lo:
                continue
            sy = int(rng.integers(lo, hi + 1))
            wall_x = x if left_is_wall else x + 1
            mask[sy, wall_x] = False
            mask[sy + 1, wall_x] = False


def generate_tile_mask(role: list[str], tile_size: int, seed: int, tile_index: int) -> np.ndarray:
    """Build the wall (Region A) mask for one tile, applying seeded variations.

    Trivial tiles (full floor, full wall, isolated blob) skip variation -
    they have nothing meaningful to wobble.
    """
    mask = _build_base_wall_mask(role, tile_size)
    if not role or role == ["FULL"] or role == ["ISOLATED"]:
        return mask
    # Seeded numpy Generator so the variation passes are vectorised yet
    # still deterministic for any given (master seed, tile_index) pair.
    rng = np.random.default_rng(_stable_per_tile_seed(seed, tile_index))
    _apply_edge_wobble(mask, rng)
    _round_outer_corners(mask, rng)
    _maybe_add_notches(mask, rng)
    return mask


# -- Region C (transition) -------------------------------------------------


# Roles whose tiles are pure wall, pure floor, or have no boundary at all
# we want C to paint into. Region C is skipped on these tiles per spec.
_REGION_C_EXCLUDED_ROLES: frozenset[tuple[str, ...]] = frozenset(
    {
        (),                # FULL_FLOOR
        ("FULL",),         # FULL_WALL
        ("ISOLATED",),     # ISOLATED_WALL
    }
)


def _role_paints_region_c(role: list[str]) -> bool:
    return tuple(role) not in _REGION_C_EXCLUDED_ROLES


def _stable_per_tile_lip_seed(seed: int, tile_index: int) -> int:
    """A separate seed mix from `_stable_per_tile_seed` so the lip wobble
    stream is independent of the wall-mask wobble stream for the same
    tile. Same property: deterministic, order-free across tiles."""
    mixed = ((seed & 0xFFFFFFFF) * 1597334677) ^ (
        (tile_index + 1) * 0xC2B2AE35
    )
    return mixed & 0xFFFFFFFF


def _boundary_wall_pixels(wall_mask: np.ndarray) -> list[tuple[int, int]]:
    """Wall pixels that have at least one 4-connected floor neighbour.
    These are the seed pixels for the lip BFS - the line the user sees
    as the silhouette boundary."""
    h, w = wall_mask.shape
    floor = ~wall_mask
    pad = np.pad(floor, 1, constant_values=False)
    has_floor_n = pad[0:h, 1:w + 1]
    has_floor_s = pad[2:h + 2, 1:w + 1]
    has_floor_w = pad[1:h + 1, 0:w]
    has_floor_e = pad[1:h + 1, 2:w + 2]
    boundary = wall_mask & (has_floor_n | has_floor_s | has_floor_w | has_floor_e)
    return [(int(y), int(x)) for y, x in np.argwhere(boundary)]


def _lip_depths_constant(
    boundary_pixels: list[tuple[int, int]], depth: int,
) -> dict[tuple[int, int], int]:
    """Used by the None and Hard Border styles - every boundary pixel
    gets the same depth."""
    d = max(1, int(depth))
    return {bp: d for bp in boundary_pixels}


def _lip_depths_stone(
    boundary_pixels: list[tuple[int, int]],
    min_depth: int,
    max_depth: int,
    wobble_rate: int,
    rng: np.random.Generator,
) -> dict[tuple[int, int], int]:
    """Stone Lip depth assignment: walk the boundary in (y, x) order and
    drift the depth by ±1 with a probability tied to wobble_rate.

    Walking in (y, x) order is a simplification of "along the boundary"
    that works well for the axis-aligned edges that dominate this tile
    set. True boundary tracing would matter for diagonal silhouettes,
    which this generator doesn't produce.

    Follow Pattern is implemented as plain noise per the spec's escape
    hatch: the generator doesn't currently know what brick/block
    parameters produced the loaded texture, so true mortar alignment is
    deferred. Wobble is left at the user's chosen rate rather than
    silently slowed.
    """
    if not boundary_pixels:
        return {}
    lo = max(1, int(min_depth))
    hi = max(lo, int(max_depth))
    rate = max(1, min(6, int(wobble_rate)))
    prob_change = rate / 6.0
    depth = (lo + hi) // 2
    out: dict[tuple[int, int], int] = {}
    for bp in sorted(boundary_pixels):
        out[bp] = max(lo, min(hi, depth))
        if rng.random() < prob_change:
            delta = 1 if rng.random() < 0.5 else -1
            depth = max(lo, min(hi, depth + delta))
    return out


def _compute_lip_geometry(
    wall_mask: np.ndarray,
    depth_at_boundary: dict[tuple[int, int], int],
    max_depth: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """BFS from each boundary wall pixel into the floor side, tracking
    which boundary pixel each floor pixel is closest to (and that
    boundary pixel's lip depth). Ties on distance keep the *greater* of
    the candidate source depths, which approximates the spec's
    outer-corner rule ("use the greater of the two depths at the corner
    point itself") without needing per-axis bookkeeping.

    Inner corners use the *lesser* per spec; we accept the same
    max-tie-break here as a known approximation - the spec calls inner
    corners "the most complex case" and tolerates manual touch-up.

    Returns three (h, w) bool arrays:
      * region_c    : pixels Region C should paint over Region B
      * outermost   : pixels at chamfer distance 1 from a wall (light
                      highlight in stone lip / colour mode)
      * innermost   : pixels at the deepest extent of the lip at their
                      local point (dark shadow)
    """
    h, w = wall_mask.shape
    dist = np.full((h, w), -1, dtype=np.int32)
    src_depth = np.zeros((h, w), dtype=np.int32)
    queue: deque[tuple[int, int]] = deque()
    for (by, bx), d in depth_at_boundary.items():
        if dist[by, bx] != -1:
            continue
        dist[by, bx] = 0
        src_depth[by, bx] = d
        queue.append((by, bx))

    while queue:
        y, x = queue.popleft()
        d_here = int(dist[y, x])
        if d_here >= max_depth:
            continue
        sd_here = int(src_depth[y, x])
        new_dist = d_here + 1
        for dy_, dx_ in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy_, x + dx_
            if not (0 <= ny < h and 0 <= nx < w):
                continue
            if wall_mask[ny, nx]:
                continue
            cur = int(dist[ny, nx])
            if cur == -1:
                dist[ny, nx] = new_dist
                src_depth[ny, nx] = sd_here
                queue.append((ny, nx))
            elif cur == new_dist and sd_here > int(src_depth[ny, nx]):
                src_depth[ny, nx] = sd_here

    region_c = np.zeros_like(wall_mask)
    outermost = np.zeros_like(wall_mask)
    innermost = np.zeros_like(wall_mask)
    for y in range(h):
        for x in range(w):
            if wall_mask[y, x]:
                continue
            d = int(dist[y, x])
            if d <= 0:
                continue
            cap = int(src_depth[y, x])
            if d <= cap:
                region_c[y, x] = True
                if d == 1:
                    outermost[y, x] = True
                if d == cap:
                    innermost[y, x] = True
    return region_c, outermost, innermost


def _brighten(color: Color, factor: float) -> Color:
    """Push each channel toward white by `factor` (0-1)."""
    r, g, b, a = color
    f = max(0.0, min(1.0, factor))
    return (
        min(255, int(round(r + (255 - r) * f))),
        min(255, int(round(g + (255 - g) * f))),
        min(255, int(round(b + (255 - b) * f))),
        a,
    )


def _darken(color: Color, factor: float) -> Color:
    """Scale each channel toward zero by `factor` (0-1)."""
    r, g, b, a = color
    f = max(0.0, min(1.0, factor))
    return (
        max(0, int(round(r * (1.0 - f)))),
        max(0, int(round(g * (1.0 - f)))),
        max(0, int(round(b * (1.0 - f)))),
        a,
    )


# -- Sheet generation ------------------------------------------------------


def _validate_textures(
    region_a: RegionSpec,
    region_b: RegionSpec,
    tile_size: int,
    region_c: RegionCSpec | None = None,
) -> None:
    candidates: list[tuple[str, Image.Image | None]] = [
        (region_a.name, region_a.texture),
        (region_b.name, region_b.texture),
    ]
    if region_c is not None:
        candidates.append((region_c.name, region_c.texture))
    for name, tex in candidates:
        if tex is None:
            continue
        if tex.size != (tile_size, tile_size):
            raise ValueError(
                f"Texture for region '{name}' must be exactly "
                f"{tile_size}x{tile_size}, got "
                f"{tex.width}x{tex.height}"
            )


def _region_block(region: RegionSpec, tile_size: int) -> np.ndarray:
    """Return a (ts, ts, 4) uint8 block of this region's content for one tile.

    Because tile_size == texture_size and tile origins are multiples of
    tile_size, sampling the texture at (px % tile_size, py % tile_size)
    is equivalent to a direct copy of the texture into the tile slot.
    Adjacent same-region tiles therefore line up seamlessly.
    """
    if region.texture is not None:
        return np.array(region.texture.convert("RGBA"), dtype=np.uint8)
    return np.full((tile_size, tile_size, 4), region.color, dtype=np.uint8)


def _region_c_block(region_c: RegionCSpec, tile_size: int) -> np.ndarray:
    """Same shape contract as `_region_block` but for the optional
    Region C - kept separate because the dataclass type is different."""
    if region_c.texture is not None:
        return np.array(region_c.texture.convert("RGBA"), dtype=np.uint8)
    return np.full((tile_size, tile_size, 4), region_c.color, dtype=np.uint8)


def _apply_region_c(
    tile_block: np.ndarray,
    wall_mask: np.ndarray,
    region_c: RegionCSpec,
    region_c_block: np.ndarray,
    seed: int,
    tile_index: int,
) -> None:
    """Mutate `tile_block` in place with Region C's lip overlay. Caller
    must have already filtered out non-applicable tile roles - this
    function assumes the tile has a wall/floor boundary worth painting
    into.

    Paint order on overlap: Region C base fill first (overwrites Region
    B at lip pixels), then for stone-lip the ~20% brighter highlight on
    outermost pixels (colour-mode only), then the ~30% darker shadow on
    innermost pixels (always - the shadow is what sells the depth drop).
    """
    boundary = _boundary_wall_pixels(wall_mask)
    if not boundary:
        return

    if region_c.style == TRANSITION_STYLE_STONE_LIP:
        rng = np.random.default_rng(_stable_per_tile_lip_seed(seed, tile_index))
        depths = _lip_depths_stone(
            boundary,
            region_c.min_depth,
            region_c.max_depth,
            region_c.wobble_rate,
            rng,
        )
    else:
        depths = _lip_depths_constant(boundary, region_c.depth)

    if not depths:
        return

    c_mask, outer_mask, inner_mask = _compute_lip_geometry(
        wall_mask, depths, region_c.effective_max_depth(),
    )
    if not bool(c_mask.any()):
        return

    tile_block[c_mask] = region_c_block[c_mask]

    if region_c.style != TRANSITION_STYLE_STONE_LIP:
        return

    if region_c.fill_mode == "color":
        highlight = np.array(_brighten(region_c.color, 0.20), dtype=np.uint8)
        active_outer = outer_mask & c_mask
        if bool(active_outer.any()):
            tile_block[active_outer] = highlight

    shadow = np.array(_darken(region_c.color, 0.30), dtype=np.uint8)
    active_inner = inner_mask & c_mask
    if bool(active_inner.any()):
        tile_block[active_inner] = shadow


def generate_tileset_sheet(
    *,
    tile_size: int,
    region_a: RegionSpec,
    region_b: RegionSpec,
    seed: int,
    transparent_background: bool = True,
    grid_overlay: bool = False,
    region_c: RegionCSpec | None = None,
) -> Image.Image:
    """Render the full 8x6 sheet (47 tiles + 1 empty slot) as a flat RGBA
    PIL image. See module docstring for the full pipeline.

    `region_c` is optional. When supplied, it overlays Region B at the
    silhouette boundary of every edge / corner / junction tile (full
    wall, full floor, isolated wall, and the empty slot are skipped).
    Region C never overwrites Region A pixels.
    """
    if tile_size not in SUPPORTED_TILE_SIZES:
        raise ValueError(
            f"tile_size must be one of {SUPPORTED_TILE_SIZES}, got {tile_size}"
        )
    _validate_textures(region_a, region_b, tile_size, region_c)

    ts = tile_size
    sheet_w = SHEET_COLS * ts
    sheet_h = SHEET_ROWS * ts
    bg = (0, 0, 0, 0) if transparent_background else (0x1a, 0x1a, 0x1a, 0xff)
    sheet_arr = np.full((sheet_h, sheet_w, 4), bg, dtype=np.uint8)

    block_a = _region_block(region_a, ts)
    block_b = _region_block(region_b, ts)
    block_c = _region_c_block(region_c, ts) if region_c is not None else None

    for tile_index, role in enumerate(TILE_ROLES):
        col = tile_index % SHEET_COLS
        row = tile_index // SHEET_COLS
        x0, y0 = col * ts, row * ts
        wall_mask = generate_tile_mask(role, ts, seed, tile_index)
        # Vectorised per-tile fill: pick block_a where the wall mask is True,
        # block_b otherwise. Both blocks are (ts, ts, 4) uint8.
        tile_block = np.where(wall_mask[..., None], block_a, block_b)
        if region_c is not None and block_c is not None and _role_paints_region_c(role):
            _apply_region_c(
                tile_block, wall_mask, region_c, block_c, seed, tile_index,
            )
        sheet_arr[y0:y0 + ts, x0:x0 + ts] = tile_block

    sheet = Image.fromarray(sheet_arr, mode="RGBA")

    if grid_overlay:
        # Bake a thin grid overlay on top of the rendered tiles. Drawn last
        # so it sits over both colour and texture fills.
        line_color = (40, 40, 40, 220)
        draw = ImageDraw.Draw(sheet)
        for c in range(1, SHEET_COLS):
            draw.line([(c * ts, 0), (c * ts, sheet_h)], fill=line_color)
        for r in range(1, SHEET_ROWS):
            draw.line([(0, r * ts), (sheet_w, r * ts)], fill=line_color)
        draw.rectangle([(0, 0), (sheet_w - 1, sheet_h - 1)], outline=line_color)

    return sheet


def default_filename(tile_size: int, seed: int) -> str:
    return f"tileset_template_{tile_size}px_seed{seed & 0xFFFFFFFF}.png"
