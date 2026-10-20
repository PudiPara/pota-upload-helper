#!/usr/bin/env python3
"""Command-line spot logger (the app does the same in its "運用中" tab).

    python3 pota_spotlog.py --parks JP-1266
    python3 pota_spotlog.py --parks JP-1266,JP-1206 --prefix JP
"""
import argparse
import time

from spots import SpotLogger


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parks", required=True, help="your park(s), comma separated")
    ap.add_argument("--call", default="JL1FVA")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--prefix", default="", help="only print activators whose park starts with this (e.g. JP)")
    args = ap.parse_args()

    def show(tm, act, parks, freq, mode, twofer):
        if not args.prefix or any(p.startswith(args.prefix.upper()) for p in parks):
            print("[%sZ] %-10s %-20s %s %s %s" % (tm, act, ",".join(parks), freq, mode, "2fer" if twofer else ""))

    lg = SpotLogger(args.parks, args.call, args.interval, on_activator=show)
    lg.start()
    print("Recording POTA spots for %s at %s (Ctrl+C to stop)" % (lg.call, ",".join(lg.parks)))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        lg.stop()
        print("\nStopped. Session %s - %s saved." % (lg.session["start"], lg.session["end"]))


if __name__ == "__main__":
    main()
