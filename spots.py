"""Everything about pota.app activator spots - the one place that knows what a spot means.

  parks_of(spot)              the park(s) a spot announces: its reference plus references in the comment
  their_parks_at(spots, t)    which park(s) a station was at around minute t, and whether that is certain
  candidate_info(rec)         the P2P candidate for a QSO record (recorded spots + pota.app spot history)
  tag_candidate(rec)          puts that candidate on the record (P2P_CANDIDATE / P2P_NOTE)
  park_info(ref), common_locations(refs)   a park as pota.app describes it; where several parks meet
  summarize(spots)            one row per station for the アクティベート中 page (2fer, band, mode group)
  SpotLogger                  records spots every minute while activating (spots-YYYYMMDD.jsonl) and the
                              session window (sessions.json) that the builder uses to find activation QSOs
  load_spots(), load_sessions()   those files, parsed; SESSION_MARGIN widens each session window

Time rules live here and nowhere else:
  SPOT_BEFORE / SPOT_AFTER   a spot this long before / after a QSO still describes the station
  TWOFER_GAP                 two parks announced this close together are one station in two parks (2fer)
"""
import datetime as dt
import glob
import json
import os
import re
import threading
import time
from collections import defaultdict
from urllib.parse import quote

from i18n import t
from locations import NAMES as LOCATION_NAMES
from potacommon import (band_from_khz, base_call, data_path, fetch_json, iso_minutes, mode_group, parks_in,
                        read_json, rec_minutes, split_parks, utc_minutes, utc_stamp, write_json)

SPOT_BEFORE = 30       # minutes
SPOT_AFTER = 10        # minutes
TWOFER_GAP = 15        # minutes
SESSION_MARGIN = 5     # minutes a QSO may fall before a session's start or after its end


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------- reading a spot
def parks_of(spot):
    """['JP-1788', 'JP-0157'] - the reference first, then references written in the comment ("2fer JP-0157")."""
    refs = [(spot.get("reference") or "").upper()] + parks_in(spot.get("comments"))
    return [r for i, r in enumerate(refs) if r and r not in refs[:i]]


def spot_time(spot):
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return dt.datetime.strptime((spot.get("spotTime") or "")[:19], fmt).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------- which park was a station at
def their_parks_at(spots, t_min):
    """spots: [(minute, [parks], raw)] for one station. -> (parks, sure).
    sure=False when several parks come from separate spots: could be a 2fer, could be a rover moving on."""
    best, together = {}, set()
    for m, parks, _ in spots:
        if t_min - SPOT_BEFORE <= m <= t_min + SPOT_AFTER:
            if len(parks) > 1:
                together.add(frozenset(parks))
            for p in parks:
                best[p] = min(best.get(p, 999), abs(m - t_min))
    if not best:
        return [], True
    near = min(best.values())
    res = sorted(p for p, d in best.items() if d <= near + TWOFER_GAP)
    sure = len(res) == 1 or any(set(res) <= g for g in together)
    return res, sure


FRESH = 10                # minutes: a spot this close to the QSO means they are still at the park
QRT = re.compile(r"\bQRT\b", re.I)


def candidate_info(rec):
    """The P2P candidate for a QSO that just arrived, and whether it is safe to accept without asking.
    -> {"parks": [...], "auto": bool, "note": "" | "qrt" | "stale" | "unsure"}
    parks: where the station was spotted around the QSO (recorded spots) plus its pota.app spot history.
    auto only when nothing is doubtful: no QRT from the activator before the QSO (they may be calling
    from home now), a spot within FRESH minutes, and the parks not pieced together from separate spots."""
    out = {"parks": [], "auto": False, "note": ""}
    t_min = rec_minutes(rec)
    if t_min is None:
        return out
    recorded = load_spots().get(base_call(rec.get("CALL")), [])
    parks, sure = their_parks_at(recorded, t_min)
    near = [(m, raw) for m, _, raw in recorded if t_min - SPOT_BEFORE <= m <= t_min + SPOT_AFTER]
    events = [(m, bool(QRT.search(raw.get("comments") or "") and _by_activator(raw))) for m, raw in near]
    refd = [raw for _, raw in near if raw.get("reference")]
    if refd:
        raw = max(refd, key=lambda r: r.get("spotTime") or "")
        h = history_info(raw.get("activator") or rec.get("CALL"), raw["reference"], wait=True) or {}
        parks += [p for p in h.get("parks") or [] if p not in parks]
        events += [(m, q) for m, q in h.get("times") or [] if t_min - SPOT_BEFORE <= m <= t_min + SPOT_AFTER]
    if not parks:
        return out
    before = sorted(e for e in events if e[0] <= t_min)
    qrt = bool(before) and before[-1][1]                 # their last word before the QSO was QRT
    fresh = any(abs(m - t_min) <= FRESH for m, q in events if not q)
    out.update(parks=parks, auto=not qrt and fresh and sure,
               note="qrt" if qrt else "stale" if not fresh else "unsure" if not sure else "")
    return out


