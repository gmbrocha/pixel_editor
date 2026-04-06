from PIL import Image

from src.core.animation_sheet import (
    create_blank_sheet,
    extract_frame,
    frame_count_for_sheet,
    sheet_cols_rows,
)


def test_create_blank_sheet_dimensions() -> None:
    img = create_blank_sheet(8, 8, 3, 2)
    assert img.size == (24, 16)


def test_sheet_cols_rows_and_extract() -> None:
    img = Image.new("RGBA", (32, 16), (255, 0, 0, 255))
    assert sheet_cols_rows(img, 8, 8) == (4, 2)
    assert frame_count_for_sheet(img, 8, 8) == 8
    fr = extract_frame(img, 8, 8, 0)
    assert fr is not None and fr.size == (8, 8)
