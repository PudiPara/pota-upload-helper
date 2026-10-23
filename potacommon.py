"""Shared helpers used by every module (stdlib only, Python 3.8+): pota.app fetch, data folder,
settings and JSON files, ADIF, callsigns, parks, bands and modes, time."""
import datetime as dt
import email.utils
import json
import os
import re
import ssl
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.pota.app"
PARK_RE = re.compile(r"\b([A-Z0-9]{1,4}-\d{4,5})\b")
APP_NAME = "Potaroo"
OLD_NAME = "POTA Upload Helper"      # the name until 2.0.0: its data folder is moved over on first start
VERSION = "2.0.68"


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
    for i in range(10):              # Windows: a reader holding the file open refuses the rename for a moment
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 9:
                raise
            time.sleep(0.05)


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


def pota_events(year):
    """POTA's event periods of a year in UTC: New Year's Week (1-7 January) and Support Your Parks (the third
    full weekend of January, April, July and October). -> [{"name", "start", "end"}], ISO, end exclusive."""
    out = [{"name": "New Year's Week", "start": "%d-01-01T00:00:00Z" % year, "end": "%d-01-08T00:00:00Z" % year}]
    for m in (1, 4, 7, 10):
        first = dt.date(year, m, 1)
        sat = first + dt.timedelta(days=(5 - first.weekday()) % 7 + 14)     # the first Saturday's Sunday is in the month
        out.append({"name": "Support Your Parks", "start": sat.isoformat() + "T00:00:00Z",
                    "end": (sat + dt.timedelta(days=2)).isoformat() + "T00:00:00Z"})
    return out


def my_call():
    """The callsign in use (設定 → コールサイン), or "" before one is saved."""
    s = load_settings()
    for c in [s.get("call")] + list(s.get("calls") or []):
        c = (c or "").strip().upper()
        if CALL_RE.fullmatch(c):
            return c
    return ""


# ---------- the network: offline mode (設定 → 通信) and hosts that did not answer
NET_RETRY = 60           # seconds a host that did not answer is left alone: nothing waits for its timeout again
_down = {}               # host -> when it last did not answer (no connection, not an HTTP error)


class Offline(urllib.error.URLError):
    """Not asked at all: offline mode is on, or this host did not answer a moment ago."""


def _host(url):
    return urllib.parse.urlsplit(url).hostname or ""


def net_check(url):
    """Before a request: raise Offline at once instead of waiting for a timeout."""
    if load_settings().get("offline"):
        raise Offline("offline mode")
    t = _down.get(_host(url))
    if t and time.time() - t < NET_RETRY:
        raise Offline("no connection")


def net_result(url, answered):
    """After a request: the host answered (any HTTP status) or not (DNS, refused, timed out)."""
    if answered:
        _down.pop(_host(url), None)
    else:
        _down[_host(url)] = time.time()


def cert_problem(e):
    """A certificate error (Python without certificates, python.org on macOS): the one case the system curl helps."""
    r = getattr(e, "reason", e)
    return isinstance(r, ssl.SSLError) or "CERTIFICATE" in str(r).upper()


def offline():
    """For the UI: "manual" (設定 → 通信), "down" (pota.app has not answered lately - the spot logger asks every
    minute) or ""."""
    if load_settings().get("offline"):
        return "manual"
    t = _down.get(_host(API))
    return "down" if t and time.time() - t < NET_RETRY * 2 else ""


CLOCK_WARN = 60          # seconds: P2P needs both logs within 15 min, and the other side's clock may be off too
_skew = None


def _note_clock(date, age=None):
    """Keep how far this computer's clock is from pota.app's (the response's Date header, 1 s resolution). A cached
    answer (CloudFront: "X-Cache: Hit", e.g. profile/ up to 5 min) carries the Date it was made and how long it has
    been kept (Age): the server's now is Date + Age.
    ponytail: only the urllib path sees headers; with the curl fallback the clock is not checked."""
    global _skew
    try:
        _skew = time.time() - email.utils.parsedate_to_datetime(date).timestamp() - float(age or 0)
    except (TypeError, ValueError):
        pass


def clock_skew():
    """Seconds this computer's clock is ahead of pota.app (behind < 0), only when off by CLOCK_WARN or
    more; None when it is close enough or nothing was fetched yet."""
    return round(_skew) if _skew is not None and abs(_skew) >= CLOCK_WARN else None


