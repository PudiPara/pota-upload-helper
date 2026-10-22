"""Offline tests: a club station's log (Club Activation Guide) - OPERATOR per QSO, the club call's QSOs kept out of
the personal call's files and the other way round, and the note to upload from the club's account only."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", os.path.join(tempfile.mkdtemp(), "data"))   # another test module may own it

import builder  # noqa: E402
import potacommon  # noqa: E402
from potacommon import read_adif  # noqa: E402


def qso(call, t, **kw):
    d = dict(CALL=call, QSO_DATE="20261020", TIME_ON=t, BAND="40m", MODE="CW", MY_SIG="POTA", MY_SIG_INFO="JP-1206")
    d.update(kw)
    return d


class ClubLogTest(unittest.TestCase):
    def setUp(self):
        self._saved = potacommon.DATA_DIR
        potacommon.DATA_DIR = tempfile.mkdtemp()
        json.dump([], open(potacommon.data_path("hunter.json"), "w"))
        json.dump([], open(potacommon.data_path("sessions.json"), "w"))
        self.recs = [qso("JA1AAA", "010000", SESSION_CALL="JA1YZZ", OPERATOR="JA1OPA"),
                     qso("JA1BBB", "010500", SESSION_CALL="JA1YZZ", OPERATOR="JA1OPB"),
                     qso("JA1CCC", "020000", SESSION_CALL="JA1ME"),
                     qso("JA1DDD", "030000")]                      # before 2.0.47: no SESSION_CALL, any call takes it

    def tearDown(self):
        potacommon.DATA_DIR = self._saved

    def build(self, call):
        return builder.build(None, ["20261020"], None, call, tempfile.mkdtemp(), offline=True,
                             recs=[dict(r) for r in self.recs], confirmed_only=True, log=lambda *a: None)

    def test_club_file_has_its_qsos_and_operators(self):
        res = self.build("JA1YZZ")
        rows = read_adif(os.path.join(res["out_dir"], res["files"][0]))
        self.assertEqual([(r["CALL"], r["STATION_CALLSIGN"], r["OPERATOR"]) for r in rows],
                         [("JA1AAA", "JA1YZZ", "JA1OPA"), ("JA1BBB", "JA1YZZ", "JA1OPB"), ("JA1DDD", "JA1YZZ", "JA1YZZ")])
        self.assertIn("JA1OPA, JA1OPB", res["notes"][0])          # the club note, not "your logger's call differs"
        self.assertEqual(len(res["notes"]), 1)

    def test_personal_file_leaves_the_club_out(self):
        res = self.build("JA1ME")
        rows = read_adif(os.path.join(res["out_dir"], res["files"][0]))
        self.assertEqual([r["CALL"] for r in rows], ["JA1CCC", "JA1DDD"])
        self.assertEqual(res["notes"], [])


if __name__ == "__main__":
    unittest.main()
