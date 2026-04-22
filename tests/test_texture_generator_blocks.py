import numpy as np

from src.core.texture_generator import (
    BlocksParams,
    BrickParams,
    TEXTURE_TYPES,
    _apply_crack,
    _apply_dings,
    _build_face_idx_map,
    generate_brick_texture,
)


RAMP = [
    (255, 255, 255, 255),
    (220, 220, 220, 255),
    (190, 190, 190, 255),
    (160, 160, 160, 255),
    (130, 130, 130, 255),
    (100, 100, 100, 255),
    (70, 70, 70, 255),
    (40, 40, 40, 255),
]


def _rgba(pixel: np.ndarray) -> tuple[int, int, int, int]:
    return tuple(int(v) for v in pixel)


def test_blocks_cracked_type_removed() -> None:
    assert "Blocks Cracked" not in TEXTURE_TYPES


def test_soft_corners_do_not_overpaint_truncated_highlight_faces() -> None:
    params = BrickParams(
        brick_width=15,
        brick_height=7,
        mortar=1,
        row_offset=0.0,
        color_variance=0,
        bevel=True,
        highlight_length=10,
        soft_corners=True,
    )
    img = generate_brick_texture(
        width=16,
        height=8,
        ramp_colors=RAMP,
        params=params,
        seed=1,
    )
    pixels = np.array(img)

    # With a 10% highlight only the top-left corner is lit. The pixel
    # approaching the top-right corner is face and must remain face even
    # when the corner-gradient pass runs.
    assert _rgba(pixels[0, 13]) == RAMP[3]


def test_soft_corners_turn_t_junction_armpits_into_mortar() -> None:
    params = BrickParams(
        brick_width=15,
        brick_height=7,
        mortar=1,
        row_offset=0.5,
        color_variance=0,
        bevel=True,
        highlight_length=100,
        soft_corners=True,
    )
    img = generate_brick_texture(
        width=32,
        height=16,
        ramp_colors=RAMP,
        params=params,
        seed=1,
    )
    pixels = np.array(img)

    # Row 1 is offset by half a block, so the vertical mortar stub at
    # x=7 meets the horizontal seams above and below it. Every bevel
    # corner flanking those T endpoints must collapse to exact mortar,
    # including the lower-left shadow bevel that previously stayed as a
    # softened shadow.
    assert _rgba(pixels[8, 6]) == RAMP[-1]
    assert _rgba(pixels[8, 8]) == RAMP[-1]
    assert _rgba(pixels[14, 6]) == RAMP[-1]
    assert _rgba(pixels[14, 8]) == RAMP[-1]

    # The adjacent bevel pixels should still form the intended soften-
    # ing gradient into those mortar corners.
    assert _rgba(pixels[8, 5]) == RAMP[2]
    assert _rgba(pixels[9, 6]) == RAMP[5]
    assert _rgba(pixels[9, 8]) == RAMP[2]
    assert _rgba(pixels[13, 6]) == RAMP[5]
    assert _rgba(pixels[13, 8]) == RAMP[5]
    assert _rgba(pixels[14, 5]) == RAMP[5]
    assert _rgba(pixels[14, 9]) == RAMP[5]

    # The first face pixel inside each softened corner should also be
    # darkened to extend the rounded transition into the block body.
    assert _rgba(pixels[9, 5]) == RAMP[5]
    assert _rgba(pixels[9, 9]) == RAMP[5]
    assert _rgba(pixels[13, 5]) == RAMP[5]
    assert _rgba(pixels[13, 9]) == RAMP[5]


