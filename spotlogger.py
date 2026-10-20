"""Record POTA activator spots while you activate, so the other station's
park(s) are still known after they QRT and their spot disappears."""
import datetime as dt
import json
import os
import threading

from potacommon import DATA_DIR, base_call, fetch_json, parks_in, split_parks


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def _save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


class SpotLogger:
    """Polls api.pota.app/spot/activator. Callbacks (called from the worker thread):
         on_activator(time_str, activator, parks_list, freq, mode, is_2fer)
         on_status(message)
    """

    def __init__(self, parks, call="JL1FVA", interval=60, on_activator=None, on_status=None):
        self.parks = split_parks(parks)
        if not self.parks:
            raise ValueError("公園の番号が正しくありません（例: JP-1281）")
        self.call = call.upper().strip()
        self.interval = max(15, int(interval))
        self.on_activator = on_activator or (lambda *a: None)
        self.on_status = on_status or (lambda *a: None)
        self._stop = threading.Event()
        self._thread = None
        self.session = None

    # ----- session bookkeeping -----
    def _sessions_path(self):
        return os.path.join(DATA_DIR, "sessions.json")

    def _load_sessions(self):
        try:
            with open(self._sessions_path(), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return []

    def _update_session(self):
        sessions = self._load_sessions()
        for s in sessions:
            if s.get("id") == self.session["id"]:
                s.update(self.session)
                break
        else:
            sessions.append(dict(self.session))
        _save_json(self._sessions_path(), sessions)

    # ----- control -----
    def start(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        t = now_utc().strftime("%Y-%m-%dT%H:%M")
        self.session = {"id": now_utc().strftime("%Y%m%d%H%M%S"), "call": self.call,
                        "parks": self.parks, "start": t, "end": t}
        self._update_session()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self.session:
            self.session["end"] = now_utc().strftime("%Y-%m-%dT%H:%M")
            self._update_session()

    def running(self):
        return bool(self._thread and self._thread.is_alive())

    # ----- worker -----
    def _run(self):
        from builder import load_hunter   # local import: avoids a cycle
        mine = base_call(self.call)
        seen, known, polls = {}, {}, 0
        while not self._stop.is_set():
            t = now_utc()
            try:
                spots = fetch_json("spot/activator")
                self.on_status("%sZ 更新（スポット %d 件）" % (t.strftime("%H:%M"), len(spots)))
            except Exception as e:
                spots = []
                self.on_status("%sZ スポット取得に失敗: %s" % (t.strftime("%H:%M"), e))
            path = os.path.join(DATA_DIR, "spots-%s.jsonl" % t.strftime("%Y%m%d"))
            with open(path, "a", encoding="utf-8") as fh:
                for s in spots:
                    key = s.get("spotId")
                    if seen.get(key) == s.get("spotTime"):
                        continue
                    seen[key] = s.get("spotTime")
                    act = base_call(s.get("activator"))
                    if act == mine:
                        continue
                    refs = [(s.get("reference") or "").upper()] + parks_in(s.get("comments"))
                    refs = [r for i, r in enumerate(refs) if r and r not in refs[:i]]
                    rec = {"seen": t.strftime("%Y-%m-%dT%H:%M:%S"), "spotTime": s.get("spotTime"),
                           "activator": s.get("activator"), "base": act, "parks": refs,
                           "frequency": s.get("frequency"), "mode": s.get("mode"),
                           "comments": s.get("comments"), "spotId": key}
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    before = known.setdefault(act, set())
                    added = [r for r in refs if r not in before]
                    if added:
                        before.update(added)
                        self.on_activator(t.strftime("%H:%M"), s.get("activator"), sorted(before),
                                          s.get("frequency"), s.get("mode"), len(before) > 1)
            self.session["end"] = t.strftime("%Y-%m-%dT%H:%M")
            self._update_session()
            if polls % 10 == 0:
                try:
                    load_hunter(self.call, False, log=self.on_status)
                except Exception as e:
                    self.on_status("ハンターログ更新に失敗: %s" % e)
            polls += 1
            self._stop.wait(self.interval)
