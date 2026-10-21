#!/usr/bin/env python3
"""POTA Upload Helper - desktop app (pywebview: WebKit on macOS, Edge WebView2 on Windows).

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
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser

import webview

import i18n
import qsolog
import updater
from builder import build, decided_parks, find_activation_qsos, list_activations
from i18n import t
from potacommon import (APP_NAME, DATA_DIR, DEFAULT_OUT, VERSION, base_call, fetch_json, iso_minutes,
                        load_settings, lock_instance, read_adif, save_settings, split_parks)
from receiver import DEFAULT_LISTENERS, Receiver, describe_state
from spots import SpotLogger, candidate_info, history_parks, says_no_overlap, summarize
from window import BarMode

SETTINGS_KEYS = ("call", "calls", "parks", "prefix", "adif", "out", "source", "lang", "terms_accepted", "p2p_auto")   # "live" is set by start_live/finish_live only
CALL_RE = re.compile(r"[A-Z0-9/]{3,}")


def clean_calls(calls, call):
    """The saved callsigns, uppercase and valid, the chosen one first."""
    out = []
    for c in [call] + list(calls or []):
        c = (c or "").strip().upper()
        if c and CALL_RE.fullmatch(c) and c not in out:
            out.append(c)
    return out or ["JL1FVA"]


def resource(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def open_path(path):
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif os.name == "nt":
        os.startfile(path)  # noqa
    else:
        subprocess.Popen(["xdg-open", path])


def qso_event(rec, uid=None):
    """What the UI needs to draw one QSO row: identity, the spot candidate, the decision so far."""
    decision = rec.get("P2P_DECISION") or ""
    parks = split_parks(rec.get("POTA_REF") or rec.get("SIG_INFO")) if decision and decision != "no" else []
    return {"action": "upsert", "uid": uid or qsolog.make_uid(rec), "call": rec.get("CALL"),
            "date": rec.get("QSO_DATE"), "time": (rec.get("TIME_ON") or "")[:4], "band": rec.get("BAND", ""),
            "ts": (rec.get("QSO_DATE") or "") + (rec.get("TIME_ON") or "").ljust(6, "0"),   # sort key, to the second
            "mode": rec.get("SUBMODE") or rec.get("MODE", ""), "decision": decision, "parks": parks,
            "candidate": split_parks(rec.get("P2P_CANDIDATE")), "my": split_parks(rec.get("MY_SIG_INFO")),
            "note": rec.get("P2P_NOTE") or ""}


class Api:
    # All state is private (underscore). pywebview exposes every public attribute of this object to
    # JavaScript and (6.x) walks them recursively; on Windows that walk entered the WinForms window
    # behind Api.bar and froze the app. tests/test_api_private.py keeps it that way.
    def __init__(self):
        self._window = None
        self._bar = None               # BarMode, once the window exists
        self._logger = None            # SpotLogger while an activation is being recorded
        self._receiver = None
        self._events = []              # spots seen while recording, for the live view
        self._qso_events = []          # QSOs received from loggers, for the live view
        self._status = ""
        self._recv_status = {}         # listener name -> state dict (codes; see receiver.describe_state)
        self._lock = threading.Lock()
        self._parks = {}              # park reference -> info from pota.app, cached
        self._spots_cache = (0, [])   # (fetched at, raw spots) for the アクティベート中 page
        self.start_receiver()
        self._resume_live()

    def _resume_live(self):
        """The app was closed (or crashed) while recording: pick the session up again, so the
        運用中 page and its QSO list come back as they were."""
        live = load_settings().get("live") or {}
        if not live.get("parks") or not live.get("start"):
            return
        self._logger = SpotLogger(live["parks"], live.get("call") or "JL1FVA", 60,
                                  on_activator=self._on_spot, on_status=self._on_status)
        self._logger.start(resume={"id": live.get("id"), "start": live["start"]})
        self._locs = live.get("locs") or {}

    # ================================================================ settings
    def get_state(self):
        s = load_settings()
        live = None
        if self._logger and self._logger.running():
            live = {"parks": self._logger.parks, "start": self._logger.session["start"]}
        calls = clean_calls(s.get("calls"), s.get("call"))
        return {"version": VERSION, "call": calls[0], "calls": calls, "parks": s.get("parks", ""),
                "prefix": s.get("prefix", "JP"), "adif": s.get("adif", ""), "out": s.get("out", DEFAULT_OUT),
                "source": s.get("source", "app"), "live": live, "bar": bool(self._bar and self._bar.active),
                "listeners": self.listeners(), "lang": s.get("lang") or "", "langs": i18n.available(),
                "terms_accepted": s.get("terms_accepted") or "", "p2p_auto": bool(s.get("p2p_auto")),
                "log_count": qsolog.count(), "receiver": self._receiver_texts()}

    def save(self, data):
        keep = {k: v for k, v in data.items() if k in SETTINGS_KEYS}
        if "lang" in keep:
            keep["lang"] = i18n.set_lang(keep["lang"])
        if "p2p_auto" in keep:
            keep["p2p_auto"] = bool(keep["p2p_auto"])
        if "calls" in keep or "call" in keep:
            s = load_settings()
            calls = clean_calls(keep.get("calls", s.get("calls")), keep.get("call", s.get("call")))
            keep.update(calls=calls, call=calls[0])
        save_settings(keep)
        return True

    # ================================================================ UDP listeners
    def listeners(self):
        return load_settings().get("listeners") or copy.deepcopy(DEFAULT_LISTENERS)

    def save_listeners(self, items):
        clean = []
        for it in items:
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
        if action == "delete":
            n = qsolog.delete(ext_id, rec.get("CALL"), rec.get("QSO_DATE"), rec.get("TIME_ON"))
            ev = {"action": "delete", "call": rec.get("CALL"), "date": rec.get("QSO_DATE"),
                  "time": (rec.get("TIME_ON") or "")[:4], "n": n}
        else:
            if self._logger and self._logger.running() and not rec.get("MY_SIG_INFO"):
                rec["MY_SIG"], rec["MY_SIG_INFO"] = "POTA", ",".join(self._logger.parks)
                if getattr(self, "_locs", None):
                    rec["MY_POTA_LOCS"] = dict(self._locs)        # parks spanning prefectures/states -> where I was
            info = candidate_info(rec)
            cand = info["parks"]
            if cand:
                rec["P2P_CANDIDATE"] = ",".join(cand)
                if info["note"]:
                    rec["P2P_NOTE"] = info["note"]          # why this one is asked even with 自動 on
            logged = split_parks(rec.get("POTA_REF") or rec.get("SIG_INFO"))
            if logged and not rec.get("P2P_DECISION"):      # the operator typed it in the logger
                qsolog.apply_decision(rec, "log", logged)
            uid = qsolog.upsert(rec, ext_id, listener)       # may carry a decision over from the other copy
            if cand and info["auto"] and not rec.get("P2P_DECISION") and load_settings().get("p2p_auto"):
                qsolog.set_p2p(uid, "yes", ",".join(cand))     # 設定: trust the spot, don't ask (all copies)
                qsolog.apply_decision(rec, "yes", cand)
            ev = qso_event(rec, uid)
        ev.update({"source": listener, "at": time.time()})
        with self._lock:
            self._qso_events.append(ev)
            self._qso_events = self._qso_events[-500:]
            if self._receiver and listener in self._receiver.state:
                self._recv_status[listener] = self._receiver.state[listener]

    # ================================================================ the activation (運用中)
    def start_live(self, parks, call, loc=""):
        parks = split_parks(parks)
        if not parks:
            return {"ok": False, "error": t("api.badPark")}
        locs = self._locs_for(parks, loc)
        if self._logger and self._logger.running():
            self._logger.stop()
        with self._lock:
            self._events, self._status = [], t("api.firstSpot")
        save_settings({"parks": ",".join(parks), "call": call.upper()})
        self._logger = SpotLogger(parks, call, 60, on_activator=self._on_spot, on_status=self._on_status)
        self._logger.start()
        sess = self._logger.session
        self._locs = locs
        save_settings({"live": {"id": sess["id"], "parks": parks, "call": call.upper(), "start": sess["start"], "locs": locs}})
        return {"ok": True, "parks": parks, "start": sess["start"], "loc": loc}

    def _on_spot(self, tm, act, parks, freq, mode, twofer):
        with self._lock:
            self._events.append({"time": tm, "call": act, "parks": parks, "freq": freq, "mode": mode,
                                "twofer": twofer, "at": time.time()})

    def _on_status(self, msg):
        with self._lock:
            self._status = msg

    def poll_live(self, since, qsince):
        with self._lock:
            return {"events": [e for e in self._events if e["at"] > since],
                    "qsos": [e for e in self._qso_events if e["at"] > qsince],
                    "status": self._status, "receiver": self._receiver_texts(),
                    "running": bool(self._logger and self._logger.running())}

    def session_qsos(self, start_iso, parks=""):
        """The live list when a session starts or the window reopens: today's QSOs at any of these
        parks (a park shared by several sessions keeps its count for the day) plus anything logged
        since the session started."""
        mine = set(split_parks(parks))
        date = start_iso[:10].replace("-", "")
        out = {}
        for r in qsolog.records([date]):
            if mine & set(split_parks(r.get("MY_SIG_INFO"))):
                out[qsolog.make_uid(r)] = dict(qso_event(r), at=0)
        for r in qsolog.between(iso_minutes(start_iso) - 5, 1 << 40):
            out.setdefault(qsolog.make_uid(r), dict(qso_event(r), at=0))
        return list(out.values())

    def set_p2p(self, uid, decision, parks=""):
        """The operator's answer for one QSO: 'yes' (candidate accepted), 'manual' (typed parks), 'no', ''."""
        parks = split_parks(parks)
        if decision in ("yes", "manual") and not parks:
            return {"ok": False, "error": t("api.badPark")}
        updated = qsolog.set_p2p(uid, decision, parks)
        if not updated:
            return {"ok": False, "error": t("api.qsoNotFound")}
        return {"ok": True, "events": [qso_event(r) for r in updated]}

    def finish_live(self, online=True):
        """End the activation at this park: stop recording, write the upload file(s) for the
        QSOs of this session, and report what was written."""
        if not self._logger:
            return {"ok": False, "error": t("api.notRecording")}
        self._logger.stop()
        sess = dict(self._logger.session)
        self._logger = None
        save_settings({"live": None})
        s = load_settings()
        try:
            mine = qsolog.between(iso_minutes(sess["start"]) - 5, iso_minutes(sess["end"]) + 5)
            # Build the whole UTC day, not just this session: a park shared by several sessions of
            # the day (JP-1206+JP-1266 in the morning, JP-1206+JP-1946 later) must end up with one
            # file holding all of its QSOs, not the latest session's only. Parks come from each
            # record (set while recording) and from the session windows in sessions.json.
            dates = sorted({sess["start"][:10].replace("-", ""), sess["end"][:10].replace("-", "")})
            res = build(None, dates, None, s.get("call", sess.get("call", "JL1FVA")),
                        s.get("out", DEFAULT_OUT), offline=not online, recs=qsolog.records(dates), confirmed_only=True)
            return {"ok": True, "session": sess, "qsos": len(mine), **res}
        except Exception as e:
            return {"ok": False, "session": sess, "error": str(e)}

    def stop_live(self):
        """Stop recording without writing files (kept for the CLI-like flow; the UI uses finish_live)."""
        if not self._logger:
            return {"ok": True}
        self._logger.stop()
        sess = self._logger.session
        self._logger = None
        save_settings({"live": None})
        return {"ok": True, "start": sess["start"], "end": sess["end"]}

    def set_bar(self, on):
        return self._bar.set(on) if self._bar else False

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
        if self._logger and self._logger.running():
            t0 = iso_minutes(self._logger.session["start"]) - 5
            worked = sorted({base_call(r.get("CALL")) for r in qsolog.between(t0, 1 << 40)})
        return {"ok": True, "at": time.strftime("%H:%M", time.gmtime(self._spots_cache[0])),
                "items": (items := summarize(spots, history=history_parks)), "worked": worked,
                "pending": sum(1 for r in items if r.get("pending"))}

    def park_info(self, refs):
        """{ref: {name, local, grid}} - local is the Japanese name when pota.app has one."""
        out = {}
        for ref in split_parks(refs):
            if ref not in self._parks:
                try:
                    p = fetch_json("park/%s" % ref, timeout=8) or {}
                    local = (p.get("parkComments") or "").strip()
                    if not re.search(r"[぀-ヿ一-鿿]", local) or len(local) > 40:
                        local = ""
                    codes = [c.strip() for c in (p.get("locationDesc") or "").split(",") if c.strip()]
                    names = [n.strip() for n in (p.get("locationName") or "").split(",")]
                    self._parks[ref] = {"name": p.get("name") or "", "local": local, "grid": p.get("grid6") or "",
                                        "comments": p.get("parkComments") or "",
                                        "locations": [{"code": c, "name": names[i] if i < len(names) else ""} for i, c in enumerate(codes)]}
                except Exception:
                    self._parks[ref] = {"name": "", "local": "", "grid": "", "locations": []}
            out[ref] = self._parks[ref]
        return out

    def park_locations(self, refs):
        """Where the operator can stand for these parks: the locations (prefecture / state) every park
        has in common. {"options": [{code, name}], "multi": [parks spanning several locations]}.
        One option = shown fixed; several = the operator picks; none = the parks don't overlap."""
        info = self.park_info(refs)
        parks = split_parks(refs)
        common = None
        for ref in parks:
            codes = [l["code"] for l in info[ref].get("locations") or []]
            if not codes:
                continue                      # unknown to pota.app: no constraint from it
            common = codes if common is None else [c for c in common if c in codes]
        names = {l["code"]: l["name"] for ref in parks for l in info[ref].get("locations") or []}
        # pota.app's own note that two of these parks don't overlap (JP-0016 says so about JP-1296)
        apart = [[a, b] for i, a in enumerate(parks) for b in parks[i + 1:]
                 if says_no_overlap(info[a].get("comments"), b) or says_no_overlap(info[b].get("comments"), a)]
        return {"options": [{"code": c, "name": names.get(c, "")} for c in (common or [])],
                "multi": [ref for ref in parks if len(info[ref].get("locations") or []) > 1], "apart": apart}

    def _locs_for(self, parks, loc):
        """{park: location} for the parks that span several locations - what the upload file needs."""
        if not loc:
            return {}
        return {ref: loc for ref in self.park_locations(",".join(parks))["multi"]}

    # ================================================================ upload files (アップロード作成)
    def pick_adif(self):
        r = self._window.create_file_dialog(OPEN_DIALOG, allow_multiple=False,
                                           file_types=("ADIF (*.adi;*.adif;*.ADI;*.ADIF)", "All files (*.*)"))
        if not r:
            return None
        path = r[0] if isinstance(r, (list, tuple)) else r
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
        if not re.fullmatch(r"\d{8}", date):
            return {"ok": False, "error": t("api.badDate")}
        try:
            recs = read_adif(path) if path else qsolog.records([date])
        except Exception as e:
            return {"ok": False, "error": t("api.logRead", err=e)}
        rows = []
        for r, _, mp in find_activation_qsos(recs, dates=[date]):
            _, parks = decided_parks(r)
            rows.append({"uid": None if path else qsolog.make_uid(r), "call": r.get("CALL", ""), "time": r.get("TIME_ON", ""),
                         "band": r.get("BAND", ""), "mode": r.get("SUBMODE") or r.get("MODE", ""), "my": sorted(mp), "parks": parks})
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
                v = v.lower()
                if not re.fullmatch(r"\d+(\.\d+)?(m|cm|mm)", v):
                    return {"ok": False, "error": t("api.badBand")}
            elif k == "MODE":
                v = v.upper()
                if not re.fullmatch(r"[A-Z0-9-]+", v):
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
        if not qsolog.delete_uid(uid):
            return {"ok": False, "error": t("api.qsoNotFound")}
        return {"ok": True, "log_count": qsolog.count()}

    def delete_activation(self, date):
        """Remove one UTC day's activation QSOs from the app's own log (the list on アップロード作成)."""
        if not re.fullmatch(r"\d{8}", str(date or "")):
            return {"ok": False, "error": t("api.badDate")}
        n = qsolog.delete_activation(str(date))
        return {"ok": True, "n": n, "log_count": qsolog.count()}

    def pick_out(self):
        r = self._window.create_file_dialog(FOLDER_DIALOG)
        if not r:
            return None
        path = r[0] if isinstance(r, (list, tuple)) else r
        save_settings({"out": path})
        return path

    def build(self, params):
        try:
            src_app = params.get("source") == "app"
            dates = params.get("dates") or None
            res = build(None if src_app else params["adif"], dates, params.get("override") or None,
                        params.get("call") or "JL1FVA", params.get("out") or DEFAULT_OUT,
                        offline=not params.get("online", True),
                        recs=qsolog.records(dates) if src_app else None, confirmed_only=src_app)
            return {"ok": True, **res}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ================================================================ updates (GitHub Releases)
    def check_update(self):
        try:
            return {"ok": True, **updater.check()}
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
        os.makedirs(DATA_DIR, exist_ok=True)
        open_path(DATA_DIR)

    def open_url(self, url):
        if url.startswith("https://"):
            webbrowser.open(url)

    def shutdown(self):
        if self._logger and self._logger.running():
            self._logger.stop()
        if self._receiver:
            self._receiver.stop()


# pywebview >= 5 has FileDialog; the bare constants are deprecated in 6 and will be removed.
_FD = getattr(webview, "FileDialog", None)
OPEN_DIALOG = _FD.OPEN if _FD else webview.OPEN_DIALOG
FOLDER_DIALOG = _FD.FOLDER if _FD else webview.FOLDER_DIALOG


def main():
    if not lock_instance():            # already running: show that window, don't start a second one
        from window import focus_running
        focus_running(APP_NAME)
        return
    updater.cleanup()
    i18n.set_lang(load_settings().get("lang") or "ja")
    api = Api()
    from window import BAR_W
    win = webview.create_window(APP_NAME, resource("ui", "index.html"), js_api=api,
                                width=1180, height=800, min_size=(BAR_W, 160))
    api._window = win
    api._bar = BarMode(win)
    win.events.closing += api.shutdown
    webview.start(debug=bool(os.environ.get("POTA_HELPER_DEBUG")))


if __name__ == "__main__":
    main()
