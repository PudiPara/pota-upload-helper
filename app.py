#!/usr/bin/env python3
"""Potaroo - desktop app (pywebview: WebKit on macOS, Edge WebView2 on Windows).

This file is the bridge between the UI (ui/) and the modules that do the work. Every public
method of Api is callable from JavaScript as window.pywebview.api.<name>() and returns plain
JSON-able data. Rules of the house:
  * Api decides nothing about radio: spots.py knows spots and 2fer, qsolog.py knows the log and
    the operator's decisions, builder.py knows upload files, receiver.py knows UDP, updater.py
    knows GitHub releases, window.py knows the bar window.
  * Errors come back as {"ok": False, "error": text}; text is translated with i18n.t().
  * Nothing here writes the logger's log.
"""
import copy
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser

import webview

import i18n
import mypota
import qsolog
import updater
import jma
import weather
from builder import activation_days, build, find_activation_qsos, list_activations
from i18n import t
from potacommon import (APP_NAME, CALL_RE, DEFAULT_OUT, VERSION, adif_mode, band_name, base_call, clock_skew, data_path, data_version, fetch_json, grid_center,
                        iso_date,
                        iso_minutes, load_settings, lock_instance, count_key, mode_known, mode_of, my_call, my_parks_of, pota_events, read_adif, rec_minutes, resource,
                        save_settings, split_parks, LOG_NAME, setup_log)
from qsolog import decided_parks
from receiver import DEFAULT_LISTENERS, Receiver, describe_state
from spots import (SESSION_MARGIN, SpotLogger, clear_records, common_locations, countries, example_parks, history_parks,
                   distance_km, park_info, parks_middle, park_status, linear_parks, shift_hours, shipped_parks, summarize, tag_candidate)
from window import BarMode, set_zoom

SETTINGS_KEYS = ("call", "calls", "op_list", "parks", "prefix", "adif", "out", "source", "lang", "country", "terms_accepted", "guide_seen", "beta", "p2p_auto", "lookup", "on_top", "font_scale", "theme", "bar_style", "dist_unit")   # "live" is set by start_live/finish_live only
DATE_RE = re.compile(r"\d{8}")
LOOK_SCALES = (1, 1.15, 1.3)            # 設定 → 表示 → 文字の大きさ
LOOK_THEMES = ("", "light", "dark")     # 設定 → 表示 → 配色 ("" = the OS)
LOOK_BARS = ("", "compact", "square")   # 設定 → ウインドウ → バーの形 ("" = the standard wide one)
SPOT_INTERVAL = 60       # seconds between pota.app spot polls while recording


def clean_calls(calls, call):
    """The saved callsigns, uppercase and valid, the chosen one first ([] before any is saved)."""
    out = []
    for c in [call] + list(calls or []):
        c = (c or "").strip().upper()
        if c and CALL_RE.fullmatch(c) and c not in out:
            out.append(c)
    return out


def session_since(start_iso):
    """The minute a session's QSOs may start (its start, less the margin spots.py allows)."""
    return iso_minutes(start_iso) - SESSION_MARGIN


def open_path(path):
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif os.name == "nt":
        os.startfile(path)  # noqa
    else:
        subprocess.Popen(["xdg-open", path])


def qso_event(rec, uid=None, hunted=None):
    """What the UI needs to draw one QSO row: identity, the spot candidate, the decision so far, and
    which of their parks the operator had not hunted before this QSO (hunted = mypota.first_hunted)."""
    ts = (rec.get("QSO_DATE") or "") + (rec.get("TIME_ON") or "").ljust(6, "0")
    theirs = split_parks(rec.get("P2P_CANDIDATE")) + decided_parks(rec)[1]
    return {"action": "upsert", "uid": uid or qsolog.make_uid(rec), "call": rec.get("CALL"),
            "date": rec.get("QSO_DATE"), "time": (rec.get("TIME_ON") or "")[:4], "band": rec.get("BAND", ""),
            "ts": ts,                                                     # sort key, to the second
            "new": mypota.new_parks(list(dict.fromkeys(theirs)), hunted, ts),
            "mode": mode_of(rec), "decision": rec.get("P2P_DECISION") or "", "parks": decided_parks(rec)[1],
            "candidate": split_parks(rec.get("P2P_CANDIDATE")), "my": my_parks_of(rec),
            # for the 10-QSO count: one key per park ("*" when the QSO has none of its own), the UI counts the
            # distinct keys of today at the session's location (count_key: what pota.app counts once)
            "ck": {p: count_key(rec, p) for p in my_parks_of(rec) or ["*"]},
            "note": rec.get("P2P_NOTE") or "",
            # to their parks (the decided ones, else the spot's candidate) from mine
            "km": distance_km(my_parks_of(rec), qsolog.their_parks_now(rec))}


