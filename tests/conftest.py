import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from PIL import Image, ImageDraw, ImageFont


def _font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial.ttf",
              "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


@pytest.fixture
def render_text():
    def make(lines, size=34, width=1300, bg="white", fg="black"):
        f = _font(size)
        step = int(size * 1.6)
        img = Image.new("RGB", (width, 60 + len(lines) * step), bg)
        d = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            d.text((30, 30 + i * step), line, fill=fg, font=f)
        return img
    return make
