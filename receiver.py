"""Receive QSOs from loggers over UDP (like OpsLog / JTAlert / GridTracker do).

Formats are detected per packet, whatever the listener is labelled:
  * N1MM Logger+ XML  <contactinfo>, <contactreplace>, <contactdelete>   (RUMlogNG, N1MM, DXLog...)
  * WSJT-X / JTDX binary protocol, message 12 "Logged ADIF"
  * plain ADIF text (one or more records), also ADIF wrapped in XML (RUMlog "Contact info ADIF")
Every listener can also forward the raw packet to another host:port, so the
app can sit between your logger and another program (e.g. RUMlog -> here -> OpsLog).
"""
import html
import os
import re
import socket
import struct
import threading
import xml.etree.ElementTree as ET

from i18n import t
from potacommon import FIELD_RE, band_from_mhz

WSJTX_MAGIC = 0xADBCCBDA
N1MM_BANDS = {"1.8": "160m", "3.5": "80m", "5": "60m", "7": "40m", "10": "30m", "14": "20m", "18": "17m",
              "21": "15m", "24": "12m", "28": "10m", "50": "6m", "144": "2m", "222": "1.25m", "420": "70cm",
              "430": "70cm", "432": "70cm", "902": "33cm", "1240": "23cm", "1296": "23cm"}
DEFAULT_LISTENERS = [
    {"name": "WSJT-X / JTDX", "kind": "wsjtx", "port": 2237, "multicast": "224.0.0.1", "enabled": True, "forward": ""},
    {"name": "RUMlogNG (N1MM)", "kind": "n1mm", "port": 2334, "multicast": "", "enabled": False, "forward": ""},
]


# ---------------------------------------------------------------- parsers
def parse_adif_text(text):
    text = html.unescape(text)
    out = []
    for chunk in re.split(r"<eor>", text, flags=re.I):
        d = {}
        for f in FIELD_RE.finditer(chunk):
            d[f.group(1).upper()] = chunk[f.end():f.end() + int(f.group(2))]
        if d.get("CALL"):
            out.append(d)
    return out


def parse_n1mm(root):
    """-> ("upsert"|"delete", record, uid)"""
    g = lambda k: (root.findtext(k) or "").strip()
    ts = g("timestamp")                       # "2026-10-20 02:26:00"
    date, tm = (ts[:10].replace("-", ""), ts[11:19].replace(":", "")) if len(ts) >= 16 else ("", "")
    uid = g("ID") or g("id") or None
    if root.tag.lower() == "contactdelete":
        return "delete", {"CALL": g("call").upper(), "QSO_DATE": date, "TIME_ON": tm}, uid
    rec = {"CALL": g("call").upper(), "QSO_DATE": date, "TIME_ON": tm}
    freq = g("txfreq") or g("rxfreq")
    if freq:
        try:
            mhz = int(float(freq)) / 100000.0      # N1MM sends 10 Hz units
            rec["FREQ"] = "%.6f" % mhz
            rec["BAND"] = band_from_mhz(mhz)
        except ValueError:
            pass
    if not rec.get("BAND") and g("band"):
        rec["BAND"] = N1MM_BANDS.get(g("band"), g("band") + "m" if g("band").isdigit() else g("band"))
    mode = g("mode").upper()
    if mode in ("FT8", "FT4", "JS8", "JT65", "JT9", "PSK31", "RTTY", "CW", "SSB", "USB", "LSB", "FM", "AM"):
        rec["MODE"] = {"USB": "SSB", "LSB": "SSB"}.get(mode, mode)
        if mode == "FT4":
            rec.update({"MODE": "MFSK", "SUBMODE": "FT4"})
    elif mode:
        rec["MODE"] = mode
    for src, dst in (("snt", "RST_SENT"), ("rcv", "RST_RCVD"), ("gridsquare", "GRIDSQUARE"),
                     ("mycall", "STATION_CALLSIGN"), ("operator", "OPERATOR"), ("name", "NAME"),
                     ("comment", "COMMENT")):
        if g(src):
            rec[dst] = g(src)
    return "upsert", rec, uid


def read_qt_string(buf, off):
    (n,) = struct.unpack_from(">I", buf, off)
    off += 4
    if n == 0xFFFFFFFF:
        return "", off
    return buf[off:off + n].decode("utf-8", "replace"), off + n


