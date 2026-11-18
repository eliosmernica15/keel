"""Generate installer assets (icons, BMP images) for Keel Desktop.

Requires: pip install Pillow
Outputs files into desktop-app/build/.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = Path(__file__).resolve().parents[1] / "build"
BUILD_DIR.mkdir(parents=True, exist_ok=True)

# Keel theme tokens (match site/ui/style.css)
BG = (8, 6, 4)            # #080604
PANEL = (24, 19, 15)      # #18130f
TEXT = (232, 224, 212)    # #e8e0d4
MUTED = (154, 143, 130)   # #9a8f82
ACCENT = (224, 122, 79)   # #e07a4f
ACCENT_DEEP = (156, 66, 42)  # #9c422a

STAR = [
    (0, -15), (0, -7), (0, 7), (0, 15),
    (-15, 0), (-7, 0), (7, 0), (15, 0),
    (-11.3, -11.3), (-5.1, -5.1),
    (5.1, 5.1), (11.3, 11.3),
    (11.3, -11.3), (5.1, -5.1),
    (-5.1, 5.1), (-11.3, 11.3),
]


def _starburst(size: int, stroke: int | None = None) -> Image.Image:
    """Render the Keel starburst mark at size×size, transparent background."""
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    c = s / 2
    # scale so the outermost ray stays ~3 px inside the box
    rad = (s / 2 - max(2, s // 16)) / 15.0
    w = stroke if stroke is not None else max(2, round(s / 24))
    for (x, y) in STAR:
        x1 = c + x * rad * (1 if y < 0 or x != 0 else 1)
        y1 = c + y * rad * (1 if x > 0 or y != 0 else 1)
        draw.line([(c + x * rad, c + y * rad)], fill=ACCENT, width=w)
    # PIL can't line() single points; redraw as segments:
    draw = ImageDraw.Draw(img)
    center = (c, c)
    inner = 7 * rad
    outer = 15 * rad
    alt = 11.3 * rad
    inner_alt = 5.1 * rad
    # 8 cardinal rays
    for ang in (0, math.pi / 4, math.pi / 2, math.pi * 3 / 4,
                math.pi, math.pi * 5 / 4, math.pi * 3 / 2, math.pi * 7 / 4):
        dx, dy = math.sin(ang), -math.cos(ang)
        if ang % (math.pi / 2) == 0:
            draw.line([center[0] + dx * inner, center[1] + dy * inner,
                       center[0] + dx * outer, center[1] + dy * outer], fill=ACCENT, width=w)
        else:
            draw.line([center[0] + dx * inner_alt, center[1] + dy * inner_alt,
                       center[0] + dx * alt, center[1] + dy * alt], fill=ACCENT, width=w)
    return img


def _draw_sidebar(width: int = 164, height: int = 314) -> Image.Image:
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / height
        r = int(BG[0] + (ACCENT_DEEP[0] - BG[0]) * t)
        g = int(BG[1] + (ACCENT_DEEP[1] - BG[1]) * t)
        b = int(BG[2] + (ACCENT_DEEP[2] - BG[2]) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    mark = _starburst(88)
    mark_rgb = Image.new("RGB", mark.size, BG)
    mark_rgb.paste(mark, mask=mark.split()[3])
    ix = (width - 88) // 2
    iy = 44
    img.paste(mark_rgb, (ix, iy))

    title_font = _bold(17)
    sub = (width - draw.textbbox((0, 0), "Keel", font=title_font)[2] + draw.textbbox((0, 0), "Keel", font=title_font)[0])
    draw.text(((width - sub) // 2, iy + 96), "Keel", fill=TEXT, font=title_font)

    tag_font = _regular(11)
    tag = "Your agents, your files,"
    tag2 = "your machine."
    tw = draw.textlength(tag, font=tag_font)
    tw2 = draw.textlength(tag2, font=tag_font)
    draw.text(((width - tw) // 2, iy + 122), tag, fill=MUTED, font=tag_font)
    draw.text(((width - tw2) // 2, iy + 138), tag2, fill=MUTED, font=tag_font)

    ver = "v0.1.0"
    vw = draw.textlength(ver, font=_regular(10))
    draw.text(((width - vw) // 2, height - 28), ver, fill=(110, 103, 95), font=_regular(10))
    return img


def _draw_header(width: int = 150, height: int = 57) -> Image.Image:
    img = Image.new("RGB", (width, height), (248, 246, 242))
    mark = _starburst(min(width, height) - 4)
    mark_rgb = Image.new("RGB", mark.size, (248, 246, 242))
    mark_rgb.paste(mark, mask=mark.split()[3])
    ox = (width - mark_rgb.width) // 2
    oy = (height - mark_rgb.height) // 2
    img.paste(mark_rgb, (ox, oy))
    return img


def _regular(size):
    for name in ("segoeui.ttf", "Segoe UI", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _bold(size):
    for name in ("segoeuib.ttf", "Segoe UI Bold", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return _regular(size)


def _make_ico(images, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    sizes = [(i.width, i.height) for i in images]
    images[-1].save(str(path), format="ICO", sizes=sizes)


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    icons = [_starburst(s) for s in sizes]
    for im in icons:
        bg = Image.new("RGBA", im.size, BG + (255,))
        bg.paste(im, (0, 0), im.split()[3])
        icons[icons.index(im)] = bg.convert("RGBA")
    _make_ico(icons, BUILD_DIR / "icon.ico")
    print("  -> icon.ico")

    rgb512 = _starburst(512)
    bg = Image.new("RGBA", rgb512.size, BG + (255,))
    bg.paste(rgb512, (0, 0), rgb512.split()[3])
    bg.save(BUILD_DIR / "icon.png")
    print("  -> icon.png")

    _draw_sidebar().save(str(BUILD_DIR / "sidebar.bmp"), format="BMP")
    print("  -> sidebar.bmp")
    _draw_header().save(str(BUILD_DIR / "header.bmp"), format="BMP")
    print("  -> header.bmp")


if __name__ == "__main__":
    main()
