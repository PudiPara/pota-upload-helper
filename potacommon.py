"""Shared helpers used by every module (stdlib only, Python 3.8+): pota.app fetch, data folder,
settings and JSON files, ADIF, callsigns, parks, bands and modes, time."""
import datetime as dt
import json
import os
import re
import ssl
import subprocess
import sys
import threading
import urllib.request

API = "https://api.pota.app"
PARK_RE = re.compile(r"\b([A-Z0-9]{1,4}-\d{4,5})\b")
APP_NAME = "Potaroo"
OLD_NAME = "POTA Upload Helper"      # the name until 2.0.0: its data folder is moved over on first start
VERSION = "2.0.38"


def _moved(new, old):
    """The folder under the new name; the old one is renamed to it the first time. If that fails (the
    old version still running holds a file) the old folder keeps being used, so no data is left behind."""
    if not os.path.exists(new) and os.path.isdir(old):
        try:
            os.rename(old, new)
        except OSError:
            return old
    return new


def _data_dir():
    env = os.environ.get("POTAROO_DATA") or os.environ.get("POTA_HELPER_DATA")
    if env:
        return env
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support")
        return _moved(os.path.join(base, APP_NAME), os.path.join(base, OLD_NAME))
    if os.name == "nt":
        base = os.environ.get("APPDATA", home)
        return _moved(os.path.join(base, APP_NAME), os.path.join(base, OLD_NAME))
    return _moved(os.path.join(home, ".potaroo"), os.path.join(home, ".pota-upload-helper"))


DATA_DIR = _data_dir()
USER_AGENT = "potaroo/" + VERSION
_docs = os.path.join(os.path.expanduser("~"), "Documents")
# files already written to the old output folder stay where they are; new installs use the new name
DEFAULT_OUT = (os.path.join(_docs, OLD_NAME) if os.path.isdir(os.path.join(_docs, OLD_NAME))
               else os.path.join(_docs, APP_NAME))


_instance_lock = None


def lock_instance():
    """True when no other copy of the app is running: holds instance.lock in DATA_DIR until
    this process exits (the OS drops the lock on a crash, so nothing stale is left behind)."""
    global _instance_lock
    os.makedirs(DATA_DIR, exist_ok=True)
    fh = open(os.path.join(DATA_DIR, "instance.lock"), "w")
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False
    _instance_lock = fh
    return True


def resource(*parts):
    """A file shipped with the app (inside the PyInstaller bundle, or next to the sources)."""
    return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), *parts)


