"""Read QSOs from Turbo HAMLOG/Win while it runs (Windows only).

HAMLOG sends nothing out over UDP and keeps HAMLOG.HDB locked, but its author publishes a
WM_COPYDATA interface (Th527API.zip, HamlogMs.txt, JG1MOU): command 116 returns the number of
records, command 119 the fields of one record (Call .. Remarks2, one per line). We ask on a
message-only window of our own; HAMLOG answers by WM_COPYDATA to it while SendMessage waits.
Conditions of the API: tools for Turbo HAMLOG only - this reads a running HAMLOG's log.
"""
import ctypes
import datetime as dt
import os
import re

from potacommon import adif_mode, band_from_mhz

CMD_COUNT, CMD_RECORD = 116, 119
WM_COPYDATA = 0x004A
FIELDS = ("call", "date", "time", "his", "my", "freq", "mode", "code", "grid", "qsl", "name", "qth", "rmk1", "rmk2")


def parse_record(text, jst_offset=9):
    """HAMLOG's 14 lines (Call .. Remarks2) -> an ADIF-like dict, times in UTC.
    Date "26/10/21", time "10:30J" (JST) or "01:30U" (UTC), Freq in MHz ("7", "7.015")."""
    lines = text.replace("\r\n", "\n").split("\n")
    if len(lines) > len(FIELDS) and (lines[0] == "" or lines[0].strip().isdigit()):
        lines = lines[1:]                                     # 115: empty first line, 119: the record number
    f = dict(zip(FIELDS, [s.strip() for s in lines] + [""] * len(FIELDS)))
    if not f["call"]:
        return None
    m = re.match(r"(\d{2,4})/(\d{1,2})/(\d{1,2})", f["date"])
    tm = re.match(r"(\d{1,2}):?(\d{2})\s*([JUju]?)", f["time"])
    if not m or not tm:
        return None
    y = int(m.group(1)); y += 2000 if y < 100 else 0
    when = dt.datetime(y, int(m.group(2)), int(m.group(3)), int(tm.group(1)), int(tm.group(2)))
    if tm.group(3).upper() != "U":
        when -= dt.timedelta(hours=jst_offset)                # HAMLOG keeps JST unless the time ends in U
    rec = {"CALL": f["call"].upper(), "QSO_DATE": when.strftime("%Y%m%d"), "TIME_ON": when.strftime("%H%M%S")}
    try:
        mhz = float(re.sub(r"[^0-9.]", "", f["freq"]) or "x")
        rec["BAND"] = band_from_mhz(mhz)
        if "." in f["freq"]:
            rec["FREQ"] = "%.6f" % mhz
    except ValueError:
        pass
    rec.update(adif_mode(f["mode"]))
    for k, a in (("his", "RST_SENT"), ("my", "RST_RCVD"), ("name", "NAME"), ("qth", "QTH"), ("grid", "GRIDSQUARE")):
        if f[k]:
            rec[a] = f[k]
    note = " ".join(x for x in (f["rmk1"], f["rmk2"]) if x)
    if note:
        rec["COMMENT"] = note
    return rec


_CLASS = "PotarooHamlog"
_PROC = None          # one window procedure for the process, kept alive for good
_CLIENTS = {}         # hwnd -> Client: the class is registered once, so the procedure finds its client here


class Client:
    """A message-only window on the calling thread; ask() must run on that same thread.
    close() it when done: a listener restart makes a new Client."""

    def __init__(self):
        global _PROC
        if os.name != "nt":
            raise OSError("Windows only")
        import ctypes.wintypes as W
        self.u = u = ctypes.windll.user32
        k = ctypes.windll.kernel32
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

        class COPYDATASTRUCT(ctypes.Structure):
            _fields_ = [("dwData", ctypes.c_size_t), ("cbData", W.DWORD), ("lpData", ctypes.c_void_p)]

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HICON),
                        ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH), ("lpszMenuName", W.LPCWSTR),
                        ("lpszClassName", W.LPCWSTR)]

        self.CDS = COPYDATASTRUCT
        u.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        u.DefWindowProcW.restype = LRESULT
        u.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT, ctypes.POINTER(ctypes.c_size_t)]
        u.FindWindowW.restype = W.HWND
        u.DestroyWindow.argtypes = [W.HWND]
        u.CreateWindowExW.restype = W.HWND
        u.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
        self._reply = None
        hinst = k.GetModuleHandleW(None)
        if _PROC is None:
            # Registered once: a class keeps the procedure it was registered with, so a per-client
            # procedure would leave a second client (after 保存して受信し直す) answering the first one.
            _PROC = WNDPROC(_dispatch)
            u.RegisterClassW(ctypes.byref(WNDCLASSW(lpfnWndProc=_PROC, hInstance=hinst, lpszClassName=_CLASS)))
        self.hwnd = u.CreateWindowExW(0, _CLASS, "Potaroo HAMLOG", 0, 0, 0, 0, 0, W.HWND(-3), None, hinst, None)
        if not self.hwnd:
            raise OSError("cannot create the message window")
        _CLIENTS[self.hwnd] = self

    def close(self):
        if self.hwnd:
            _CLIENTS.pop(self.hwnd, None)
            self.u.DestroyWindow(self.hwnd)
            self.hwnd = None

    def _copydata(self, lp):
        cds = ctypes.cast(lp, ctypes.POINTER(self.CDS)).contents
        data = ctypes.string_at(cds.lpData, cds.cbData) if cds.lpData and cds.cbData else b""
        self._reply = data.split(b"\0", 1)[0].decode("cp932", "replace")
        return 1

    def running(self):
        return bool(self.u.FindWindowW("TThwin", None))

    def ask(self, cmd, arg=None, timeout_ms=3000):
        """Send a command; -> HAMLOG's answer text, or None when HAMLOG isn't there or didn't answer."""
        h = self.u.FindWindowW("TThwin", None)
        if not h:
            return None
        buf = ctypes.create_string_buffer(arg.encode("cp932") + b"\0") if arg is not None else None
        cds = self.CDS(cmd, len(buf) if buf is not None else 0, ctypes.cast(buf, ctypes.c_void_p) if buf is not None else None)
        self._reply = None
        res = ctypes.c_size_t(0)
        ok = self.u.SendMessageTimeoutW(h, WM_COPYDATA, self.hwnd, ctypes.addressof(cds), 0x0002, timeout_ms, ctypes.byref(res))
        return self._reply if ok else None

    def count(self):
        """Records in HAMLOG.HDB, or None."""
        r = self.ask(CMD_COUNT)
        m = re.search(r"\d+", r or "")
        return int(m.group()) if m else None

    def record(self, n):
        r = self.ask(CMD_RECORD, str(n))
        return parse_record(r) if r else None


def _dispatch(hwnd, msg, wp, lp):
    c = _CLIENTS.get(hwnd)
    if c and msg == WM_COPYDATA:
        return c._copydata(lp)
    return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wp, lp)
