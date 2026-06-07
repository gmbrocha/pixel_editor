from __future__ import annotations

import colorsys
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np
from PIL import Image


Point = tuple[int, int]
Rect = tuple[int, int, int, int]
Color = tuple[int, int, int, int]


@dataclass
class Layer:
    """A single image layer.

    `image` is an RGBA `PIL.Image.Image` that must match the document's
    canvas dimensions. `history` is the per-layer undo stack of prior images.
    `visible` toggles whether the layer participates in compositing.
    """

    name: str
    image: Image.Image
    visible: bool = True
    history: list[Image.Image] = field(default_factory=list)


def composite_layers(layers: Iterable[Layer]) -> Image.Image:
    """Composite layers in stack order (bottom -> top) using normal alpha
    compositing. Invisible layers are skipped. Returns a fresh RGBA image.
    """
    layer_list = [layer for layer in layers if layer.visible]
    if not layer_list:
        # Caller is responsible for ensuring at least one layer exists; if none
        # are visible we still need *some* canvas to return.
        any_layer = next(iter(layers), None)
        if any_layer is None:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        return Image.new("RGBA", any_layer.image.size, (0, 0, 0, 0))
    base = Image.new("RGBA", layer_list[0].image.size, (0, 0, 0, 0))
    for layer in layer_list:
        base.alpha_composite(layer.image.convert("RGBA"))
    return base