def tag_candidate(rec):
    """Put the P2P candidate on a received record (P2P_CANDIDATE, and P2P_NOTE when it is doubtful).
    -> candidate_info(rec)."""
    info = candidate_info(rec)
    if info["parks"]:
        rec["P2P_CANDIDATE"] = ",".join(info["parks"])
        if info["note"]:
            rec["P2P_NOTE"] = info["note"]          # why this one is asked even with 自動 on
    return info


def _by_activator(raw):
    return base_call(raw.get("spotter")) == base_call(raw.get("activator"))


# ---------------------------------------------------------------- parks that say they don't overlap
NO_OVERLAP = re.compile(r"(?:does\s*n[o']?t|do\s*n[o']?t|not|no)\s+overlap|重なる[^。\n]{0,12}(?:ありません|ない)|重なりません|重ならない|重複しません|重複しない", re.I)


def says_no_overlap(comment, other):
    """True when a park's pota.app comment names `other` in a sentence saying the two don't overlap
    ("This park does NOT overlap with JP-1296." / 「…(JP-1296)と重なる指定地域はありません。」)."""
    for sentence in re.split(r"[。\n]|(?<=\.)\s", comment or ""):
        if other.upper() in sentence.upper() and NO_OVERLAP.search(sentence):
            return True
    return False


# ---------------------------------------------------------------- a station's spot history on pota.app
# pota.app keeps every spot of an activator at a park (spot/comments/{activator}/{reference}) and shows the
# activator's own latest comment apart from the newest spot - that is where "2-fer: X Y" survives after
# RBN or PSKReporter respot the station with their own comment.
HISTORY_TTL = 600         # seconds a station's history result is kept
HISTORY_WINDOW = 180      # minutes: older comments belong to another activation
FER = re.compile(r"\d\s*-?\s*fer|twofer|threefer", re.I)
_hist_lock = threading.Lock()
_hist = {}                # (ACTIVATOR, REFERENCE) -> (fetched_at, parks)
_hist_queue = []
_hist_worker = None


def fetch_history(activator, reference):
    try:
        return fetch_json("spot/comments/%s/%s" % (quote(activator, safe=""), reference), timeout=8) or []
    except Exception:
        return []


def parks_from_history(hist, activator, reference, now=None):
    """[reference, ...more parks]: references named in the activator's own comments of the recent
    history (any), and in other spotters' comments only when they say 2fer/3fer - a hunter's
    "P2P from US-1234" names the hunter's park, not the activator's."""
    now = now or now_utc()
    out = [reference.upper()]
    for mine in (True, False):
        for x in hist:
            tm = spot_time(x)
            if not tm or (now - tm).total_seconds() > HISTORY_WINDOW * 60:
                continue
            own = (x.get("spotter") or "").upper() == activator.upper()
            if own != mine or (not own and not FER.search(x.get("comments") or "")):
                continue
            for p in parks_in(x.get("comments")):
                if p not in out:
                    out.append(p)
    return out


def history_parks(activator, reference, wait=False):
    h = history_info(activator, reference, wait)
    return None if h is None else h["parks"]


