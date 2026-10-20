"""Offline tests for the GitHub Releases updater (no network)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTA_HELPER_DATA", tempfile.mkdtemp())

import potacommon  # noqa: E402
import updater  # noqa: E402

REL = {"tag_name": "v9.2.0", "html_url": "https://github.com/x/y/releases/tag/v9.2.0", "body": "notes",
       "assets": [{"name": "POTA-Upload-Helper-macOS.zip", "browser_download_url": updater.DOWNLOAD_PREFIX + "v9.2.0/POTA-Upload-Helper-macOS.zip"},
                  {"name": "POTA-Upload-Helper-Windows.zip", "browser_download_url": updater.DOWNLOAD_PREFIX + "v9.2.0/POTA-Upload-Helper-Windows.zip"}]}


class UpdaterTest(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(updater.parse_version("1.10"), (1, 10, 0))
        self.assertEqual(updater.parse_version(""), (0, 0, 0))
        self.assertGreater(updater.parse_version("v1.10.0"), updater.parse_version("v1.9.9"))

    def test_summarize_picks_the_asset_for_the_os(self):
        mac = updater.summarize(REL, platform="darwin", installed="/Applications/POTA Upload Helper.app")
        self.assertTrue(mac["newer"])
        self.assertTrue(mac["asset"].endswith("macOS.zip"))
        self.assertTrue(mac["can_install"])
        self.assertFalse(mac["translocated"])
        win = updater.summarize(REL, platform="win32", installed=r"C:\Apps\POTA Upload Helper.exe")
        self.assertTrue(win["asset"].endswith("Windows.zip"))
        src = updater.summarize(REL, platform="darwin", installed=None)      # running from source
        self.assertFalse(src["can_install"])
        self.assertEqual(src["page"], REL["html_url"])
        tl = updater.summarize(REL, platform="darwin", installed="/private/var/folders/x/AppTranslocation/y/d/POTA Upload Helper.app")
        self.assertTrue(tl["translocated"])

    def test_not_newer_when_same_or_older(self):
        same = updater.summarize({"tag_name": "v" + potacommon.VERSION, "assets": []}, platform="darwin", installed=None)
        self.assertFalse(same["newer"])
        self.assertFalse(same["can_install"])

    def test_download_refuses_other_hosts(self):
        with self.assertRaises(ValueError):
            updater.download("https://example.com/evil.zip", os.path.join(tempfile.mkdtemp(), "x.zip"))


if __name__ == "__main__":
    unittest.main()
