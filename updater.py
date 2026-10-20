"""Update the app from GitHub Releases (stdlib only).

check()    -> what the latest release is and whether this build can install it
install()  -> download the zip for this OS and swap the running app for it
relaunch() -> start the new copy once this process has quit (macOS); on Windows
              the helper script started by install() does that
"""
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

from potacommon import APP_NAME, VERSION, fetch_json

REPO = "PudiPara/pota-upload-helper"
LATEST = "https://api.github.com/repos/%s/releases/latest" % REPO
PAGE = "https://github.com/%s/releases/latest" % REPO
DOWNLOAD_PREFIX = "https://github.com/%s/releases/download/" % REPO
ASSETS = {"darwin": "POTA-Upload-Helper-macOS.zip", "win32": "POTA-Upload-Helper-Windows.zip"}


def parse_version(tag):
    """'v1.2.3' / '1.2' -> (1, 2, 3) / (1, 2, 0)"""
    nums = [int(x) for x in re.findall(r"\d+", tag or "")][:3]
    return tuple(nums + [0] * (3 - len(nums)))


def frozen():
    return bool(getattr(sys, "frozen", False))


def app_path():
    """The installed thing to replace: the .app on macOS, the .exe on Windows, None from source."""
    if not frozen():
        return None
    exe = os.path.abspath(sys.executable)
    if sys.platform == "darwin":
        app = os.path.dirname(os.path.dirname(os.path.dirname(exe)))   # X.app/Contents/MacOS/X
        return app if app.endswith(".app") else None
    if os.name == "nt":
        return exe
    return None


def translocated(path):
    """macOS runs a quarantined app from a hidden read-only copy; we can't know where the user keeps it."""
    return bool(path) and "/AppTranslocation/" in path


def summarize(rel, platform=None, installed=None):
    """-> dict for the UI, from the GitHub 'latest release' JSON."""
    platform = platform or sys.platform
    tag = rel.get("tag_name") or ""
    want = ASSETS.get("win32" if platform.startswith("win") else platform)
    asset = next((a for a in rel.get("assets") or [] if a.get("name") == want), None)
    url = (asset or {}).get("browser_download_url") or ""
    installed = installed if installed is not None else app_path()
    return {"current": VERSION, "latest": tag.lstrip("vV"), "newer": parse_version(tag) > parse_version(VERSION),
            "notes": (rel.get("body") or "")[:3000], "page": rel.get("html_url") or PAGE, "asset": url,
            "can_install": bool(url and installed), "translocated": translocated(installed)}


def check():
    return summarize(fetch_json(LATEST, timeout=15))


# ---------------------------------------------------------------- download / install
def download(url, dest, timeout=600):
    if not url.startswith(DOWNLOAD_PREFIX):
        raise ValueError("更新ファイルの場所が想定と違います: %s" % url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pota-upload-helper/" + VERSION})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as fh:
            shutil.copyfileobj(r, fh)
    except (ssl.SSLError, urllib.error.URLError):
        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
        subprocess.run(["curl", "-sSL", "-m", str(timeout), "-A", "pota-upload-helper/" + VERSION, "-o", dest, url],
                       check=True, **kw)
    if os.path.getsize(dest) < 1_000_000:
        raise RuntimeError("ダウンロードしたファイルが小さすぎます（%d バイト）" % os.path.getsize(dest))


def install(url, installed=None):
    """-> {'relaunch': path} when the app was replaced in place, or
          {'manual': path, 'manual_dir': dir} when the new copy was only put somewhere for the user."""
    installed = installed or app_path()
    if not installed:
        raise RuntimeError("ソースから起動しているので自動更新はできません。")
    work = tempfile.mkdtemp(prefix="pota-update-")
    zip_path = os.path.join(work, "update.zip")
    download(url, zip_path)
    if sys.platform == "darwin":
        return _install_mac(zip_path, work, installed)
    if os.name == "nt":
        return _install_win(zip_path, work, installed)
    raise RuntimeError("この OS では自動更新に対応していません。")


def _install_mac(zip_path, work, app):
    subprocess.run(["ditto", "-x", "-k", zip_path, work], check=True)      # keeps the bundle intact
    apps = [d for d in os.listdir(work) if d.endswith(".app")]
    if not apps:
        raise RuntimeError("更新ファイルにアプリが入っていません。")
    new = os.path.join(work, apps[0])
    if translocated(app):
        dest = os.path.join(os.path.expanduser("~/Downloads"), os.path.basename(new))
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.move(new, dest)
        return {"manual": dest, "manual_dir": os.path.dirname(dest)}
    old = app + ".old"
    if os.path.exists(old):
        shutil.rmtree(old, ignore_errors=True)
    os.rename(app, old)                   # the running process keeps its files; cleanup() removes .old next start
    try:
        shutil.move(new, app)
    except Exception:
        os.rename(old, app)
        raise
    return {"relaunch": app}


def _install_win(zip_path, work, exe):
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(work)
    exes = [f for f in os.listdir(work) if f.lower().endswith(".exe")]
    if not exes:
        raise RuntimeError("更新ファイルに実行ファイルが入っていません。")
    new = os.path.join(work, exes[0])
    script = os.path.join(work, "update.cmd")
    with open(script, "w", encoding="cp932", errors="replace") as fh:
        fh.write("@echo off\r\n:wait\r\n"
                 'tasklist /FI "PID eq %d" 2>nul | find "%d" >nul\r\n' % (os.getpid(), os.getpid()) +
                 "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)\r\n"
                 'move /y "%s" "%s.old" >nul\r\n' % (exe, exe) +
                 'move /y "%s" "%s" >nul\r\n' % (new, exe) +
                 'start "" "%s"\r\n' % exe)
    subprocess.Popen(["cmd.exe", "/c", script], creationflags=0x00000008 | 0x00000200 | 0x08000000, close_fds=True)
    return {"relaunch": exe}


def relaunch(path):
    """macOS: start the new bundle once this process is gone (the helper script does it on Windows)."""
    if sys.platform == "darwin":
        subprocess.Popen(["/bin/sh", "-c", 'sleep 2; open -n "%s"' % path.replace('"', '\\"')])


def cleanup():
    """Remove the previous copy left behind by install(). Call at startup."""
    p = app_path()
    if not p:
        return
    old = p + ".old"
    try:
        if os.path.isdir(old):
            shutil.rmtree(old, ignore_errors=True)
        elif os.path.isfile(old):
            os.remove(old)
    except OSError:
        pass
