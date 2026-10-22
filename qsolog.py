"""The app's own QSO log (SQLite), filled by loggers over UDP, and the operator's P2P decisions.

One contact often arrives twice: WSJT-X reports it at its start, the logger at its end. A copy is the
same base call, band and mode within TWIN_WINDOW minutes; reads keep one (dedupe), and a decision or a
delete is applied to every copy.
"""
import datetime as dt
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

from potacommon import adif_mode, base_call, data_path, minutes, mode_of, my_parks_of, rec_minutes, split_parks, their_parks_of

TWIN_WINDOW = 3          # minutes
_ready = set()           # databases whose table and indexes are made (once per process, not per connection)
_lock = threading.Lock()


@contextmanager
def _conn():
    """A connection under the module lock, committed and closed on the way out."""
    with _lock:
        os.makedirs(data_path(), exist_ok=True)
        path = data_path("qsolog.db")
        con = sqlite3.connect(path, check_same_thread=False)
        try:
            if path not in _ready or not os.path.exists(path):
                con.execute("""CREATE TABLE IF NOT EXISTS qso (
                    uid TEXT PRIMARY KEY, call TEXT, qso_date TEXT, time_on TEXT, band TEXT, mode TEXT,
                    data TEXT, source TEXT, received REAL, deleted INTEGER DEFAULT 0, ext_id TEXT)""")
                if "ext_id" not in [r[1] for r in con.execute("PRAGMA table_info(qso)")]:
                    con.execute("ALTER TABLE qso ADD COLUMN ext_id TEXT")
                con.execute("CREATE INDEX IF NOT EXISTS qso_date ON qso(qso_date)")
                con.execute("CREATE INDEX IF NOT EXISTS qso_ext ON qso(ext_id)")   # a logger's edit / delete by its id
                _ready.add(path)
            yield con
            con.commit()
        finally:
            con.close()


def make_uid(rec):
    return "%s|%s|%s|%s|%s" % (rec.get("CALL", "").upper(), rec.get("QSO_DATE", ""),
                               rec.get("TIME_ON", "")[:4], (rec.get("BAND") or "").lower(), mode_of(rec))


def _days_around(date):
    """The UTC day before, the day, the day after: a contact over 0000Z has its copies on two days (WSJT-X
    reports its start, the logger its end)."""
    d = dt.datetime.strptime(date, "%Y%m%d")
    return [(d + dt.timedelta(days=k)).strftime("%Y%m%d") for k in (-1, 0, 1)]


def _twins(con, date, call, time_on, band=None, mode=None):
    """uids of the live rows that are the same contact (band/mode only when given), the day around 0000Z too."""
    try:
        tm, days = minutes(date, time_on), _days_around(date)
    except (TypeError, ValueError):
        return []                                  # no time: nothing to pair it with
    out = []
    for uid, d2, c2, t2, b2, m2 in con.execute(
            "SELECT uid, qso_date, call, time_on, band, mode FROM qso WHERE qso_date IN (?,?,?) AND deleted=0", days).fetchall():
        try:
            near = abs(minutes(d2, t2) - tm) <= TWIN_WINDOW
        except (TypeError, ValueError):
            continue
        if near and base_call(c2) == base_call(call) and band in (None, b2) and mode in (None, m2):
            out.append(uid)
    return out


