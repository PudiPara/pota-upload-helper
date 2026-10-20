"""Shrink the pywebview window to a strip above the logger while activating, and grow it back."""
import sys

import webview

BAR_W, BAR_H = 640, 236


class BarMode:
    def __init__(self, window):
        self.window = window
        self._full = None          # (x, y, w, h) before the window became a bar

    @property
    def active(self):
        return self._full is not None

    def set(self, on):
        w = self.window
        if not w:
            return False

        def step(what, fn):          # each window call is best effort; report instead of aborting the rest
            try:
                fn()
            except Exception as e:
                print("bar mode %s failed: %s" % (what, e), file=sys.stderr)

        if on and self._full is None:
            self._full = (w.x, w.y, w.width, w.height)
            step("on_top", lambda: setattr(w, "on_top", True))
            step("resize", lambda: w.resize(BAR_W, BAR_H))

            def move_top_right():
                scr = webview.screens           # a list-like proxy in pywebview 5/6, a function in 4
                try:
                    scr = scr[0]
                except TypeError:
                    scr = scr()[0]
                w.move(max(0, scr.width - BAR_W - 24), 40)
            step("move", move_top_right)
        elif not on and self._full is not None:
            x, y, width, height = self._full
            self._full = None
            step("on_top", lambda: setattr(w, "on_top", False))
            step("resize", lambda: w.resize(width, height))
            step("move", lambda: w.move(x, y))
        return self._full is not None
