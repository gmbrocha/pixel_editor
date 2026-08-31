import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from PIL import Image
import numpy as np
import os
import subprocess
import sys
import threading


def compute_tile_ranges(total_px, grid, start_border, end_border, inside):
    tile_space = total_px - start_border - end_border - (grid - 1) * inside
    ranges, pos = [], start_border
    for _ in range(grid):
        s = round(pos)
        e = round(pos + tile_space / grid) - 1
        ranges.append((s, e))
        pos += tile_space / grid + inside
    return ranges


def detect_grid(image_path):
    """Analyze an image to auto-detect grid line widths and tile count.

    Returns a dict with keys: grid, top, bottom, left, right, inside, or None on failure.
    Grid lines are detected as rows/columns with low pixel variance (uniform color).
    """
    img = Image.open(image_path).convert("RGB")
    arr = np.array(img, dtype=np.float32)
    gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    h, w = gray.shape

    def find_runs(is_grid):
        runs = []
        i = 0
        while i < len(is_grid):
            val = is_grid[i]
            j = i
            while j < len(is_grid) and is_grid[j] == val:
                j += 1
            runs.append((i, j - i, bool(val)))
            i = j
        return runs

    def detect_axis(std_per_line, max_grid_width=12):
        median_std = np.median(std_per_line)
        if median_std < 1e-6:
            return None
        threshold = median_std * 0.25
        is_grid = std_per_line < threshold
        runs = find_runs(is_grid)

        if len(runs) < 3:
            return None

        # Reclassify low-variance runs that are too wide to be grid lines
        runs = [(s, l, is_line and l <= max_grid_width) for s, l, is_line in runs]
        # Merge adjacent content runs that resulted from reclassification
        merged = [runs[0]]
        for s, l, is_line in runs[1:]:
            prev_s, prev_l, prev_is = merged[-1]
            if not is_line and not prev_is:
                merged[-1] = (prev_s, prev_l + l, False)
            else:
                merged.append((s, l, is_line))
        runs = merged

        if len(runs) < 3:
            return None

        content_runs = [r for r in runs if not r[2]]
        if len(content_runs) < 2:
            return None

        start_border = runs[0][1] if runs[0][2] else 0
        end_border = runs[-1][1] if runs[-1][2] else 0

        all_grid = [r for r in runs if r[2]]
        inner = all_grid[:]
        if start_border > 0 and inner:
            inner = inner[1:]
        if end_border > 0 and inner:
            inner = inner[:-1]

        inside = int(round(np.mean([length for _, length, _ in inner]))) if inner else 0

        return {
            "start_border": start_border,
            "end_border": end_border,
            "inside": inside,
            "n_tiles": len(content_runs),
        }

    row_std = np.array([gray[y, :].std() for y in range(h)])
    col_std = np.array([gray[:, x].std() for x in range(w)])

    h_result = detect_axis(row_std)
    v_result = detect_axis(col_std)

    if h_result is None or v_result is None:
        return None

    n_tiles = max(h_result["n_tiles"], v_result["n_tiles"])

    return {
        "grid": n_tiles,
        "top": h_result["start_border"],
        "bottom": h_result["end_border"],
        "left": v_result["start_border"],
        "right": v_result["end_border"],
        "inside": max(h_result["inside"], v_result["inside"]),
    }


def quantize_image(img, max_colors):
    """Reduce to max_colors discrete colors via median cut, preserving alpha."""
    if max_colors <= 0:
        return img
    if img.mode == "RGBA":
        alpha = img.getchannel("A")
        q = img.convert("RGB").quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
        result = q.convert("RGB").convert("RGBA")
        result.putalpha(alpha)
        return result
    q = img.convert("RGB").quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
    return q.convert("RGB")


