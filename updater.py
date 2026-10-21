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

from i18n import t
from potacommon import USER_AGENT, VERSION, data_version, fetch_json

REPO = "PudiPara/potaroo"
LATEST = "https://api.github.com/repos/%s/releases/latest" % REPO
PAGE = "https://github.com/%s/releases/latest" % REPO
DOWNLOAD_PREFIX = "https://github.com/%s/releases/download/" % REPO
# the repo was PudiPara/pota-upload-helper until 2.0.2; GitHub redirects that name to this one
DOWNLOAD_PREFIXES = (DOWNLOAD_PREFIX, "https://github.com/PudiPara/pota-upload-helper/releases/download/")
# 1.x looks for POTA-Upload-Helper-*.zip; CI publishes those names too until nobody is on 1.x
ASSETS = {"darwin": "Potaroo-macOS.zip", "win32": "Potaroo-Windows.zip"}
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{7E2D4C3A-5B6F-4F0E-9B8A-2C1D0E9F7A51}_is1"   # windows.iss AppId
LSREGISTER = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
OLD_NAMES = ("POTA Upload Helper.app", "POTA Upload Helper.exe")   # 1.x; updates up to 2.0.33 kept it


def parse_version(tag):
    """'v1.2.3' / '1.2' -> (1, 2, 3) / (1, 2, 0)"""
    nums = [int(x) for x in re.findall(r"\d+", tag or "")][:3]
    return tuple(nums + [0] * (3 - len(nums)))


def parse_tag(tag):
    """'v2.0.21' -> ((2, 0, 21), ""); a data-only release 'v2.0.21-data-2026.11.01' -> ((2, 0, 21), "2026.11.01")."""
    app, _, data = (tag or "").partition("-data-")
    return parse_version(app), data


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


def summarize(rel, platform=None, installed=None, current_data=None):
    """-> dict for the UI, from the GitHub 'latest release' JSON."""
    platform = platform or sys.platform
    tag = rel.get("tag_name") or ""
    want = ASSETS.get("win32" if platform.startswith("win") else platform)
    asset = next((a for a in rel.get("assets") or [] if a.get("name") == want), None)
    url = (asset or {}).get("browser_download_url") or ""
    installed = installed if installed is not None else app_path()
    app, data = parse_tag(tag)
    newer_app = app > parse_version(VERSION)
    # the same app with newer pota.app data (a monthly data release): an update, but a quiet one in the UI
    newer_data = app == parse_version(VERSION) and bool(data) and data > (current_data if current_data is not None else data_version())
    return {"current": VERSION, "latest": tag.lstrip("vV").partition("-data-")[0], "newer": newer_app or newer_data,
            "data_only": newer_data and not newer_app, "data_latest": data,
            "data_current": current_data if current_data is not None else data_version(),
            "notes": (rel.get("body") or "")[:3000], "page": rel.get("html_url") or PAGE, "asset": url,
            "can_install": bool(url and installed), "translocated": translocated(installed)}


def check():
    return summarize(fetch_json(LATEST, timeout=15))


# ---------------------------------------------------------------- download / install
def download(url, dest, timeout=600):
    if not url.startswith(DOWNLOAD_PREFIXES):
        raise ValueError(t("updater.badUrl", url=url))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as fh:
            shutil.copyfileobj(r, fh)
    except (ssl.SSLError, urllib.error.URLError):
        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
        subprocess.run(["curl", "-sSL", "-m", str(timeout), "-A", USER_AGENT, "-o", dest, url],
                       check=True, **kw)
    if os.path.getsize(dest) < 1_000_000:
        raise RuntimeError(t("updater.tooSmall", n=os.path.getsize(dest)))


def install(url, installed=None):
    """-> {'relaunch': path} when the app was replaced in place, or
          {'manual': path, 'manual_dir': dir} when the new copy was only put somewhere for the user."""
    installed = installed or app_path()
    if not installed:
        raise RuntimeError(t("updater.fromSource"))
    work = tempfile.mkdtemp(prefix="potaroo-update-")
    zip_path = os.path.join(work, "update.zip")
    download(url, zip_path)
    if sys.platform == "darwin":
        return _install_mac(zip_path, work, installed)
    if os.name == "nt":
        return _install_win(zip_path, work, installed)
    raise RuntimeError(t("updater.unsupportedOs"))


def new_path(installed, new_name):
    """Where a copy renamed to new_name goes: next to the installed one. Unless a file of that name is
    already there (a copy from the DMG next to it): then nowhere new, the installed path."""
    dest = os.path.join(os.path.dirname(installed), new_name)
    if os.path.normcase(dest) != os.path.normcase(installed) and os.path.exists(dest):
        return installed
    return dest


