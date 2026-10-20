"""運用終了 writes the whole UTC day: a park shared by several sessions of one day keeps every QSO."""
import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("POTA_HELPER_DATA", os.path.join(tempfile.mkdtemp(), "data"))   # another test module may own it
sys.modules.setdefault("webview", types.SimpleNamespace(OPEN_DIALOG=1, FOLDER_DIALOG=2))  # app.py imports it
sys.path.insert(0, ROOT)
import app  # noqa: E402
import potacommon  # noqa: E402
import qsolog  # noqa: E402


class FinishBuildsTheWholeDay(unittest.TestCase):
    def test_shared_park_file_keeps_every_session(self):
        out = tempfile.mkdtemp(prefix="pota-day-")
        potacommon.save_settings({"out": out, "call": "JL1FVA"})
        api = app.Api.__new__(app.Api)
        sessions = [("JP-1206,JP-1266", "2026-01-03T00:00:00", "2026-01-03T00:30:00", "JA1AAA"),
                    ("JP-1206,JP-1946", "2026-01-03T01:00:00", "2026-01-03T01:30:00", "JA1BBA")]
        for i, (parks, start, end, call) in enumerate(sessions):
            qsolog.upsert({"CALL": call, "QSO_DATE": "20260103", "TIME_ON": start[11:13] + "1000", "BAND": "40m",
                           "MODE": "CW", "MY_SIG": "POTA", "MY_SIG_INFO": parks}, "day-%d" % i, "x")
            api._logger = types.SimpleNamespace(stop=lambda: None,
                                                session={"start": start, "end": end, "parks": parks.split(","), "call": "JL1FVA"})
            r = api.finish_live(online=False)
            self.assertTrue(r["ok"], r)
        shared = open(os.path.join(out, "JL1FVA@JP-1206-20260103.adi"), encoding="utf-8").read()
        self.assertIn("JA1AAA", shared); self.assertIn("JA1BBA", shared)          # both sessions
        first = open(os.path.join(out, "JL1FVA@JP-1266-20260103.adi"), encoding="utf-8").read()
        self.assertIn("JA1AAA", first); self.assertNotIn("JA1BBA", first)          # only its own session


if __name__ == "__main__":
    unittest.main()
