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
import time

from potacommon import data_path, read_json, their_parks_of, utc_stamp, write_json

FILE = "mypota.json"
HUNTER_COLS = {"Reference", "First QSO Date", "QSOs"}
ACTIVATOR_COLS = HUNTER_COLS | {"Attempts", "Activations"}
ACTIVATED_MIN = 10        # QSOs that make an activation count (pota.app's rule)


def _load():
    return read_json(data_path(FILE), {})


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
    hunted.sort(key=lambda r: (r["first"], r["ref"]), reverse=True)
    activated.sort(key=lambda r: (r["last"], r["ref"]), reverse=True)
    return {"hunted": hunted, "activated": activated, "imported": status()}