def parse_packet(data):
    """-> list of (action, record, uid). Unknown packets -> []"""
    if len(data) >= 12 and struct.unpack_from(">I", data, 0)[0] == WSJTX_MAGIC:
        _, _, mtype = struct.unpack_from(">III", data, 0)
        if mtype == 12:                                        # Logged ADIF
            _, off = read_qt_string(data, 12)
            adif, _ = read_qt_string(data, off)
            return [("upsert", r, None) for r in parse_adif_text(adif)]
        return []
    text = data.decode("utf-8", "replace").strip()
    if text.startswith("<?xml") or text.lower().startswith("<contact"):
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            root = None
        if root is not None and root.tag.lower() in ("contactinfo", "contactreplace", "contactdelete"):
            return [parse_n1mm(root)]
        # XML that carries ADIF inside (RUMlog "Contact info ADIF" etc.)
        return [("upsert", r, None) for r in parse_adif_text(text)]
    if re.search(r"<call:\d+", text, re.I):
        return [("upsert", r, None) for r in parse_adif_text(text)]
    return []


# ---------------------------------------------------------------- receiver
LOOPBACK = "127.0.0.1"


def bind_address(group):
    """Where a listener binds. Unicast listeners take packets from this computer only
    (loggers send to 127.0.0.1), so nothing on the network can feed QSOs in.
    A multicast listener (WSJT-X on 224.0.0.1) must bind the group itself to receive it;
    Windows can't bind a multicast address, so there it binds the wildcard and the
    group membership does the filtering."""
    if not group:
        return LOOPBACK
    return "" if os.name == "nt" else group


def describe_state(state):
    """A listener's state dict (see Receiver.state) -> {"code", "text"} in the current language."""
    if not isinstance(state, dict):
        state = {"code": "off"}
    code = state.get("code", "off")
    port = state.get("port", "")
    where = "%s:%s" % (state["multicast"], port) if state.get("multicast") else t("recv.port", port=port)
    text = {"off": t("recv.off"), "error": t("recv.cantOpen", port=port, err=state.get("err", "")),
            "badforward": t("recv.badForward"), "listening": t("recv.listening", where=where),
            "receiving": t("recv.receiving", where=where)}.get(code, code)
    return {"code": code, "text": text}


class Receiver:
    """One UDP socket per enabled listener. on_qso(action, record, uid, listener_name) and
    on_status(listener_name, state) are called from worker threads. self.state[name] is a dict:
    {"code": off|error|badforward|listening|receiving, "port", "multicast", "err"} - codes, not text,
    so the UI can translate them (describe_state)."""

    def __init__(self, listeners, on_qso, on_status=None):
        self.listeners = listeners
        self.on_qso = on_qso
        self.on_status = on_status or (lambda *a: None)
        self._stop = threading.Event()
        self._threads = []
        self.state = {}

    def start(self):
        self._stop.clear()
        for cfg in self.listeners:
            if not cfg.get("enabled"):
                self.state[cfg["name"]] = {"code": "off"}
                continue
            t = threading.Thread(target=self._run, args=(cfg,), daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2)
        self._threads = []

    def _open(self, cfg):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        group = (cfg.get("multicast") or "").strip()
        s.bind((bind_address(group), int(cfg["port"])))
        if group:
            mreq = struct.pack("4s4s", socket.inet_aton(group), socket.inet_aton("0.0.0.0"))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        s.settimeout(1.0)
        return s

    def _run(self, cfg):
        name = cfg["name"]
        base = {"port": cfg["port"], "multicast": (cfg.get("multicast") or "").strip()}
        try:
            sock = self._open(cfg)
        except OSError as e:
            self.state[name] = dict(base, code="error", err=str(e.strerror or e))
            self.on_status(name, self.state[name])
            return
        self.state[name] = dict(base, code="listening")
        self.on_status(name, self.state[name])
        fwd = None
        if cfg.get("forward"):
            try:
                h, p = cfg["forward"].rsplit(":", 1)
                fwd = (h.strip() or "127.0.0.1", int(p))
            except ValueError:
                self.state[name] = dict(base, code="badforward")
                self.on_status(name, self.state[name])
        out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if fwd else None
        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            if out:
                try:
                    out.sendto(data, fwd)
                except OSError:
                    pass
            for action, rec, uid in parse_packet(data):
                self.state[name] = dict(base, code="receiving")
                self.on_qso(action, rec, uid, name)
        sock.close()
