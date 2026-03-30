from __future__ import annotations

from PySide6.QtGui import QImage, QPixmap
from PIL import Image


def pil_image_to_qimage(image: Image.Image) -> QImage:
    rgba_image = image.convert("RGBA")
    data = rgba_image.tobytes("raw", "RGBA")
    qimage = QImage(
        data,
        rgba_image.width,
        rgba_image.height,
        rgba_image.width * 4,
        QImage.Format.Format_RGBA8888,
    )
    return qimage.copy()


def pil_image_to_qpixmap(image: Image.Image) -> QPixmap:
    return QPixmap.fromImage(pil_image_to_qimage(image))
