"""Build pota.app upload files (one per your park and UTC date).

Input is either the app's own log (records carry the operator's P2P decisions, confirmed_only=True)
or an ADIF exported from the logger. The other station's park (park-to-park) comes from, in order:
  1. the pota.app hunter log (what the other activator uploaded -> verified)
  2. the decision made while activating (app log) - or, for an ADIF file, spots recorded at the time
  3. SIG_INFO / POTA_REF already in the log
If the other station was a 2fer the QSO is repeated once per park; if you were in several parks a
file is written for each of them (pota.app does not accept multi-value references).
What a spot means (parks, 2fer, time windows) is spots.py's business; this module only asks it.
"""
import datetime as dt
import os
import re
from collections import defaultdict

from i18n import t as tr
from potacommon import (CALL_RE, DEFAULT_OUT, SUBMODES, band_name, base_call, count_key, data_path, fetch_json, fix_mode_band, iso_minutes, mode_known,
                        mode_of, my_parks_of, pota_key, read_adif, read_json, rec_minutes, split_parks, their_parks_of,
                        write_adif, write_json)
from qsolog import decided_parks
from spots import load_sessions, load_spots, their_parks_at

ORDER = ["STATION_CALLSIGN", "OPERATOR", "CALL", "QSO_DATE", "TIME_ON", "BAND", "FREQ", "MODE", "SUBMODE",
         "RST_SENT", "RST_RCVD", "MY_SIG", "MY_SIG_INFO", "MY_POTA_REF", "SIG", "SIG_INFO", "POTA_REF",
         "MY_STATE", "MY_GRIDSQUARE", "GRIDSQUARE", "COMMENT"]
KEEP = ["CALL", "QSO_DATE", "TIME_ON", "BAND", "FREQ", "MODE", "SUBMODE", "RST_SENT", "RST_RCVD",
        "MY_GRIDSQUARE", "GRIDSQUARE"]
HUNTER_WINDOW = 15     # minutes: hunter log time vs your log time (pota.app's P2P match: "within 15 minutes")


def band_norm(b):
    return (b or "").lower()


def hhmm(rec):
    return (rec.get("TIME_ON") or "")[:4]


def hunter_match(entries, t, band):
    """The hunter-log entries (their uploads) for one of my QSOs at minute t on band: within HUNTER_WINDOW, the
    nearest in time only (with all parks logged at that moment - their 2fer), so a rover worked twice within
    the window is not given both parks. An entry without a band matches any. -> [(park, entry)]"""
    near = [(abs(m - t), p, x) for m, hb, p, x in entries if abs(m - t) <= HUNTER_WINDOW and (not hb or hb == band)]
    best = min((d for d, _, _ in near), default=None)
    return [(p, x) for d, p, x in near if d == best]


def records(adif_path=None, recs=None):
    """The records to work on (the app log's, or an ADIF file's), MODE/SUBMODE and BAND as ADIF writes them."""
    out = [fix_mode_band(dict(r)) for r in (recs if recs is not None else read_adif(adif_path))]
    for r in out:
        for k in ("CALL", "MODE", "SUBMODE", "OPERATOR", "STATION_CALLSIGN"):   # calls: A-Z 0-9 /; modes as ADIF spells them
            if r.get(k) or k == "CALL":
                r[k] = (r.get(k) or "").upper().strip()
        if r.get("OPERATOR") and not CALL_RE.fullmatch(r["OPERATOR"]):
            r.pop("OPERATOR")                    # not a callsign: the file then writes the chosen call
    return out


