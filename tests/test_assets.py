from PIL import Image

from src.core.assets import SavedAsset, build_tilesheet


def test_build_tilesheet_places_assets_in_grid():
    first = SavedAsset(name="one", image=Image.new("RGBA", (4, 4), (255, 0, 0, 255)))
    second = SavedAsset(name="two", image=Image.new("RGBA", (4, 4), (0, 255, 0, 255)))
    third = SavedAsset(name="three", image=Image.new("RGBA", (4, 4), (0, 0, 255, 255)))

    tilesheet = build_tilesheet([first, second, third], columns=2, padding=1)

    assert tilesheet.size == (9, 9)
    assert tilesheet.getpixel((0, 0)) == (255, 0, 0, 255)
    assert tilesheet.getpixel((5, 0)) == (0, 255, 0, 255)
    assert tilesheet.getpixel((0, 5)) == (0, 0, 255, 255)
