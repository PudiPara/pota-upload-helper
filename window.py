"""The bar: a second, small always-on-top window above the logger while activating; the main window
stays as it is, so the other pages can be used meanwhile."""
import os
import sys

import webview

BAR_W, BAR_H = 600, 116


def _top_right():
    scr = webview.screens           # a list-like proxy in pywebview 5/6, a function in 4
    try:
        scr = scr[0]
    except TypeError:
        scr = scr()[0]
    return max(0, scr.width - BAR_W - 24), 40


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
        if u.IsIconic(h):
            u.ShowWindow(h, 9)      # SW_RESTORE (only when minimized: it would un-maximize too)
        u.SetForegroundWindow(h)


class BarMode:
    def __init__(self, window, url, js_api, title, keep_on_top=False, bar_on_top=True):
        self.window = window             # the main window
        self._url, self._api, self._title = url, js_api, title
        self._bar = None                 # the bar window while it is open
        self._on = False
        self.keep_on_top = keep_on_top   # 設定 → ウインドウ: the main window on top
        self.bar_on_top = bar_on_top     # 設定 → ウインドウ: the bar on top

    def set_on_top(self, on):
        """設定 → 常に最前面 for the main window."""
        self.keep_on_top = bool(on)
        w = self.window
        if w:
            _run_steps(w, [("on_top", lambda: setattr(w, "on_top", self.keep_on_top))])
        return self.keep_on_top

    def set_bar_on_top(self, on):
        self.bar_on_top = bool(on)
        bar = self._bar
        if bar:
            _run_steps(self.window, [("bar on_top", lambda: setattr(bar, "on_top", self.bar_on_top))])
        return self.bar_on_top

    def fit(self, width, inner):
        """Make the bar as wide as its content (CSS px `width`; `inner` = the page's current width, so the
        window's own border is kept), keeping its right edge where it is."""
        bar = self._bar
        if not bar:
            return

        def run():
            new = bar.width - inner + width
            x = bar.x + bar.width - new
            bar.resize(new, bar.height)
            bar.move(x, bar.y)
        _run_steps(self.window, [("fit", run)])

    @property
    def active(self):
        return self._on

    def _closed(self):
        self._bar, self._on = None, False

    def _open(self):
        x, y = _top_right()
        bar = webview.create_window(self._title, self._url + "#bar", js_api=self._api, width=BAR_W, height=BAR_H,
                                    x=x, y=y, frameless=True, on_top=self.bar_on_top)   # a banner: dragged by its tile (.pywebview-drag-region)
        bar.events.closed += self._closed
        self._bar = bar

    def set(self, on):
        """Open the bar window (index.html#bar) or close it. The calls go through the main window's UI
        thread (_run_steps): a window created or destroyed from the API thread can deadlock on Windows."""
        w = self.window
        if not w:
            return False
        if on and not self._on:
            self._on = True
            _run_steps(w, [("open", self._open)])
        elif not on and self._on:
            self._on = False
            bar = self._bar
            _run_steps(w, [("close", lambda: bar and bar.destroy())])
        return self._on
