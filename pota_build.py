#!/usr/bin/env python3
"""Build pota.app upload files from a logger ADIF export (RUMlog etc.).

    python3 pota_build.py RUMlog_export.adif                  # every activation in the file
    python3 pota_build.py RUMlog_export.adif --date 20261020  # one UTC day
    python3 pota_build.py RUMlog_export.adif --date 20261020 --my-parks JP-1281,JP-1285

What it does
  * Finds your activation QSOs: QSOs inside a pota_spotlog.py session, or with
    MY_SIG_INFO set (comma separated = you were in several parks).
  * Works out the other station's park(s) (park-to-park), in this order:
      1. pota.app hunter log (what the other activator uploaded -> verified)
      2. spots recorded by pota_spotlog.py during your activation
      3. SIG_INFO already in your log
    If the other station was a 2fer, the QSO is repeated once per park.
  * Writes one file per (your park, UTC date):  out/JL1FVA@JP-1281-20261020.adi
    plus report.txt and rumlog_p2p_fix.adi (the parks found, to fix your log).
"""
import argparse
import glob
import json
import os
from collections import defaultdict

from potacommon import (DATA_DIR, HERE, base_call, fetch_json, iso_minutes, minutes,
                        read_adif, split_parks, write_adif)

ORDER = ["STATION_CALLSIGN", "OPERATOR", "CALL", "QSO_DATE", "TIME_ON", "BAND", "FREQ", "MODE", "SUBMODE",
         "RST_SENT", "RST_RCVD", "MY_SIG", "MY_SIG_INFO", "MY_POTA_REF", "SIG", "SIG_INFO", "POTA_REF",
         "MY_GRIDSQUARE", "GRIDSQUARE", "COMMENT"]
KEEP = ["CALL", "QSO_DATE", "TIME_ON", "BAND", "FREQ", "MODE", "SUBMODE", "RST_SENT", "RST_RCVD",
        "MY_GRIDSQUARE", "GRIDSQUARE"]
HUNTER_WINDOW = 5      # minutes: hunter log time vs your log time
SPOT_BEFORE = 30       # minutes: a spot this long before the QSO still counts
SPOT_AFTER = 10        # minutes: a spot this long after the QSO still counts
TWOFER_GAP = 15        # minutes: two parks spotted this close together = 2fer


def band_norm(b):
    return (b or "").lower()