def adopt_name():
    """A copy still named "POTA Upload Helper" (1.x; updates up to 2.0.33 kept the installed file name, so
    Finder, the Start menu and the OS's icon cache went on showing the old name and icon) renames itself to
    Potaroo, points its shortcuts at the new name (Windows), makes the OS read the new icon, and starts again
    from there. Call first thing (before the single-instance lock). -> True: this process should quit now."""
    cur = app_path()
    if not cur or os.path.basename(cur) not in OLD_NAMES or translocated(cur):
        return False
    dest = new_path(cur, "Potaroo" + os.path.splitext(cur)[1])
    if dest == cur:
        return False
    try:
        os.rename(cur, dest)             # a running exe / bundle can be renamed (not deleted)
    except OSError:
        return False
    if sys.platform == "darwin":
        for cmd in (["touch", dest], [LSREGISTER, "-f", dest]):
            try:
                subprocess.run(cmd, check=False, timeout=20)
            except Exception:
                pass
        relaunch(dest)
        return True
    work = tempfile.mkdtemp(prefix="potaroo-rename-")
    fix = os.path.join(work, "shortcuts.ps1")
    with open(fix, "w", encoding="utf-8-sig") as fh:       # BOM: Windows PowerShell 5.1 reads it as UTF-8
        fh.write(SHORTCUTS_PS1)
    script = os.path.join(work, "rename.cmd")
    with open(script, "w", encoding="cp932", errors="replace") as fh:
        fh.write("@echo off\r\n:wait\r\n"
                 'tasklist /FI "PID eq %d" 2>nul | find "%d" >nul\r\n' % (os.getpid(), os.getpid()) +
                 "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)\r\n"
                 'powershell -NoProfile -ExecutionPolicy Bypass -File "%s" "%s" "%s"\r\n' % (fix, cur, dest) +
                 "ie4uinit.exe -show >nul 2>&1\r\n" +          # Explorer forgets the icon it kept for the old file
                 "timeout /t 2 /nobreak >nul\r\n" +
                 'explorer.exe "%s"\r\n' % dest)
    subprocess.Popen(["cmd.exe", "/c", script], creationflags=0x08000000, close_fds=True, env=child_env())
    return True


def _install_mac(zip_path, work, app):
    subprocess.run(["ditto", "-x", "-k", zip_path, work], check=True)      # keeps the bundle intact
    apps = [d for d in os.listdir(work) if d.endswith(".app")]
    if not apps:
        raise RuntimeError(t("updater.noApp"))
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


def child_env():
    """The environment for a process that will outlive this one and start the new app. A PyInstaller
    onefile parent tells its child where the unpacked files are through _PYI_* variables (older
    bootloaders: _MEIPASS2); inherited by the new app, it would skip unpacking and look for
    python3xx.dll in our temp folder, which is gone by then ("Failed to load Python DLL")."""
    return {k: v for k, v in os.environ.items() if not k.startswith("_PYI_") and k != "_MEIPASS2"}


def _install_win(zip_path, work, exe):
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(work)
    exes = [f for f in os.listdir(work) if f.lower().endswith(".exe")]
    if not exes:
        raise RuntimeError(t("updater.noExe"))
    new = os.path.join(work, exes[0])
    script = os.path.join(work, "update.cmd")
    with open(script, "w", encoding="cp932", errors="replace") as fh:
        fh.write("@echo off\r\n:wait\r\n"
                 'tasklist /FI "PID eq %d" 2>nul | find "%d" >nul\r\n' % (os.getpid(), os.getpid()) +
                 "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)\r\n"
                 'move /y "%s" "%s.old" >nul\r\n' % (exe, exe) +
                 'move /y "%s" "%s" >nul\r\n' % (new, exe) +
                 "timeout /t 2 /nobreak >nul\r\n" +           # let the old bootloader finish its cleanup
                 'explorer.exe "%s"\r\n' % exe)                # started by the shell, outside our process tree
    # CREATE_NO_WINDOW only: with DETACHED_PROCESS the script has no console at all and its
    # tasklist | find wait loop never ends (verified on Windows 11), so the exe was never swapped.
    subprocess.Popen(["cmd.exe", "/c", script], creationflags=0x08000000, close_fds=True, env=child_env())
    return {"relaunch": exe}


def relaunch(path):
    """macOS: start the new bundle once this process is gone (the helper script does it on Windows)."""
    if sys.platform == "darwin":
        subprocess.Popen(["/bin/sh", "-c", 'sleep 2; open -n "%s"' % path.replace('"', '\\"')], env=child_env())


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


# adopt_name renamed the exe: point the shortcuts that started the old one at it (Start menu, desktop, the
# taskbar's pinned ones), rename the "POTA Upload Helper" ones to Potaroo (not the pinned: renaming unpins),
# and show the new name and icon in Settings > Apps.   shortcuts.ps1 <old exe> <new exe> [folder ...]
SHORTCUTS_PS1 = r"""param([string]$Old, [string]$New, [Parameter(ValueFromRemainingArguments = $true)][string[]]$Dirs)
$real = -not $Dirs                 # folders given = a test: leave the registry alone
if ($real) { $Dirs = @([Environment]::GetFolderPath('StartMenu'), [Environment]::GetFolderPath('Desktop'),
                            (Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch')) }
$sh = New-Object -ComObject WScript.Shell
foreach ($d in $Dirs) {
  if (-not (Test-Path -LiteralPath $d)) { continue }
  Get-ChildItem -LiteralPath $d -Recurse -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object {
    try {
      $l = $sh.CreateShortcut($_.FullName)
      if ($l.TargetPath -ieq $Old) {
        $l.TargetPath = $New; $l.IconLocation = "$New,0"; $l.Save()
        if ($_.BaseName -eq 'POTA Upload Helper' -and $_.FullName -notlike '*User Pinned*') {
          Rename-Item -LiteralPath $_.FullName -NewName 'Potaroo.lnk' -ErrorAction SilentlyContinue }
      }
    } catch {}
  }
}
$k = 'HKCU:\UNINSTALL_KEY'
if ($real -and (Test-Path $k)) { Set-ItemProperty $k DisplayName 'Potaroo'; Set-ItemProperty $k DisplayIcon $New }
""".replace("UNINSTALL_KEY", UNINSTALL_KEY)


def relaunch(path):
    """macOS: start the new bundle once this process is gone (the helper script does it on Windows)."""
    if sys.platform == "darwin":
        subprocess.Popen(["/bin/sh", "-c", 'sleep 2; open -n "%s"' % path.replace('"', '\\"')], env=child_env())


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