class Api:
    # All state is private (underscore). pywebview exposes every public attribute of this object to
    # JavaScript and (6.x) walks them recursively; on Windows that walk entered the WinForms window
    # behind Api.bar and froze the app. tests/test_api_private.py keeps it that way.
    _weather = None                    # weather.summarize() at the parks while recording, + seq and new (alerts to notify)
    _wx_stop = threading.Event()       # set = stop looking (each recording gets its own)
    _wx_seq = 0                        # every look's number, counting on over recordings
    _award_base = None                 # the achievement keys reached when recording started (mypota.awards)
    _award_lock = threading.Lock()     # two listeners (WSJT-X and the logger) report the same QSO at once
    def __init__(self):
        self._window = None
        self._bar = None               # BarMode, once the window exists
        self._busy = set()             # what the page is in the middle of ("edit": the QSO editor is open)
        self._allow_close = False      # the operator confirmed closing (quit_app)
        self._logger = None            # SpotLogger while an activation is being recorded
        self._receiver = None
        self._events = []              # spots seen while recording, for the live view
        self._qso_events = []          # QSOs received from loggers, for the live view
        self._status = ""
        self._recv_status = {}         # listener name -> state dict (codes; see receiver.describe_state)
        self._lock = threading.Lock()
        self._locs = {}               # {park: location} of the running session (parks across prefectures)
        self._operator = ""           # a club station's operator (OPERATOR) for QSOs whose logger sends none
        self._hunted = (0, None)      # (computed at, mypota.first_hunted) - the "New" marks
        self._spots_cache = (0, [])   # (fetched at, raw spots) for the アクティベート中 page
        self.start_receiver()
        self._resume_live()

    def _resume_live(self):
        """The app was closed (or crashed) while recording: pick the session up again, so the
        運用中 page and its QSO list come back as they were."""
        live = load_settings().get("live") or {}
        if not live.get("parks") or not live.get("start"):
            return
        self._logger = SpotLogger(live["parks"], live.get("call") or my_call(), SPOT_INTERVAL,
                                  on_activator=self._on_spot, on_status=self._on_status)
        self._logger.start(resume={"id": live.get("id"), "start": live["start"]})
        self._locs = live.get("locs") or {}
        self._operator = live.get("operator") or ""
        self._start_weather(live["parks"])
        self._start_awards()

    def _start_weather(self, parks):
        """Look at the weather at the parks now and every weather.EVERY while this recording lasts."""
        self._wx_stop.set()
        self._wx_stop = stop = threading.Event()
        self._weather = None
        at = parks_middle(parks)
        if at:
            japan = any(p.startswith("JP-") for p in parks)      # the JMA's warnings too (jma.py)
            threading.Thread(target=self._weather_loop, args=(at, stop, japan), daemon=True).start()

    def _weather_loop(self, at, stop, japan=False):
        """Open-Meteo every weather.EVERY. In Japan the JMA's warnings too: read again as soon as the JMA's feed lists a
        new bulletin from the park's office (looked at every jma.FEED_EVERY), and every weather.JMA_EVERY anyway, whatever
        Open-Meteo did (a failed look keeps its last answer, or none yet: the JMA's warnings still go out)."""
        first, om, om_at, jma_at = True, None, 0.0, 0.0
        while not stop.is_set():
            try:
                now = time.time()
                slow = now - om_at >= weather.EVERY - 5   # Open-Meteo's turn (and the JMA's forecast's)
                issued = False
                if japan:
                    try:
                        issued = jma.feed_news(*at)
                    except Exception as e:     # the feed is a shortcut: the JMA_EVERY look still comes
                        logging.warning("jma feed: %s", e)
                if not (slow or issued or (japan and now - jma_at >= weather.JMA_EVERY - 5)):
                    stop.wait(jma.FEED_EVERY)
                    continue
                if slow:
                    try:
                        om, om_at = weather.fetch(*at), time.time()
                    except Exception as e:     # no weather is no reason to bother the operator
                        logging.warning("weather: %s", e)
                        om_at = time.time()    # the next try at the next EVERY, not at the JMA's next look
                if om is None and not japan:
                    stop.wait(weather.EVERY)
                    continue
                w = dict(om or {"alerts": {}, "hours": [], "sun": None})   # Japan with no Open-Meteo yet: the JMA's only
                if japan:                      # the JMA's warnings, and no alerts of the forecast's own (weather.add_jma)
                    try:
                        found = jma.warnings(*at)
                    except Exception as e:     # keep the last answer: a hiccup must not re-notify the same warnings
                        logging.warning("jma: %s", e)
                        found = (self._weather or {}).get("jma") or []
                    try:
                        where = jma.place(*at)
                    except Exception:          # the warnings still show, without the name
                        where = None
                    weather.add_jma(w, found, where)
                    jma_at = now
                    last_fc = (self._weather or {}).get("jma_forecast")
                    try:                       # the JMA's forecast for the 天気 tab: at Open-Meteo's pace (it changes a few times a day)
                        weather.add_jma_forecast(w, jma.forecast(*at) if slow or not last_fc else last_fc)
                    except Exception as e:
                        logging.warning("jma forecast: %s", e)
                        weather.add_jma_forecast(w, last_fc)
                Api._wx_seq += 1                # never repeats across recordings: a window that saw the last one takes this
                with self._lock:
                    if not stop.is_set():
                        self._weather = dict(w, seq=Api._wx_seq, first=first, new=weather.news(self._weather, w))
                        first = False
            except Exception as e:
                logging.warning("weather: %s", e)
            stop.wait(jma.FEED_EVERY if japan else weather.EVERY)

    def _first_hunted(self, max_age=30):
        """mypota.first_hunted over the app log, recomputed at most every max_age seconds."""
        at, first = self._hunted
        if time.time() - at > max_age:
            first = mypota.first_hunted(qsolog.records())
            self._hunted = (time.time(), first)
        return first

    def _event(self, rec, uid=None):
        return qso_event(rec, uid, self._first_hunted())

    def _stop_logger(self):
        """Stop recording and forget the running session. -> its session dict, or None."""
        if not self._logger:
            return None
        self._logger.stop()
        self._wx_stop.set()
        self._weather = None
        sess = dict(self._logger.session)
        self._logger = None
        save_settings({"live": None})
        return sess

    def _recording(self):
        return bool(self._logger and self._logger.running())

    # ================================================================ settings
    def get_state(self):
        s = load_settings()
        live = ({"parks": self._logger.parks, "start": self._logger.session["start"], "locs": self._locs,
                 "operator": self._operator, "shifts": shift_hours(self._logger.parks), "weather": self._weather}
                if self._recording() else None)
        year = time.gmtime().tm_year
        calls = clean_calls(s.get("calls"), s.get("call"))
        lookup = s.get("lookup") or ["qrz"]
        return {"version": VERSION, "data_version": data_version(), "call": calls[0] if calls else "", "calls": calls, "operators": s.get("operators") or {}, "op_list": clean_calls(s.get("op_list"), ""), "events": pota_events(year) + pota_events(year + 1), "parks": s.get("parks", ""),
                "prefix": "home" if s.get("prefix", "home") else "", "adif": s.get("adif", ""), "out": s.get("out", DEFAULT_OUT),
                "source": s.get("source", "app"), "live": live, "bar": bool(self._bar and self._bar.active),
                "listeners": self.listeners(), "hamlog": sys.platform == "win32", "lang": s.get("lang") or "", "langs": i18n.available(),
                "country": s.get("country") or "", "countries": countries(),
                "terms_accepted": s.get("terms_accepted") or "", "guide_seen": bool(s.get("guide_seen")), "beta": bool(s.get("beta")), "p2p_auto": bool(s.get("p2p_auto")), "on_top": bool(s.get("on_top")), **self._look(s), "dist_unit": s.get("dist_unit") or "", "bar_on_top": s.get("bar_on_top", True) is not False,
                "lookup": lookup if isinstance(lookup, list) else [lookup],
                "log_count": qsolog.count(), "receiver": self._receiver_texts(), "mypota": mypota.status()}

    def examples(self, country):
        """The example parks of the operator's country for the UI copy; the Python side's strings use them too."""
        i18n.examples = example_parks(country or "")
        return i18n.examples

    def save(self, data):
        keep = {k: v for k, v in data.items() if k in SETTINGS_KEYS}
        if "lang" in keep:
            keep["lang"] = i18n.set_lang(keep["lang"])
        if "p2p_auto" in keep:
            keep["p2p_auto"] = bool(keep["p2p_auto"])
        if "font_scale" in keep and keep["font_scale"] not in LOOK_SCALES:
            keep.pop("font_scale")
        if "font_scale" in keep and self._bar:
            self._bar.set_zoom(keep["font_scale"])            # both windows, now
        if "bar_style" in keep and keep["bar_style"] not in LOOK_BARS:
            keep.pop("bar_style")
        if "theme" in keep and keep["theme"] not in LOOK_THEMES:
            keep.pop("theme")
        if "dist_unit" in keep and keep["dist_unit"] not in ("km", "mi"):
            keep.pop("dist_unit")
        if "op_list" in keep:                     # a club station's operators (設定 → 基本), offered at the start
            keep["op_list"] = clean_calls(keep["op_list"], "")
        if "calls" in keep or "call" in keep:
            s = load_settings()
            calls = clean_calls(keep.get("calls", s.get("calls")), keep.get("call", s.get("call")))
            keep.update(calls=calls, call=calls[0] if calls else "")
        save_settings(keep)
        return True

    # ================================================================ UDP listeners
    def listeners(self):
        return load_settings().get("listeners") or copy.deepcopy(DEFAULT_LISTENERS)

    def save_listeners(self, items):
        clean = []
        for it in items:
            if it.get("kind") == "hamlog":            # asks HAMLOG through its window messages: no port
                clean.append({"name": (it.get("name") or "Turbo HAMLOG").strip()[:40], "kind": "hamlog", "port": 0,
                              "multicast": "", "enabled": bool(it.get("enabled")), "forward": ""})
                continue
            try:
                port = int(it.get("port"))
            except (TypeError, ValueError):
                return {"ok": False, "error": t("api.portNum")}
            if not 1 <= port <= 65535:
                return {"ok": False, "error": t("api.portRange")}
            mc = (it.get("multicast") or "").strip()
            if mc and not re.fullmatch(r"2(2[4-9]|3\d)\.\d{1,3}\.\d{1,3}\.\d{1,3}", mc):
                return {"ok": False, "error": t("api.mcFormat")}
            fwd = (it.get("forward") or "").strip()
            if fwd and not re.fullmatch(r"[\w.\-]+:\d{1,5}", fwd):
                return {"ok": False, "error": t("api.fwdFormat")}
            clean.append({"name": (it.get("name") or t("api.listenerName")).strip()[:40], "kind": it.get("kind", "auto"),
                          "port": port, "multicast": mc, "enabled": bool(it.get("enabled")), "forward": fwd})
        save_settings({"listeners": clean})
        self.start_receiver()
        time.sleep(0.4)
        return {"ok": True, "listeners": clean, "receiver": self._receiver_texts()}

    def start_receiver(self):
        if self._receiver:
            self._receiver.stop()
        self._recv_status = {}
        self._receiver = Receiver(self.listeners(), self._on_qso, self._on_recv_status)
        self._receiver.start()
        self._recv_status.update(self._receiver.state)

    def _receiver_texts(self):
        return {name: describe_state(st) for name, st in list(self._recv_status.items())}

    def _on_recv_status(self, name, state):
        with self._lock:
            self._recv_status[name] = state

    def _on_qso(self, action, rec, ext_id, listener):
        """A logger reported a QSO (or deleted one). Store it, tag it with my park and the spot
        candidate, and queue an event for the live view."""
        if action == "backfill":      # HAMLOG read back after a restart: never overwrite (parks, a delete)
            if qsolog.known(qsolog.make_uid(rec)):
                return
            action = "upsert"
        if action == "delete":
            gone = qsolog.delete(ext_id, rec.get("CALL"), rec.get("QSO_DATE"), rec.get("TIME_ON"),
                                 rec.get("BAND"), mode_of(rec) if rec.get("MODE") else None)
            ev = {"action": "delete", "call": rec.get("CALL"), "uids": gone}
        else:
            lg = self._logger if self._recording() else None   # one look: finish_live may clear it meanwhile
            if lg and not my_parks_of(rec):
                if (rec.get("MY_SIG") or "POTA").upper() == "POTA":
                    rec["MY_SIG"], rec["MY_SIG_INFO"] = "POTA", ",".join(lg.parks)
                else:                                   # MY_SIG_INFO holds another program's reference (WWFF)
                    rec["MY_POTA_REF"] = ",".join(lg.parks)
                if self._locs:
                    rec["MY_POTA_LOCS"] = dict(self._locs)        # parks spanning prefectures/states -> where I was
            if lg:
                rec.setdefault("SESSION_CALL", lg.call)   # whose log: a club call's QSOs never go into mine
                if self._operator and not rec.get("OPERATOR"):
                    rec["OPERATOR"] = self._operator            # club station: who was at the radio (HAMLOG sends none)
            info = tag_candidate(rec)
            accept = info["parks"] if info["auto"] and load_settings().get("p2p_auto") else None   # 設定 → P2P
            uid = qsolog.received(rec, ext_id, listener, accept)
            # twins: copies the list already shows (WSJT-X's start time, the logger's end time) - one row each contact
            ev = dict(self._event(rec, uid), twins=qsolog.twins(uid), live=self._in_session(rec), prev=qsolog.earlier_parks(rec))
        ev.update({"source": listener, "at": time.time()})
        with self._lock:
            self._qso_events.append(ev)
            self._qso_events = self._qso_events[-500:]
        if action != "delete" and self._recording():
            self._check_awards()

    # ---- achievements reached while recording (mypota.awards): what is new since the recording started
    def _award_keys(self):
        recs = qsolog.records()
        return mypota.awards(recs, activation_days(recs), time.strftime("%Y%m%d", time.gmtime()))

    def _start_awards(self):
        """What the record reaches when recording starts (on a thread: the log may be long); later QSOs compare to it."""
        self._award_base = None
        def base():
            try:
                self._award_base = set(self._award_keys())
            except Exception as e:
                logging.warning("awards: %s", e)
        threading.Thread(target=base, daemon=True).start()

    def _check_awards(self):
        with self._award_lock:
            if self._award_base is None:
                return
            try:
                now = self._award_keys()
            except Exception as e:
                logging.warning("awards: %s", e)
                return
            new = [dict(v, key=k) for k, v in now.items() if k not in self._award_base]
            self._award_base |= set(now)
        if new:                                    # the windows celebrate it (not confirmed until the log is uploaded)
            with self._lock:
                self._qso_events.append({"action": "award", "awards": new, "at": time.time()})

    # ================================================================ the activation (運用中)
    def start_live(self, parks, call, loc="", operator=""):
        parks = split_parks(parks)
        if not parks:
            return {"ok": False, "error": t("api.badPark")}
        call = (call or "").strip().upper()
        if not CALL_RE.fullmatch(call):
            return {"ok": False, "error": t("api.noCall")}
        operator = (operator or "").strip().upper()
        if operator == call:
            operator = ""                      # not a club station: OPERATOR = the call, as before
        if operator and not CALL_RE.fullmatch(operator):
            return {"ok": False, "error": t("api.badOperator")}
        if len(parks) > 1:
            cl = common_locations(parks)
            if cl["none"]:                     # no prefecture/state in common: no 2fer
                return {"ok": False, "error": t("live.err.noLoc")}
            if cl["apart"]:                    # pota.app's park comment says they don't overlap
                a, b = cl["apart"][0]
                return {"ok": False, "error": t("live.warn.apart", a=a, b=b)}
        locs = self._locs_for(parks, loc)
        self._stop_logger()
        with self._lock:
            self._events, self._status = [], i18n.Text("api.firstSpot")
        save_settings({"parks": ",".join(parks), "call": call, "operators": dict(load_settings().get("operators") or {}, **{call: operator})})
        self._logger = SpotLogger(parks, call, SPOT_INTERVAL, on_activator=self._on_spot, on_status=self._on_status)
        self._logger.start()
        sess = self._logger.session
        self._locs, self._operator = locs, operator
        self._start_weather(parks)
        self._start_awards()
        save_settings({"live": {"id": sess["id"], "parks": parks, "call": call, "start": sess["start"], "locs": locs,
                                "operator": operator}})
        return {"ok": True, "parks": parks, "start": sess["start"], "loc": loc, "locs": locs, "operator": operator,
                "shifts": shift_hours(parks)}

    def set_operator(self, operator):
        """A club station changes operators without stopping: QSOs from now on carry the new OPERATOR."""
        live = load_settings().get("live")
        if not self._recording() or not live:
            return {"ok": False, "error": t("api.notRecording")}
        operator = (operator or "").strip().upper()
        if operator == live.get("call"):
            operator = ""
        if operator and not CALL_RE.fullmatch(operator):
            return {"ok": False, "error": t("api.badOperator")}
        self._operator = operator
        save_settings({"operators": dict(load_settings().get("operators") or {}, **{live["call"]: operator}),
                       "live": dict(live, operator=operator)})
        return {"ok": True, "operator": operator}

    def _in_session(self, rec):
        """Does this QSO belong in the running session's list: logged at one of its parks today (a park
        shared with an earlier session keeps its count), or since the session started."""
        lg = self._logger
        if not (lg and lg.running()):
            return False
        if set(my_parks_of(rec)) & set(lg.parks):
            return True
        t = rec_minutes(rec)
        return t is None or t >= session_since(lg.session["start"])

    def _on_spot(self, tm, act, parks, freq, mode, twofer):
        with self._lock:
            self._events.append({"time": tm, "call": act, "parks": parks, "freq": freq, "mode": mode,
                                "twofer": twofer, "at": time.time(),
                                "km": distance_km(self._logger.parks, parks) if self._logger else None})
            self._events = self._events[-500:]             # poll_live looks through them every second

    def _on_status(self, msg):
        with self._lock:
            self._status = msg

    def poll_live(self, since, qsince):
        with self._lock:
            return {"events": [e for e in self._events if e["at"] > since],
                    "qsos": [e for e in self._qso_events if e["at"] > qsince],
                    "status": str(self._status), "receiver": self._receiver_texts(),
                    "running": self._recording(), "look": self._look(), "bar": bool(self._bar and self._bar.active),
                    "clock": clock_skew(), "weather": self._weather}

    def _look(self, s=None):
        """設定 → 表示 for both windows: {font_scale, theme, bar_style}."""
        s = s or load_settings()
        return {"font_scale": s.get("font_scale", 1), "theme": s.get("theme", ""), "bar_style": s.get("bar_style", "")}

    def session_qsos(self, start_iso, parks=""):
        """The live list when a session starts or the window reopens: today's QSOs at any of these
        parks (a park shared by several sessions keeps its count for the day) plus anything logged
        since the session started."""
        mine = set(split_parks(parks))
        out = {}
        for r in qsolog.records([iso_date(start_iso)]):
            if mine & set(my_parks_of(r)):
                out[qsolog.make_uid(r)] = dict(self._event(r), at=0)
        for r in qsolog.between(session_since(start_iso)):
            out.setdefault(qsolog.make_uid(r), dict(self._event(r), at=0))
        return list(out.values())

    def set_p2p(self, uid, decision, parks=""):
        """The operator's answer for one QSO: 'yes' (candidate accepted), 'manual' (typed parks), 'no', ''."""
        parks = split_parks(parks)
        if decision in ("yes", "manual") and not parks:
            return {"ok": False, "error": t("api.badPark")}
        updated = qsolog.set_p2p(uid, decision, parks)
        if not updated:
            return {"ok": False, "error": t("api.qsoNotFound")}
        self._hunted = (0, None)                 # a P2P hunts their park
        events = [self._event(r) for r in updated]
        with self._lock:                         # the other window (main / bar) picks the answer up in poll_live
            self._qso_events += [dict(e, action="update", at=time.time()) for e in events]
            self._qso_events = self._qso_events[-500:]
        return {"ok": True, "events": events}

    def finish_live(self, online=True):
        """End the activation at this park: stop recording, write the upload file(s) for the
        QSOs of this session, and report what was written."""
        sess = self._stop_logger()
        if not sess:
            return {"ok": False, "error": t("api.notRecording")}
        s = load_settings()
        try:
            mine = qsolog.between(session_since(sess["start"]), iso_minutes(sess["end"]) + SESSION_MARGIN)
            # Build the whole UTC day, not just this session: a park shared by several sessions of
            # the day (JP-1206+JP-1266 in the morning, JP-1206+JP-1946 later) must end up with one
            # file holding all of its QSOs, not the latest session's only. Parks come from each
            # record (set while recording) and from the session windows in sessions.json.
            dates = sorted({iso_date(sess["start"]), iso_date(sess["end"])})
            res = build(None, dates, None, sess.get("call") or my_call(),
                        s.get("out", DEFAULT_OUT), offline=not online, recs=qsolog.records(dates), confirmed_only=True)
            return {"ok": True, "session": sess, "qsos": len(mine), **res}
        except Exception as e:
            return {"ok": False, "session": sess, "error": str(e)}

    def stop_live(self):
        """Stop recording without writing files (kept for the CLI-like flow; the UI uses finish_live)."""
        sess = self._stop_logger()
        return {"ok": True, "start": sess["start"], "end": sess["end"]} if sess else {"ok": True}

    def map_points(self, mine, groups):
        """運用中 → 地図: [lat, lon] of the middle of my parks and of each P2P's parks (the same points as the
        distances: spots.middle of spots.park_at), None where no position is known."""
        def at(refs):
            m = parks_middle(split_parks(",".join(refs or [])))
            return list(m) if m else None
        return {"me": at(mine), "groups": [at(g) for g in groups or []]}

    def set_bar(self, on):
        """Open or close the bar window."""
        return self._bar.set(on) if self._bar else False

    def fit_bar(self, width, height=100):
        """The bar measured its content: make the window that size (no line wraps, nothing to spare;
        taller with a bigger text size)."""
        try:
            width, height = max(200, min(2000, int(width))), max(60, min(400, int(height)))
        except (TypeError, ValueError):
            return False
        if self._bar:
            self._bar.fit(width, height)
        return True

    def set_on_top(self, on):
        """設定 → ウインドウ: the main window on top (saved)."""
        save_settings({"on_top": bool(on)})
        return self._bar.set_on_top(on) if self._bar else bool(on)

    def set_bar_on_top(self, on):
        """設定 → ウインドウ: the bar on top (saved; on unless turned off)."""
        save_settings({"bar_on_top": bool(on)})
        return self._bar.set_bar_on_top(on) if self._bar else bool(on)

    # ================================================================ who is activating now
    def spots_now(self, max_age=45):
        at, spots = self._spots_cache
        if time.time() - at > max_age:
            try:
                spots = fetch_json("spot/activator", timeout=15) or []
                self._spots_cache = (time.time(), spots)
            except Exception as e:
                if not spots:
                    return {"ok": False, "error": t("api.spotsFail", err=e)}
        worked = []
        if self._recording():
            worked = sorted({base_call(r.get("CALL")) for r in qsolog.between(session_since(self._logger.session["start"]))})
        return {"ok": True, "at": time.strftime("%H:%M", time.gmtime(self._spots_cache[0])),
                "items": (items := summarize(spots, history=history_parks,
                                             new_of=lambda parks, first=self._first_hunted(): mypota.new_parks(parks, first))),
                "worked": worked,
                "pending": sum(1 for r in items if r.get("pending"))}

    def park_info(self, refs):
        """{ref: spots.park_info(ref)} - name, grid, comments, locations."""
        return {ref: park_info(ref) for ref in split_parks(refs)}

    def park_locations(self, refs):
        """spots.common_locations: where the operator can stand for these parks together; with "spread_km",
        how far apart the parks' points are (the widest pair) - a 2fer needs being inside every park at
        once, which a park's single point can't tell, so the page only notes the distance."""
        parks = split_parks(refs)
        km = [distance_km([a], [b]) for i, a in enumerate(parks) for b in parks[i + 1:]]
        km = [k for k in km if k is not None]
        return dict(common_locations(refs), spread_km=max(km) if km else None, linear=linear_parks(parks))

    def my_parks(self, refs):
        """{ref: mypota.activations} - this park's next activation by the operator's record (None per
        park before activator_parks.csv is imported)."""
        days = activation_days(qsolog.records())
        return {ref: mypota.activations(ref, days) for ref in split_parks(refs)}

    def mypota_record(self):
        """実績 page: mypota.record over the app log, each park with its name from the shipped park list
        (no pota.app request, so a long list stays instant)."""
        recs = qsolog.records()
        rec, parks = mypota.record(recs, activation_days(recs)), shipped_parks()
        for row in rec["hunted"] + rec["activated"]:
            name, _, grid, at, _ = parks.get(row["ref"]) or ("", "", "", None, True)
            # [lat, lon] for the map: the park's own position, else the middle of its grid square
            row["name"], row["at"] = name, at or grid_center(grid)
            row["listed"] = park_status(row["ref"])          # active / retired / no
        return rec

    def import_mypota(self):
        """設定 → POTA の実績: pick pota.app's hunter_parks.csv / activator_parks.csv and import them."""
        r = self._window.create_file_dialog(OPEN_DIALOG, allow_multiple=True, file_types=("CSV (*.csv)", "All files (*.*)"))
        paths = list(r) if isinstance(r, (list, tuple)) else [r] if r else []
        if not paths:
            return None
        res = mypota.import_files(paths)
        if not res["ok"]:
            return {"ok": False, "error": t("api.mypotaBad", file=os.path.basename(res["bad"]))}
        self._hunted = (0, None)
        return {"ok": True, "mypota": mypota.status()}

    def _locs_for(self, parks, loc):
        """{park: location} for the parks that span several locations - what the upload file needs."""
        if not loc:
            return {}
        return {ref: loc for ref in common_locations(parks)["multi"]}

    # ================================================================ upload files (アップロード作成)
    def _pick(self, kind, **kw):
        """A file or folder dialog -> the chosen path, or None."""
        r = self._window.create_file_dialog(kind, **kw)
        if not r:
            return None
        return r[0] if isinstance(r, (list, tuple)) else r

    def pick_adif(self):
        path = self._pick(OPEN_DIALOG, allow_multiple=False, file_types=("ADIF (*.adi;*.adif;*.adx;*.ADI;*.ADIF;*.ADX)", "All files (*.*)"))
        if not path:
            return None
        save_settings({"adif": path, "source": "adif"})
        return self.activations(path)

    def activations(self, path=None):
        """path=None -> the app's own log."""
        try:
            if path:
                if not os.path.exists(path):
                    return {"path": path, "items": [], "error": t("api.fileNotFound")}
                rows = list_activations(path)
            else:
                rows = list_activations(recs=qsolog.records())
            return {"path": path or "", "items": [{"date": d, "parks": p.split(","), "qsos": n, "per": per, "pota": pota} for d, p, n, per, pota in rows]}
        except Exception as e:
            return {"path": path or "", "items": [], "error": t("api.logRead", err=e)}

    # ---- the editor (アップロード作成 → 中身を見る): one activation day's QSOs
    def activation_qsos(self, date, path=None):
        """Rows for the editor: from the app log (editable) or from an ADIF file (read-only)."""
        date = str(date or "")
        if not DATE_RE.fullmatch(date):
            return {"ok": False, "error": t("api.badDate")}
        try:
            recs = read_adif(path) if path else qsolog.records([date])
        except Exception as e:
            return {"ok": False, "error": t("api.logRead", err=e)}
        rows = []
        for r, _, mp in find_activation_qsos(recs, dates=[date]):
            _, parks = decided_parks(r)
            rows.append({"uid": None if path else qsolog.make_uid(r), "call": r.get("CALL", ""), "time": r.get("TIME_ON", ""),
                         "band": r.get("BAND", ""), "mode": mode_of(r), "my": sorted(mp), "parks": parks})
        rows.sort(key=lambda x: x["time"])
        return {"ok": True, "editable": not path, "rows": rows}

    def save_qso(self, uid, fields):
        """One edited cell of the editor. fields: {CALL|TIME_ON|BAND|MODE|parks: text}."""
        clean = {}
        for k, v in (fields or {}).items():
            v = str(v or "").strip()
            if k == "CALL":
                v = v.upper()
                if not CALL_RE.fullmatch(v):
                    return {"ok": False, "error": t("cfg.calls.err")}
            elif k == "TIME_ON":
                if not re.fullmatch(r"\d{4}(\d{2})?", v):
                    return {"ok": False, "error": t("api.badTime")}
            elif k == "BAND":
                v = band_name(v)                         # an ADIF band only ("11m" is not one)
                if not v:
                    return {"ok": False, "error": t("api.badBand")}
            elif k == "MODE":
                v = v.upper().strip()                    # USB, FT4 ... are fine: qsolog.update writes MODE + SUBMODE
                if not mode_known(adif_mode(v)):
                    return {"ok": False, "error": t("api.badMode")}
            elif k == "parks":
                if v and not split_parks(v):
                    return {"ok": False, "error": t("api.badPark")}
            else:
                continue
            clean[k] = v
        new_uid = qsolog.update(uid, clean)
        if not new_uid:
            return {"ok": False, "error": t("api.qsoNotFound")}
        return {"ok": True, "uid": new_uid}

    def delete_qso(self, uid):
        """Delete one contact (the editor, the 履歴 page) with the copy another program sent of it."""
        twins = qsolog.twins(uid)
        if not qsolog.delete_uid(uid):
            return {"ok": False, "error": t("api.qsoNotFound")}
        for u in twins:
            qsolog.delete_uid(u)
        return {"ok": True, "log_count": qsolog.count()}

    def delete_activation(self, date):
        """Remove one UTC day's activation QSOs from the app's own log (the list on アップロード作成)."""
        date = str(date or "")
        if not DATE_RE.fullmatch(date):
            return {"ok": False, "error": t("api.badDate")}
        # exactly what the list counted: QSOs with my park recorded, and QSOs inside a recording window
        # (builder.find_activation_qsos); each with the twin copy another program sent
        n = 0
        for r, _, _ in find_activation_qsos(qsolog.records([date]), dates=[date]):
            n += 1 if qsolog.delete(None, r.get("CALL"), r.get("QSO_DATE"), r.get("TIME_ON"), r.get("BAND"), mode_of(r)) else 0   # a QSO, not its copies
        return {"ok": True, "n": n, "log_count": qsolog.count()}

    def qso_history(self):
        """履歴 page: every QSO the app has received, newest first (qsolog.history), and
        {park: "retired" | "no"} for the parks in it that are not active in pota.app's list."""
        rows = qsolog.history()
        refs = {p for r in rows for p in r["my"] + r["their"]}
        return {"rows": rows, "parks": {p: s for p in refs if (s := park_status(p)) != "active"}}

    def clear_app_data(self):
        """設定 → アプリ: delete the app's own QSO log, P2P decisions, session windows and spot recordings.
        Not while a session is open (it lives in them) - settings.live, not the spot thread, which may have
        stopped while the session goes on. Settings, imported CSVs and hunter.json stay."""
        if self._recording() or load_settings().get("live"):
            return {"ok": False, "error": t("api.clearRecording")}
        n = qsolog.clear()
        clear_records()
        self._hunted = (0, None)
        return {"ok": True, "n": n, "log_count": qsolog.count()}

    def pick_out(self):
        path = self._pick(FOLDER_DIALOG)
        if path:
            save_settings({"out": path})
        return path

    def build(self, params):
        try:
            src_app = params.get("source") == "app"
            dates = params.get("dates") or None
            res = build(None if src_app else params["adif"], dates, params.get("override") or None,
                        params.get("call") or my_call(), params.get("out") or DEFAULT_OUT,
                        offline=not params.get("online", True),
                        recs=qsolog.records(dates) if src_app else None, confirmed_only=src_app)
            return {"ok": True, **res}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ================================================================ updates (GitHub Releases)
    def check_update(self):
        try:
            return {"ok": True, **updater.check(bool(load_settings().get("beta")))}
        except Exception as e:
            return {"ok": False, "error": t("api.updCheckFail", err=e)}

    def install_update(self, url):
        try:
            res = updater.install(url)
        except Exception as e:
            return {"ok": False, "error": t("api.updFail", err=e)}
        if res.get("relaunch"):
            threading.Thread(target=self._relaunch, args=(res["relaunch"],), daemon=True).start()
        return {"ok": True, **res}

    def _relaunch(self, path):
        time.sleep(1.0)              # let the UI show "restarting"
        updater.relaunch(path)
        self.shutdown()
        if self._window:
            self._window.destroy()

    # ================================================================ misc
    def open_out(self, path):
        path = path or DEFAULT_OUT
        os.makedirs(path, exist_ok=True)
        open_path(path)

    def open_data(self):
        os.makedirs(data_path(), exist_ok=True)
        open_path(data_path())

    def open_log(self):
        """設定 → アプリ → ログを開く: potaroo.log (potacommon.setup_log)."""
        p = data_path(LOG_NAME)
        open_path(p if os.path.exists(p) else data_path())

    def report_info(self, lines=60):
        """設定 → アプリ → 不具合を報告: what the report starts with - versions, the OS, the end of potaroo.log.
        Nothing is sent from here: the page shows it for the operator to read, edit, copy or open on GitHub."""
        import platform
        tail = []
        p = data_path(LOG_NAME)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                tail = fh.read().splitlines()[-int(lines):]
        return {"version": VERSION, "data_version": data_version(), "lines": len(tail), "log": "\n".join(tail),
                "os": "%s %s (%s)" % (platform.system(), platform.release(), platform.version())}

    def log_js(self, msg):
        """A JavaScript error in the page (window error / unhandled rejection) -> potaroo.log."""
        logging.getLogger("page").error(str(msg)[:4000])
        return True

    def open_url(self, url):
        if url.startswith("https://"):
            webbrowser.open(url)

    def set_busy(self, what, on):
        """The page starts / stops something that closing the window would cut off (the QSO editor)."""
        (self._busy.add if on else self._busy.discard)(str(what))
        return True

    def close_reasons(self):
        """Why closing the window should be confirmed: ["live"] while recording, ["edit"] in the editor."""
        if self._allow_close:
            return []
        return (["live"] if self._recording() else []) + (["edit"] if "edit" in self._busy else [])

    def quit_app(self):
        """The operator confirmed: close the window (and with it the bar) without asking again."""
        self._allow_close = True
        from window import _run_steps
        _run_steps(self._window, [("close", self._window.destroy)])
        return True

    def shutdown(self):
        if self._recording():
            self._logger.stop()
        if self._receiver:
            self._receiver.stop()