class PixelDocument:
    """A pixel document containing one or more stacked image layers.

    `layers` is ordered bottom-first: `layers[0]` is the bottom of the stack
    and `layers[-1]` renders on top during compositing. The Layer panel
    presents the same list reversed so the visually-topmost layer is shown at
    the top of the UI.

    Backwards-compatible facade: the legacy `image` and `image_history`
    attributes proxy to the currently active layer so all pre-existing call
    sites that read or write `document.image` keep operating on whichever
    layer the user has selected.
    """

    def __init__(
        self,
        image: Image.Image | None = None,
        name: str = "pixel_map",
        palette: list[Color] | None = None,
        *,
        layers: list[Layer] | None = None,
        active_layer_index: int = 0,
    ) -> None:
        if layers is not None and image is not None:
            raise ValueError("Pass either `image` or `layers`, not both")
        if layers is None:
            if image is None:
                raise ValueError("PixelDocument requires `image` or `layers`")
            layers = [Layer(name="Layer 1", image=image)]
        if not layers:
            raise ValueError("PixelDocument requires at least one layer")

        self.layers: list[Layer] = list(layers)
        self.active_layer_index: int = max(0, min(len(self.layers) - 1, active_layer_index))
        self.name: str = name
        self.palette: list[Color] = list(palette or [])
        self.selected_pixels: set[Point] = set()
        self.selection_rect: Rect | None = None
        self.current_color: Color = (0, 0, 0, 255)
        self.use_transparent_color: bool = False

    # --- Active-layer facade -------------------------------------------------

    @property
    def active_layer(self) -> Layer:
        return self.layers[self.active_layer_index]

    @property
    def image(self) -> Image.Image:
        """Live reference to the active layer's image. Tools read/write this
        and it stays the active layer."""
        return self.active_layer.image

    @image.setter
    def image(self, value: Image.Image) -> None:
        self.active_layer.image = value

    @property
    def image_history(self) -> list[Image.Image]:
        return self.active_layer.history

    @image_history.setter
    def image_history(self, value: list[Image.Image]) -> None:
        self.active_layer.history = value

    # --- Geometry ------------------------------------------------------------

    @property
    def width(self) -> int:
        return self.layers[0].image.width

    @property
    def height(self) -> int:
        return self.layers[0].image.height

    # --- Compositing / export -----------------------------------------------

    def composite_visible(self) -> Image.Image:
        """Flatten all visible layers (bottom -> top) into a single RGBA image."""
        return composite_layers(self.layers)

    def clone_image(self) -> Image.Image:
        """Return a copy of the active layer's image (does NOT flatten layers).

        For an export-style flattened copy use `composite_visible()`.
        """
        return self.image.copy()

    # --- Layer management ---------------------------------------------------

    def add_layer(self, name: str | None = None) -> int:
        """Insert a new fully-transparent layer directly above the active
        layer and make it active. Returns the new active index."""
        size = (self.width, self.height)
        blank = Image.new("RGBA", size, (0, 0, 0, 0))
        layer = Layer(name=name or self._next_layer_name(), image=blank)
        insert_at = self.active_layer_index + 1
        self.layers.insert(insert_at, layer)
        self.active_layer_index = insert_at
        return self.active_layer_index

    def _next_layer_name(self) -> str:
        """Pick the smallest 'Layer N' name not already in use."""
        existing = {layer.name for layer in self.layers}
        n = len(self.layers) + 1
        while f"Layer {n}" in existing:
            n += 1
        return f"Layer {n}"

    def _unique_layer_name(self, base_name: str) -> str:
        existing = {layer.name for layer in self.layers}
        if base_name not in existing:
            return base_name
        n = 2
        while f"{base_name} {n}" in existing:
            n += 1
        return f"{base_name} {n}"

    def selected_points(self) -> set[Point]:
        """Return every selected pixel clipped to the document canvas."""
        points = set(self.selected_pixels)
        if self.selection_rect is not None:
            points.update(rect_points(self.selection_rect))
        return {
            (x, y)
            for x, y in points
            if 0 <= x < self.width and 0 <= y < self.height
        }

    def copy_selection_image(self, *, compact: bool) -> Image.Image | None:
        """Copy selected pixels from the active layer into a transparent image.

        When `compact` is true, the returned image is cropped to the selected
        pixels' bounds. Otherwise it matches the full document canvas.
        """
        points = self.selected_points()
        if not points:
            return None

        if compact:
            xs = [x for x, _ in points]
            ys = [y for _, y in points]
            left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
            out = Image.new("RGBA", (right - left + 1, bottom - top + 1), (0, 0, 0, 0))
        else:
            left = top = 0
            out = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

        source = self.image.convert("RGBA")
        source_pixels = source.load()
        out_pixels = out.load()
        for x, y in points:
            out_pixels[x - left, y - top] = source_pixels[x, y]
        return out

    def copy_selection_to_new_layer(self, name: str | None = None) -> tuple[int, int] | None:
        """Create a new layer above the active layer from the selected pixels.

        The active source layer is not modified. Returns the new active layer
        index and selected pixel count, or None if nothing is selected.
        """
        points = self.selected_points()
        if not points:
            return None
        image = self.copy_selection_image(compact=False)
        if image is None:
            return None

        layer_name = name or self._unique_layer_name("Selection Copy")
        insert_at = self.active_layer_index + 1
        self.layers.insert(insert_at, Layer(name=layer_name, image=image))
        self.active_layer_index = insert_at
        return insert_at, len(points)

    def delete_layer(self, index: int) -> bool:
        """Remove the layer at `index`. Refuses to delete the last remaining
        layer. Returns True on success."""
        if not (0 <= index < len(self.layers)) or len(self.layers) <= 1:
            return False
        del self.layers[index]
        if self.active_layer_index >= len(self.layers):
            self.active_layer_index = len(self.layers) - 1
        elif self.active_layer_index > index:
            self.active_layer_index -= 1
        return True

    def move_layer(self, index: int, delta: int) -> int | None:
        """Move the layer at `index` by `delta` slots (positive = up the
        stack, i.e. toward the top of the list). Returns the new index, or
        None if no move happened."""
        if delta == 0:
            return index
        new_index = index + delta
        if not (0 <= index < len(self.layers)):
            return None
        if not (0 <= new_index < len(self.layers)):
            return None
        layer = self.layers.pop(index)
        self.layers.insert(new_index, layer)
        # Keep the active-layer pointer attached to whichever layer the user
        # was editing.
        if self.active_layer_index == index:
            self.active_layer_index = new_index
        elif index < self.active_layer_index <= new_index:
            self.active_layer_index -= 1
        elif new_index <= self.active_layer_index < index:
            self.active_layer_index += 1
        return new_index

    def set_active_layer(self, index: int) -> bool:
        if not (0 <= index < len(self.layers)):
            return False
        self.active_layer_index = index
        return True

    def rename_layer(self, index: int, new_name: str) -> bool:
        new_name = new_name.strip()
        if not new_name or not (0 <= index < len(self.layers)):
            return False
        self.layers[index].name = new_name
        return True

    def set_layer_visibility(self, index: int, visible: bool) -> bool:
        if not (0 <= index < len(self.layers)):
            return False
        self.layers[index].visible = bool(visible)
        return True

    def apply_to_all_layers(self, transform: Callable[[Image.Image], Image.Image]) -> None:
        """Apply `transform` (must be size-consistent across calls) to every
        layer's image. Used by canvas-dim-changing operations like resize,
        trim, flip, and rotate so all layers stay aligned in the same
        coordinate system."""
        new_layers: list[Image.Image] = [transform(layer.image) for layer in self.layers]
        sizes = {img.size for img in new_layers}
        if len(sizes) != 1:
            raise ValueError(
                f"apply_to_all_layers transform produced inconsistent sizes: {sizes}"
            )
        for layer, new_img in zip(self.layers, new_layers):
            layer.image = new_img
            layer.history.clear()


