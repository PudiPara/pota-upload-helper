"""Offline tests: the achievements reached while recording (mypota.awards) - Rover from the app's log alone, Unique /
Repeat Offender / Kilo only once the CSVs are imported."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", os.path.join(tempfile.mkdtemp(), "data"))   # another test module may own it

import mypota  # noqa: E402
import potacommon  # noqa: E402
from potacommon import data_path, write_json  # noqa: E402

DAY = "20261022"


def csv_parks(n, activations=1, qsos=10):
    return {"JP-%04d" % i: {"first": "2026-01-01", "qsos": qsos, "attempts": activations, "activations": activations} for i in range(1, n + 1)}


class AwardsTest(unittest.TestCase):
    def setUp(self):
        self._saved = potacommon.DATA_DIR
        potacommon.DATA_DIR = tempfile.mkdtemp()

    def tearDown(self):
        potacommon.DATA_DIR = self._saved

    def test_rover_without_csv(self):
        five = {"JP-%04d" % i: 10 for i in range(1, 6)}
        self.assertEqual(mypota.awards([], [(DAY, dict(five, **{"JP-0006": 9}))], DAY),
                         {"rover:%s:Warthog" % DAY: {"kind": "rover", "name": "Warthog", "n": 5}})
        self.assertEqual(mypota.awards([], [(DAY, {"JP-0001": 10})], DAY), {})          # no CSV: no Unique from one park

    def test_unique_and_repeat_offender_with_csv(self):
        write_json(data_path("mypota.json"), {"activator": {"at": "2026-10-01T00:00:00Z", "parks": csv_parks(9)}})
        before = set(mypota.awards([], [], DAY))
        after = mypota.awards([], [(DAY, {"JP-0100": 10})], DAY)            # the tenth park activated today
        self.assertEqual([k for k in after if k not in before], ["unique:10"])
        write_json(data_path("mypota.json"), {"activator": {"at": "2026-10-01T00:00:00Z", "parks": csv_parks(1, activations=19, qsos=190)}})
        before = set(mypota.awards([], [], DAY))
        after = mypota.awards([], [(DAY, {"JP-0001": 10})], DAY)            # its 20th activation
        self.assertIn("goal:JP-0001:Oasis", set(after) - before)

    def test_six_pack_from_the_app_log(self):
        q = lambda call, band, **kw: dict(CALL=call, QSO_DATE=DAY, TIME_ON="010000", BAND=band, MODE="FT8", MY_SIG="POTA", MY_SIG_INFO="JP-0001", **kw)
        recs = [q("JA1A%02d" % i, "6m") for i in range(10)] + [q("JA1B%02d" % i, "40m") for i in range(10)]
        recs += [q("JA1P2P", "6m", SIG="POTA", SIG_INFO="JP-0500", P2P_DECISION="yes"), q("JA1NO", "6m", SIG="POTA", SIG_INFO="JP-0600")]
        self.assertEqual(mypota.six_pack(recs), {"activated": ["JP-0001"], "hunted": ["JP-0500"]})
        self.assertEqual(mypota.six_pack(recs[3:]), {"activated": [], "hunted": ["JP-0500"]})   # 9 QSOs on 6m


if __name__ == "__main__":
    unittest.main()