# pywebview >= 5 has FileDialog; the bare constants are deprecated in 6 and will be removed.
_FD = getattr(webview, "FileDialog", None)
OPEN_DIALOG = _FD.OPEN if _FD else webview.OPEN_DIALOG
FOLDER_DIALOG = _FD.FOLDER if _FD else webview.FOLDER_DIALOG


def main():
    if updater.adopt_name():           # still named "POTA Upload Helper": renamed to Potaroo, starts again from there
        return
    if not lock_instance():            # already running: show that window, don't start a second one
        from window import focus_running
        focus_running(APP_NAME)
        return
    setup_log()
    updater.cleanup()
    i18n.set_lang(load_settings().get("lang") or "ja")
    # the shipped park list (97k lines) is read beside the window's start-up, not before it
    threading.Thread(target=lambda: setattr(i18n, "examples", example_parks(load_settings().get("country") or "")), daemon=True).start()
    api = Api()
    win = webview.create_window(APP_NAME, resource("ui", "index.html"), js_api=api,
                                width=1180, height=800, min_size=(600, 160), on_top=bool(load_settings().get("on_top")))
    api._window = win
    api._bar = BarMode(win, resource("ui", "index.html"), api, APP_NAME + " - " + t("bar.title"),
                       keep_on_top=bool(load_settings().get("on_top")), bar_on_top=load_settings().get("bar_on_top", True) is not False)
    def closing():                     # returning False cancels the close; None lets it go
        reasons = api.close_reasons()
        if reasons:                    # recording or editing: ask in the page first (quit_app closes for real)
            threading.Thread(target=lambda: win.evaluate_js("window.potarooAskClose(%s)" % json.dumps(reasons)), daemon=True).start()
            return False
        api.shutdown()
        api._bar.close_now()           # the bar never outlives the main window
    win.events.closing += closing
    api._bar.zoom = load_settings().get("font_scale", 1)
    win.events.loaded += lambda: set_zoom(win, api._bar.zoom)
    # OpenStreetMap's tile policy asks apps to name themselves in the User-Agent (the maps' tiles are the web view's only fetch)
    webview.start(debug=bool(os.environ.get("POTAROO_DEBUG")),
                  user_agent="Mozilla/5.0 (compatible; Potaroo/%s; +https://github.com/PudiPara/potaroo)" % VERSION)
    # The windows are gone. Exit now: pywebview answers each JS call on a non-daemon thread that waits
    # for the run loop, and one still waiting when it stopped (poll_live every second) kept the process
    # alive with its windows frozen on screen (macOS, "固まる" on closing the window).
    api.shutdown()
    os._exit(0)


if __name__ == "__main__":
    main()