@dataclass(slots=True)
class ColorShift:
    hue_degrees: float = 0.0
    saturation_delta: float = 0.0
    value_delta: float = 0.0
    alpha_delta: int = 0


def create_blank_pixel_map(width: int, height: int) -> PixelDocument:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    return PixelDocument(image=image, name=f"blank_{width}x{height}")


def rect_points(rect: Rect) -> set[Point]:
    left, top, right, bottom = normalize_rect(rect)
    return {
        (x, y)
        for y in range(top, bottom + 1)
        for x in range(left, right + 1)
    }


def normalize_rect(rect: Rect) -> Rect:
    left, top, right, bottom = rect
    return (
        min(left, right),
        min(top, bottom),
        max(left, right),
        max(top, bottom),
    )


def move_rect_contents(image: Image.Image, rect: Rect, dx: int, dy: int) -> tuple[Image.Image, Rect]:
    left, top, right, bottom = normalize_rect(rect)
    width = right - left + 1
    height = bottom - top + 1

    moved = image.copy()
    chunk = image.crop((left, top, right + 1, bottom + 1))

    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            moved.putpixel((x, y), (0, 0, 0, 0))

    new_left = max(0, min(image.width - width, left + dx))
    new_top = max(0, min(image.height - height, top + dy))
    moved.alpha_composite(chunk, (new_left, new_top))
    new_rect = (
        new_left,
        new_top,
        new_left + width - 1,
        new_top + height - 1,
    )
    return moved, new_rect


def flip_image_horizontal(image: Image.Image) -> Image.Image:
    return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)


def flip_image_vertical(image: Image.Image) -> Image.Image:
    return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def rotate_image_clockwise(image: Image.Image) -> Image.Image:
    return image.transpose(Image.Transpose.ROTATE_270)


def rotate_image_counterclockwise(image: Image.Image) -> Image.Image:
    return image.transpose(Image.Transpose.ROTATE_90)


def darken_image(image: Image.Image, percent: int) -> Image.Image:
    amount = max(0, min(100, percent)) / 100.0
    factor = 1.0 - amount
    source = image.convert("RGBA")
    darkened = source.copy()

    for y in range(source.height):
        for x in range(source.width):
            red, green, blue, alpha = source.getpixel((x, y))
            if alpha == 0:
                continue
            darkened.putpixel(
                (x, y),
                (
                    int(round(red * factor)),
                    int(round(green * factor)),
                    int(round(blue * factor)),
                    alpha,
                ),
            )

    return darkened


