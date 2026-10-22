"""Offline tests: POTA parks are read from POTA_REF / *_SIG_INFO only when *_SIG says POTA (a WWFF
reference such as JAFF-0123 looks like a park), and ADIF's "park@location" form is understood."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", os.path.join(tempfile.mkdtemp(), "data"))   # another test module may own it

import builder  # noqa: E402
import potacommon  # noqa: E402
import qsolog  # noqa: E402
from potacommon import my_parks_of, split_parks, their_parks_of  # noqa: E402


def rec(**kw):
    d = dict(CALL="JA1ABC", QSO_DATE="20261020", TIME_ON="040000", BAND="40m", MODE="FT8")
    d.update(kw)
    return d


class SigParksTest(unittest.TestCase):
    def test_split_parks_location_per_park(self):
        self.assertEqual(split_parks("US-4239@US-MI"), ["US-4239"])
        self.assertEqual(split_parks("K-0817,K-4578@US-WY"), ["K-0817", "K-4578"])

    def test_their_parks(self):
        self.assertEqual(their_parks_of(rec(SIG="WWFF", SIG_INFO="JAFF-0123")), [])
        self.assertEqual(their_parks_of(rec(SIG="WWFF", SIG_INFO="JAFF-0123", POTA_REF="JP-1138")), ["JP-1138"])
        self.assertEqual(their_parks_of(rec(SIG="pota", SIG_INFO="JP-1138")), ["JP-1138"])
        self.assertEqual(their_parks_of(rec(SIG_INFO="JP-1138")), ["JP-1138"])      # no SIG: as before

    def test_my_parks(self):
        self.assertEqual(my_parks_of(rec(MY_SIG="WWFF", MY_SIG_INFO="JAFF-0001")), [])
        self.assertEqual(my_parks_of(rec(MY_SIG="WWFF", MY_SIG_INFO="JAFF-0001", MY_POTA_REF="JP-0016@JP-KN")),
                         ["JP-0016"])
        self.assertEqual(my_parks_of(rec(MY_SIG_INFO="JP-0016")), ["JP-0016"])


class SigParksStoreTest(unittest.TestCase):
    def setUp(self):
        self._saved = potacommon.DATA_DIR
        potacommon.DATA_DIR = tempfile.mkdtemp()

    def tearDown(self):
        potacommon.DATA_DIR = self._saved

    def test_wwff_is_not_a_logged_p2p(self):
        r = rec(SIG="WWFF", SIG_INFO="JAFF-0123", MY_SIG="POTA", MY_SIG_INFO="JP-0016")
        qsolog.received(r)
        self.assertNotIn("P2P_DECISION", r)
        self.assertEqual(r["SIG"], "WWFF")
        self.assertEqual(qsolog.history()[0]["my"], ["JP-0016"])

    def test_my_wwff_is_not_my_park(self):
        qsolog.received(rec(MY_SIG="WWFF", MY_SIG_INFO="JAFF-0001"))
        self.assertEqual(qsolog.history()[0]["my"], [])

    def test_build_uses_pota_ref_beside_wwff(self):
        r = rec(MY_SIG="WWFF", MY_SIG_INFO="JAFF-0001", MY_POTA_REF="JP-0016",
                SIG="WWFF", SIG_INFO="JAFF-0123", POTA_REF="JP-1138")
        activ = builder.find_activation_qsos([r], sessions=[])
        self.assertEqual(activ[0][2], ["JP-0016"])


if __name__ == "__main__":
    unittest.main()
