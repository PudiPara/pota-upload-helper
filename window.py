"""Shrink the pywebview window to a strip above the logger while activating, and grow it back."""
import os
import sys

import webview

BAR_W, BAR_H = 640, 236


def _top_right(w):
    scr = webview.screens           # a list-like proxy in pywebview 5/6, a function in 4
    try:
        scr = scr[0]
    except TypeError:
        scr = scr()[0]
    w.move(max(0, scr.width - BAR_W - 24), 40)


def _run_steps(w, steps):
    """Run window calls, each best effort (report, don't abort the rest).
    On Windows they are posted to the UI thread and not waited for: the pywebview API thread holds
    the GIL while WinForms sends a message to the UI thread, and the UI thread is waiting for the
    GIL to answer another JavaScript call -> deadlock (froze 「記録を始める」). macOS calls them directly."""
    def run():
        for what, fn in steps:
            try:
                fn()
            except Exception as e:
                print("bar mode %s failed: %s" % (what, e), file=sys.stderr)
    native = getattr(w, "native", None)
    if os.name == "nt" and hasattr(native, "BeginInvoke"):
        from System import Func, Type    # pythonnet, always there when pywebview runs on Windows
        native.BeginInvoke(Func[Type](run))
    else:
        run()


def focus_running(title):
    """A second copy was started: bring the first one's window to the front instead (Windows;
    macOS already does this itself when an .app is opened twice)."""
    if os.name != "nt":
        return
    import ctypes
    u = ctypes.windll.user32
    h = u.FindWindowW(None, title)
    if h:
        u.ShowWindow(h, 9)          # SW_RESTORE
        u.SetForegroundWindow(h)


class BarMode:
    def __init__(self, window, keep_on_top=False):
        self.window = window
        self._full = None          # (x, y, w, h) before the window became a bar
        self.keep_on_top = keep_on_top   # 設定 → 常に最前面: also outside bar mode

    def set_on_top(self, on):
        """設定 → 常に最前面. Bar mode is always on top; this decides the full window."""
        self.keep_on_top = bool(on)
        w = self.window
        if w and self._full is None:
            _run_steps(w, [("on_top", lambda: setattr(w, "on_top", self.keep_on_top))])
        return self.keep_on_top

    @property
    def active(self):
        return self._full is not None

    def set(self, on):
        w = self.window
        if not w:
            return False
        if on and self._full is None:
            self._full = (w.x, w.y, w.width, w.height)
            _run_steps(w, [("on_top", lambda: setattr(w, "on_top", True)),
                           ("resize", lambda: w.resize(BAR_W, BAR_H)),
                           ("move", lambda: _top_right(w))])
        elif not on and self._full is not None:
            x, y, width, height = self._full
            self._full = None
            _run_steps(w, [("on_top", lambda: setattr(w, "on_top", self.keep_on_top)),
                           ("resize", lambda: w.resize(width, height)),
                           ("move", lambda: w.move(x, y))])
        return self._full is not None
