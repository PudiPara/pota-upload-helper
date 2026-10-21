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


def mode_of(rec):
    """The mode pota.app will store: SUBMODE when present (FT4), else MODE. Part of what makes
    a QSO distinct there (CALL, MODE, QSO_DATE, BAND, parks), so part of our duplicate key too."""
    return (rec.get("SUBMODE") or rec.get("MODE") or "").upper()


def make_uid(rec):
    return "%s|%s|%s|%s|%s" % (rec.get("CALL", "").upper(), rec.get("QSO_DATE", ""),
                               rec.get("TIME_ON", "")[:4], (rec.get("BAND") or "").lower(), mode_of(rec))


def upsert(rec, ext_id=None, source=""):
    """Same QSO (call, date, minute, band, mode) from two programs is stored once."""
    uid = make_uid(rec)
    with _lock:
        con = _db()
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
        con.commit()
        con.close()
    return uid


def known(uid):
    """True when this QSO was ever stored (deleted ones too)."""
    with _lock:
        con = _db()
        row = con.execute("SELECT 1 FROM qso WHERE uid=?", (uid,)).fetchone()
        con.close()
    return bool(row)


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
    """decision: 'yes' (spot candidate accepted), 'manual' (typed), 'no', or '' (undecided)."""
    for k in ("SIG", "SIG_INFO", "POTA_REF"):
        rec.pop(k, None)
    if decision in ("yes", "manual", "log") and parks:
        rec.update({"P2P_DECISION": decision, "SIG": "POTA", "SIG_INFO": ",".join(parks), "POTA_REF": ",".join(parks)})
    elif decision == "no":
        rec["P2P_DECISION"] = "no"
    else:
        rec.pop("P2P_DECISION", None)
    return rec


def set_p2p(uid, decision, parks, window=3):
    """Record the operator's P2P decision for a QSO - and for the copy another
    program may have reported for the same contact (WSJT-X vs the logger).
    -> list of updated records."""
    from potacommon import base_call, minutes, split_parks
    parks = split_parks(parks)
    updated = []
    with _lock:
        con = _db()
        row = con.execute("SELECT call, qso_date, time_on, band, mode FROM qso WHERE uid=? AND deleted=0", (uid,)).fetchone()
        if not row:
            con.close()
            return []
        c, d, t, band, mode = row
        try:
            tm = minutes(d, t or "0000")
        except ValueError:
            tm = None
        for u2, c2, t2, b2, m2, data in con.execute("SELECT uid, call, time_on, band, mode, data FROM qso WHERE qso_date=? AND deleted=0",
                                                  (d,)).fetchall():
            if u2 != uid:
                try:
                    near = tm is not None and abs(minutes(d, t2 or "0000") - tm) <= window
                except ValueError:
                    near = False
                if not (near and base_call(c2) == base_call(c) and b2 == band and m2 == mode):
                    continue
            rec = apply_decision(json.loads(data), decision, parks)
            con.execute("UPDATE qso SET data=? WHERE uid=?", (json.dumps(rec, ensure_ascii=False), u2))
            updated.append(rec)
        con.commit()
        con.close()
    return updated


def delete(ext_id=None, call=None, qso_date=None, time_on=None, window=3):
    """Delete a QSO the logger deleted - and the copy another program (WSJT-X)
    may have reported for the same contact."""
    from potacommon import base_call, minutes
    with _lock:
        con = _db()
        targets = []
        if ext_id:
            targets = con.execute("SELECT call, qso_date, time_on, band, mode FROM qso WHERE ext_id=? AND deleted=0",
                                  (ext_id,)).fetchall()
        if not targets and call:
            targets = [((call or "").upper(), qso_date, time_on or "", None, None)]
        n = 0
        for c, d, t, band, mode in targets:
            try:
                tm = minutes(d, (t or "0000"))
            except ValueError:
                continue
            for uid, c2, t2, b2, m2 in con.execute("SELECT uid, call, time_on, band, mode FROM qso WHERE qso_date=? AND deleted=0",
                                               (d,)).fetchall():
                try:
                    near = abs(minutes(d, t2 or "0000") - tm) <= window
                except ValueError:
                    near = False
                if near and base_call(c2) == base_call(c) and (band is None or b2 == band) and (mode is None or m2 == mode):
                    con.execute("UPDATE qso SET deleted=1 WHERE uid=?", (uid,))
                    n += 1
        con.commit()
        con.close()
    return n


def update(uid, fields):
    """Edit one stored QSO: CALL, TIME_ON, BAND, MODE and/or "parks" (their park, the operator's
    decision). The key may change, so the old row is retired and the record stored again.
    -> the new uid, or None when the QSO is gone."""
    from potacommon import split_parks
    with _lock:
        con = _db()
        row = con.execute("SELECT data, ext_id, source FROM qso WHERE uid=? AND deleted=0", (uid,)).fetchone()
        con.close()
    if not row:
        return None
    rec, ext_id, source = json.loads(row[0]), row[1], row[2]
    for k in ("CALL", "TIME_ON", "BAND", "MODE"):
        if k in fields:
            rec[k] = fields[k]
    if "MODE" in fields:
        rec.pop("SUBMODE", None)
    if "parks" in fields:
        parks = split_parks(fields["parks"])
        apply_decision(rec, "manual" if parks else "no", parks)
    new_uid = make_uid(rec)
    if new_uid != uid:
        with _lock:
            con = _db()
            con.execute("UPDATE qso SET deleted=1 WHERE uid=?", (uid,))
            con.commit()
            con.close()
    return upsert(rec, ext_id, source)


def delete_uid(uid):
    """Soft-delete one stored QSO. -> True when it existed."""
    with _lock:
        con = _db()
        n = con.execute("UPDATE qso SET deleted=1 WHERE uid=? AND deleted=0", (uid,)).rowcount
        con.commit()
        con.close()
    return n > 0


def delete_activation(qso_date):
    """Drop (soft-delete) the activation QSOs of one UTC day - those with my park in them, which is
    what the アップロード作成 list shows. -> how many."""
    n = 0
    with _lock:
        con = _db()
        for uid, data in con.execute("SELECT uid, data FROM qso WHERE qso_date=? AND deleted=0", (qso_date,)).fetchall():
            if json.loads(data).get("MY_SIG_INFO"):
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


def between(t0, t1):
    """Records whose time is within [t0, t1] (minutes, see potacommon.minutes), deduped."""
    from potacommon import minutes
    out = []
    for r in records():
        try:
            t = minutes(r.get("QSO_DATE", ""), r.get("TIME_ON") or "0000")
        except ValueError:
            continue
        if t0 <= t <= t1:
            out.append(r)
    return out


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
        # my parks are part of the key: the same station worked again minutes later from another
        # park is a second QSO, not the logger's copy of the first one
        k = (base_call(r.get("CALL")), (r.get("BAND") or "").lower(), mode_of(r), r.get("MY_SIG_INFO") or "")
        if k in last and t - last[k][0] <= window:
            prev = last[k][1]
            if (bool(r.get("P2P_DECISION")), len(r)) > (bool(prev.get("P2P_DECISION")), len(prev)):   # keep the richer record
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