# ---------- data sources ----------
def load_hunter(call, offline):
    """pota.app public profile shows the last 25 hunter QSOs. Every run (and
    pota_spotlog.py) merges them into data/hunter.json so the history grows."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, "hunter.json")
    have = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    if not offline:
        try:
            prof = fetch_json("profile/%s" % base_call(call))
            have += prof.get("recent_activity", {}).get("hunter_qsos", [])
        except Exception as e:
            print("! pota.app hunter log download failed (%s) - using saved copy only" % e)
    uniq = {}
    for h in have:
        k = (h.get("date"), base_call(h.get("callsign")), h.get("band"), h.get("reference"))
        uniq[k] = h
    have = sorted(uniq.values(), key=lambda h: h.get("date", ""))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(have, fh, ensure_ascii=False, indent=1)
    out = defaultdict(list)
    for h in have:
        try:
            out[base_call(h["callsign"])].append((iso_minutes(h["date"]), band_norm(h.get("band")), h["reference"].upper(), h))
        except Exception:
            pass
    return out


def load_spots():
    out = defaultdict(list)   # base call -> [(minute, [parks], rec)]
    for f in sorted(glob.glob(os.path.join(DATA_DIR, "spots-*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            try:
                s = json.loads(line)
                m = iso_minutes(s.get("spotTime") or s["seen"])
            except Exception:
                continue
            if s.get("parks"):
                out[s["base"]].append((m, s["parks"], s))
    return out


def load_sessions():
    path = os.path.join(DATA_DIR, "sessions.json")
    res = []
    if os.path.exists(path):
        for s in json.load(open(path, encoding="utf-8")):
            if s.get("start") and s.get("end"):
                res.append((iso_minutes(s["start"]) - 5, iso_minutes(s["end"]) + 5, s["parks"]))
    return res


# ---------- matching ----------
def their_parks_from_spots(spots, t):
    """-> (parks, sure). sure=False when several parks come from separate spots
    (could be a 2fer, could be a rover moving between parks)."""
    best, together = {}, set()
    for m, parks, _ in spots:
        if t - SPOT_BEFORE <= m <= t + SPOT_AFTER:
            if len(parks) > 1:
                together.add(frozenset(parks))
            for p in parks:
                d = abs(m - t)
                best[p] = min(best.get(p, 999), d)
    if not best:
        return [], True
    near = min(best.values())
    res = sorted(p for p, d in best.items() if d <= near + TWOFER_GAP)
    sure = len(res) == 1 or any(set(res) <= g for g in together)
    return res, sure


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("adif", help="ADIF exported from your logger")
    ap.add_argument("--date", action="append", help="only this UTC date YYYYMMDD (repeatable)")
    ap.add_argument("--my-parks", help="your park(s) for the selected date(s), overrides the log")
    ap.add_argument("--call", default="JL1FVA")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--offline", action="store_true", help="do not download the pota.app hunter log")
    args = ap.parse_args()

    call = args.call.upper()
    recs = read_adif(args.adif)
    hunter = load_hunter(call, args.offline)
    spots = load_spots()
    sessions = load_sessions()
    override = split_parks(args.my_parks) if args.my_parks else None

    activ = []   # (rec, my_parks)
    for r in recs:
        d = r.get("QSO_DATE", "")
        if args.date and d not in args.date:
            continue
        try:
            t = minutes(d, r.get("TIME_ON", "0000"))
        except ValueError:
            continue
        mp = override
        if not mp:
            for a, b, parks in sessions:
                if a <= t <= b:
                    mp = parks
        if not mp and (r.get("MY_SIG", "POTA").upper() in ("POTA", "")):
            mp = split_parks(r.get("MY_POTA_REF") or r.get("MY_SIG_INFO"))
        if mp:
            activ.append((r, t, mp))

    if not activ:
        print("No activation QSOs found (need MY_SIG_INFO, a spot-log session, or --my-parks).")
        return

    os.makedirs(args.out, exist_ok=True)
    files = defaultdict(list)          # (park, date) -> records
    report = defaultdict(lambda: {"qsos": set(), "p2p": [], "calls": set()})
    fixes, notes = [], []
    used_hunter = set()

    for r, t, my_parks in activ:
        b = base_call(r["CALL"])
        band = band_norm(r.get("BAND"))
        h = [(p, x) for m, hb, p, x in hunter.get(b, []) if abs(m - t) <= HUNTER_WINDOW and (not hb or hb == band)]
        h_parks = sorted({p for p, _ in h})
        for _, x in h:
            used_hunter.add(id(x))
        s_parks, s_sure = their_parks_from_spots(spots.get(b, []), t)
        log_parks = split_parks(r.get("POTA_REF") or r.get("SIG_INFO")) if r.get("SIG", "POTA").upper() in ("POTA", "") else []
        if h_parks:
            theirs, src = h_parks, "hunter log (verified)"
            extra = [p for p in log_parks + s_parks if p not in h_parks]
            if extra:
                notes.append("%s %s %s: hunter log says %s, log/spots also had %s (ignored)"
                             % (r["QSO_DATE"], r["TIME_ON"][:4], r["CALL"], ",".join(h_parks), ",".join(extra)))
        else:
            theirs = sorted(set(log_parks) | set(s_parks))
            src = "+".join(x for x, ok in (("your log", log_parks), ("spots", s_parks)) if ok)
            if not s_sure and not set(s_parks) <= set(log_parks):
                notes.append("%s %s %s: spotted at %s close together -> treated as 2fer, please check"
                             % (r["QSO_DATE"], r["TIME_ON"][:4], r["CALL"], ",".join(s_parks)))
        if theirs and sorted(theirs) != sorted(log_parks):
            fixes.append({"CALL": r["CALL"], "QSO_DATE": r["QSO_DATE"], "TIME_ON": r.get("TIME_ON"),
                          "BAND": r.get("BAND"), "MODE": r.get("MODE"), "SIG": "POTA", "SIG_INFO": ",".join(theirs)})
        for mp in my_parks:
            key = (mp, r["QSO_DATE"])
            rep = report[key]
            rep["qsos"].add((b, r["QSO_DATE"], r.get("TIME_ON", "")[:4], band, r.get("MODE")))
            rep["calls"].add(b)
            if theirs:
                rep["p2p"].append((r.get("TIME_ON", "")[:4], r["CALL"], ",".join(theirs), src))
            for tp in (theirs or [None]):
                o = {k: r.get(k) for k in KEEP}
                o.update({"STATION_CALLSIGN": call, "OPERATOR": r.get("OPERATOR") or call,
                          "MY_SIG": "POTA", "MY_SIG_INFO": mp, "MY_POTA_REF": mp})
                if tp:
                    o.update({"SIG": "POTA", "SIG_INFO": tp, "POTA_REF": tp})
                files[key].append(o)

    # hunter-log P2P on activation days that are missing from your log
    days = {k[1] for k in files}
    for lst in hunter.values():
        for m, hb, p, x in lst:
            d = x["date"][:10].replace("-", "")
            if d in days and id(x) not in used_hunter:
                notes.append("%s %s %s %s %s: in pota.app hunter log but not matched in your log (call/time differs?)"
                             % (d, x["date"][11:16].replace(":", ""), x.get("callsign"), x.get("band"), p))

    lines = []
    for (mp, d) in sorted(files, key=lambda k: (k[1], k[0])):
        fn = "%s@%s-%s.adi" % (call.replace("/", "_"), mp, d)
        write_adif(os.path.join(args.out, fn), files[(mp, d)], ORDER)
        rep = report[(mp, d)]
        n = len(rep["qsos"])
        lines.append("%s  %3d QSOs (%d stations) %s  -> %s" % (mp, n, len(rep["calls"]),
                     "OK" if n >= 10 else "!! fewer than 10 QSOs", fn))
        for tm, c, ps, src in rep["p2p"]:
            lines.append("      P2P %s %-10s %-20s [%s]" % (tm, c, ps, src))
    if fixes:
        write_adif(os.path.join(args.out, "rumlog_p2p_fix.adi"), fixes,
                   ["CALL", "QSO_DATE", "TIME_ON", "BAND", "MODE", "SIG", "SIG_INFO"])
        lines.append("\n%d QSOs had park-to-park info your log was missing -> rumlog_p2p_fix.adi" % len(fixes))
    if notes:
        lines.append("\nPlease check:")
        lines += ["  - " + n for n in notes]
    text = "\n".join(lines)
    with open(os.path.join(args.out, "report.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)
    print("\nFiles written to %s" % args.out)


if __name__ == "__main__":
    main()
