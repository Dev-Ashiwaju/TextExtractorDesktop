"""Generates app icons: src/textextractor/assets/icon.png, packaging/icon.ico, packaging/icon.icns.
Usage: python scripts/make_icons.py   (requires Pillow)"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def render(size: int = 1024) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    # vertical indigo gradient clipped to a rounded square
    grad = Image.new("RGBA", (s, s))
    top, bottom = (99, 102, 241), (67, 56, 202)
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        gd.line([(0, y), (s, y)], fill=tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([int(s * .04), int(s * .04), int(s * .96), int(s * .96)], radius=int(s * .22), fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    w = (255, 255, 255, 255)
    # "T" glyph
    d.rounded_rectangle([int(s * .27), int(s * .25), int(s * .73), int(s * .35)], radius=int(s * .02), fill=w)
    d.rounded_rectangle([int(s * .45), int(s * .25), int(s * .55), int(s * .66)], radius=int(s * .02), fill=w)
    # "scan lines" suggesting extracted text
    soft = (255, 255, 255, 170)
    d.rounded_rectangle([int(s * .27), int(s * .74), int(s * .73), int(s * .78)], radius=int(s * .02), fill=soft)
    d.rounded_rectangle([int(s * .27), int(s * .82), int(s * .58), int(s * .86)], radius=int(s * .02), fill=soft)
    return img


if __name__ == "__main__":
    big = render(1024)
    assets = ROOT / "src" / "textextractor" / "assets"
    packaging = ROOT / "packaging"
    assets.mkdir(parents=True, exist_ok=True)
    packaging.mkdir(exist_ok=True)
    big.resize((512, 512), Image.Resampling.LANCZOS).save(assets / "icon.png")
    big.save(packaging / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.save(packaging / "icon.icns")
    print("icons written")