def lighten_image(image: Image.Image, percent: int) -> Image.Image:
    amount = max(0, min(100, percent)) / 100.0
    source = image.convert("RGBA")
    lightened = source.copy()

    for y in range(source.height):
        for x in range(source.width):
            red, green, blue, alpha = source.getpixel((x, y))
            if alpha == 0:
                continue
            lightened.putpixel(
                (x, y),
                (
                    int(round(red + (255 - red) * amount)),
                    int(round(green + (255 - green) * amount)),
                    int(round(blue + (255 - blue) * amount)),
                    alpha,
                ),
            )

    return lightened


def normalize_to_black_white(image: Image.Image, black_threshold: int) -> Image.Image:
    threshold = max(0, min(255, black_threshold))
    source = image.convert("RGBA")
    normalized = source.copy()

    for y in range(source.height):
        for x in range(source.width):
            red, green, blue, alpha = source.getpixel((x, y))
            if alpha == 0:
                continue
            luma = int(round(0.299 * red + 0.587 * green + 0.114 * blue))
            normalized.putpixel(
                (x, y),
                (0, 0, 0, alpha) if luma <= threshold else (255, 255, 255, alpha),
            )

    return normalized


def replace_color(image: Image.Image, color: Color, replacement: Color) -> tuple[Image.Image, int]:
    if color[3] == 0:
        return image.convert("RGBA").copy(), 0

    source = image.convert("RGBA")
    replaced = source.copy()
    replacements = 0

    for y in range(source.height):
        for x in range(source.width):
            if source.getpixel((x, y)) != color:
                continue
            replaced.putpixel((x, y), replacement)
            replacements += 1

    return replaced, replacements


def replace_color_with_transparent(image: Image.Image, color: Color) -> tuple[Image.Image, int]:
    return replace_color(image, color, (0, 0, 0, 0))


def replace_similar_color_with_transparent(
    image: Image.Image,
    color: Color,
    tolerance: int,
) -> tuple[Image.Image, int]:
    source = image.convert("RGBA")
    arr = np.array(source)
    if color[3] == 0:
        return source.copy(), 0

    rgb = arr[..., :3].astype(np.int32)
    target = np.array(color[:3], dtype=np.int32)
    delta = rgb - target
    tolerance = max(0, min(441, int(tolerance)))
    mask = (arr[..., 3] != 0) & (np.sum(delta * delta, axis=-1) <= tolerance * tolerance)
    replaced_count = int(mask.sum())
    if replaced_count == 0:
        return source.copy(), 0

    replaced = arr.copy()
    replaced[mask] = np.array([0, 0, 0, 0], dtype=np.uint8)
    return Image.fromarray(replaced, mode="RGBA"), replaced_count


def replace_light_background_with_transparent(
    image: Image.Image,
    min_brightness: int,
    max_saturation: int,
) -> tuple[Image.Image, int]:
    source = image.convert("RGBA")
    arr = np.array(source)
    rgb = arr[..., :3].astype(np.float32)

    min_brightness = max(0, min(255, int(min_brightness)))
    max_saturation = max(0, min(255, int(max_saturation)))
    luma = (0.299 * rgb[..., 0]) + (0.587 * rgb[..., 1]) + (0.114 * rgb[..., 2])
    channel_max = rgb.max(axis=-1)
    channel_min = rgb.min(axis=-1)
    saturation = np.zeros_like(channel_max)
    nonzero = channel_max > 0
    saturation[nonzero] = ((channel_max[nonzero] - channel_min[nonzero]) / channel_max[nonzero]) * 255

    mask = (arr[..., 3] != 0) & (luma >= min_brightness) & (saturation <= max_saturation)
    replaced_count = int(mask.sum())
    if replaced_count == 0:
        return source.copy(), 0

    replaced = arr.copy()
    replaced[mask] = np.array([0, 0, 0, 0], dtype=np.uint8)
    return Image.fromarray(replaced, mode="RGBA"), replaced_count


