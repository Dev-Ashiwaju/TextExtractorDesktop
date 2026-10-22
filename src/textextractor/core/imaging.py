"""Image loading and transformation (Pillow). The original file is never modified."""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_DIMENSION = 2800            # longest side of the working copy
MAX_SOURCE_PIXELS = 300_000_000  # refuse absurdly large files instead of exhausting memory

ImageSource = Union[str, Path, bytes, bytearray]


class ImageLoadError(Exception):
    """kind is one of: 'inaccessible', 'corrupted', 'too_large'."""

    MESSAGES = {
        "inaccessible": "This file can't be opened. It may have been moved or deleted, or you may not have permission to read it.",
        "corrupted": "This file isn't a readable image, or it is corrupted.",
        "too_large": "This image is too large to process on this computer. Try a smaller image.",
    }

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind

    @property
    def user_message(self) -> str:
        return self.MESSAGES[self.kind]


@dataclass(frozen=True)
class PixelRect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class CropRect:
    """Crop area as fractions (0..1) of the image, independent of resolution."""
    left: float = 0.0
    top: float = 0.0
    right: float = 1.0
    bottom: float = 1.0

    MIN_SIZE = 0.03

    @property
    def is_full(self) -> bool:
        return self.left <= 0 and self.top <= 0 and self.right >= 1 and self.bottom >= 1

    def to_pixels(self, width: int, height: int) -> PixelRect:
        if width <= 0 or height <= 0:
            raise ValueError("Image must have a positive size")
        clamp = lambda v, lo, hi: max(lo, min(hi, v))  # noqa: E731
        x = clamp(round(clamp(self.left, 0.0, 1.0) * width), 0, width - 1)
        y = clamp(round(clamp(self.top, 0.0, 1.0) * height), 0, height - 1)
        r = clamp(round(clamp(self.right, 0.0, 1.0) * width), x + 1, width)
        b = clamp(round(clamp(self.bottom, 0.0, 1.0) * height), y + 1, height)
        return PixelRect(x, y, r - x, b - y)


def load_image(source: ImageSource) -> Image.Image:
    """Decode into an RGB, EXIF-corrected, down-scaled working copy.

    Raises ImageLoadError('inaccessible' | 'corrupted' | 'too_large').
    """
    try:
        if isinstance(source, (bytes, bytearray)):
            fp: io.IOBase = io.BytesIO(bytes(source))
        else:
            fp = open(source, "rb")
    except (OSError, ValueError) as e:  # FileNotFoundError, PermissionError, IsADirectoryError...
        raise ImageLoadError("inaccessible") from e

    try:
        with fp, Image.open(fp) as im:
            if im.width * im.height > MAX_SOURCE_PIXELS:
                raise ImageLoadError("too_large")
            if im.format == "JPEG":
                im.draft("RGB", (MAX_DIMENSION, MAX_DIMENSION))  # decode at reduced size: faster, less memory
            im.load()
            im = ImageOps.exif_transpose(im)
            im = _flatten_to_rgb(im)
    except ImageLoadError:
        raise
    except MemoryError as e:
        raise ImageLoadError("too_large") from e
    except Image.DecompressionBombError as e:
        raise ImageLoadError("too_large") from e
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as e:
        raise ImageLoadError("corrupted") from e

    if max(im.size) > MAX_DIMENSION:
        im.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
    return im


def _flatten_to_rgb(im: Image.Image) -> Image.Image:
    """Transparent PNG screenshots must be composited on white, otherwise text can turn into black-on-black."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return im.convert("RGB")


def rotate(image: Image.Image, degrees_clockwise: int) -> Image.Image:
    """Returns a rotated copy (positive = clockwise). The source is untouched."""
    d = degrees_clockwise % 360
    if d == 0:
        return image
    return image.rotate(-d, expand=True, resample=Image.Resampling.BICUBIC)


def crop(image: Image.Image, rect: CropRect) -> Image.Image:
    if rect.is_full:
        return image
    p = rect.to_pixels(*image.size)
    return image.crop((p.x, p.y, p.x + p.width, p.y + p.height))
