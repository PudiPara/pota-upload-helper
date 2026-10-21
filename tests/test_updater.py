"""Offline tests for the GitHub Releases updater (no network)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", tempfile.mkdtemp())

import potacommon  # noqa: E402
import updater  # noqa: E402

REL = {"tag_name": "v9.2.0", "html_url": "https://github.com/x/y/releases/tag/v9.2.0", "body": "notes",
       "assets": [{"name": "Potaroo-macOS.zip", "browser_download_url": updater.DOWNLOAD_PREFIX + "v9.2.0/Potaroo-macOS.zip"},
                  {"name": "Potaroo-Windows.zip", "browser_download_url": updater.DOWNLOAD_PREFIX + "v9.2.0/Potaroo-Windows.zip"}]}


class UpdaterTest(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(updater.parse_version("1.10"), (1, 10, 0))
        self.assertEqual(updater.parse_version(""), (0, 0, 0))
        self.assertGreater(updater.parse_version("v1.10.0"), updater.parse_version("v1.9.9"))

    def test_summarize_picks_the_asset_for_the_os(self):
        mac = updater.summarize(REL, platform="darwin", installed="/Applications/Potaroo.app")
        self.assertTrue(mac["newer"])
        self.assertTrue(mac["asset"].endswith("macOS.zip"))
        self.assertTrue(mac["can_install"])
        self.assertFalse(mac["translocated"])
        win = updater.summarize(REL, platform="win32", installed=r"C:\Apps\Potaroo.exe")
        self.assertTrue(win["asset"].endswith("Windows.zip"))
        src = updater.summarize(REL, platform="darwin", installed=None)      # running from source
        self.assertFalse(src["can_install"])
        self.assertEqual(src["page"], REL["html_url"])
        tl = updater.summarize(REL, platform="darwin", installed="/private/var/folders/x/AppTranslocation/y/d/Potaroo.app")
        self.assertTrue(tl["translocated"])

    def test_not_newer_when_same_or_older(self):
        same = updater.summarize({"tag_name": "v" + potacommon.VERSION, "assets": []}, platform="darwin", installed=None)
        self.assertFalse(same["newer"])
        self.assertFalse(same["can_install"])

    def test_download_refuses_other_hosts(self):
        with self.assertRaises(ValueError):
            updater.download("https://example.com/evil.zip", os.path.join(tempfile.mkdtemp(), "x.zip"))


class RenamedRepo(unittest.TestCase):
    def test_downloads_from_the_old_and_the_new_repo_name_only(self):
        import unittest.mock as m
        for url in ("https://github.com/PudiPara/potaroo/releases/download/v9/x.zip",
                    updater.DOWNLOAD_PREFIX + "v9/x.zip"):
            with m.patch("urllib.request.urlopen", side_effect=OSError("offline")), m.patch("subprocess.run", side_effect=OSError("no curl")):
                with self.assertRaises(Exception) as e:
                    updater.download(url, "x")
                self.assertNotIsInstance(e.exception, ValueError)
        with self.assertRaises(ValueError):
            updater.download("https://github.com/someone/else/releases/download/v9/x.zip", "x")


if __name__ == "__main__":
    unittest.main()


class ChildEnv(unittest.TestCase):
    def test_pyinstaller_variables_are_not_inherited(self):
        os.environ["_PYI_APPLICATION_HOME_DIR"] = r"C:	mp\_MEI1"; os.environ["_MEIPASS2"] = "x"; os.environ["KEEP_ME"] = "1"
        try:
            env = updater.child_env()
        finally:
            for k in ("_PYI_APPLICATION_HOME_DIR", "_MEIPASS2", "KEEP_ME"):
                os.environ.pop(k, None)
        self.assertNotIn("_PYI_APPLICATION_HOME_DIR", env); self.assertNotIn("_MEIPASS2", env); self.assertEqual(env["KEEP_ME"], "1")