def problems(rec, call):
    """What pota.app (or POTA's rules) will not take in this QSO: [(note key, extra format args)]. The QSO
    stays in the file - the operator fixes it (中身を見る) or the logger. pota.app refuses the whole file for
    a mode or band it does not know, a contact with yourself or a future date."""
    out = []
    mode, call_ = rec.get("MODE") or "", (rec.get("CALL") or "").upper()
    if not mode_known(rec):
        out.append(("b.note.badMode", {"mode": mode or "-"}))
    elif rec.get("SUBMODE") and rec["SUBMODE"].upper() not in SUBMODES:   # pota.app keeps the SUBMODE
        out.append(("b.note.badMode", {"mode": rec["SUBMODE"]}))
    try:
        if dt.datetime.strptime(rec.get("QSO_DATE") or "", "%Y%m%d").year < 1930 or len(rec["QSO_DATE"]) != 8:
            raise ValueError
    except (ValueError, KeyError):
        out.append(("b.note.badDate", {"value": rec.get("QSO_DATE") or "-"}))
    if not band_name(rec.get("BAND")):
        out.append(("b.note.noBand", {}))
    if call_ and call_ in {call.upper(), (rec.get("OPERATOR") or "").upper()}:
        out.append(("b.note.self", {}))
    if not re.fullmatch(r"[A-Z0-9/]+", call_):
        out.append(("b.note.badCall", {}))
    if not re.fullmatch(r"([01]\d|2[0-3])[0-5]\d([0-5]\d)?", rec.get("TIME_ON") or ""):
        out.append(("b.note.badTime", {"value": rec.get("TIME_ON") or "-"}))
    if (rec.get("QSO_DATE") or "") > dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d"):
        out.append(("b.note.future", {}))
    if (rec.get("PROP_MODE") or "").upper() == "RPT":
        out.append(("b.note.repeater", {}))
    for ref, sig, info in (("POTA_REF", "SIG", "SIG_INFO"), ("MY_POTA_REF", "MY_SIG", "MY_SIG_INFO")):
        raw = rec.get(ref) or (rec.get(info) if (rec.get(sig) or "POTA").upper() == "POTA" else "")
        bad = [x for x in re.split(r"[,\s;]+", (raw or "").upper()) if re.fullmatch(r"[A-Z]{1,4}\d{4,5}", x)]
        if bad:                                  # "US1234": a park without its hyphen (not a SOTA "W2/WE-003")
            out.append(("b.note.parkUnread", {"value": ",".join(bad),         # {park}: how it should read
                                              "park": re.sub(r"^([A-Z]+)(\d)", r"\1-\2", bad[0])}))
    return out


# ---------- data sources ----------
def load_hunter(call, offline=False, log=print):
    """pota.app's public profile shows your last 25 hunter QSOs. Every run (and
    the spot logger) merges them into hunter.json so the history keeps growing."""
    path = data_path("hunter.json")
    have = read_json(path, [])
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
    write_json(path, have)
    out = defaultdict(list)
    for h in have:
        try:
            out[base_call(h["callsign"])].append((iso_minutes(h["date"]), band_norm(h.get("band")), h["reference"].upper(), h))
        except Exception:
            pass
    return out


# ---------- selecting activation QSOs ----------
def find_activation_qsos(recs, dates=None, my_parks=None, sessions=None):
    override = split_parks(my_parks) if my_parks else None
    sessions = sessions if sessions is not None else load_sessions()
    activ = []
    for r in recs:
        if dates and r.get("QSO_DATE", "") not in dates:
            continue
        t = rec_minutes(r)
        if t is None:
            continue
        mp = override
        if not mp:
            mp = my_parks_of(r)                 # recorded with the QSO: wins
        if not mp:
            for a, b, parks in sessions:        # else the session window it fell in (windows carry a margin,
                if a <= t <= b:                 # so they must never override a QSO's own parks)
                    mp = parks
        if mp:
            activ.append((r, t, mp))
    return activ


def list_activations(adif_path=None, recs=None):
    """[(date, 'JP-1281,JP-1285', qso_count, {park: the QSOs that count there (count_key)}, {park: lines pota.app keeps})]
    newest first, for the GUI. The parks of a day are listed, not joined as one 2fer: a day may hold
    several sessions."""
    recs = records(adif_path, recs)
    agg = defaultdict(lambda: [defaultdict(set), 0, defaultdict(set)])
    for r, t, mp in find_activation_qsos(recs):
        a = agg[r["QSO_DATE"]]
        _, theirs = decided_parks(r)
        for p in mp:
            a[0][p].add(count_key(r, p))
            for tp in (theirs or [""]):        # their 2fer is one line per park
                a[2][p].add(pota_key(dict(r, SIG_INFO=tp)))
        a[1] += 1
    return sorted(((d, ",".join(sorted(v[0])), v[1], {p: len(k) for p, k in v[0].items()}, {p: len(k) for p, k in v[2].items()})
                   for d, v in agg.items()), reverse=True)