def darken_joints(img, threshold=30, darken_pct=20):
    """Detect thin 1-2px edges via Sobel and darken them."""
    if darken_pct <= 0:
        return img
    arr = np.array(img, dtype=np.float32)
    rgb = arr[:, :, :3] if arr.ndim == 3 else arr
    gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]

    padded = np.pad(gray, 1, mode="edge")
    # Sobel X kernel: [[-1,0,1],[-2,0,2],[-1,0,1]]
    sx = (
        -padded[:-2, :-2] + padded[:-2, 2:]
        - 2 * padded[1:-1, :-2] + 2 * padded[1:-1, 2:]
        - padded[2:, :-2] + padded[2:, 2:]
    )
    # Sobel Y kernel: [[-1,-2,-1],[0,0,0],[1,2,1]]
    sy = (
        -padded[:-2, :-2] - 2 * padded[:-2, 1:-1] - padded[:-2, 2:]
        + padded[2:, :-2] + 2 * padded[2:, 1:-1] + padded[2:, 2:]
    )
    mag = np.sqrt(sx * sx + sy * sy)
    mag_max = mag.max()
    if mag_max > 0:
        mag /= mag_max

    mask = mag > (threshold / 100.0)
    factor = 1.0 - darken_pct / 100.0
    result = arr.copy()
    result[:, :, 0][mask] *= factor
    result[:, :, 1][mask] *= factor
    result[:, :, 2][mask] *= factor
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8), mode=img.mode)