# ---------------------------------------------------------------- storing
def upsert(rec, ext_id=None, source=""):
    """Same QSO (call, date, minute, band, mode) from two programs is stored once."""
    uid = make_uid(rec)
    with _conn() as con:
        if ext_id:   # an edit in the logger (time/band changed) replaces the old row
            con.execute("UPDATE qso SET deleted=1 WHERE ext_id=? AND uid<>?", (ext_id, uid))
        if not rec.get("P2P_DECISION"):   # WSJT-X and the logger both send it: keep what the operator decided
            row = con.execute("SELECT data FROM qso WHERE uid=?", (uid,)).fetchone()
            if row:
                _carry_decision(json.loads(row[0]), rec)
        con.execute("""INSERT INTO qso(uid, call, qso_date, time_on, band, mode, data, source, received, deleted, ext_id)
                       VALUES(?,?,?,?,?,?,?,?,?,0,?)
                       ON CONFLICT(uid) DO UPDATE SET call=excluded.call, qso_date=excluded.qso_date,
                       time_on=excluded.time_on, band=excluded.band, mode=excluded.mode, data=excluded.data,
                       source=excluded.source, received=excluded.received, deleted=0,
                       ext_id=COALESCE(excluded.ext_id, qso.ext_id)""",
                    (uid, rec.get("CALL", "").upper(), rec.get("QSO_DATE", ""), rec.get("TIME_ON", ""),
                     (rec.get("BAND") or "").lower(), mode_of(rec), json.dumps(rec, ensure_ascii=False),
                     source, time.time(), ext_id))
    return uid


def received(rec, ext_id=None, source="", accept=None):
    """A QSO a logger sent. Their park typed in the logger (SIG_INFO / POTA_REF) is the decision
    "log"; a decision made on the other copy is kept; accept = spot candidate parks to record as "yes"
    without asking (設定 → P2P). -> uid. rec is updated in place."""
    logged = their_parks_of(rec)
    if logged and not rec.get("P2P_DECISION"):
        apply_decision(rec, "log", logged)
    uid = upsert(rec, ext_id, source)
    if accept and not rec.get("P2P_DECISION"):
        set_p2p(uid, "yes", accept)
        apply_decision(rec, "yes", split_parks(accept))
    return uid


def known(uid):
    """True when this QSO was ever stored (deleted ones too)."""
    with _conn() as con:
        return con.execute("SELECT 1 FROM qso WHERE uid=?", (uid,)).fetchone() is not None


# ---------------------------------------------------------------- the operator's P2P decision
P2P_KEYS = ("P2P_DECISION", "P2P_CANDIDATE", "SIG", "SIG_INFO", "POTA_REF")


def _carry_decision(src, dst):
    if not src.get("P2P_DECISION"):
        return
    for k in ("SIG", "SIG_INFO", "POTA_REF"):
        dst.pop(k, None)
    for k in P2P_KEYS:
        if src.get(k):
            dst[k] = src[k]


def apply_decision(rec, decision, parks):
    """decision: 'yes' (spot candidate accepted), 'manual' (typed), 'log' (typed in the logger), 'no',
    or '' (undecided)."""
    for k in ("SIG", "SIG_INFO", "POTA_REF"):
        rec.pop(k, None)
    if decision in ("yes", "manual", "log") and parks:
        rec.update({"P2P_DECISION": decision, "SIG": "POTA", "SIG_INFO": ",".join(parks), "POTA_REF": ",".join(parks)})
    elif decision == "no":
        rec["P2P_DECISION"] = "no"
    else:
        rec.pop("P2P_DECISION", None)
    return rec


def decided_parks(rec):
    """-> (decided, parks): the decision recorded for this QSO. decided=False when nobody has said
    anything yet; "no" = decided, no parks."""
    dec = rec.get("P2P_DECISION")
    if not dec:
        return False, []
    if dec == "no":
        return True, []
    return True, their_parks_of(rec)


def earlier_parks(rec):
    """A rover calling again (#52): their parks at this station's previous contact of the day (decided, else its
    spot candidate) when they differ from this QSO's. -> [] otherwise. A twin copy (within TWIN_WINDOW) is not earlier."""
    t, call = rec_minutes(rec), base_call(rec.get("CALL"))
    if t is None:
        return []
    now = decided_parks(rec)[1] or split_parks(rec.get("P2P_CANDIDATE"))
    for r in reversed(records([rec.get("QSO_DATE")])):
        rt = rec_minutes(r)
        if base_call(r.get("CALL")) != call or rt is None or rt >= t - TWIN_WINDOW:
            continue
        parks = decided_parks(r)[1] or ([] if decided_parks(r)[0] else split_parks(r.get("P2P_CANDIDATE")))
        if parks:
            return parks if set(parks) != set(now) else []
    return []