def replace_colors(image: Image.Image, replacements: dict[Color, Color]) -> tuple[Image.Image, int]:
    source = image.convert("RGBA")
    replaced = source.copy()
    replacements_applied = 0
    normalized_map = {key: value for key, value in replacements.items() if key[3] != 0}
    if not normalized_map:
        return replaced, 0

    for y in range(source.height):
        for x in range(source.width):
            pixel = source.getpixel((x, y))
            replacement = normalized_map.get(pixel)
            if replacement is None:
                continue
            replaced.putpixel((x, y), replacement)
            replacements_applied += 1

    return replaced, replacements_applied


# Pixels with alpha below this value are treated as transparent for the purposes of
# the morphological color operations below. Matches the spec in the design doc.
_MORPH_ALPHA_THRESHOLD = 50


def _dilate_bool_3x3(mask: np.ndarray, pad_value: bool) -> np.ndarray:
    """Return the 8-connected (Chebyshev) dilation of a boolean mask.

    Out-of-bounds neighbors are treated as `pad_value`. This lets dilation
    use `False` (no source outside the canvas) while erosion uses `True`
    (out-of-bounds counts as a non-source neighbor, so edge source pixels erode).
    """
    h, w = mask.shape
    padded = np.full((h + 2, w + 2), pad_value, dtype=bool)
    padded[1:-1, 1:-1] = mask
    out = np.zeros_like(mask)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= padded[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
    return out


def dilate_color(
    image: Image.Image,
    color: Color,
    thickness: int,
    alpha_threshold: int = _MORPH_ALPHA_THRESHOLD,
) -> tuple[Image.Image, int]:
    """Thicken regions of `color` by `thickness` pixels in every direction.

    For every transparent pixel (alpha < `alpha_threshold`) within `thickness`
    pixels (Chebyshev distance, i.e. 8-neighbor) of any source-color pixel,
    fill it with `color`. Pixels that are non-transparent and not the source
    color are preserved.

    The implementation runs `thickness` independent 1-pixel passes on a fresh
    copy each iteration so growth never feeds itself within the same pass.

    Returns the new image and the number of pixels that were filled.
    """
    base = image.convert("RGBA").copy()
    if thickness <= 0:
        return base, 0
    r, g, b, a = color
    if a < alpha_threshold:
        return base, 0

    arr = np.array(base)
    target = np.array([r, g, b, a], dtype=np.uint8)
    total_filled = 0

    for _ in range(thickness):
        src_mask = np.all(arr == target, axis=-1) & (arr[..., 3] >= alpha_threshold)
        transparent_mask = arr[..., 3] < alpha_threshold
        neighbor = _dilate_bool_3x3(src_mask, pad_value=False)
        fill = neighbor & transparent_mask
        filled_count = int(fill.sum())
        if filled_count == 0:
            break
        new_arr = arr.copy()
        new_arr[fill] = target
        arr = new_arr
        total_filled += filled_count

    return Image.fromarray(arr, mode="RGBA"), total_filled


def erode_color(
    image: Image.Image,
    color: Color,
    thickness: int,
    alpha_threshold: int = _MORPH_ALPHA_THRESHOLD,
) -> tuple[Image.Image, int]:
    """Thin regions of `color` by `thickness` pixels in every direction.

    For every source-color pixel within `thickness` pixels (Chebyshev distance)
    of any pixel that is transparent (alpha < `alpha_threshold`) or a different
    color, set it to fully transparent. Out-of-canvas neighbors are treated as
    "not source" so source pixels along the image border erode inward as well.

    The implementation runs `thickness` independent 1-pixel passes on a fresh
    copy each iteration so shrinkage never feeds itself within the same pass.

    Returns the new image and the number of pixels that were cleared.
    """
    base = image.convert("RGBA").copy()
    if thickness <= 0:
        return base, 0
    r, g, b, a = color
    if a < alpha_threshold:
        return base, 0

    arr = np.array(base)
    target = np.array([r, g, b, a], dtype=np.uint8)
    transparent_pixel = np.array([0, 0, 0, 0], dtype=np.uint8)
    total_cleared = 0

    for _ in range(thickness):
        src_mask = np.all(arr == target, axis=-1) & (arr[..., 3] >= alpha_threshold)
        not_src_mask = ~src_mask
        neighbor_not_src = _dilate_bool_3x3(not_src_mask, pad_value=True)
        remove = src_mask & neighbor_not_src
        cleared_count = int(remove.sum())
        if cleared_count == 0:
            break
        new_arr = arr.copy()
        new_arr[remove] = transparent_pixel
        arr = new_arr
        total_cleared += cleared_count

    return Image.fromarray(arr, mode="RGBA"), total_cleared


def _rgb_to_hsv_arrays(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized RGB->HSV. Input: (H, W, 3) uint8. Returns (h, s, v) float32
    arrays with h in [0, 360), s and v in [0, 1]."""
    r = rgb[..., 0].astype(np.float32) / 255.0
    g = rgb[..., 1].astype(np.float32) / 255.0
    b = rgb[..., 2].astype(np.float32) / 255.0
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    diff = cmax - cmin

    h = np.zeros_like(cmax)
    nonzero = diff > 1e-12
    mask_r = (cmax == r) & nonzero
    mask_g = (cmax == g) & nonzero & ~mask_r
    mask_b = (cmax == b) & nonzero & ~mask_r & ~mask_g
    h[mask_r] = ((g[mask_r] - b[mask_r]) / diff[mask_r]) % 6.0
    h[mask_g] = (b[mask_g] - r[mask_g]) / diff[mask_g] + 2.0
    h[mask_b] = (r[mask_b] - g[mask_b]) / diff[mask_b] + 4.0
    h = (h * 60.0) % 360.0

    s = np.where(cmax > 1e-12, diff / np.maximum(cmax, 1e-12), 0.0)
    v = cmax
    return h.astype(np.float32), s.astype(np.float32), v.astype(np.float32)


def flood_erase_outside_color(
    image: Image.Image,
    seed: Point,
    boundary_color: Color,
    hue_tolerance_degrees: float = 20.0,
    min_saturation: float = 0.25,
    alpha_threshold: int = _MORPH_ALPHA_THRESHOLD,
    eight_connected: bool = True,
) -> tuple[Image.Image, int]:
    """Flood-fill from `seed` through everything that is NOT the boundary color
    and clear the visited pixels to transparent.

    A pixel counts as "boundary" (a wall) if its hue is within
    `hue_tolerance_degrees` of `boundary_color`'s hue, its saturation is at
    least `min_saturation` (0..1), and it is opaque (alpha >= alpha_threshold).

    Already-transparent pixels are passable but not "cleared again" (they were
    already transparent). The boundary color itself is preserved, and anything
    enclosed by the boundary (i.e. unreachable from the seed without crossing
    the boundary) is also preserved.

    Returns the new image and the number of pixels that were cleared
    (set to fully transparent on this pass).
    """
    base = image.convert("RGBA").copy()
    sx, sy = seed
    h_img = base.height
    w_img = base.width
    if not (0 <= sx < w_img and 0 <= sy < h_img):
        return base, 0

    arr = np.array(base)

    # HSV of the boundary color
    br, bg, bb, ba = boundary_color
    if ba < alpha_threshold:
        return base, 0
    boundary_h_arr, _, _ = _rgb_to_hsv_arrays(
        np.array([[[br, bg, bb]]], dtype=np.uint8)
    )
    boundary_hue = float(boundary_h_arr[0, 0])

    # HSV of every pixel
    hue, sat, _ = _rgb_to_hsv_arrays(arr[..., :3])
    hue_diff = np.abs(((hue - boundary_hue + 180.0) % 360.0) - 180.0)
    boundary_mask = (
        (hue_diff <= hue_tolerance_degrees)
        & (sat >= min_saturation)
        & (arr[..., 3] >= alpha_threshold)
    )

    # Cannot start the flood inside the wall.
    if boundary_mask[sy, sx]:
        return base, 0

    visited = np.zeros((h_img, w_img), dtype=bool)
    visited[sy, sx] = True
    queue: deque[tuple[int, int]] = deque()
    queue.append((sx, sy))

    if eight_connected:
        offsets = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
    else:
        offsets = ((0, -1), (-1, 0), (1, 0), (0, 1))

    # Local refs in tight loop for speed.
    bm = boundary_mask
    vs = visited
    pop = queue.popleft
    push = queue.append
    while queue:
        x, y = pop()
        for dx, dy in offsets:
            nx = x + dx
            ny = y + dy
            if 0 <= nx < w_img and 0 <= ny < h_img and not vs[ny, nx] and not bm[ny, nx]:
                vs[ny, nx] = True
                push((nx, ny))

    # Only count pixels that actually had to be cleared (had non-zero alpha).
    cleared_mask = visited & (arr[..., 3] > 0)
    cleared_count = int(cleared_mask.sum())
    if cleared_count == 0:
        return base, 0

    new_arr = arr.copy()
    new_arr[visited] = (0, 0, 0, 0)
    return Image.fromarray(new_arr, mode="RGBA"), cleared_count


def calculate_color_shift(source: Color, target: Color) -> ColorShift:
    source_h, source_s, source_v, source_a = _rgba_to_hsva(source)
    target_h, target_s, target_v, target_a = _rgba_to_hsva(target)
    return ColorShift(
        hue_degrees=_shortest_hue_delta(source_h, target_h),
        saturation_delta=target_s - source_s,
        value_delta=target_v - source_v,
        alpha_delta=target_a - source_a,
    )


def apply_color_shift(source: Color, shift: ColorShift) -> Color:
    hue, saturation, value, alpha = _rgba_to_hsva(source)
    shifted_hue = (hue + shift.hue_degrees) % 360.0
    shifted_saturation = max(0.0, min(1.0, saturation + shift.saturation_delta))
    shifted_value = max(0.0, min(1.0, value + shift.value_delta))
    shifted_alpha = max(0, min(255, alpha + shift.alpha_delta))
    return _hsva_to_rgba(shifted_hue, shifted_saturation, shifted_value, shifted_alpha)


def calculate_ramp_shifts(ramp: list[Color]) -> list[ColorShift]:
    if len(ramp) < 2:
        return []
    return [
        calculate_color_shift(ramp[index], ramp[index + 1])
        for index in range(len(ramp) - 1)
    ]


def apply_ramp_shifts(base: Color, shifts: list[ColorShift]) -> list[Color]:
    ramp = [base]
    current = base
    for shift in shifts:
        current = apply_color_shift(current, shift)
        ramp.append(current)
    return ramp


def _rgba_to_hsva(color: Color) -> tuple[float, float, float, int]:
    red, green, blue, alpha = color
    hue, saturation, value = colorsys.rgb_to_hsv(red / 255.0, green / 255.0, blue / 255.0)
    return (hue * 360.0, saturation, value, alpha)


def _hsva_to_rgba(hue_degrees: float, saturation: float, value: float, alpha: int) -> Color:
    red, green, blue = colorsys.hsv_to_rgb(
        (hue_degrees % 360.0) / 360.0,
        max(0.0, min(1.0, saturation)),
        max(0.0, min(1.0, value)),
    )
    return (
        int(round(red * 255)),
        int(round(green * 255)),
        int(round(blue * 255)),
        max(0, min(255, int(alpha))),
    )


def _shortest_hue_delta(start_hue: float, end_hue: float) -> float:
    return ((end_hue - start_hue + 180.0) % 360.0) - 180.0


def push_image_history(document: PixelDocument, max_entries: int = 20) -> None:
    document.image_history.append(document.image.copy())
    if len(document.image_history) > max_entries:
        document.image_history = document.image_history[-max_entries:]


def undo_image_history(document: PixelDocument) -> bool:
    if not document.image_history:
        return False
    document.image = document.image_history.pop()
    return True
