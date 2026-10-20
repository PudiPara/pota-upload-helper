"""The app's own QSO log (SQLite), filled by loggers over UDP."""
import json
import os
import sqlite3
import threading
import time

from potacommon import DATA_DIR

_lock = threading.Lock()


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(os.path.join(DATA_DIR, "qsolog.db"), check_same_thread=False)
    con.execute("""CREATE TABLE IF NOT EXISTS qso (
        uid TEXT PRIMARY KEY, call TEXT, qso_date TEXT, time_on TEXT, band TEXT, mode TEXT,
        data TEXT, source TEXT, received REAL, deleted INTEGER DEFAULT 0, ext_id TEXT)""")
    cols = [r[1] for r in con.execute("PRAGMA table_info(qso)")]
    if "ext_id" not in cols:
        con.execute("ALTER TABLE qso ADD COLUMN ext_id TEXT")
    con.execute("CREATE INDEX IF NOT EXISTS qso_date ON qso(qso_date)")
    return con


def make_uid(rec):
    return "%s|%s|%s|%s" % (rec.get("CALL", "").upper(), rec.get("QSO_DATE", ""),
                            rec.get("TIME_ON", "")[:4], (rec.get("BAND") or "").lower())


def upsert(rec, ext_id=None, source=""):
    """Same QSO (call, date, minute, band) from two programs is stored once."""
    uid = make_uid(rec)
    with _lock:
        con = _db()
        if ext_id:   # an edit in the logger (time/band changed) replaces the old row
            con.execute("UPDATE qso SET deleted=1 WHERE ext_id=? AND uid<>?", (ext_id, uid))
        con.execute("""INSERT INTO qso(uid, call, qso_date, time_on, band, mode, data, source, received, deleted, ext_id)
                       VALUES(?,?,?,?,?,?,?,?,?,0,?)
                       ON CONFLICT(uid) DO UPDATE SET call=excluded.call, qso_date=excluded.qso_date,
                       time_on=excluded.time_on, band=excluded.band, mode=excluded.mode, data=excluded.data,
                       source=excluded.source, received=excluded.received, deleted=0,
                       ext_id=COALESCE(excluded.ext_id, qso.ext_id)""",
                    (uid, rec.get("CALL", "").upper(), rec.get("QSO_DATE", ""), rec.get("TIME_ON", ""),
                     (rec.get("BAND") or "").lower(), rec.get("MODE", ""), json.dumps(rec, ensure_ascii=False),
                     source, time.time(), ext_id))
        con.commit()
        con.close()
    return uid


def delete(ext_id=None, call=None, qso_date=None, time_on=None, window=3):
    """Delete a QSO the logger deleted - and the copy another program (WSJT-X)
    may have reported for the same contact."""
    from potacommon import base_call, minutes
    with _lock:
        con = _db()
        targets = []
        if ext_id:
            targets = con.execute("SELECT call, qso_date, time_on, band FROM qso WHERE ext_id=? AND deleted=0",
                                  (ext_id,)).fetchall()
        if not targets and call:
            targets = [((call or "").upper(), qso_date, time_on or "", None)]
        n = 0
        for c, d, t, band in targets:
            try:
                tm = minutes(d, (t or "0000"))
            except ValueError:
                continue
            for uid, c2, t2, b2 in con.execute("SELECT uid, call, time_on, band FROM qso WHERE qso_date=? AND deleted=0",
                                               (d,)).fetchall():
                try:
                    near = abs(minutes(d, t2 or "0000") - tm) <= window
                except ValueError:
                    near = False
                if near and base_call(c2) == base_call(c) and (band is None or b2 == band):
                    con.execute("UPDATE qso SET deleted=1 WHERE uid=?", (uid,))
                    n += 1
        con.commit()
        con.close()
    return n


def records(dates=None):
    con = _db()
    if dates:
        q = "SELECT data FROM qso WHERE deleted=0 AND qso_date IN (%s) ORDER BY qso_date, time_on" % ",".join("?" * len(dates))
        rows = con.execute(q, list(dates)).fetchall()
    else:
        rows = con.execute("SELECT data FROM qso WHERE deleted=0 ORDER BY qso_date, time_on").fetchall()
    con.close()
    return dedupe([json.loads(r[0]) for r in rows])


def dedupe(recs, window=3):
    """Drop a QSO that another program already reported within a few minutes
    (e.g. WSJT-X logs the start time, the logger the end time)."""
    from potacommon import base_call, minutes
    kept, last = [], {}
    for r in recs:
        try:
            t = minutes(r.get("QSO_DATE", ""), (r.get("TIME_ON") or "0000"))
        except ValueError:
            kept.append(r)
            continue
        k = (base_call(r.get("CALL")), (r.get("BAND") or "").lower())
        if k in last and t - last[k][0] <= window:
            prev = last[k][1]
            if len(r) > len(prev):          # keep the richer record
                kept[kept.index(prev)] = r
                last[k] = (last[k][0], r)
            continue
        kept.append(r)
        last[k] = (t, r)
    return kept


def recent(limit=200, since_date=None):
    con = _db()
    rows = con.execute("SELECT uid, data, source, received FROM qso WHERE deleted=0 %s ORDER BY qso_date DESC, time_on DESC LIMIT ?"
                       % ("AND qso_date>=?" if since_date else ""),
                       ([since_date] if since_date else []) + [limit]).fetchall()
    con.close()
    return [{"uid": u, "rec": json.loads(d), "source": s, "received": t} for u, d, s, t in rows]


def count():
    con = _db()
    n = con.execute("SELECT COUNT(*) FROM qso WHERE deleted=0").fetchone()[0]
    con.close()
    return n
