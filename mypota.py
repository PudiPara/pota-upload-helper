"""The operator's own POTA record: which parks they have hunted and activated.

Source: the two CSVs pota.app offers a logged-in user (hunter_parks.csv, activator_parks.csv), imported
by hand (設定 → POTA の実績). The app never logs in to pota.app. After an import the record grows
locally, so it stays useful until the next import:
  hunted     + the hunter log the app already fetches (hunter.json, builder.load_hunter)
             + the P2P parks confirmed in the app's own log (a P2P contact hunts the other park)
  activated  + the activation days in the app's own log after the import day
Nothing here talks to pota.app.
"""
import csv
import io
import os
import time

from potacommon import count_key, data_path, my_parks_of, read_json, their_parks_of, utc_stamp, write_json

FILE = "mypota.json"
HUNTER_COLS = {"Reference", "First QSO Date", "QSOs"}
ACTIVATOR_COLS = HUNTER_COLS | {"Attempts", "Activations"}
ACTIVATED_MIN = 10        # QSOs that make an activation count (pota.app's rule)

# pota.app achievements (docs.pota.app → Achievement Certificates)
# Unique Reference: parks hunted / activated; an activator's park counts once it has 10 QSOs in all, over any attempts
UNIQUE_STEPS = (10, 20, 30, 40, 50, 75, *range(100, 1001, 100), *range(1500, 20001, 500))
# Repeat Offender: every 20 activations (activator) / QSOs (hunter) at one park, five names a tier, tiers without end
RO_NAMES = ("Oasis", "Fox Den", "Bear Cave", "Fishing Hole", "Eagle's Nest")
RO_STEP = 20
TIERS = ("Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten")
KILO = 1000               # Kilo: 1000 QSOs from one park (activator only)
# Rover: parks activated (10 QSOs each) in one UTC day
ROVER = ((30, "Lion"), (25, "Leopard"), (20, "Ostrich"), (15, "Cheetah"), (10, "Rhino"), (5, "Warthog"))


def next_unique(n):
    """The next Unique Reference level after n parks, or None past the last one."""
    return next((s for s in UNIQUE_STEPS if s > n), None)


def _ro_name(k):
    """The k-th Repeat Offender level (1 = Oasis at 20): "Fox Den", "Tier Two Oasis" (as docs.pota.app writes it) ..."""
    tier = (k - 1) // len(RO_NAMES) + 1
    word = TIERS[tier - 2] if 2 <= tier <= len(TIERS) + 1 else str(tier)
    return ("Tier %s " % word if tier > 1 else "") + RO_NAMES[(k - 1) % len(RO_NAMES)]


def rover(parks):
    """The Rover award for this many parks activated in one UTC day, or None."""
    return next((a for k, a in ROVER if parks >= k), None)


def goals(n, kilo=False):
    """A park's achievements from its count: {"has": [names reached, highest first], "next": name,
    "left": count to go} - "next" only from halfway (10 of 20) so a list of parks is not all hints.
    n = activations (activator) or QSOs (hunter); kilo: n is the activator's QSOs, for Kilo."""
    out = {"has": [], "next": None, "left": None}
    if not n:
        return out
    if kilo:
        if n >= KILO:
            out["has"].append("Kilo")
        elif n >= KILO // 2:
            out.update(next="Kilo", left=KILO - n)
        return out
    k = n // RO_STEP
    if k:
        out["has"].append(_ro_name(k))
    if k or n >= RO_STEP // 2:
        out.update(next=_ro_name(k + 1), left=(k + 1) * RO_STEP - n)
    return out


_cache = (None, {})


