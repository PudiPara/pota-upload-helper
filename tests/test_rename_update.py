"""An update gives a copy still named "POTA Upload Helper" the app's name (updater.new_path), and on
Windows points its shortcuts at the renamed exe (updater.SHORTCUTS_PS1)."""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import updater  # noqa: E402


class NewPath(unittest.TestCase):
    def test_old_name_becomes_the_new_one(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.path.join(d, "POTA Upload Helper.exe")
            open(old, "w").close()
            self.assertEqual(updater.new_path(old, "Potaroo.exe"), os.path.join(d, "Potaroo.exe"))

    def test_same_name_stays(self):
        with tempfile.TemporaryDirectory() as d:
            cur = os.path.join(d, "Potaroo.exe")
            open(cur, "w").close()
            self.assertEqual(updater.new_path(cur, "Potaroo.exe"), cur)

    def test_never_over_another_file(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.path.join(d, "POTA Upload Helper.app")
            os.mkdir(old)
            os.mkdir(os.path.join(d, "Potaroo.app"))           # e.g. a copy from the DMG next to it
            self.assertEqual(updater.new_path(old, "Potaroo.app"), old)


class AdoptName(unittest.TestCase):
    def test_only_the_old_name_renames(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("Potaroo.exe", "Potaroo.app", "Other.exe"):
                p = os.path.join(d, name)
                orig = updater.app_path
                updater.app_path = lambda p=p: p
                try:
                    self.assertFalse(updater.adopt_name())     # nothing to do, nothing renamed
                finally:
                    updater.app_path = orig
            self.assertFalse(updater.adopt_name())             # from source: no installed copy


@unittest.skipUnless(os.name == "nt", "Windows shortcuts")
class Shortcuts(unittest.TestCase):
    def ps(self, code):
        return subprocess.run(["powershell", "-NoProfile", "-Command", code], capture_output=True, text=True, check=True).stdout.strip()

    def test_shortcuts_follow_the_exe(self):
        with tempfile.TemporaryDirectory() as d:
            old, new = os.path.join(d, "POTA Upload Helper.exe"), os.path.join(d, "Potaroo.exe")
            menu, pinned = os.path.join(d, "Start", "POTA Upload Helper"), os.path.join(d, "User Pinned", "TaskBar")
            for f in (menu, pinned):
                os.makedirs(f)
            make = "$s = New-Object -ComObject WScript.Shell; foreach ($p in @('%s', '%s', '%s')) { $l = $s.CreateShortcut($p); $l.TargetPath = '%s'; $l.Save() }"
            other = os.path.join(menu, "Other.lnk")
            self.ps(make % (os.path.join(menu, "POTA Upload Helper.lnk"), os.path.join(pinned, "POTA Upload Helper.lnk"), other, old))
            self.ps("$s = New-Object -ComObject WScript.Shell; $l = $s.CreateShortcut('%s'); $l.TargetPath = '%s'; $l.Save()" % (other, os.path.join(d, "else.exe")))
            script = os.path.join(d, "shortcuts.ps1")
            with open(script, "w", encoding="utf-8-sig") as fh:
                fh.write(updater.SHORTCUTS_PS1)
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, old, new,
                            os.path.join(d, "Start"), os.path.join(d, "User Pinned")], check=True, capture_output=True)
            target = lambda p: self.ps("(New-Object -ComObject WScript.Shell).CreateShortcut('%s').TargetPath" % p)
            renamed = os.path.join(menu, "Potaroo.lnk")
            self.assertTrue(os.path.exists(renamed))                       # the Start menu one: renamed
            self.assertEqual(target(renamed).lower(), new.lower())
            kept = os.path.join(pinned, "POTA Upload Helper.lnk")          # the pinned one: same name (renaming unpins)
            self.assertEqual(target(kept).lower(), new.lower())
            self.assertTrue(target(other).lower().endswith("else.exe"))    # another app's shortcut: untouched


if __name__ == "__main__":
    unittest.main()
