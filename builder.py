"""Build pota.app upload files (one per your park and UTC date) from a logger ADIF.

The other station's park (park-to-park) is taken from, in this order:
  1. the pota.app hunter log (what the other activator uploaded -> verified)
  2. spots recorded by the spot logger during your activation
  3. SIG_INFO / POTA_REF already in your log
If the other station was a 2fer the QSO is repeated once per park; if you
were in several parks a file is written for each of them.
"""
import json
import os
import glob
from collections import defaultdict

from i18n import t as tr
from potacommon import (DATA_DIR, DEFAULT_OUT, base_call, fetch_json, iso_minutes, minutes,
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
def load_hunter(call, offline=False, log=print):
    """pota.app's public profile shows your last 25 hunter QSOs. Every run (and
    the spot logger) merges them into hunter.json so the history keeps growing."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, "hunter.json")
    try:
        have = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    except ValueError:
        have = []
    if not offline:
        try:
            prof = fetch_json("profile/%s" % base_call(call))
            have += prof.get("recent_activity", {}).get("hunter_qsos", [])
        except Exception as e:
            log(tr("b.hunterFail", err=e))
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
    try:
        data = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    except ValueError:
        data = []
    for s in data:
        if s.get("start") and s.get("end"):
            res.append((iso_minutes(s["start"]) - 5, iso_minutes(s["end"]) + 5, s["parks"]))
    return res


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


# ---------- selecting activation QSOs ----------
def find_activation_qsos(recs, dates=None, my_parks=None, sessions=None):
    override = split_parks(my_parks) if my_parks else None
    sessions = sessions if sessions is not None else load_sessions()
    activ = []
    for r in recs:
        d = r.get("QSO_DATE", "")
        if dates and d not in dates:
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
    return activ


def list_activations(adif_path=None, recs=None):
    """[(date, 'JP-1281,JP-1285', qso_count)] newest first, for the GUI."""
    recs = recs if recs is not None else read_adif(adif_path)
    agg = defaultdict(lambda: [set(), 0])
    for r, t, mp in find_activation_qsos(recs):
        a = agg[r["QSO_DATE"]]
        a[0].update(mp)
        a[1] += 1
    return sorted(((d, ",".join(sorted(v[0])), v[1]) for d, v in agg.items()), reverse=True)


# ---------- main entry ----------
def live_p2p(rec, spots_only=False):
    """Park(s) the other station was spotted at around the time of a QSO that just
    arrived - the candidate the operator is asked to confirm. spots_only=False also
    falls back to SIG_INFO/POTA_REF already in the record."""
    try:
        t = minutes(rec.get("QSO_DATE", ""), rec.get("TIME_ON") or "0000")
    except ValueError:
        return []
    spots = load_spots().get(base_call(rec.get("CALL")), [])
    parks, _ = their_parks_from_spots(spots, t)
    if parks or spots_only:
        return parks
    return split_parks(rec.get("POTA_REF") or rec.get("SIG_INFO"))


def decided_parks(rec):
    """-> (decided, parks): the operator's live decision for this QSO (or the logger's own
    SIG_INFO, decision 'log'). decided=False when nobody has said anything yet."""
    dec = rec.get("P2P_DECISION")
    if not dec:
        return False, []
    if dec == "no":
        return True, []
    return True, split_parks(rec.get("POTA_REF") or rec.get("SIG_INFO"))


def build(adif_path=None, dates=None, my_parks=None, call="JL1FVA", out_dir=None, offline=False, log=print,
          recs=None, confirmed_only=False):
    """confirmed_only: the records come from the app's own log, where the operator confirms
    P2P during the activation. Then spots are never used as a guess - only what was
    confirmed (or typed), plus the pota.app hunter log, which is the other side's upload."""
    call = call.upper().strip()
    out_dir = out_dir or DEFAULT_OUT
    recs = recs if recs is not None else read_adif(adif_path)
    hunter = load_hunter(call, offline, log)
    spots = load_spots()
    activ = find_activation_qsos(recs, dates, my_parks)
    if not activ:
        msg = tr("b.noActivation")
        return {"text": msg, "files": [], "out_dir": out_dir, "summary": [], "notes": [msg]}

    os.makedirs(out_dir, exist_ok=True)
    files = defaultdict(list)
    report = defaultdict(lambda: {"qsos": set(), "p2p": [], "calls": set()})
    notes = []
    used_hunter = set()

    for r, t, mp_list in activ:
        b = base_call(r["CALL"])
        band = band_norm(r.get("BAND"))
        h = [(p, x) for m, hb, p, x in hunter.get(b, []) if abs(m - t) <= HUNTER_WINDOW and (not hb or hb == band)]
        h_parks = sorted({p for p, _ in h})
        for _, x in h:
            used_hunter.add(id(x))
        decided, d_parks = decided_parks(r)
        if decided:
            s_parks, s_sure, log_parks = [], True, d_parks
        elif confirmed_only:
            s_parks, s_sure, log_parks = [], True, []
            cand = split_parks(r.get("P2P_CANDIDATE"))
            if cand:
                notes.append(tr("b.note.unconfirmed", date=r["QSO_DATE"], time=r["TIME_ON"][:4], call=r["CALL"], parks=",".join(cand)))
        else:
            s_parks, s_sure = their_parks_from_spots(spots.get(b, []), t)
            log_parks = split_parks(r.get("POTA_REF") or r.get("SIG_INFO")) if r.get("SIG", "POTA").upper() in ("POTA", "") else []
        if h_parks:
            theirs, src = h_parks, "hunter"        # src codes: hunter | confirmed | manual | log | spot | logspot
            extra = [p for p in log_parks + s_parks if p not in h_parks]
            if extra:
                notes.append(tr("b.note.hunterWins", date=r["QSO_DATE"], time=r["TIME_ON"][:4], call=r["CALL"],
                               hunter=",".join(h_parks), extra=",".join(extra)))
            elif decided and not d_parks:
                notes.append(tr("b.note.hunterOverridesNo", date=r["QSO_DATE"], time=r["TIME_ON"][:4], call=r["CALL"],
                               hunter=",".join(h_parks)))
        else:
            theirs = sorted(set(log_parks) | set(s_parks))
            src = ("confirmed" if r.get("P2P_DECISION") == "yes" else "manual" if r.get("P2P_DECISION") == "manual"
                   else "logspot" if log_parks and s_parks else "spot" if s_parks else "log")
            if not s_sure and not set(s_parks) <= set(log_parks):
                notes.append(tr("b.note.twofer", date=r["QSO_DATE"], time=r["TIME_ON"][:4], call=r["CALL"], parks=",".join(s_parks)))
        for mp in mp_list:
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

    days = {k[1] for k in files}
    for lst in hunter.values():
        for m, hb, p, x in lst:
            d = x["date"][:10].replace("-", "")
            if d in days and id(x) not in used_hunter:
                notes.append(tr("b.note.missing", date=d, time=x["date"][11:16].replace(":", ""), call=x.get("callsign"),
                               band=x.get("band"), park=p))

    lines, written, summary = [], [], []
    for (mp, d) in sorted(files, key=lambda k: (k[1], k[0])):
        fn = "%s@%s-%s.adi" % (call.replace("/", "_"), mp, d)
        write_adif(os.path.join(out_dir, fn), files[(mp, d)], ORDER)
        written.append(fn)
        rep = report[(mp, d)]
        n = len(rep["qsos"])
        summary.append({"park": mp, "date": d, "file": fn, "qsos": n, "stations": len(rep["calls"]),
                        "records": len(files[(mp, d)]),
                        "p2p": [{"time": tm, "call": c, "parks": ps.split(","), "source": src}
                                for tm, c, ps, src in rep["p2p"]]})
        lines.append(tr("b.line.file", date=d, park=mp, n=n, stations=len(rep["calls"]), short="" if n >= 10 else tr("b.short"), file=fn))
        for tm, c, ps, src in rep["p2p"]:
            lines.append("      P2P %s %-10s %-20s [%s]" % (tm, c, ps, src))
    if notes:
        lines.append("\n" + tr("b.notes"))
        lines += ["  - " + n for n in notes]
    text = "\n".join(lines)
    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return {"text": text, "files": written, "out_dir": out_dir, "summary": summary, "notes": notes}
