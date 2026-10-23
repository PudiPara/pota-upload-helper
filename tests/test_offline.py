"""Offline: a host that did not answer is left alone for a while (nothing waits for its timeout again), offline mode
asks nothing at all, and the system curl is tried only for a certificate problem."""
import os
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", os.path.join(tempfile.mkdtemp(), "data"))   # another test module may own it

import potacommon  # noqa: E402


class OfflineTest(unittest.TestCase):
    def setUp(self):
        self._saved = potacommon.DATA_DIR, potacommon.urllib.request.urlopen, potacommon.subprocess.run
        potacommon.DATA_DIR = tempfile.mkdtemp()
        potacommon._down.clear()
        self.calls = []

        def no_answer(req, timeout=0):
            self.calls.append(req.full_url)
            raise urllib.error.URLError(TimeoutError("timed out"))
        potacommon.urllib.request.urlopen = no_answer
        potacommon.subprocess.run = lambda *a, **k: self.fail("curl is only for a certificate problem")

    def tearDown(self):
        potacommon.DATA_DIR, potacommon.urllib.request.urlopen, potacommon.subprocess.run = self._saved
        potacommon._down.clear()

    def test_no_answer_then_no_wait(self):
        with self.assertRaises(urllib.error.URLError):
            potacommon.fetch_json("spot/activator")
        with self.assertRaises(potacommon.Offline):
            potacommon.fetch_json("spot/comments/X/JP-0001")          # not asked: no second timeout
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(potacommon.offline(), "down")
        with self.assertRaises(urllib.error.URLError):
            potacommon.fetch_json("https://api.open-meteo.com/v1/forecast")
        self.assertEqual(len(self.calls), 2)

    def test_offline_mode_asks_nothing(self):
        potacommon.save_settings({"offline": True})
        with self.assertRaises(potacommon.Offline):
            potacommon.fetch_json("spot/activator")
        self.assertEqual((self.calls, potacommon.offline()), ([], "manual"))


if __name__ == "__main__":
    unittest.main()