def fetch_json(path, timeout=20):
    """GET api.pota.app/<path>. Falls back to the system curl when Python's
    SSL certificates are not set up (common with python.org installs on macOS)."""
    url = path if path.startswith("http") else API + "/" + path.lstrip("/")
    net_check(url)                     # offline: raise at once, nothing waits
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            net_result(url, True)
            if url.startswith(API + "/"):      # pota.app's own clock only: a CDN's cached answer (the JMA's) carries an old Date
                _note_clock(r.headers.get("Date"), r.headers.get("Age"))
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError:
        net_result(url, True)          # the host answered
        raise
    except (ssl.SSLError, urllib.error.URLError, OSError) as e:
        if not cert_problem(e):        # no answer: offline for a moment (asking curl too used to double every wait)
            net_result(url, False)
            raise
        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}   # no console window on Windows
        out = subprocess.run(["curl", "-sS", "-m", str(timeout), "-A", USER_AGENT, url],
                             capture_output=True, check=True, **kw)
        return json.loads(out.stdout.decode("utf-8"))


# ---------- bands and modes ----------
BAND_EDGES = [(.1357, .1378, "2190m"), (.472, .479, "630m"), (.501, .504, "560m"), (1.8, 2.0, "160m"),
              (3.5, 4.0, "80m"), (5.06, 5.45, "60m"), (7.0, 7.3, "40m"), (10.1, 10.15, "30m"), (14.0, 14.35, "20m"),
              (18.068, 18.168, "17m"), (21.0, 21.45, "15m"), (24.89, 24.99, "12m"), (28.0, 29.7, "10m"),
              (40, 45, "8m"), (50.0, 54.0, "6m"), (54.000001, 69.9, "5m"), (70, 71, "4m"), (144.0, 148.0, "2m"),
              (222.0, 225.0, "1.25m"), (420.0, 450.0, "70cm"), (902.0, 928.0, "33cm"), (1240.0, 1300.0, "23cm"),
              (2300, 2450, "13cm"), (3300, 3500, "9cm"), (5650, 5925, "6cm"), (10000, 10500, "3cm"),
              (24000, 24250, "1.25cm"), (47000, 47200, "6mm"), (75500, 81000, "4mm"), (119980, 123000, "2.5mm"),
              (134000, 149000, "2mm"), (241000, 250000, "1mm"), (300000, 7500000, "submm")]   # ADIF 3.1.8 Band
BANDS = {b for _, _, b in BAND_EDGES}
PHONE_MODES = {"SSB", "USB", "LSB", "FM", "AM", "PHONE", "DV", "DIGITALVOICE", "DMR", "C4FM", "DSTAR", "D-STAR",
               "FREEDV", "M17"}
