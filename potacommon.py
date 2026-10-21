"""Shared helpers for the JL1FVA POTA tools (stdlib only, Python 3.8+)."""
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.request

API = "https://api.pota.app"
PARK_RE = re.compile(r"\b([A-Z0-9]{1,4}-\d{4,5})\b")
APP_NAME = "Potaroo"
OLD_NAME = "POTA Upload Helper"      # the name until 2.0.0: its data folder is moved over on first start
VERSION = "2.0.1"


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


def load_settings():
    path = os.path.join(DATA_DIR, "settings.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_settings(d):
    os.makedirs(DATA_DIR, exist_ok=True)
    cur = load_settings()
    cur.update(d)
    with open(os.path.join(DATA_DIR, "settings.json"), "w", encoding="utf-8") as fh:
        json.dump(cur, fh, ensure_ascii=False, indent=1)


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


def minutes(date_yyyymmdd, hhmm):
    """Minutes since epoch-ish (good enough for differences) from ADIF date/time."""
    import datetime as dt
    t = dt.datetime.strptime(date_yyyymmdd + hhmm[:4], "%Y%m%d%H%M")
    return int(t.replace(tzinfo=dt.timezone.utc).timestamp() // 60)


def iso_minutes(iso):
    import datetime as dt
    iso = iso.replace("Z", "")[:16]
    t = dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M")
    return int(t.replace(tzinfo=dt.timezone.utc).timestamp() // 60)