def set_p2p(uid, decision, parks):
    """Record the operator's P2P decision for a QSO and its copies. -> the updated records."""
    parks = split_parks(parks)
    updated = []
    with _conn() as con:
        row = con.execute("SELECT call, qso_date, time_on, band, mode FROM qso WHERE uid=? AND deleted=0", (uid,)).fetchone()
        if not row:
            return []
        c, d, t, band, mode = row
        uids = _twins(con, d, c, t, band, mode)
        for u in ([uid] if uid not in uids else []) + uids:
            rec = apply_decision(json.loads(con.execute("SELECT data FROM qso WHERE uid=?", (u,)).fetchone()[0]), decision, parks)
            con.execute("UPDATE qso SET data=? WHERE uid=?", (json.dumps(rec, ensure_ascii=False), u))
            updated.append(rec)
    return updated


def twins(uid):
    """uids of the other stored copies of this QSO (the live list shows a contact once)."""
    with _conn() as con:
        row = con.execute("SELECT call, qso_date, time_on, band, mode FROM qso WHERE uid=?", (uid,)).fetchone()
        return [u for u in _twins(con, row[1], row[0], row[2], row[3], row[4]) if u != uid] if row else []


# ---------------------------------------------------------------- edits and deletes
def delete(ext_id=None, call=None, qso_date=None, time_on=None, band=None, mode=None):
    """Delete a QSO the logger deleted (by its id there, else call/date/time and the band / mode when known)
    and its copies. -> the uids deleted."""
    gone = []
    with _conn() as con:
        targets = []
        if ext_id:
            targets = con.execute("SELECT call, qso_date, time_on, band, mode FROM qso WHERE ext_id=? AND deleted=0",
                                  (ext_id,)).fetchall()
        if not targets and call:
            targets = [(call.upper(), qso_date, time_on or "", (band or "").lower() or None, mode or None)]
        for c, d, t, band, mode in targets:
            for uid in _twins(con, d, c, t, band, mode):
                if con.execute("UPDATE qso SET deleted=1 WHERE uid=? AND deleted=0", (uid,)).rowcount:
                    gone.append(uid)
    return gone


def update(uid, fields):
    """Edit one stored QSO: CALL, TIME_ON, BAND, MODE and/or "parks" (their park, the operator's
    decision). The key may change, so the old row is retired and the record stored again.
    -> the new uid, or None when the QSO is gone."""
    with _conn() as con:
        row = con.execute("SELECT data, ext_id, source FROM qso WHERE uid=? AND deleted=0", (uid,)).fetchone()
    if not row:
        return None
    rec, ext_id, source = json.loads(row[0]), row[1], row[2]
    for k in ("CALL", "TIME_ON", "BAND"):
        if k in fields:
            rec[k] = fields[k]
    if "MODE" in fields:
        rec.pop("SUBMODE", None)
        rec.update(adif_mode(fields["MODE"]))    # "USB" -> SSB + USB, "FT4" -> MFSK + FT4
    if "parks" in fields:
        parks = split_parks(fields["parks"])
        apply_decision(rec, "manual" if parks else "no", parks)
    if make_uid(rec) != uid:
        delete_uid(uid)
    return upsert(rec, ext_id, source)


def delete_uid(uid):
    """Soft-delete one stored QSO. -> True when it existed."""
    with _conn() as con:
        return con.execute("UPDATE qso SET deleted=1 WHERE uid=? AND deleted=0", (uid,)).rowcount > 0