ADIF_MODES = {   # ADIF 3.1.8 Mode enumeration: MODE -> its SUBMODEs
    "AM": "",
    "ARDOP": "",
    "ATV": "",
    "CHIP": "CHIP64,CHIP128",
    "CLO": "",
    "CONTESTI": "",
    "CW": "PCW",
    "DIGITALVOICE": "C4FM,DMR,DSTAR,FREEDV,M17",
    "DOMINO": "DOM-M,DOM4,DOM5,DOM8,DOM11,DOM16,DOM22,DOM44,DOM88,DOMINOEX,DOMINOF",
    "DYNAMIC": "FREEDATA,VARA HF,VARA SATELLITE,VARA FM 1200,VARA FM 9600",
    "FAX": "",
    "FM": "",
    "FSK441": "",
    "FSK": "SCAMP_FAST,SCAMP_SLOW,SCAMP_VSLOW",
    "FT8": "",
    "HELL": "FMHELL,FSKH105,FSKH245,FSKHELL,HELL80,HELLX5,HELLX9,HFSK,PSKHELL,SLOWHELL",
    "ISCAT": "ISCAT-A,ISCAT-B",
    "JT4": "JT4A,JT4B,JT4C,JT4D,JT4E,JT4F,JT4G",
    "JT6M": "",
    "JT9": ("JT9-1,JT9-2,JT9-5,JT9-10,JT9-30,JT9A,JT9B,JT9C,JT9D,JT9E,JT9E FAST,JT9F,JT9F FAST,JT9G,"
           "JT9G FAST,JT9H,JT9H FAST"),
    "JT44": "",
    "JT65": "JT65A,JT65B,JT65B2,JT65C,JT65C2",
    "MFSK": ("FSQCALL,FST4,FST4W,FT2,FT4,JS8,JTMS,JTTY,MFSK4,MFSK8,MFSK11,MFSK16,MFSK22,MFSK31,MFSK32,MFSK64,"
            "MFSK64L,MFSK128,MFSK128L,Q65"),
    "MSK144": "",
    "MTONE": "SCAMP_OO,SCAMP_OO_SLW",
    "MT63": "",
    "OFDM": "RIBBIT_PIX,RIBBIT_SMS",
    "OLIVIA": "OLIVIA 4/125,OLIVIA 4/250,OLIVIA 8/250,OLIVIA 8/500,OLIVIA 16/500,OLIVIA 16/1000,OLIVIA 32/1000",
    "OPERA": "OPERA-BEACON,OPERA-QSO",
    "PAC": "PAC2,PAC3,PAC4",
    "PAX": "PAX2",
    "PKT": "",
    "PSK": ("8PSK125,8PSK125F,8PSK125FL,8PSK250,8PSK250F,8PSK250FL,8PSK500,8PSK500F,8PSK1000,8PSK1000F,"
           "8PSK1200F,FSK31,PSK10,PSK31,PSK63,PSK63F,PSK63RC4,PSK63RC5,PSK63RC10,PSK63RC20,PSK63RC32,PSK125,"
           "PSK125C12,PSK125R,PSK125RC10,PSK125RC12,PSK125RC16,PSK125RC4,PSK125RC5,PSK250,PSK250C6,PSK250R,"
           "PSK250RC2,PSK250RC3,PSK250RC5,PSK250RC6,PSK250RC7,PSK500,PSK500C2,PSK500C4,PSK500R,PSK500RC2,"
           "PSK500RC3,PSK500RC4,PSK800C2,PSK800RC2,PSK1000,PSK1000C2,PSK1000R,PSK1000RC2,PSKAM10,PSKAM31,"
           "PSKAM50,PSKFEC31,QPSK31,QPSK63,QPSK125,QPSK250,QPSK500,SIM31"),
    "PSK2K": "",
    "Q15": "",
    "QRA64": "QRA64A,QRA64B,QRA64C,QRA64D,QRA64E",
    "ROS": "ROS-EME,ROS-HF,ROS-MF",
    "RTTY": "ASCI",
    "RTTYM": "",
    "SSB": "LSB,USB",
    "SSTV": "",
    "T10": "",
    "THOR": "THOR-M,THOR4,THOR5,THOR8,THOR11,THOR16,THOR22,THOR25X4,THOR50X1,THOR50X2,THOR100",
    "THRB": "THRBX,THRBX1,THRBX2,THRBX4,THROB1,THROB2,THROB4",
    "TOR": "AMTORFEC,GTOR,NAVTEX,SITORB",
    "V4": "",
    "VOI": "",
    "WINMOR": "",
    "WSPR": "",
}
SUBMODES = {sub: mode for mode, subs in ADIF_MODES.items() for sub in subs.split(",") if sub}
MODE_ALIASES = {"D-STAR": "DSTAR", "DV": "DIGITALVOICE"}   # loggers' words for ADIF ones (VarAC: HF, FM or SAT - not guessed)


def band_name(value):
    """A BAND value as ADIF spells it ("20M" -> "20m"), or "" when it is not an ADIF band ("11m", "70m")."""
    v = (value or "").strip().lower()
    return v if v in BANDS else ""


def freq_text(value):
    """A FREQ as ADIF writes it: "14,074" (a decimal comma, as some locales type it) -> "14.074"."""
    v = str(value if value is not None else "").strip()
    return v.replace(",", ".") if "," in v and "." not in v else v


def band_from_mhz(mhz):
    try:
        mhz = float(freq_text(mhz))
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
    """A logger's mode word -> ADIF MODE (+SUBMODE): USB -> SSB + USB, FT4 -> MFSK + FT4, D-STAR -> DIGITALVOICE +
    DSTAR (a submode is never written as the MODE; ADIF 3.1.8 Mode / Submode). Other words stay as they are."""
    m = (mode or "").upper().strip()
    m = MODE_ALIASES.get(m, m)
    if m in SUBMODES:
        return {"MODE": SUBMODES[m], "SUBMODE": m}
    return {"MODE": m} if m else {}


