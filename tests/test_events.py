"""Offline tests: POTA event periods, Early / Late Shift hours and the Rover count in the build result."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", os.path.join(tempfile.mkdtemp(), "data"))   # another test module may own it

import builder  # noqa: E402
import potacommon  # noqa: E402
import spots  # noqa: E402


class EventsTest(unittest.TestCase):
    def test_support_your_parks_is_the_third_full_weekend(self):
        syp = [e["start"][:10] for e in potacommon.pota_events(2026) if e["name"] == "Support Your Parks"]
        self.assertEqual(syp, ["2026-01-17", "2026-04-18", "2026-07-18", "2026-10-17"])
        # 1 January 2023 was a Sunday: that weekend is not a full one, the third full weekend is 21-22
        self.assertEqual(potacommon.pota_events(2023)[1]["start"][:10], "2023-01-21")

    def test_shift_hours_by_longitude(self):
        self.assertEqual(spots.shift_hours(["JP-1206"]), {"early": [17, 6], "late": [9, 8]})    # Tokyo: 02 and 18 JST
        self.assertEqual(spots.shift_hours([]), {})


class RoverTest(unittest.TestCase):
    def setUp(self):
        self._saved = potacommon.DATA_DIR
        potacommon.DATA_DIR = tempfile.mkdtemp()
        json.dump([], open(potacommon.data_path("hunter.json"), "w"))
        json.dump([], open(potacommon.data_path("sessions.json"), "w"))

    def tearDown(self):
        potacommon.DATA_DIR = self._saved

    def test_parks_activated_in_a_day(self):
        recs = [dict(CALL="JA1A%02d" % i, QSO_DATE="20261020", TIME_ON="01%02d00" % i, BAND="40m", MODE="CW",
                     MY_SIG="POTA", MY_SIG_INFO=p) for p in ("JP-1206", "JP-1266", "JP-0001", "JP-0002", "JP-0003")
                for i in range(10)]
        recs.append(dict(CALL="JA1ZZZ", QSO_DATE="20261020", TIME_ON="050000", BAND="40m", MODE="CW", MY_SIG_INFO="JP-0004"))
        res = builder.build(None, ["20261020"], None, "JA1ME", tempfile.mkdtemp(), offline=True, recs=recs,
                            confirmed_only=True, log=lambda *a: None)
        self.assertEqual(res["rover"], [{"date": "20261020", "parks": 5, "award": "Warthog"}])   # JP-0004: 1 QSO


if __name__ == "__main__":
    unittest.main()