def _digest(hist, activator, reference):
    """{"parks": [...], "times": [(minute, is_qrt_by_the_activator)]} from a spot history."""
    times = []
    for x in hist:
        tm = spot_time(x)
        if tm:
            own = base_call(x.get("spotter")) == base_call(activator)
            times.append((utc_minutes(tm), bool(own and QRT.search(x.get("comments") or ""))))
    return {"parks": parks_from_history(hist, activator, reference), "times": times}


def history_info(activator, reference, wait=False):
    """A station's pota.app history digested, cached HISTORY_TTL seconds. wait=False (the
    アクティベート中 page) schedules the fetch on a worker and returns None until it is in;
    wait=True (a QSO just arrived) fetches now."""
    key = ((activator or "").upper(), (reference or "").upper())
    if not key[0] or not key[1]:
        return None
    with _hist_lock:
        e = _hist.get(key)
        if e and time.time() - e[0] < HISTORY_TTL:
            return e[1]
    if wait:
        info = _digest(fetch_history(*key), *key)
        with _hist_lock:
            _hist[key] = (time.time(), info)
        return info
    with _hist_lock:
        if key not in _hist_queue:
            _hist_queue.append(key)
        _start_history_worker()
    return None


def _start_history_worker():
    global _hist_worker
    if _hist_worker and _hist_worker.is_alive():
        return
    _hist_worker = threading.Thread(target=_drain_history, daemon=True)
    _hist_worker.start()


def _drain_history():
    while True:
        with _hist_lock:
            if not _hist_queue:
                return
            key = _hist_queue.pop(0)
        info = _digest(fetch_history(*key), *key)
        with _hist_lock:
            _hist[key] = (time.time(), info)


# ---------------------------------------------------------------- the files the logger writes
def load_spots():
    """{base call: [(minute, [parks], raw)]} from every spots-*.jsonl in the data dir."""
    out = defaultdict(list)
    for f in sorted(glob.glob(data_path("spots-*.jsonl"))):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    s = json.loads(line)
                    m = iso_minutes(s.get("spotTime") or s["seen"])
                except Exception:
                    continue
                if s.get("parks"):
                    out[s["base"]].append((m, s["parks"], s))
    return out


def load_sessions():
    """[(start minute - SESSION_MARGIN, end minute + SESSION_MARGIN, [my parks])] from sessions.json."""
    return [(iso_minutes(s["start"]) - SESSION_MARGIN, iso_minutes(s["end"]) + SESSION_MARGIN, s["parks"])
            for s in read_json(data_path("sessions.json"), []) if s.get("start") and s.get("end")]


# ---------------------------------------------------------------- a park as pota.app describes it
_parks = {}                # reference -> park_info, for the run of the app


def park_info(ref):
    """{name, grid, comments, locations: [{code, name}]} - name is pota.app's (English) park name, the same
    for every user; locations are the prefectures / states it lies in."""
    if ref not in _parks:
        try:
            p = fetch_json("park/%s" % ref, timeout=8) or {}
        except Exception:
            return {"name": "", "grid": "", "comments": "", "locations": []}     # asked again next time
        # names from the shipped table: pota.app sorts locationDesc by code and locationName by name,
        # so pairing them by position mixes them up (US-4239: US-ND would be "New York")
        codes = [c.strip() for c in (p.get("locationDesc") or "").split(",") if c.strip()]
        _parks[ref] = {"name": p.get("name") or "", "grid": p.get("grid6") or "",
                       "comments": p.get("parkComments") or "",
                       "locations": [{"code": c, "name": LOCATION_NAMES.get(c, "")} for c in codes]}
    return _parks[ref]