def fix_mode_band(rec):
    """A received record as ADIF writes it, whatever the logger sent: MODE + SUBMODE from adif_mode; a known
    SUBMODE decides its MODE (DATA + FT4 -> MFSK + FT4, C4FM + C4FM -> DIGITALVOICE + C4FM; pota.app keeps the
    SUBMODE), BAND from FREQ (MHz) when it has none. -> rec, changed in place."""
    if rec.get("FREQ"):
        rec["FREQ"] = freq_text(rec["FREQ"])
        if not re.fullmatch(r"\d+(\.\d*)?|\.\d+", rec["FREQ"]):
            rec.pop("FREQ")                      # not a number ("14.074.000"): FREQ is optional for POTA, BAND is not
    sub = (rec.get("SUBMODE") or "").upper().strip()
    if sub in SUBMODES:
        rec.update(MODE=SUBMODES[sub], SUBMODE=sub)
    elif rec.get("MODE") and not sub:
        rec.update(adif_mode(rec["MODE"]))
    if not rec.get("BAND") and rec.get("FREQ"):
        rec["BAND"] = band_from_mhz(rec["FREQ"])
    return rec


def mode_known(rec):
    """Is the record's MODE one pota.app accepts (an ADIF mode)? Empty counts as not known."""
    return (rec.get("MODE") or "").upper() in ADIF_MODES


def mode_of(rec):
    """The mode pota.app tells QSOs apart by: the SUBMODE of a data mode (FT4 under MFSK), else MODE.
    An SSB sideband is not a different mode there."""
    mode = (rec.get("MODE") or "").upper()
    sub = (rec.get("SUBMODE") or "").upper()
    return mode if mode == "SSB" or not sub else sub


def pota_key(rec):
    """What pota.app keeps once per park file: CALL + BAND + MODE + their park (SIG_INFO)."""
    return ((rec.get("CALL") or "").upper(), (rec.get("BAND") or "").lower(), mode_of(rec), rec.get("SIG_INFO") or "")


def count_key(rec, park):
    """What makes this QSO one of the 10 an activation needs at `park`: "date|location|CALL|band|mode". pota.app
    counts an activation per park, location and UTC day, and drops a QSO with the same CALL (as written), band
    and mode there as a duplicate (Rules; the account-wide check is the same for one callsign)."""
    loc = (rec.get("MY_POTA_LOCS") or {}).get(park, "")
    return "|".join([rec.get("QSO_DATE") or "", loc, (rec.get("CALL") or "").upper(), (rec.get("BAND") or "").lower(),
                     mode_of(rec)])


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
        p = p.split("@")[0].strip()          # ADIF POTARef: "US-4239@US-MI" carries the location per park
        if p and PARK_RE.fullmatch(p) and p not in out:
            out.append(p)
    return out


def _sig_parks(rec, ref, sig, info):
    # *_SIG_INFO holds the reference of whatever *_SIG names: a WWFF "JAFF-0123" looks like a park
    return split_parks(rec.get(ref)) or (split_parks(rec.get(info)) if (rec.get(sig) or "POTA").upper() == "POTA" else [])


def their_parks_of(rec):
    """The other station's POTA parks in a record: POTA_REF, else SIG_INFO when SIG is POTA (or unset)."""
    return _sig_parks(rec, "POTA_REF", "SIG", "SIG_INFO")


def my_parks_of(rec):
    """My POTA parks in a record: MY_POTA_REF, else MY_SIG_INFO when MY_SIG is POTA (or unset)."""
    return _sig_parks(rec, "MY_POTA_REF", "MY_SIG", "MY_SIG_INFO")


# ---------- ADIF ----------
TAG_RE = re.compile(r"<([^:<>{},\s]+)(?::(\d+)(?::[^<>]*)?)?>")      # <NAME:LEN:TYPE>, <EOR>, <EOH>
NEXT_RE = re.compile(r"\s*(?:<|$)")