def data_version():
    """The version of the shipped pota.app data (assets/pota-data.txt, "2026.10.21"), "" when missing."""
    try:
        with open(resource("assets", "pota-data.txt"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


LOG_NAME = "potaroo.log"


def setup_log():
    """potaroo.log in the data folder (1 MB, one older copy): warnings and errors from Python (stderr too:
    the installed app has no console), uncaught exceptions in any thread, the page's JavaScript errors
    (Api.log_js), and one line per start. For bug reports: the operator looks at it and sends it."""
    import logging
    import logging.handlers
    import platform
    os.makedirs(data_path(), exist_ok=True)
    h = logging.handlers.RotatingFileHandler(data_path(LOG_NAME), maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(logging.WARNING)                       # pywebview's own INFO lines stay out
    log = logging.getLogger("potaroo")
    log.setLevel(logging.INFO)

    class _Stderr:                                       # print(..., file=sys.stderr) -> the log
        def write(self, s):
            if s.strip():
                logging.getLogger("stderr").warning(s.rstrip())

        def flush(self):
            pass
    if sys.stderr is None or getattr(sys, "frozen", False):
        sys.stderr = _Stderr()
    sys.excepthook = lambda t, v, tb: logging.getLogger("crash").error("uncaught", exc_info=(t, v, tb))
    threading.excepthook = lambda a: logging.getLogger("crash").error(
        "uncaught in thread %s", a.thread.name if a.thread else "?", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    log.info("start %s (data %s) on %s %s (%s), Python %s", VERSION, data_version(), platform.system(), platform.release(), platform.version(),
             platform.python_version())


def data_path(name=""):
    """A file in the data folder (read at call time, so tests can point DATA_DIR elsewhere)."""
    return os.path.join(DATA_DIR, name) if name else DATA_DIR


def read_json(path, default):
    """The JSON in path, or default when the file is missing or broken."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    """Write through a temp file and rename, so a crash never leaves half a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_settings():
    return read_json(data_path("settings.json"), {})


_SETTINGS_LOCK = threading.Lock()


def save_settings(d):
    # one at a time: two saves at once (each JS call has its own thread) each read the old file and the
    # last write dropped the other's key (設定 → 表示: text size then colors, clicked quickly)
    with _SETTINGS_LOCK:
        cur = load_settings()
        cur.update(d)
        write_json(data_path("settings.json"), cur)


CALL_RE = re.compile(r"[A-Z0-9/]{3,}")


def my_call():
    """The callsign in use (設定 → コールサイン), or "" before one is saved."""
    s = load_settings()
    for c in [s.get("call")] + list(s.get("calls") or []):
        c = (c or "").strip().upper()
        if CALL_RE.fullmatch(c):
            return c
    return ""


def fetch_json(path, timeout=20):
    """GET api.pota.app/<path>. Falls back to the system curl when Python's
    SSL certificates are not set up (common with python.org installs on macOS)."""
    url = path if path.startswith("http") else API + "/" + path.lstrip("/")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (ssl.SSLError, urllib.error.URLError) as e:
        if isinstance(e, urllib.error.HTTPError):
            raise
        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}   # no console window on Windows
        out = subprocess.run(["curl", "-sS", "-m", str(timeout), "-A", USER_AGENT, url],
                             capture_output=True, check=True, **kw)
        return json.loads(out.stdout.decode("utf-8"))


# ---------- bands and modes ----------
BAND_EDGES = [(1.8, 2.0, "160m"), (3.5, 4.0, "80m"), (5.0, 5.5, "60m"), (7.0, 7.3, "40m"), (10.1, 10.15, "30m"),
              (14.0, 14.35, "20m"), (18.068, 18.168, "17m"), (21.0, 21.45, "15m"), (24.89, 24.99, "12m"),
              (28.0, 29.7, "10m"), (50.0, 54.0, "6m"), (144.0, 148.0, "2m"), (222.0, 225.0, "1.25m"),
              (420.0, 450.0, "70cm"), (902.0, 928.0, "33cm"), (1240.0, 1300.0, "23cm")]
PHONE_MODES = {"SSB", "USB", "LSB", "FM", "AM", "PHONE", "DV", "DMR", "C4FM", "DSTAR"}


def band_from_mhz(mhz):
    try:
        mhz = float(mhz)
    except (TypeError, ValueError):
        return ""
    for lo, hi, b in BAND_EDGES:
        if lo <= mhz <= hi:
            return b
    return ""


def band_from_khz(khz):
    try:
        return band_from_mhz(float(khz) / 1000.0)
    except (TypeError, ValueError):
        return ""


def adif_mode(mode):
    """A logger's mode word -> ADIF MODE (+SUBMODE): USB/LSB are SSB submodes, FT4 an MFSK one."""
    m = (mode or "").upper().strip()
    if m in ("USB", "LSB"):
        return {"MODE": "SSB", "SUBMODE": m}
    if m == "FT4":
        return {"MODE": "MFSK", "SUBMODE": "FT4"}
    return {"MODE": m} if m else {}


def mode_of(rec):
    """The mode pota.app tells QSOs apart by: the SUBMODE of a data mode (FT4 under MFSK), else MODE.
    An SSB sideband is not a different mode there."""
    mode = (rec.get("MODE") or "").upper()
    sub = (rec.get("SUBMODE") or "").upper()
    return mode if mode == "SSB" or not sub else sub


def pota_key(rec):
    """What pota.app keeps once per park file: CALL + BAND + MODE + their park (SIG_INFO)."""
    return ((rec.get("CALL") or "").upper(), (rec.get("BAND") or "").lower(), mode_of(rec), rec.get("SIG_INFO") or "")


def mode_group(mode):
    """'cw' | 'phone' | 'data' | '' - how pota.app groups modes."""
    m = (mode or "").upper().strip()
    return "cw" if m == "CW" else "phone" if m in PHONE_MODES else "data" if m else ""


def base_call(call):
    """JK1XOQ/P -> JK1XOQ, JS2PHO/2 -> JS2PHO, 7J1/K1ABC -> K1ABC."""
    call = (call or "").upper().strip()
    parts = [p for p in call.split("/") if p]
    cands = [p for p in parts if re.search(r"\d", p) and re.search(r"[A-Z]", p) and len(p) >= 3]
    if not cands:
        return call
    return max(cands, key=len)


def parks_in(text):
    return PARK_RE.findall((text or "").upper())


def grid_center(grid):
    """(lat, lon) of the middle of a Maidenhead locator ("PM95rq", 4 or 6 characters), or None."""
    g = (grid or "").strip().upper()
    if len(g) not in (4, 6) or not ("A" <= g[0] <= "R" and "A" <= g[1] <= "R" and g[2:4].isdigit()):
        return None
    lon = (ord(g[0]) - 65) * 20 - 180 + int(g[2]) * 2
    lat = (ord(g[1]) - 65) * 10 - 90 + int(g[3])
    if len(g) == 6:
        if not ("A" <= g[4] <= "X" and "A" <= g[5] <= "X"):
            return None
        return round(lat + (ord(g[5]) - 65) / 24 + 1 / 48, 4), round(lon + (ord(g[4]) - 65) / 12 + 1 / 24, 4)
    return lat + .5, lon + 1


def split_parks(value):
    if isinstance(value, (list, tuple, set)):
        value = ",".join(value)
    out = []
    for p in re.split(r"[,\s;]+", (value or "").upper()):
        p = p.strip()
        if p and PARK_RE.fullmatch(p) and p not in out:
            out.append(p)
    return out


# ---------- ADIF ----------
FIELD_RE = re.compile(r"<(\w+):(\d+)(?::\w)?>", re.I)


def read_adif(path):
    text = open(path, encoding="utf-8", errors="ignore").read()
    m = re.search(r"<eoh>", text, re.I)
    body = text[m.end():] if m else text
    recs = []
    for chunk in re.split(r"<eor>", body, flags=re.I):
        d = {}
        for f in FIELD_RE.finditer(chunk):
            n = int(f.group(2))
            d[f.group(1).upper()] = chunk[f.end():f.end() + n]
        if "CALL" in d:
            recs.append(d)
    return recs


def adif_field(name, value):
    value = "" if value is None else str(value)
    return "<%s:%d>%s" % (name, len(value), value)


def write_adif(path, recs, order, program="Potaroo"):
    lines = ["Generated by %s\n<ADIF_VER:5>3.1.4 <PROGRAMID:%d>%s <EOH>\n" % (program, len(program), program)]
    for r in recs:
        parts = [adif_field(k, r[k]) for k in order if r.get(k) not in (None, "")]
        parts += [adif_field(k, v) for k, v in r.items() if k not in order and v not in (None, "")]
        lines.append(" ".join(parts) + " <EOR>\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


# ---------- time: minutes since the epoch (UTC) make differences easy ----------
def utc_minutes(t):
    return int(t.replace(tzinfo=dt.timezone.utc).timestamp() // 60)


def minutes(date_yyyymmdd, hhmm):
    """From ADIF QSO_DATE + TIME_ON (ValueError when they are not a time)."""
    return utc_minutes(dt.datetime.strptime(date_yyyymmdd + hhmm[:4], "%Y%m%d%H%M"))


def rec_minutes(rec):
    """A record's QSO_DATE + TIME_ON in minutes, or None."""
    try:
        return minutes(rec.get("QSO_DATE") or "", rec.get("TIME_ON") or "0000")
    except ValueError:
        return None


def iso_minutes(iso):
    return utc_minutes(dt.datetime.strptime(iso.replace("Z", "")[:16], "%Y-%m-%dT%H:%M"))


def iso_date(iso):
    """"2026-10-21T06:37:22" -> "20261021" (the ADIF QSO_DATE)."""
    return iso[:10].replace("-", "")


def utc_stamp(t=None):
    """"2026-10-21T06:37:22" - the session and spot timestamps."""
    return (t or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S")
