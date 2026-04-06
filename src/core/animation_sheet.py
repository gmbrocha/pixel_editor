from __future__ import annotations

from PIL import Image


def create_blank_sheet(frame_w: int, frame_h: int, cols: int, rows: int) -> Image.Image:
    w = max(1, frame_w) * max(1, cols)
    h = max(1, frame_h) * max(1, rows)
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def sheet_cols_rows(sheet: Image.Image, frame_w: int, frame_h: int) -> tuple[int, int]:
    if frame_w < 1 or frame_h < 1:
        return 0, 0
    cols = sheet.width // frame_w
    rows = sheet.height // frame_h
    return max(0, cols), max(0, rows)


def frame_count_for_sheet(sheet: Image.Image, frame_w: int, frame_h: int) -> int:
    cols, rows = sheet_cols_rows(sheet, frame_w, frame_h)
    return cols * rows


def extract_frame(
    sheet: Image.Image,
    frame_w: int,
    frame_h: int,
    index: int,
) -> Image.Image | None:
    cols, total_rows = sheet_cols_rows(sheet, frame_w, frame_h)
    if index < 0 or cols < 1 or total_rows < 1 or frame_w < 1 or frame_h < 1:
        return None
    row = index // cols
    col = index % cols
    if row >= total_rows or col >= cols:
        return None
    left = col * frame_w
    top = row * frame_h
    if left + frame_w > sheet.width or top + frame_h > sheet.height:
        return None
    return sheet.crop((left, top, left + frame_w, top + frame_h)).copy()


def average_cell_rgba(sheet: Image.Image, frame_w: int, frame_h: int, col: int, row: int) -> tuple[int, int, int, int]:
    left = col * frame_w
    top = row * frame_h
    chunk = sheet.crop((left, top, min(left + frame_w, sheet.width), min(top + frame_h, sheet.height)))
    rgba = chunk.convert("RGBA")
    if rgba.width == 0 or rgba.height == 0:
        return 0, 0, 0, 0
    r = g = b = a = 0
    n = 0
    for y in range(rgba.height):
        for x in range(rgba.width):
            px = rgba.getpixel((x, y))
            r += px[0]
            g += px[1]
            b += px[2]
            a += px[3]
            n += 1
    if n == 0:
        return 0, 0, 0, 0
    return (r // n, g // n, b // n, a // n)