def common_locations(refs):
    """Where the operator can stand for these parks together: {"options": [{code, name}] the locations
    every park has in common (one = fixed, several = the operator picks, none = they don't overlap),
    "multi": parks spanning several locations, "apart": [[a, b]] pairs pota.app says don't overlap}."""
    parks = split_parks(refs)
    info = {ref: park_info(ref) for ref in parks}
    common = None
    for ref in parks:
        codes = [loc["code"] for loc in info[ref]["locations"]]
        if codes:                          # unknown to pota.app: no constraint from it
            common = codes if common is None else [c for c in common if c in codes]
    names = {loc["code"]: loc["name"] for ref in parks for loc in info[ref]["locations"]}
    apart = [[a, b] for i, a in enumerate(parks) for b in parks[i + 1:]
             if says_no_overlap(info[a]["comments"], b) or says_no_overlap(info[b]["comments"], a)]
    return {"options": [{"code": c, "name": names.get(c, "")} for c in (common or [])],
            "multi": [ref for ref in parks if len(info[ref]["locations"]) > 1], "apart": apart}


# ---------------------------------------------------------------- who is on the air now
CONTINENTS = {   # ISO 3166 alpha-2 (the park prefix) -> continent, for the アクティベート中 region filter
    "as": "AF AM AZ BH BD BT BN KH CN CY GE HK IN ID IR IQ IL JP JO KZ KW KG LA LB MO MY MV MN MM NP KP OM PK PS PH QA SA SG KR LK SY TW TJ TH TL TR TM AE UZ VN YE",
    "eu": "AL AD AT AX BY BE BA BG HR CZ DK EE FO FI FR DE GI GR GG HU IS IE IM IT JE XK LV LI LT LU MT MD MC ME NL MK NO PL PT RO RU SM RS SK SI ES SJ SE CH UA GB VA",
    "na": "AG AI AW BB BL BM BQ BS BZ CA CR CU CW DM DO GD GL GP GT HN HT JM KN KY LC MF MQ MS MX NI PA PM PR SV SX TC TT US VC VG VI",
    "sa": "AR BO BR CL CO EC FK GF GY PE PY SR UY VE",
    "af": "DZ AO BJ BW BF BI CV CM CF TD KM CD CG CI DJ EG GQ ER SZ ET GA GM GH GN GW KE LS LR LY MG MW ML MR MU YT MA MZ NA NE NG RE RW SH ST SN SC SL SO ZA SS SD TZ TG TN UG EH ZM ZW",
    "oc": "AS AU CK FJ PF GU KI MH FM NR NC NZ NU NF MP PW PG PN WS SB TK TO TV VU WF",
}
_CONTINENT_OF = {cc: k for k, v in CONTINENTS.items() for cc in v.split()}


def continent_of(country):
    """'as' | 'eu' | 'na' | 'sa' | 'af' | 'oc' | '' for a park prefix."""
    return _CONTINENT_OF.get((country or "").upper(), "")


