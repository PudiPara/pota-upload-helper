#!/usr/bin/env python3
"""Build assets/icon.icns (macOS), assets/icon.ico (Windows) and assets/icon-256.png from
assets/icon-1024.png with Pillow, on any OS.

icon-1024.png is assets/icon.svg rasterized at 1024x1024 WITH A TRANSPARENT BACKGROUND
(a browser canvas or `rsvg-convert -w 1024 icon.svg > icon-1024.png`). Don't use macOS
qlmanage for that step: it paints a white background, which showed up as white corners
around the Windows icon. The generated files are committed.
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")


def main():
    src = Image.open(os.path.join(A, "icon-1024.png")).convert("RGBA")
    assert src.size == (1024, 1024) and src.getpixel((0, 0))[3] == 0, "need a 1024px transparent PNG"
    src.save(os.path.join(A, "icon.icns"), sizes=[(s, s) for s in (16, 32, 64, 128, 256, 512, 1024)])
    src.save(os.path.join(A, "icon.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)], bitmap_format="png")
    src.resize((256, 256), Image.LANCZOS).save(os.path.join(A, "icon-256.png"))
    for name in ("icon.icns", "icon.ico", "icon-256.png"):
        im = Image.open(os.path.join(A, name))
        print(name, im.size, "corner alpha", im.convert("RGBA").getpixel((0, 0))[3])


if __name__ == "__main__":
    main()