def parse_adif(text):
    """ADI records ({FIELD: value}, those with a CALL) from text. Each value is exactly its length long, so a
    tag or <eor> written inside a COMMENT stays in the COMMENT; the header (up to <EOH>) is skipped. A value
    whose length is wrong (counted in bytes, or Shift_JIS read as UTF-8) runs into the next field: then it
    is cut where the next tag starts, so the fields after it are still read."""
    m = re.search(r"<eoh>", text, re.I)
    pos, recs, d = (m.end() if m else 0), [], {}
    while True:
        m = TAG_RE.search(text, pos)
        if not m:
            break
        pos = m.end()
        name = m.group(1).upper()
        if m.group(2) is None:                           # <EOR> (or a stray <...> between fields)
            if name == "EOR":
                if d.get("CALL"):
                    recs.append(d)
                d = {}
            continue
        v = text[pos:pos + int(m.group(2))]
        if not NEXT_RE.match(text, pos + len(v)):        # not followed by a tag: the length was wrong
            nxt = TAG_RE.search(text, pos)               # the value ends where the next tag starts
            if nxt and nxt.start() < pos + len(v):
                v = text[pos:nxt.start()]
        d[name] = v
        pos += len(v)
    if d.get("CALL"):
        recs.append(d)
    return recs


def parse_adx(root):
    """Records ({FIELD: value}, those with a CALL) of an ADX document (ADIF's XML form; root = the <ADX>
    element): each <RECORD>'s children are its fields, <APP PROGRAMID= FIELDNAME=> becomes APP_<prog>_<name>,
    USERDEF fields are left out."""
    recs = []
    for rec in root.iter():
        if rec.tag.upper() != "RECORD":
            continue
        d = {}
        for f in rec:
            tag = f.tag.upper()
            if tag == "APP":
                tag = "APP_%s_%s" % (f.get("PROGRAMID", ""), f.get("FIELDNAME", ""))
            if tag != "USERDEF":
                d[tag.upper()] = (f.text or "").strip()
        if d.get("CALL"):
            recs.append(d)
    return recs


def read_adif(path):
    """The records of an ADI file, or of an ADX one (ADIF's XML form)."""
    text = open(path, encoding="utf-8-sig", errors="ignore").read()      # -sig: .NET loggers write a BOM
    head = text.lstrip()[:200].upper()
    if head.startswith("<?XML") or head.startswith("<ADX"):
        import xml.etree.ElementTree as ET
        try:
            return parse_adx(ET.fromstring(text.lstrip()))
        except ET.ParseError:
            pass
    return parse_adif(text)


GRID_RE = re.compile(r"[A-R]{2}(\d{2}([A-X]{2}(\d{2})?)?)?", re.I)      # ADIF GridSquare: 2, 4, 6 or 8 characters


def adif_value(name, value):
    """A value as an ADI file may hold it: ASCII 32-126 only ("IntlString ... cannot be used in ADI files"),
    full-width forms made plain first (NFKC: "５９" -> "59"); "" when anything else is left (a Japanese name,
    a line break) or a grid square is not one."""
    v = unicodedata.normalize("NFKC", "" if value is None else str(value)).strip()
    if not all(32 <= ord(c) <= 126 for c in v):
        return ""
    if name in ("GRIDSQUARE", "MY_GRIDSQUARE") and not GRID_RE.fullmatch(v):
        return ""
    return v


def adif_field(name, value):
    value = "" if value is None else str(value)
    return "<%s:%d>%s" % (name, len(value), value)


def write_adif(path, recs, order, program="Potaroo"):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d %H%M%S")
    lines = ["Generated by %s\n<ADIF_VER:5>3.1.8 <PROGRAMID:%d>%s <PROGRAMVERSION:%d>%s <CREATED_TIMESTAMP:15>%s <EOH>\n"
             % (program, len(program), program, len(VERSION), VERSION, stamp)]
    for r in recs:
        vals = [(k, adif_value(k, r.get(k))) for k in order] + [(k, adif_value(k, v)) for k, v in r.items() if k not in order]
        parts = [adif_field(k, v) for k, v in vals if v]
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
    """A record's QSO_DATE + TIME_ON in minutes, or None (no TIME_ON is no time, not 00:00)."""
    try:
        date = rec.get("QSO_DATE") or ""
        return minutes(date, rec["TIME_ON"]) if rec.get("TIME_ON") and re.fullmatch(r"\d{8}", date) else None
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
