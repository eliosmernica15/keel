"""Build one labelled contact sheet per theme x viewport for visual QA.

Reads the 72 PNGs written by tests/e2e/09-theme-viewports.spec.ts and writes
tests/e2e/screenshots/themes/contact-sheets/<theme>-<WxH>-contact.png.
No runtime dependency beyond Pillow, already used for the earlier sheets.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
THEMES = os.path.join(ROOT, "e2e", "screenshots", "themes")
OUT = os.path.join(THEMES, "contact-sheets")
VIEWPORTS = ["360x800", "390x844", "768x1024", "1024x768", "1280x800", "1440x900"]
DESTINATIONS = ["cowork", "code", "duet", "fleet", "capabilities", "settings"]
CELL = (480, 300)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for theme in ("dark", "light"):
        for vp in VIEWPORTS:
            sheet = Image.new("RGB", (CELL[0] * 3, (CELL[1] + 22) * 2), "#202020")
            draw = ImageDraw.Draw(sheet)
            missing: list[str] = []
            for i, dest in enumerate(DESTINATIONS):
                src = os.path.join(THEMES, theme, vp, f"{dest}.png")
                if not os.path.exists(src):
                    missing.append(dest)
                    continue
                img = Image.open(src).convert("RGB")
                img.thumbnail(CELL)
                x = (i % 3) * CELL[0]
                y = (i // 3) * (CELL[1] + 22)
                sheet.paste(img, (x, y + 22))
                draw.text((x + 6, y + 5), f"{theme} {vp} {dest}", fill="#ffffff")
            name = f"{theme}-{vp}-contact.png"
            sheet.save(os.path.join(OUT, name))
            print(f"{name}: {6 - len(missing)}/6" + (f" missing={missing}" if missing else ""))


if __name__ == "__main__":
    main()
