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

from potacommon import data_path, read_json, utc_stamp, write_json

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
def first_hunted(app_records=()):
    """{ref: earliest known hunt as "YYYYMMDDHHMMSS"} - None before hunter_parks.csv is imported.
    app_records: the app log's records (their confirmed P2P parks count as hunted at the QSO)."""
    data = _load().get("hunter")
    if not data:
        return None
    first = {}

    def seen(ref, ts):
        if ts and (ref not in first or ts < first[ref]):
            first[ref] = ts

    for ref, r in data["parks"].items():
        seen(ref, r["first"].replace("-", "").ljust(14, "0"))
    for h in read_json(data_path("hunter.json"), []):             # the hunter log builder keeps fetching
        if h.get("reference") and h.get("date"):
            seen(h["reference"].upper(), "".join(c for c in h["date"] if c.isdigit())[:14].ljust(14, "0"))
    for r in app_records:
        if r.get("P2P_DECISION") in ("yes", "manual", "log"):
            for ref in (r.get("POTA_REF") or r.get("SIG_INFO") or "").upper().replace(" ", "").split(","):
                if ref:
                    seen(ref, (r.get("QSO_DATE") or "") + (r.get("TIME_ON") or "").ljust(6, "0"))
    return first


def new_parks(parks, first, at=None):
    """The parks not hunted before `at` ("YYYYMMDDHHMMSS", default now) - [] when first is None."""
    if first is None:
        return []
    at = at or time.strftime("%Y%m%d%H%M%S", time.gmtime())
    return [p for p in parks if p not in first or first[p] >= at]


# ---------------------------------------------------------------- activated
def activations(ref, app_days=()):
    """What this park's next activation would be: {"next": n, "done": successful, "qsos": total,
    "first": date} - None before activator_parks.csv is imported. app_days: [(YYYYMMDD, {park: qsos})]
    from the app log; only days after the import day are added (the CSV already counts the rest)."""
    data = _load().get("activator")
    if not data:
        return None
    r = data["parks"].get(ref) or {"first": "", "qsos": 0, "attempts": 0, "activations": 0}
    since = data["at"][:10].replace("-", "")
    attempts, done, qsos, first = r["attempts"], r["activations"], r["qsos"], r["first"]
    for day, per in app_days:
        n = per.get(ref, 0)
        if n and day > since:
            attempts += 1
            done += 1 if n >= ACTIVATED_MIN else 0
            qsos += n
            first = first or "%s-%s-%s" % (day[:4], day[4:6], day[6:])
    return {"next": attempts + 1, "done": done, "qsos": qsos, "first": first}