def test_soft_corners_clamp_darker_face_inner_corner_to_shadow_stop() -> None:
    params = BrickParams(
        brick_width=15,
        brick_height=7,
        mortar=1,
        row_offset=0.5,
        color_variance=2,
        bevel=True,
        highlight_length=100,
        soft_corners=True,
    )
    img = generate_brick_texture(
        width=32,
        height=32,
        ramp_colors=RAMP,
        params=params,
        seed=1,
    )
    pixels = np.array(img)

    # This block lands on face stop 4 (130). Its inner-corner face
    # pixels should darken two stops, but clamp at the bevel-shadow
    # stop rather than falling all the way to mortar.
    assert _rgba(pixels[25, 10]) == RAMP[6]
    assert _rgba(pixels[25, 22]) == RAMP[6]
    assert _rgba(pixels[29, 10]) == RAMP[6]
    assert _rgba(pixels[29, 22]) == RAMP[6]


def test_surface_dings_stay_on_face_pixels_and_use_face_derived_gradient() -> None:
    params = BlocksParams(
        brick_width=15,
        brick_height=7,
        mortar=1,
        row_offset=0.0,
        color_variance=0,
        bevel=True,
        highlight_length=100,
        soft_corners=False,
        surface_dings=True,
        ding_amount=100,
        cracks=False,
    )
    base = np.array(
        generate_brick_texture(
            width=16,
            height=8,
            ramp_colors=RAMP,
            params=params.to_brick_params(),
            seed=1,
        )
    )
    face_idx_map = _build_face_idx_map(16, 8, params.to_brick_params(), 1, len(RAMP))
    ramp_idx = {color: idx for idx, color in enumerate(RAMP)}

    found_gradient = False
    for seed in range(128):
        out = base.copy()
        _apply_dings(
            out,
            0,
            0,
            15,
            7,
            seed,
            0,
            0,
            RAMP,
            face_idx_map,
            params.ding_amount,
        )

        changed = [
            (y, x)
            for y in range(out.shape[0])
            for x in range(out.shape[1])
            if _rgba(out[y, x]) != _rgba(base[y, x])
        ]
        colors = {_rgba(out[y, x]) for y, x in changed}
        if changed and len(colors) >= 2:
            found_gradient = True
            break

    assert found_gradient
    assert all(face_idx_map[y, x] >= 0 for y, x in changed)
    assert all(ramp_idx[_rgba(out[y, x])] > ramp_idx[_rgba(base[y, x])] for y, x in changed)
    assert all(ramp_idx[_rgba(out[y, x])] <= len(RAMP) - 2 for y, x in changed)