def _load():
    """mypota.json, read again only when the file changed (awards look at it on every QSO). Its size is part of the
    key: Windows' file times are coarse, two writes close together kept one time (CI caught it)."""
    global _cache
    path = data_path(FILE)
    try:
        st = os.stat(path)
        key = (path, st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _cache[0] != key:
        _cache = (key, read_json(path, {}))
    return _cache[1]


def _rows(text):
    """-> ("hunter" | "activator", {ref: fields}) or None when the text is not one of the two CSVs."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    cols = set(reader.fieldnames or [])
    kind = "activator" if ACTIVATOR_COLS <= cols else "hunter" if HUNTER_COLS <= cols else None
    if not kind:
        return None
    out = {}
    for r in reader:
        ref = (r.get("Reference") or "").strip().upper()
        if not ref:
            continue
        rec = {"first": (r.get("First QSO Date") or "").strip(), "qsos": int(r.get("QSOs") or 0)}
        if kind == "activator":
            rec.update(attempts=int(r.get("Attempts") or 0), activations=int(r.get("Activations") or 0))
        out[ref] = rec
    return kind, out


def import_files(paths):
    """Read the CSVs (either kind, any order) into mypota.json. -> {"ok", "hunter": n, "activator": n}
    or {"ok": False, "bad": path} for a file that is not one of them (nothing is saved then)."""
    got = {}
    for path in paths:
        try:
            with open(path, encoding="utf-8-sig", newline="") as fh:
                parsed = _rows(fh.read())
        except (OSError, UnicodeDecodeError, ValueError):
            parsed = None
        if not parsed:
            return {"ok": False, "bad": path}
        got[parsed[0]] = parsed[1]
    data = _load()
    for kind, parks in got.items():
        data[kind] = {"at": utc_stamp(), "parks": parks}
    write_json(data_path(FILE), data)
    global _cache
    _cache = (None, {})                    # read it again whatever the file's time says
    return {"ok": True, **{k: len(v["parks"]) for k, v in data.items() if k in ("hunter", "activator")}}


def status():
    """{"hunter": {"n", "at"}, "activator": {"n", "at"}} for what has been imported."""
    return {k: {"n": len(v["parks"]), "at": v["at"]} for k, v in _load().items() if k in ("hunter", "activator")}


# ---------------------------------------------------------------- hunted
def _hunts(app_records=()):
    """{ref: (earliest hunt "YYYYMMDDHHMMSS", source)} - source "csv" (hunter_parks.csv), "log" (the
    pota.app hunter log the app keeps fetching, hunter.json) or "app" (a confirmed P2P in the app log)."""
    first = {}

    def seen(ref, ts, src):
        if ts and (ref not in first or ts < first[ref][0]):
            first[ref] = (ts, src)

    for ref, r in ((_load().get("hunter") or {}).get("parks") or {}).items():
        seen(ref, r["first"].replace("-", "").ljust(14, "0"), "csv")
    for h in read_json(data_path("hunter.json"), []):
        if h.get("reference") and h.get("date"):
            seen(h["reference"].upper(), "".join(c for c in h["date"] if c.isdigit())[:14].ljust(14, "0"), "log")
    for r in app_records:
        if r.get("P2P_DECISION") in ("yes", "manual", "log"):
            for ref in their_parks_of(r):
                seen(ref, (r.get("QSO_DATE") or "") + (r.get("TIME_ON") or "").ljust(6, "0"), "app")
    return first


def first_hunted(app_records=()):
    """{ref: earliest known hunt as "YYYYMMDDHHMMSS"} - None before hunter_parks.csv is imported.
    app_records: the app log's records (their confirmed P2P parks count as hunted at the QSO)."""
    if not _load().get("hunter"):
        return None
    return {ref: ts for ref, (ts, _) in _hunts(app_records).items()}


def new_parks(parks, first, at=None):
    """The parks not hunted before `at` ("YYYYMMDDHHMMSS", default now) - [] when first is None."""
    if first is None:
        return []
    at = at or time.strftime("%Y%m%d%H%M%S", time.gmtime())
    return [p for p in parks if p not in first or first[p] >= at]


# ---------------------------------------------------------------- activated
def _activated(app_days=()):
    """{ref: {first, last, qsos, attempts, activations, added, app}}: activator_parks.csv plus the app
    log's activation days after the import day (the CSV already counts the rest; every day without a CSV).
    app_days: [(YYYYMMDD, {park: qsos})]; added = a park the CSV does not have, app = days added,
    last = the latest day known (the app log, any day; the CSV has only the first)."""
    data = _load().get("activator") or {}
    since = (data.get("at") or "")[:10].replace("-", "")
    out = {ref: dict(r, added=False, app=0, last=r["first"]) for ref, r in (data.get("parks") or {}).items()}
    per_day = {}
    for day, per in app_days:                      # one activation per park and UTC day
        for ref, n in per.items():
            per_day[(day, ref)] = per_day.get((day, ref), 0) + n
    for (day, ref), n in sorted(per_day.items()):
        iso = "%s-%s-%s" % (day[:4], day[4:6], day[6:])
        if n and ref in out:
            out[ref]["last"] = max(out[ref]["last"], iso)
        if n and day > since:
            r = out.setdefault(ref, {"first": "", "last": iso, "qsos": 0, "attempts": 0, "activations": 0, "added": True, "app": 0})
            r["attempts"] += 1
            r["activations"] += 1 if n >= ACTIVATED_MIN else 0
            r["qsos"] += n
            r["app"] += 1
            r["first"] = r["first"] or iso
    return out


def activations(ref, app_days=()):
    """What this park's next activation would be: {"next": n, "done": successful, "qsos": total,
    "first": date} - None before activator_parks.csv is imported."""
    if not _load().get("activator"):
        return None
    r = _activated(app_days).get(ref) or {"first": "", "qsos": 0, "attempts": 0, "activations": 0}
    return {"next": r["attempts"] + 1, "done": r["activations"], "qsos": r["qsos"], "first": r["first"]}


# ---------------------------------------------------------------- the 実績 page
def record(app_records=(), app_days=()):
    """{"hunted": [{ref, first, source, qsos, added}], "activated": [{ref, first, last, attempts,
    activations, qsos, added, app}], "imported": status()} - newest first (activated: by last). added = not in the imported CSV: hunted
    or activated since, found by this app (its P2P log / activations) or pota.app's hunter log."""
    csv_hunt = (_load().get("hunter") or {}).get("parks") or {}
    hunted = [{"ref": ref, "first": "%s-%s-%s" % (ts[:4], ts[4:6], ts[6:8]), "source": src,
               "qsos": (csv_hunt.get(ref) or {}).get("qsos"), "added": ref not in csv_hunt}
              for ref, (ts, src) in _hunts(app_records).items()]
    activated = [dict(r, ref=ref) for ref, r in _activated(app_days).items()]
    for r in hunted:
        r["goals"] = goals(r["qsos"])
    for r in activated:
        ro, kilo = goals(r["activations"]), goals(r["qsos"], kilo=True)
        hint = ro if ro["next"] else kilo
        r["goals"] = {"has": kilo["has"] + ro["has"], "next": hint["next"], "left": hint["left"]}
    hunted.sort(key=lambda r: (r["first"], r["ref"]), reverse=True)
    activated.sort(key=lambda r: (r["last"], r["ref"]), reverse=True)
    # Unique Reference: an activated park counts from 10 QSOs in all, a hunted one from its first QSO
    n = {"hunted": len(hunted), "activated": sum(1 for r in activated if r["qsos"] >= ACTIVATED_MIN)}
    return {"hunted": hunted, "activated": activated, "imported": status(), "six": six_pack(app_records),
            "unique": {k: {"n": v, "next": next_unique(v)} for k, v in n.items()}}


def six_pack(app_records=()):
    """6 Pack (#47), from this app's log only (the CSVs have no bands): {"activated": parks where one UTC day had 10
    QSOs on 6m, "hunted": parks hunted (a confirmed P2P) on 6m}; the award needs 6 of either."""
    days, hunted = {}, set()
    for r in app_records:
        if (r.get("BAND") or "").lower() != "6m":
            continue
        for p in my_parks_of(r):
            days.setdefault((r.get("QSO_DATE"), p), set()).add(count_key(r, p))
        if r.get("P2P_DECISION") in ("yes", "manual", "log"):
            hunted.update(their_parks_of(r))
    return {"activated": sorted({p for (_, p), ks in days.items() if len(ks) >= ACTIVATED_MIN}), "hunted": sorted(hunted)}


# ---------------------------------------------------------------- achievements reached while recording
def awards(app_records=(), app_days=(), day=None):
    """{key: {"kind", "name", "n", "park"}} of the achievements the record reaches now - compared before and after a
    QSO, a new key is one just reached. Not confirmed: pota.app counts them once the log is uploaded.
    Rover (the day's parks with 10 QSOs) needs only this app's log; Unique / Repeat Offender / Kilo need the imported
    CSVs (without them every park would look new)."""
    out = {}
    if day:
        n = len({p for d, per in app_days if d == day for p, q in per.items() if q >= ACTIVATED_MIN})
        name = rover(n)
        if name:
            out["rover:%s:%s" % (day, name)] = {"kind": "rover", "name": name, "n": n}
    data = _load()
    if not data.get("activator") and not data.get("hunter"):
        return out
    rec = record(app_records, app_days)
    for kind, have in (("unique", data.get("activator")), ("uniqueHunt", data.get("hunter"))):
        if have:
            n = rec["unique"]["activated" if kind == "unique" else "hunted"]["n"]
            out.update({"%s:%d" % (kind, s): {"kind": kind, "n": s} for s in UNIQUE_STEPS if s <= n})
    if data.get("activator"):
        for r in rec["activated"]:
            for name in r["goals"]["has"]:
                out["goal:%s:%s" % (r["ref"], name)] = {"kind": "kilo" if name == "Kilo" else "ro", "name": name, "park": r["ref"]}
    return out