# ---------- main entry ----------
def build(adif_path=None, dates=None, my_parks=None, call="", out_dir=None, offline=False, log=print,
          recs=None, confirmed_only=False):
    """confirmed_only: the records come from the app's own log, where the operator confirms
    P2P during the activation. Then spots are never used as a guess - only what was
    confirmed (or typed), plus the pota.app hunter log, which is the other side's upload."""
    call = (call or "").upper().strip()
    if not call:
        raise ValueError(tr("api.noCall"))
    out_dir = out_dir or DEFAULT_OUT
    recs = records(adif_path, recs)
    hunter = load_hunter(call, offline, log)
    spots = load_spots()
    activ = find_activation_qsos(recs, dates, my_parks)
    # a QSO without a valid time can't be placed in a session or a file: say so instead of leaving it out quietly
    untimed = [tr(k, date=r.get("QSO_DATE") or "-", time=hhmm(r) or "----", call=r.get("CALL") or "-", **kw)
               for r in recs if (not dates or r.get("QSO_DATE") in dates) and rec_minutes(r) is None
               for k, kw in problems(r, call) if k in ("b.note.badTime", "b.note.badDate")]
    if not activ:
        msg = tr("b.noActivation")
        return {"text": msg, "files": [], "out_dir": out_dir, "summary": [], "notes": [msg] + untimed}

    os.makedirs(out_dir, exist_ok=True)
    files = defaultdict(list)
    report = defaultdict(lambda: {"qsos": set(), "count": set(), "p2p": [], "rows": [], "calls": set()})
    notes = list(untimed)
    used_hunter = set()
    differ = set()                 # the logger's own callsigns when they are not the one chosen here

    for r, t, mp_list in activ:
        b = base_call(r["CALL"])
        for key, kw in problems(r, call):
            notes.append(tr(key, date=r["QSO_DATE"], time=hhmm(r), call=r["CALL"], **kw))
        band = band_norm(r.get("BAND"))
        h = hunter_match(hunter.get(b, []), t, band)
        h_parks = sorted({p for p, _ in h})
        exact = {x.get("callsign", "").upper() for _, x in h} - {r["CALL"]}
        if exact:                                  # pota.app matches a P2P on the call as written, not the base call
            notes.append(tr("b.note.callExact", date=r["QSO_DATE"], time=hhmm(r), call=r["CALL"], theirs=",".join(sorted(exact))))
        for k in ("STATION_CALLSIGN", "OPERATOR"):
            if (r.get(k) or call).upper() != call:
                differ.add(r[k].upper())
        for _, x in h:
            used_hunter.add(id(x))
        decided, d_parks = decided_parks(r)
        if decided:
            s_parks, s_sure, log_parks = [], True, d_parks
        elif confirmed_only:
            s_parks, s_sure, log_parks = [], True, []
            cand = split_parks(r.get("P2P_CANDIDATE"))
            if cand:
                notes.append(tr("b.note.unconfirmed", date=r["QSO_DATE"], time=hhmm(r), call=r["CALL"], parks=",".join(cand)))
        else:
            s_parks, s_sure = their_parks_at(spots.get(b, []), t)
            log_parks = their_parks_of(r)
        if h_parks:
            theirs, src = h_parks, "hunter"        # src codes: hunter | confirmed | manual | log | spot | logspot
            extra = [p for p in log_parks + s_parks if p not in h_parks]
            if extra:
                notes.append(tr("b.note.hunterWins", date=r["QSO_DATE"], time=hhmm(r), call=r["CALL"],
                               hunter=",".join(h_parks), extra=",".join(extra)))
            elif decided and not d_parks:
                notes.append(tr("b.note.hunterOverridesNo", date=r["QSO_DATE"], time=hhmm(r), call=r["CALL"],
                               hunter=",".join(h_parks)))
        else:
            theirs = sorted(set(log_parks) | set(s_parks))
            src = ("confirmed" if r.get("P2P_DECISION") == "yes" else "manual" if r.get("P2P_DECISION") == "manual"
                   else "logspot" if log_parks and s_parks else "spot" if s_parks else "log")
            if not s_sure and not set(s_parks) <= set(log_parks):
                notes.append(tr("b.note.twofer", date=r["QSO_DATE"], time=hhmm(r), call=r["CALL"], parks=",".join(s_parks)))
        for mp in mp_list:
            loc = (r.get("MY_POTA_LOCS") or {}).get(mp, "")      # "JP-TK" when the park spans several
            key = (mp, r["QSO_DATE"], loc)
            rep = report[key]
            rep["qsos"].add((b, r["QSO_DATE"], hhmm(r), band, r.get("MODE")))
            rep["count"].add(count_key(r, mp))           # what counts toward the 10 (a re-QSO on the band/mode does not)
            rep["calls"].add(b)
            if theirs:
                rep["p2p"].append((hhmm(r), r["CALL"], ",".join(theirs), src))
            rep["rows"].append({"time": hhmm(r), "call": r["CALL"], "band": band or "",
                                "mode": mode_of(r), "parks": list(theirs), "source": src if theirs else ""})
            for tp in (theirs or [None]):
                o = {k: r.get(k) for k in KEEP}
                o.update({"STATION_CALLSIGN": call, "OPERATOR": r.get("OPERATOR") or call,
                          "MY_SIG": "POTA", "MY_SIG_INFO": mp, "MY_POTA_REF": mp})
                if loc:
                    o["MY_STATE"] = loc.split("-", 1)[-1]
                if tp:
                    o.update({"SIG": "POTA", "SIG_INFO": tp, "POTA_REF": tp})
                files[key].append(o)

    if differ:
        notes.insert(0, tr("b.note.callDiffers", call=call, logger=", ".join(sorted(differ))))
    days = {k[1] for k in files}
    for lst in hunter.values():
        for m, hb, p, x in lst:
            d = x["date"][:10].replace("-", "")
            if d in days and id(x) not in used_hunter:
                notes.append(tr("b.note.missing", date=d, time=x["date"][11:16].replace(":", ""), call=x.get("callsign"),
                               band=x.get("band"), park=p))

    lines, written, summary = [], [], []
    # the upload files of this build in a folder of their own (UTC day, or first-last day), the report beside
    # it: dragging the folder onto pota.app then takes neither report.txt nor files uploaded before
    span = sorted(days)
    files_dir = os.path.join(out_dir, span[0] if len(span) == 1 else "%s-%s" % (span[0], span[-1]))
    os.makedirs(files_dir, exist_ok=True)
    for (mp, d, loc) in sorted(files, key=lambda k: (k[1], k[0], k[2])):
        # the documented name for a park crossing state lines: CALL@PARK-DATE-LOCATION.adi
        fn = "%s@%s-%s%s.adi" % (call.replace("/", "_"), mp, d, "-" + loc if loc else "")
        write_adif(os.path.join(files_dir, fn), files[(mp, d, loc)], ORDER)
        written.append(fn)
        rep = report[(mp, d, loc)]
        n, counted = len(rep["qsos"]), len(rep["count"])
        summary.append({"park": mp, "date": d, "loc": loc, "file": fn, "qsos": n, "counted": counted, "stations": len(rep["calls"]),
                        "records": len(files[(mp, d, loc)]), "rows": rep["rows"],
                        # what pota.app will keep: its duplicate key is CALL+MODE+date+BAND+MY_SIG_INFO+SIG_INFO
                        "unique": len({pota_key(o) for o in files[(mp, d, loc)]}),
                        "p2p": [{"time": tm, "call": c, "parks": ps.split(","), "source": src}
                                for tm, c, ps, src in rep["p2p"]]})
        lines.append(tr("b.line.file", date=d, park=mp, n=n, stations=len(rep["calls"]), short="" if counted >= 10 else tr("b.short"), file=fn))
        for tm, c, ps, src in rep["p2p"]:
            lines.append("      P2P %s %-10s %-20s [%s]" % (tm, c, ps, src))
    if notes:
        lines.append("\n" + tr("b.notes"))
        lines += ["  - " + n for n in notes]
    text = "\n".join(lines)
    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return {"text": text, "files": written, "out_dir": files_dir, "summary": summary, "notes": notes}
