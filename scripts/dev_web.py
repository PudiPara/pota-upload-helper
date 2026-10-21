#!/usr/bin/env python3
"""Run the UI in a normal browser for development checks (no pywebview window).

    POTAROO_DATA=./data python scripts/dev_web.py [port]      -> http://127.0.0.1:8765/

Serves ui/ and answers POST /api/<method> with the JSON result of the real app.Api method, so the page
behaves like the desktop app. A small script injected into index.html defines window.pywebview.api.
Window-only calls (file dialogs, bar mode) do nothing here. Binds 127.0.0.1 only; dev use only.
"""
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("POTAROO_DATA", os.path.join(ROOT, "data"))
sys.path.insert(0, ROOT)
import app  # noqa: E402

UI = os.path.join(ROOT, "ui")
SHIM = b"""<script>
window.pywebview = { api: new Proxy({}, { get: (_, name) => (...args) =>
  fetch('/api/' + name, { method: 'POST', body: JSON.stringify(args) }).then((r) => r.json()) }) };
</script>
"""
app.Api.start_receiver = lambda self: None   # the desktop dev app owns the UDP listeners
api = app.Api()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=UI, **kw)

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = open(os.path.join(UI, "index.html"), "rb").read()
            html = html.replace(b'<script src="app.js">', SHIM + b'<script src="app.js">', 1)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html)
            return
        super().do_GET()

    def do_POST(self):
        name = self.path.rsplit("/", 1)[-1]
        fn = getattr(api, name, None)
        if name.startswith("_") or not callable(fn):
            self.send_error(404)
            return
        args = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"[]")
        try:
            result = fn(*args)
        except Exception as e:          # window-only calls etc.
            result = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        body = json.dumps(result, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print("http://127.0.0.1:%d/  (data: %s)" % (port, os.environ["POTAROO_DATA"]), flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