# ---------------------------------------------------------------- reading
def records(dates=None):
    """The live records (of these QSO_DATEs), oldest first, one per contact."""
    with _conn() as con:
        if dates:                     # the days around too: a contact over 0000Z has a copy on the other day
            around = sorted({x for d in dates for x in _days_around(d)})
            q = "SELECT data FROM qso WHERE deleted=0 AND qso_date IN (%s) ORDER BY qso_date, time_on" % ",".join("?" * len(around))
            rows = con.execute(q, around).fetchall()
        else:
            rows = con.execute("SELECT data FROM qso WHERE deleted=0 ORDER BY qso_date, time_on").fetchall()
    recs = dedupe([json.loads(r[0]) for r in rows])
    return [r for r in recs if not dates or r.get("QSO_DATE") in dates]


def history():
    """Every live contact, newest first, one per contact, for the 履歴 page:
    [{uid, date, time, call, band, mode, my: [parks], their: [parks], p2p, source}] - their parks only
    once the operator decided (decided_parks)."""
    with _conn() as con:
        rows = con.execute("SELECT uid, source, data FROM qso WHERE deleted=0 ORDER BY qso_date, time_on").fetchall()
    recs = []
    for uid, source, data in rows:
        r = json.loads(data)
        r["_uid"], r["_source"] = uid, source or ""
        recs.append(r)
    out = [{"uid": r["_uid"], "date": r.get("QSO_DATE", ""), "time": (r.get("TIME_ON") or "")[:4],
            "call": r.get("CALL", ""), "band": r.get("BAND", ""), "mode": mode_of(r),
            "my": my_parks_of(r),
            "their": decided_parks(r)[1], "p2p": r.get("P2P_DECISION") or "", "source": r["_source"]}
           for r in dedupe(recs)]
    return out[::-1]


def clear():
    """Delete every stored QSO for good (設定 → このアプリの内部データを削除). -> how many rows went."""
    with _conn() as con:
        return con.execute("DELETE FROM qso").rowcount


def between(t0, t1=None):
    """Records whose time is within [t0, t1] (minutes, see potacommon.minutes; t1=None: up to now).
    Reads only the UTC days the window covers (records() widens them for copies over 0000Z)."""
    day = lambda m: time.strftime("%Y%m%d", time.gmtime(m * 60))
    d0, d1 = day(t0), day(t1 if t1 is not None else time.time() // 60)
    dates, d = [], dt.datetime.strptime(d0, "%Y%m%d")
    while d.strftime("%Y%m%d") <= d1:
        dates.append(d.strftime("%Y%m%d"))
        d += dt.timedelta(days=1)
    out = []
    for r in records(dates):
        t = rec_minutes(r)
        if t is not None and t0 <= t and (t1 is None or t <= t1):
            out.append(r)
    return out


def dedupe(recs):
    """Keep one record per contact: a copy another program reported within TWIN_WINDOW minutes is
    dropped, the richer record (one with a decision, then more fields) kept."""
    kept, last = [], {}
    for r in recs:
        t = rec_minutes(r)
        if t is None:
            kept.append(r)
            continue
        # my parks are part of the key: the same station worked again minutes later from another
        # park is a second QSO, not the logger's copy of the first one
        k = (base_call(r.get("CALL")), (r.get("BAND") or "").lower(), mode_of(r), tuple(my_parks_of(r)))
        if k in last and t - last[k][0] <= TWIN_WINDOW:
            t0, i = last[k]
            prev = kept[i]
            if (bool(r.get("P2P_DECISION")), len(r)) > (bool(prev.get("P2P_DECISION")), len(prev)):
                if r.get("QSO_DATE") != prev.get("QSO_DATE"):      # over 0000Z: the day it started (ADIF, pota.app)
                    r = dict(r, QSO_DATE=prev["QSO_DATE"], TIME_ON=prev.get("TIME_ON"))
                kept[i] = r
            continue
        last[k] = (t, len(kept))
        kept.append(r)
    return kept


def count():
    with _conn() as con:
        return con.execute("SELECT COUNT(*) FROM qso WHERE deleted=0").fetchone()[0]