def test_cracks_scale_with_amount_anchor_to_one_seam_and_stay_vertical() -> None:
    params = BlocksParams(
        brick_width=15,
        brick_height=7,
        mortar=1,
        row_offset=0.0,
        color_variance=0,
        bevel=True,
        highlight_length=100,
        soft_corners=False,
        surface_dings=False,
        cracks=True,
        crack_amount=100,
    )
    is_mortar = np.ones((8, 16), dtype=bool)
    is_mortar[0:7, 0:15] = False

    face_idx_map = np.full((8, 16), -1, dtype=np.int16)
    face_idx_map[1:6, 1:14] = 5
    is_bevel = (~is_mortar) & (face_idx_map < 0)

    base = np.empty((8, 16, 4), dtype=np.uint8)
    base[:] = np.array(RAMP[-1], dtype=np.uint8)
    base[0:7, 0:15] = np.array(RAMP[6], dtype=np.uint8)
    base[1:6, 1:14] = np.array(RAMP[5], dtype=np.uint8)

    no_crack = base.copy()
    no_crack_pixels: set[tuple[int, int]] = set()
    _apply_crack(
        no_crack,
        0,
        0,
        15,
        7,
        0,
        0,
        0,
        RAMP,
        0,
        bevel=True,
        is_mortar=is_mortar,
        face_idx_map=face_idx_map,
        crack_record=no_crack_pixels,
    )
    assert not no_crack_pixels
    assert np.array_equal(no_crack, base)

    found = 0
    seen_top = False
    seen_bottom = False
    died_out = False
    for seed in range(500):
        out = base.copy()
        crack_pixels: set[tuple[int, int]] = set()
        _apply_crack(
            out,
            0,
            0,
            15,
            7,
            seed,
            0,
            0,
            RAMP,
            params.crack_amount,
            bevel=True,
            is_mortar=is_mortar,
            face_idx_map=face_idx_map,
            crack_record=crack_pixels,
        )
        if not crack_pixels:
            continue

        found += 1
        ys = [y for y, _x in crack_pixels]
        xs = [x for _y, x in crack_pixels]
        vertical_span = max(ys) - min(ys) + 1
        horizontal_span = max(xs) - min(xs) + 1
        row_widths = {
            y: sum(1 for yy, _x in crack_pixels if yy == y)
            for y in set(ys)
        }

        anchored_top = min(ys) == 0
        anchored_bottom = max(ys) == 6
        assert anchored_top or anchored_bottom
        assert vertical_span >= 2
        assert vertical_span >= horizontal_span
        assert min(xs) >= 1
        assert max(xs) <= 13
        assert max(row_widths.values()) <= 2

        seen_top = seen_top or anchored_top
        seen_bottom = seen_bottom or anchored_bottom

        if anchored_top and max(ys) < 6:
            died_out = True
        if anchored_bottom and min(ys) > 0:
            died_out = True

    assert found > 0
    assert seen_top
    assert seen_bottom
    assert died_out

    # Find a visible crack for fringe verification.
    out = base.copy()
    crack_pixels: set[tuple[int, int]] = set()
    for seed in range(500):
        out = base.copy()
        crack_pixels.clear()
        _apply_crack(
            out,
            0,
            0,
            15,
            7,
            seed,
            0,
            0,
            RAMP,
            params.crack_amount,
            bevel=True,
            is_mortar=is_mortar,
            face_idx_map=face_idx_map,
            crack_record=crack_pixels,
        )
        if crack_pixels:
            break
    assert crack_pixels
    assert any(is_bevel[y, x] for y, x in crack_pixels)

    fringe = [
        (y, x)
        for y in range(out.shape[0])
        for x in range(out.shape[1])
        if _rgba(out[y, x]) != _rgba(base[y, x]) and (y, x) not in crack_pixels
    ]
    assert fringe
    assert all(_rgba(out[y, x]) == RAMP[-2] for y, x in fringe)


def test_through_cracks_can_have_small_midline_gaps() -> None:
    params = BlocksParams(
        brick_width=15,
        brick_height=11,
        mortar=1,
        row_offset=0.0,
        color_variance=0,
        bevel=True,
        highlight_length=100,
        soft_corners=False,
        surface_dings=False,
        cracks=True,
        crack_amount=100,
    )
    is_mortar = np.ones((12, 16), dtype=bool)
    is_mortar[0:11, 0:15] = False

    face_idx_map = np.full((12, 16), -1, dtype=np.int16)
    face_idx_map[1:10, 1:14] = 5

    base = np.empty((12, 16, 4), dtype=np.uint8)
    base[:] = np.array(RAMP[-1], dtype=np.uint8)
    base[0:11, 0:15] = np.array(RAMP[6], dtype=np.uint8)
    base[1:10, 1:14] = np.array(RAMP[5], dtype=np.uint8)

    found_gap = False
    for seed in range(4000):
        out = base.copy()
        crack_pixels: set[tuple[int, int]] = set()
        gap_pixels: set[tuple[int, int]] = set()
        _apply_crack(
            out,
            0,
            0,
            15,
            11,
            seed,
            0,
            0,
            RAMP,
            params.crack_amount,
            bevel=True,
            is_mortar=is_mortar,
            face_idx_map=face_idx_map,
            crack_record=crack_pixels,
            gap_record=gap_pixels,
        )
        if not gap_pixels:
            continue

        found_gap = True
        assert 1 <= len(gap_pixels) <= 4
        assert all((y, x) not in crack_pixels for y, x in gap_pixels)
        assert all(_rgba(out[y, x]) == _rgba(base[y, x]) for y, x in gap_pixels)
        assert all(2 <= y <= 8 for y, _x in gap_pixels)
        break

    assert found_gap