def summarize(spots, now=None, history=None):
    """One row per station from api.pota.app/spot/activator, newest first: the parks of its spots
    of the last TWOFER_GAP minutes merged (more than one = 2fer), band and mode group computed here
    so the UI only displays. history(activator, reference) -> parks or None adds what the station's
    spot history says; None marks the row pending (the page asks again shortly)."""
    now = now or now_utc()
    by = {}
    for s in spots:
        tm = spot_time(s)
        base = base_call(s.get("activator"))
        if tm and base:
            by.setdefault(base, []).append((tm, s, parks_of(s)))
    out = []
    for base, items in by.items():
        items.sort(key=lambda x: x[0], reverse=True)
        t0, newest, parks = items[0]
        parks = list(parks)
        for tm, _, refs in items[1:]:
            if (t0 - tm).total_seconds() <= TWOFER_GAP * 60:
                parks += [r for r in refs if r not in parks]
        pending = False
        if history:
            hp = history(newest.get("activator"), newest.get("reference"))
            pending = hp is None
            parks += [p for p in (hp or []) if p not in parks]
        out.append({"call": newest.get("activator") or base, "base": base, "parks": parks, "twofer": len(parks) > 1,
                    "country": parks[0].split("-")[0] if parks else "",      # park prefix = ISO 3166 alpha-2
                    "region": continent_of(parks[0].split("-")[0]) if parks else "",
                    "location": newest.get("locationDesc") or "",            # "JP-13", "US-NY,US-NJ"
                    "freq": newest.get("frequency"), "band": band_from_khz(newest.get("frequency")),
                    "mode": newest.get("mode") or "", "group": mode_group(newest.get("mode")),
                    "time": t0.strftime("%H:%M"), "ago": max(0, int((now - t0).total_seconds() // 60)),
                    "comments": newest.get("comments") or "", "spots": len(items), "pending": pending})
    out.sort(key=lambda e: (e["ago"], e["base"]))
    return out


# ---------------------------------------------------------------- recording while activating
class SpotLogger:
    """Polls api.pota.app/spot/activator every `interval` seconds while you activate, so the other
    station's park(s) are still known after they QRT. Callbacks run on the worker thread:
         on_activator(time_str, activator, parks_list, freq, mode, is_2fer)   a station's parks grew
         on_status(message)
    Also keeps the session window (start/end, my parks) in sessions.json and refreshes hunter.json."""

    def __init__(self, parks, call, interval=60, on_activator=None, on_status=None):
        self.parks = split_parks(parks)
        if not self.parks:
            raise ValueError(t("spot.badPark"))
        self.call = call.upper().strip()
        self.interval = max(15, int(interval))
        self.on_activator = on_activator or (lambda *a: None)
        self.on_status = on_status or (lambda *a: None)
        self._stop = threading.Event()
        self._thread = None
        self.session = None

    # ----- session bookkeeping -----
    def _update_session(self):
        path = data_path("sessions.json")
        sessions = read_json(path, [])
        for s in sessions:
            if s.get("id") == self.session["id"]:
                s.update(self.session)
                break
        else:
            sessions.append(dict(self.session))
        write_json(path, sessions)

    # ----- control -----
    def start(self, resume=None):
        """resume: {"id", "start"} of the session this app was recording before it was closed or
        crashed - the same session goes on (same id in sessions.json, the clock keeps its start)."""
        os.makedirs(data_path(), exist_ok=True)
        stamp = utc_stamp()      # seconds: the elapsed clock starts at 0
        self.session = {"id": (resume or {}).get("id") or now_utc().strftime("%Y%m%d%H%M%S"), "call": self.call,
                        "parks": self.parks, "start": (resume or {}).get("start") or stamp, "end": stamp}
        self._update_session()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self.session:
            self.session["end"] = utc_stamp()
            self._update_session()

    def running(self):
        return bool(self._thread and self._thread.is_alive())

    # ----- worker -----
    def _run(self):
        from builder import load_hunter   # local import: avoids a cycle
        mine = base_call(self.call)
        seen, known, polls = {}, {}, 0
        while not self._stop.is_set():
            now = now_utc()
            try:
                spots = fetch_json("spot/activator")
                self.on_status(t("spot.updated", time=now.strftime("%H:%M"), n=len(spots)))
            except Exception as e:
                spots = []
                self.on_status(t("spot.fetchFail", time=now.strftime("%H:%M"), err=e))
            path = data_path("spots-%s.jsonl" % now.strftime("%Y%m%d"))
            with open(path, "a", encoding="utf-8") as fh:
                for s in spots:
                    key = s.get("spotId")
                    if seen.get(key) == s.get("spotTime"):
                        continue
                    seen[key] = s.get("spotTime")
                    act = base_call(s.get("activator"))
                    if act == mine:
                        continue
                    refs = parks_of(s)
                    rec = {"seen": utc_stamp(now), "spotTime": s.get("spotTime"),
                           "activator": s.get("activator"), "base": act, "parks": refs,
                           "frequency": s.get("frequency"), "mode": s.get("mode"),
                           "comments": s.get("comments"), "spotId": key}
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    before = known.setdefault(act, set())
                    added = [r for r in refs if r not in before]
                    if added:
                        before.update(added)
                        self.on_activator(now.strftime("%H:%M"), s.get("activator"), sorted(before),
                                          s.get("frequency"), s.get("mode"), len(before) > 1)
            self.session["end"] = utc_stamp(now)
            self._update_session()
            if polls % 10 == 0:
                try:
                    load_hunter(self.call, False, log=self.on_status)
                except Exception as e:
                    self.on_status(t("spot.hunterFail", err=e))
            polls += 1
            self._stop.wait(self.interval)
