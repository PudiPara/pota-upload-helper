#!/usr/bin/env python3
"""Render assets/icon.svg into assets/icon.icns (macOS) and assets/icon.ico (Windows).

Runs on macOS only (qlmanage, sips, iconutil). The generated files are committed,
so CI on Windows needs nothing but the .ico.
"""
import os
import shutil
import struct
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(ROOT, "assets", "icon.svg")
ICNS = os.path.join(ROOT, "assets", "icon.icns")
ICO = os.path.join(ROOT, "assets", "icon.ico")
PNG = os.path.join(ROOT, "assets", "icon-256.png")


def run(*cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    work = tempfile.mkdtemp(prefix="icons-")
    run("qlmanage", "-t", "-s", "1024", "-o", work, SVG)      # QuickLook renders the SVG
    base = os.path.join(work, "icon.svg.png")

    def png(size):
        out = os.path.join(work, "icon-%d.png" % size)
        run("sips", "-z", str(size), str(size), base, "--out", out)
        return out

    iconset = os.path.join(work, "icon.iconset")
    os.makedirs(iconset)
    for pt in (16, 32, 128, 256, 512):
        shutil.copy(png(pt), os.path.join(iconset, "icon_%dx%d.png" % (pt, pt)))
        shutil.copy(png(pt * 2), os.path.join(iconset, "icon_%dx%d@2x.png" % (pt, pt)))
    run("iconutil", "-c", "icns", iconset, "-o", ICNS)

    sizes = (16, 24, 32, 48, 64, 128, 256)            # ICO with PNG-compressed entries
    blobs = [open(png(s), "rb").read() for s in sizes]
    offset = 6 + 16 * len(sizes)
    with open(ICO, "wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, len(sizes)))
        for s, b in zip(sizes, blobs):
            fh.write(struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(b), offset))
            offset += len(b)
        for b in blobs:
            fh.write(b)
    shutil.copy(png(256), PNG)
    print("wrote", ICNS, ICO, PNG)


if __name__ == "__main__":
    main()
