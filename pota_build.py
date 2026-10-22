#!/usr/bin/env python3
"""Command-line upload builder (the app does the same in its "アップロード作成" tab).

    python3 pota_build.py export.adif
    python3 pota_build.py export.adif --date 20261020 --my-parks JP-1266,JP-1206
"""
import argparse

from builder import build
from potacommon import DEFAULT_OUT, my_call


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("adif")
    ap.add_argument("--date", action="append", help="UTC date YYYYMMDD (repeatable)")
    ap.add_argument("--my-parks")
    ap.add_argument("--call", default=my_call())
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    res = build(a.adif, a.date, a.my_parks, a.call, a.out, a.offline)
    print(res["text"])
    if res["files"]:
        print("\nFiles written to %s" % res["out_dir"])


if __name__ == "__main__":
    main()
