#!/usr/bin/env python3
"""A second copy of the dev app on a copy of ./data, for anything that changes data (deletes, finishing an
activation, test QSOs): the dev app on ./data is never touched.

    python scripts/copy_instance.py            # copy ./data -> <tmp>/potaroo-copy, start it
    python scripts/copy_instance.py --keep     # start it on the copy made last time

The copy listens for WSJT-X on UDP 22299 only (send with scripts/send_test_qso.py 22299 CALL), writes its
upload files to <copy>/out, and is driven with CDP_PORT=9334 node scripts/cdp.mjs ... (Windows / WebView2).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COPY = os.path.join(tempfile.gettempdir(), "potaroo-copy")
UDP, CDP = 22299, 9334

if "--keep" not in sys.argv or not os.path.isdir(COPY):
    shutil.rmtree(COPY, ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, "data"), COPY, ignore=shutil.ignore_patterns("*.lock", "potaroo.log*"))
    p = os.path.join(COPY, "settings.json")
    s = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    s["out"] = os.path.join(COPY, "out")
    s["listeners"] = [{"name": "test", "kind": "wsjtx", "port": UDP, "multicast": "", "enabled": True, "forward": ""}]
    json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

env = dict(os.environ, POTAROO_DATA=COPY, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--remote-debugging-port=%d" % CDP)
py = sys.executable
if os.name == "nt" and os.path.basename(py).lower() == "python.exe" and os.path.exists(py[:-10] + "pythonw.exe"):
    py = py[:-10] + "pythonw.exe"                       # no console window
subprocess.Popen([py, os.path.join(ROOT, "app.py")], env=env, cwd=ROOT)
print("copy instance on %s - UDP %d, CDP_PORT=%d" % (COPY, UDP, CDP))
