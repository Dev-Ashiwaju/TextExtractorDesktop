import io

import pytest
from PIL import Image

from textextractor.core import imaging
from textextractor.core.imaging import CropRect, ImageLoadError, crop, load_image, rotate


def test_crop_rect_pixels():
    assert CropRect().to_pixels(1000, 500) == imaging.PixelRect(0, 0, 1000, 500)
    assert CropRect().is_full
    p = CropRect(0.25, 0.1, 0.75, 0.9).to_pixels(1000, 1000)
    assert (p.x, p.y, p.width, p.height) == (250, 100, 500, 800)


def test_degenerate_and_out_of_range_crops_stay_valid():
    p = CropRect(1, 1, 1, 1).to_pixels(10, 10)
    assert p.width >= 1 and p.height >= 1 and p.x + p.width <= 10 and p.y + p.height <= 10
    p = CropRect(-1, -1, 2, 2).to_pixels(80, 40)
    assert (p.width, p.height) == (80, 40)
    with pytest.raises(ValueError):
        CropRect().to_pixels(0, 10)


def test_rotate_and_crop_return_copies_and_swap_dimensions():
    img = Image.new("RGB", (200, 100), "white")
    assert rotate(img, 90).size == (100, 200)
    assert rotate(img, -90).size == (100, 200)
    assert rotate(img, 180).size == (200, 100)
    assert rotate(img, 360) is img
    assert img.size == (200, 100)
    assert crop(img, CropRect(0, 0, 0.5, 0.5)).size == (100, 50)
    assert crop(img, CropRect()) is img


def test_load_png_bytes_and_path(tmp_path):
    img = Image.new("RGB", (64, 32), "red")
    p = tmp_path / "a.png"
    img.save(p)
    assert load_image(p).size == (64, 32)
    assert load_image(str(p)).mode == "RGB"
    assert load_image(p.read_bytes()).size == (64, 32)


def test_large_image_is_downscaled_and_file_untouched(tmp_path):
    p = tmp_path / "big.png"
    Image.new("RGB", (6000, 3000), "gray").save(p)
    before = p.read_bytes()
    out = load_image(p)
    assert max(out.size) <= imaging.MAX_DIMENSION
    assert p.read_bytes() == before


def test_transparent_png_is_flattened_on_white(tmp_path):
    p = tmp_path / "t.png"
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(p)
    assert load_image(p).getpixel((5, 5)) == (255, 255, 255)


def test_exif_orientation_is_applied(tmp_path):
    img = Image.new("RGB", (200, 100), "white")
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 CW to display
    p = tmp_path / "o.jpg"
    img.save(p, exif=exif)
    assert load_image(p).size == (100, 200)


def test_error_kinds(tmp_path):
    with pytest.raises(ImageLoadError) as e:
        load_image(tmp_path / "missing.png")
    assert e.value.kind == "inaccessible"
    with pytest.raises(ImageLoadError) as e:
        load_image(tmp_path)  # a directory
    assert e.value.kind == "inaccessible"
    bad = tmp_path / "bad.png"
    bad.write_bytes(bytes(range(256)) * 8)
    with pytest.raises(ImageLoadError) as e:
        load_image(bad)
    assert e.value.kind == "corrupted"
    with pytest.raises(ImageLoadError) as e:
        load_image(b"")
    assert e.value.kind == "corrupted"
    truncated = io.BytesIO()
    Image.new("RGB", (300, 300), "blue").save(truncated, "PNG")
    with pytest.raises(ImageLoadError):
        load_image(truncated.getvalue()[:100])


def test_oversized_source_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(imaging, "MAX_SOURCE_PIXELS", 100)
    p = tmp_path / "x.png"
    Image.new("RGB", (50, 50)).save(p)
    with pytest.raises(ImageLoadError) as e:
        load_image(p)
    assert e.value.kind == "too_large"
    assert e.value.user_message
