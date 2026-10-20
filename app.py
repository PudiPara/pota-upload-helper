#!/usr/bin/env python3
"""POTA Upload Helper - desktop app (pywebview: WebKit on macOS, Edge WebView2 on Windows)."""
import copy
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser

import webview

import qsolog
from builder import build, list_activations, live_p2p
from potacommon import (APP_NAME, DATA_DIR, DEFAULT_OUT, VERSION, base_call, fetch_json, iso_minutes,
                        load_settings, minutes, save_settings, split_parks)
from receiver import DEFAULT_LISTENERS, Receiver
from spotlogger import SpotLogger


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


class Api:
    """Every public method is callable from JavaScript as window.pywebview.api.<name>()."""

    def __init__(self):
        self.window = None
        self.logger = None
        self.receiver = None
        self.events = []          # spots seen while recording
        self.qso_events = []      # QSOs received from loggers
        self.status = ""
        self.recv_status = {}
        self.lock = threading.Lock()
        self._parks = {}
        self.start_receiver()

    # ---------- settings ----------
    def get_state(self):
        s = load_settings()
        live = None
        if self.logger and self.logger.running():
            live = {"parks": self.logger.parks, "start": self.logger.session["start"]}
        return {"version": VERSION, "call": s.get("call", "JL1FVA"), "parks": s.get("parks", ""),
                "prefix": s.get("prefix", "JP"), "adif": s.get("adif", ""), "out": s.get("out", DEFAULT_OUT),
                "source": s.get("source", "app"), "live": live, "listeners": self.listeners(),
                "log_count": qsolog.count(), "receiver": self.recv_status}

    def save(self, data):
        save_settings({k: v for k, v in data.items() if k in ("call", "parks", "prefix", "adif", "out", "source")})
        return True

    # ---------- UDP receiving ----------
    def listeners(self):
        return load_settings().get("listeners") or copy.deepcopy(DEFAULT_LISTENERS)

    def save_listeners(self, items):
        clean = []
        for it in items:
            try:
                port = int(it.get("port"))
            except (TypeError, ValueError):
                return {"ok": False, "error": "ポート番号は数字で入力してください。"}
            if not 1 <= port <= 65535:
                return {"ok": False, "error": "ポート番号は 1〜65535 です。"}
            mc = (it.get("multicast") or "").strip()
            if mc and not re.fullmatch(r"2(2[4-9]|3\d)\.\d{1,3}\.\d{1,3}\.\d{1,3}", mc):
                return {"ok": False, "error": "マルチキャストのアドレスは 224.0.0.1 のような形です。"}
            fwd = (it.get("forward") or "").strip()
            if fwd and not re.fullmatch(r"[\w.\-]+:\d{1,5}", fwd):
                return {"ok": False, "error": "転送先は 127.0.0.1:2335 のように「アドレス:ポート」で入力してください。"}
            clean.append({"name": (it.get("name") or "受信口").strip()[:40], "kind": it.get("kind", "auto"),
                          "port": port, "multicast": mc, "enabled": bool(it.get("enabled")), "forward": fwd})
        save_settings({"listeners": clean})
        self.start_receiver()
        time.sleep(0.4)
        return {"ok": True, "listeners": clean, "receiver": self.recv_status}

    def start_receiver(self):
        if self.receiver:
            self.receiver.stop()
        self.recv_status = {}
        self.receiver = Receiver(self.listeners(), self._on_qso, self._on_recv_status)
        self.receiver.start()
        self.recv_status.update(self.receiver.state)

    def _on_recv_status(self, name, msg):
        with self.lock:
            self.recv_status[name] = msg

    def _on_qso(self, action, rec, ext_id, listener):
        if action == "delete":
            n = qsolog.delete(ext_id, rec.get("CALL"), rec.get("QSO_DATE"), rec.get("TIME_ON"))
            ev = {"action": "delete", "call": rec.get("CALL"), "date": rec.get("QSO_DATE"),
                  "time": (rec.get("TIME_ON") or "")[:4], "n": n}
        else:
            if self.logger and self.logger.running() and not rec.get("MY_SIG_INFO"):
                rec["MY_SIG"], rec["MY_SIG_INFO"] = "POTA", ",".join(self.logger.parks)
            uid = qsolog.upsert(rec, ext_id, listener)
            ev = {"action": "upsert", "uid": uid, "call": rec.get("CALL"), "date": rec.get("QSO_DATE"),
                  "time": (rec.get("TIME_ON") or "")[:4], "band": rec.get("BAND", ""),
                  "mode": rec.get("SUBMODE") or rec.get("MODE", ""), "parks": live_p2p(rec)}
        ev.update({"source": listener, "at": time.time()})
        with self.lock:
            self.qso_events.append(ev)
            self.qso_events = self.qso_events[-500:]
            self.recv_status[listener] = (self.receiver.state.get(listener) if self.receiver else "") or ""

    # ---------- live spot logging ----------
    def start_live(self, parks, call):
        parks = split_parks(parks)
        if not parks:
            return {"ok": False, "error": "公園番号の形式が違います。JP-1281 のように入力してください。"}
        if self.logger and self.logger.running():
            self.logger.stop()
        with self.lock:
            self.events, self.status = [], "最初のスポットを取得しています"
        save_settings({"parks": ",".join(parks), "call": call.upper()})
        self.logger = SpotLogger(parks, call, 60, on_activator=self._on_spot, on_status=self._on_status)
        self.logger.start()
        return {"ok": True, "parks": parks, "start": self.logger.session["start"]}

    def stop_live(self):
        if not self.logger:
            return {"ok": True}
        self.logger.stop()
        s = self.logger.session
        self.logger = None
        return {"ok": True, "start": s["start"], "end": s["end"]}

    def _on_spot(self, tm, act, parks, freq, mode, twofer):
        with self.lock:
            self.events.append({"time": tm, "call": act, "parks": parks, "freq": freq, "mode": mode,
                                "twofer": twofer, "at": time.time()})

    def _on_status(self, msg):
        with self.lock:
            self.status = msg

    def session_qsos(self, start_iso):
        """QSOs already in the app log since the session started (for re-opening the window)."""
        t0 = iso_minutes(start_iso) - 5
        d0 = start_iso[:10].replace("-", "")
        out = []
        for r in qsolog.records():
            if r.get("QSO_DATE", "") < d0:
                continue
            try:
                if minutes(r["QSO_DATE"], r.get("TIME_ON") or "0000") < t0:
                    continue
            except ValueError:
                continue
            out.append({"action": "upsert", "call": r.get("CALL"), "date": r.get("QSO_DATE"),
                        "time": (r.get("TIME_ON") or "")[:4], "band": r.get("BAND", ""),
                        "mode": r.get("SUBMODE") or r.get("MODE", ""), "parks": live_p2p(r), "at": 0})
        return out

    def poll_live(self, since, qsince):
        with self.lock:
            return {"events": [e for e in self.events if e["at"] > since],
                    "qsos": [e for e in self.qso_events if e["at"] > qsince],
                    "status": self.status, "receiver": dict(self.recv_status),
                    "running": bool(self.logger and self.logger.running())}

    # ---------- build ----------
    def pick_adif(self):
        r = self.window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
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
                    return {"path": path, "items": [], "error": "ファイルが見つかりません。もう一度選んでください。"}
                rows = list_activations(path)
            else:
                rows = list_activations(recs=qsolog.records())
            return {"path": path or "", "items": [{"date": d, "parks": p.split(","), "qsos": n} for d, p, n in rows]}
        except Exception as e:
            return {"path": path or "", "items": [], "error": "ログを読めませんでした: %s" % e}

    def pick_out(self):
        r = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if not r:
            return None
        path = r[0] if isinstance(r, (list, tuple)) else r
        save_settings({"out": path})
        return path

    def build(self, params):
        try:
            src_app = params.get("source") == "app"
            res = build(None if src_app else params["adif"], params.get("dates") or None,
                        params.get("override") or None, params.get("call") or "JL1FVA",
                        params.get("out") or DEFAULT_OUT, offline=not params.get("online", True),
                        recs=qsolog.records(params.get("dates") or None) if src_app else None)
            return {"ok": True, **res}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- park names ----------
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
                    self._parks[ref] = {"name": p.get("name") or "", "local": local, "grid": p.get("grid6") or ""}
                except Exception:
                    self._parks[ref] = {"name": "", "local": "", "grid": ""}
            out[ref] = self._parks[ref]
        return out

    # ---------- misc ----------
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
        if self.logger and self.logger.running():
            self.logger.stop()
        if self.receiver:
            self.receiver.stop()


def main():
    api = Api()
    win = webview.create_window(APP_NAME, resource("ui", "index.html"), js_api=api,
                                width=1180, height=800, min_size=(900, 620))
    api.window = win
    win.events.closing += api.shutdown
    webview.start(debug=bool(os.environ.get("POTA_HELPER_DEBUG")))


if __name__ == "__main__":
    main()
