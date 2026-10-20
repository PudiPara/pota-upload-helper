#!/usr/bin/env python3
"""Record POTA activator spots in real time while you are activating.

Start it when you begin an activation and leave it running (Ctrl+C to stop):

    python3 pota_spotlog.py --parks JP-1281
    python3 pota_spotlog.py --parks JP-1281,JP-1285      # 2fer / 3fer

Every minute it downloads the current spot list from api.pota.app and keeps,
for every activator, which park(s) they were spotted at and when -- so it is
still known after they QRT and their spot disappears. It also records your
activation session (your parks + start/end time) for pota_build.py.

Files are written to ./data/:
    spots-YYYYMMDD.jsonl        every spot seen (one JSON object per line)
    sessions.json               your activation sessions
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

from potacommon import DATA_DIR, base_call, fetch_json, parks_in, split_parks
from pota_build import load_hunter


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def load_sessions(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return []


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parks", required=True, help="your park(s), comma separated, e.g. JP-1281,JP-1285")
    ap.add_argument("--call", default="JL1FVA", help="your callsign (default JL1FVA)")
    ap.add_argument("--interval", type=int, default=60, help="seconds between downloads (default 60)")
    ap.add_argument("--prefix", default="", help="only print activators whose park starts with this, e.g. JP (all are still saved)")
    args = ap.parse_args()

    my_parks = split_parks(args.parks)
    if not my_parks:
        sys.exit("--parks: no valid park reference found (example: JP-1281)")
    os.makedirs(DATA_DIR, exist_ok=True)
    sess_path = os.path.join(DATA_DIR, "sessions.json")
    sessions = load_sessions(sess_path)
    session = {"call": args.call.upper(), "parks": my_parks,
               "start": now_utc().strftime("%Y-%m-%dT%H:%M"), "end": None}
    sessions.append(session)
    save_json(sess_path, sessions)

    mine = base_call(args.call)
    seen = {}          # spotId -> spotTime already written
    known = {}         # (base call) -> set(parks) already announced
    polls = 0
    print("Recording POTA spots for %s at %s  (Ctrl+C to stop)" % (args.call.upper(), ", ".join(my_parks)))
    try:
        while True:
            t = now_utc()
            try:
                spots = fetch_json("spot/activator")
            except Exception as e:  # network hiccup: keep going
                print("[%s] download failed: %s" % (t.strftime("%H:%M"), e))
                spots = []
            out_path = os.path.join(DATA_DIR, "spots-%s.jsonl" % t.strftime("%Y%m%d"))
            new = 0
            with open(out_path, "a", encoding="utf-8") as fh:
                for s in spots:
                    key = s.get("spotId")
                    if seen.get(key) == s.get("spotTime"):
                        continue
                    seen[key] = s.get("spotTime")
                    act = base_call(s.get("activator"))
                    if act == mine:
                        continue
                    refs = [s.get("reference", "").upper()] + parks_in(s.get("comments"))
                    refs = [r for i, r in enumerate(refs) if r and r not in refs[:i]]
                    rec = {"seen": t.strftime("%Y-%m-%dT%H:%M:%S"), "spotTime": s.get("spotTime"),
                           "activator": s.get("activator"), "base": act, "parks": refs,
                           "frequency": s.get("frequency"), "mode": s.get("mode"),
                           "comments": s.get("comments"), "spotId": key}
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    new += 1
                    if not args.prefix or any(r.startswith(args.prefix.upper()) for r in refs):
                        before = known.setdefault(act, set())
                        added = [r for r in refs if r not in before]
                        if added:
                            before.update(added)
                            tag = "2fer+" if len(before) > 1 else ""
                            print("[%s] %-10s %s %s %s %s" % (t.strftime("%H:%MZ"), s.get("activator"), ",".join(sorted(before)),
                                                           s.get("frequency"), s.get("mode"), tag))
            session["end"] = t.strftime("%Y-%m-%dT%H:%M")
            save_json(sess_path, sessions)
            polls += 1
            if polls % 10 == 1:   # keep a copy of the pota.app hunter log (last 25) growing
                try:
                    load_hunter(args.call, False)
                except Exception as e:
                    print("[%s] hunter log update failed: %s" % (t.strftime("%H:%M"), e))
            time.sleep(max(15, args.interval))
    except KeyboardInterrupt:
        session["end"] = now_utc().strftime("%Y-%m-%dT%H:%M")
        save_json(sess_path, sessions)
        print("\nStopped. Session saved: %s %s - %s" % (",".join(my_parks), session["start"], session["end"]))


if __name__ == "__main__":
    main()