def _label_connected_components(mask):
    """Two-pass connected component labeling with union-find (4-connected)."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    parent = [0]

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    next_label = 1
    for y in range(h):
        for x in range(w):
            if not mask[y, x]:
                continue
            above = labels[y - 1, x] if y > 0 and mask[y - 1, x] else 0
            left = labels[y, x - 1] if x > 0 and mask[y, x - 1] else 0
            if above == 0 and left == 0:
                labels[y, x] = next_label
                parent.append(next_label)
                next_label += 1
            elif above != 0 and left == 0:
                labels[y, x] = above
            elif above == 0 and left != 0:
                labels[y, x] = left
            else:
                labels[y, x] = min(above, left)
                union(above, left)

    for y in range(h):
        for x in range(w):
            if labels[y, x]:
                labels[y, x] = find(labels[y, x])
    return labels


def remove_dark_background(tile_img, brightness_cutoff=20, min_area=50):
    """Make large contiguous near-black regions transparent per-tile."""
    if brightness_cutoff <= 0:
        return tile_img
    rgba = tile_img.convert("RGBA")
    arr = np.array(rgba)
    rgb = arr[:, :, :3].astype(np.float32)
    brightness = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    dark_mask = brightness < brightness_cutoff

    if not dark_mask.any():
        return rgba

    labels = _label_connected_components(dark_mask)
    min_thickness = 8
    removal_mask = np.zeros(dark_mask.shape, dtype=bool)
    unique_labels = np.unique(labels)
    for lbl in unique_labels:
        if lbl == 0:
            continue
        region = labels == lbl
        if region.sum() < min_area:
            continue
        ys, xs = np.where(region)
        bbox_h = ys.max() - ys.min() + 1
        bbox_w = xs.max() - xs.min() + 1
        if bbox_h < min_thickness or bbox_w < min_thickness:
            continue
        removal_mask |= region

    arr[removal_mask] = [0, 0, 0, 0]

    return Image.fromarray(arr, "RGBA")


def process_tileset(input_path, output_dir, grid, top, bottom, left, right, inside, trim,
                    max_colors=0, joint_thresh=0, joint_darken=0,
                    bg_cutoff=0, bg_min_area=50, output_prefix=None):
    img = Image.open(input_path)
    arr = np.array(img)
    W, H = img.size

    tile_cols = compute_tile_ranges(W, grid, left, right, inside)
    tile_rows = compute_tile_ranges(H, grid, top, bottom, inside)

    tiles = []
    for (y1, y2) in tile_rows:
        row = []
        for (x1, x2) in tile_cols:
            tile = Image.fromarray(arr[y1 + trim:y2 - trim + 1, x1 + trim:x2 - trim + 1])
            row.append(tile)
        tiles.append(row)

    use_alpha = bg_cutoff > 0
    base = output_prefix if output_prefix else os.path.splitext(os.path.basename(input_path))[0]

    def assemble(tiles, tile_px, resample):
        mode = "RGBA" if use_alpha else "RGB"
        out = Image.new(mode, (tile_px * grid, tile_px * grid), (0, 0, 0, 0) if use_alpha else (0, 0, 0))
        for ri, row in enumerate(tiles):
            for ci, tile in enumerate(row):
                resized = tile.convert(mode).resize((tile_px, tile_px), resample)
                if use_alpha:
                    out.paste(resized, (ci * tile_px, ri * tile_px), resized)
                else:
                    out.paste(resized, (ci * tile_px, ri * tile_px))
        return out

    def post_process(img320):
        if joint_darken > 0:
            img320 = darken_joints(img320, joint_thresh, joint_darken)
        if bg_cutoff > 0:
            img320 = remove_dark_background(img320, bg_cutoff, bg_min_area)
        if max_colors > 0:
            img320 = quantize_image(img320, max_colors)
        return img320

    # Variation A: bicubic all the way
    a320 = post_process(assemble(tiles, 32, Image.BICUBIC))
    a160 = a320.resize((160, 160), Image.BICUBIC)
    a320.save(os.path.join(output_dir, f"{base}_A_lanczos_320.png"))
    a160.save(os.path.join(output_dir, f"{base}_A_lanczos_160.png"))

    # Variation B: bicubic then nearest
    b320 = post_process(assemble(tiles, 32, Image.BICUBIC))
    b160 = b320.resize((160, 160), Image.NEAREST)
    b320.save(os.path.join(output_dir, f"{base}_B_hybrid_320.png"))
    b160.save(os.path.join(output_dir, f"{base}_B_hybrid_160.png"))

    # Baseline: nearest all the way
    c320 = post_process(assemble(tiles, 32, Image.NEAREST))
    c160 = c320.resize((160, 160), Image.NEAREST)
    c320.save(os.path.join(output_dir, f"{base}_baseline_nearest_320.png"))
    c160.save(os.path.join(output_dir, f"{base}_baseline_nearest_160.png"))


class App:
    def __init__(self, root):
        root.title("Tileset Grid Remover")
        root.resizable(False, False)

        self.files = []
        self.output_dir = tk.StringVar()

        # --- File list ---
        frame_files = ttk.LabelFrame(root, text="Input Files", padding=8)
        frame_files.pack(fill="x", padx=10, pady=(10, 4))

        self.listbox = tk.Listbox(frame_files, height=8, width=70)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frame_files, orient="vertical", command=self.listbox.yview)
        sb.pack(side="left", fill="y")
        self.listbox.config(yscrollcommand=sb.set)

        btn_frame = ttk.Frame(frame_files)
        btn_frame.pack(side="left", padx=(8, 0))
        ttk.Button(btn_frame, text="Add Files", command=self.add_files).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Remove Selected", command=self.remove_selected).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Clear All", command=self.clear_all).pack(fill="x", pady=2)

        # --- Output dir ---
        frame_out = ttk.LabelFrame(root, text="Output Folder", padding=8)
        frame_out.pack(fill="x", padx=10, pady=4)
        ttk.Entry(frame_out, textvariable=self.output_dir, width=55).pack(side="left", fill="x", expand=True)
        ttk.Button(frame_out, text="Browse", command=self.browse_output).pack(side="left", padx=(6, 0))
        ttk.Button(frame_out, text="Open", command=self.open_output).pack(side="left", padx=(4, 0))

        # --- Settings ---
        frame_cfg = ttk.LabelFrame(root, text="Grid Settings", padding=8)
        frame_cfg.pack(fill="x", padx=10, pady=4)

        self.vars = {}
        defaults = [
            ("Grid", 10), ("Top Border", 5), ("Bottom Border", 5), ("Left Border", 5),
            ("Right Border", 5), ("Inside Border", 5), ("Trim", 1), ("Max Colors", 32),
            ("Joint Thresh", 30), ("Joint Darken%", 20), ("BG Cutoff", 0), ("BG Min Area", 50),
        ]
        for i, (label, val) in enumerate(defaults):
            ttk.Label(frame_cfg, text=label).grid(row=i // 4, column=(i % 4) * 2, sticky="e", padx=(4, 2))
            v = tk.IntVar(value=val)
            ttk.Entry(frame_cfg, textvariable=v, width=5).grid(row=i // 4, column=(i % 4) * 2 + 1, padx=(0, 8))
            self.vars[label] = v

        # --- Auto Detect + Process ---
        btn_row = ttk.Frame(root)
        btn_row.pack(pady=8)
        ttk.Button(btn_row, text="Auto Detect Grid", command=self.auto_detect).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Process All", command=self.run).pack(side="left", padx=4)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(root, textvariable=self.status).pack(pady=(0, 10))

    def add_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp")])
        for p in paths:
            if p not in self.files:
                self.files.append(p)
                self.listbox.insert("end", p)

    def remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            self.files.pop(i)
            self.listbox.delete(i)

    def clear_all(self):
        self.files.clear()
        self.listbox.delete(0, "end")

    def browse_output(self):
        d = filedialog.askdirectory()
        if d:
            self.output_dir.set(d)

    def open_output(self):
        d = self.output_dir.get()
        if not d or not os.path.isdir(d):
            messagebox.showwarning("No folder", "Set a valid output folder first.")
            return
        if sys.platform == "win32":
            os.startfile(d)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])

    def auto_detect(self):
        if not self.files:
            path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp")])
            if not path:
                return
        else:
            path = self.files[0]

        self.status.set("Detecting grid...")
        try:
            result = detect_grid(path)
        except Exception as e:
            messagebox.showerror("Detection failed", str(e))
            self.status.set("Detection failed")
            return

        if result is None:
            messagebox.showwarning("Detection failed", "Could not detect grid lines in this image.")
            self.status.set("Detection failed")
            return

        self.vars["Grid"].set(result["grid"])
        self.vars["Top Border"].set(result["top"])
        self.vars["Bottom Border"].set(result["bottom"])
        self.vars["Left Border"].set(result["left"])
        self.vars["Right Border"].set(result["right"])
        self.vars["Inside Border"].set(result["inside"])

        name = os.path.basename(path)
        self.status.set(
            f"Detected from {name}: {result['grid']}x{result['grid']} grid, "
            f"borders T={result['top']} B={result['bottom']} L={result['left']} R={result['right']}, "
            f"inside={result['inside']}"
        )

    def run(self):
        if not self.files:
            messagebox.showwarning("No files", "Add at least one input file.")
            return
        out = self.output_dir.get()
        if not out or not os.path.isdir(out):
            messagebox.showwarning("No output", "Pick a valid output folder.")
            return

        g = self.vars["Grid"].get()
        t, b, l, r, ins, trim = (self.vars[k].get() for k in
            ["Top Border", "Bottom Border", "Left Border", "Right Border", "Inside Border", "Trim"])
        max_colors = self.vars["Max Colors"].get()
        jt = self.vars["Joint Thresh"].get()
        jd = self.vars["Joint Darken%"].get()
        bg_cut = self.vars["BG Cutoff"].get()
        bg_area = self.vars["BG Min Area"].get()

        files = list(self.files)
        self.status.set(f"Processing 0/{len(files)} ...")

        def work():
            for idx, f in enumerate(files, 1):
                try:
                    process_tileset(f, out, g, t, b, l, r, ins, trim,
                                    max_colors, jt, jd, bg_cut, bg_area)
                except Exception as e:
                    print(f"Error on {f}: {e}")
                root.after(0, lambda i=idx: self.status.set(f"Processing {i}/{len(files)} ..."))
            root.after(0, lambda: self.status.set(f"Done — processed {len(files)} file(s)."))
            root.after(0, lambda: messagebox.showinfo("Done", f"Processed {len(files)} file(s) to:\n{out}"))

        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
