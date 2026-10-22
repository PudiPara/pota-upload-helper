"""Offline tests: modes and bands as ADIF 3.1.8 spells them (#16, #21, #32) - loggers' words become MODE +
SUBMODE, BAND comes from FREQ, the editor stores ADIF values, and the build notes what pota.app would refuse."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", os.path.join(tempfile.mkdtemp(), "data"))   # DATA_DIR is fixed at import

import builder  # noqa: E402
import potacommon  # noqa: E402
import qsolog  # noqa: E402
from potacommon import adif_mode, band_from_mhz, band_name, fix_mode_band, mode_group, mode_of  # noqa: E402
from receiver import parse_packet  # noqa: E402


def rec(**kw):
    d = dict(CALL="JA1ABC", QSO_DATE="20261020", TIME_ON="010000", BAND="40m", MODE="FT8")
    d.update(kw)
    return d


class Modes(unittest.TestCase):
    def test_logger_words(self):
        self.assertEqual(adif_mode("usb"), {"MODE": "SSB", "SUBMODE": "USB"})
        self.assertEqual(adif_mode("FT2"), {"MODE": "MFSK", "SUBMODE": "FT2"})
        self.assertEqual(adif_mode("D-STAR"), {"MODE": "DIGITALVOICE", "SUBMODE": "DSTAR"})
        self.assertEqual(adif_mode("DV"), {"MODE": "DIGITALVOICE"})
        self.assertEqual(adif_mode("PSK31"), {"MODE": "PSK", "SUBMODE": "PSK31"})
        self.assertEqual(adif_mode("VarAC"), {"MODE": "DYNAMIC", "SUBMODE": "VARA HF"})
        self.assertEqual(adif_mode("FT8"), {"MODE": "FT8"})

    def test_groups_and_keys(self):
        self.assertEqual(mode_group("DIGITALVOICE"), "phone")
        self.assertEqual(mode_of(adif_mode("DSTAR")), "DSTAR")
        self.assertEqual(mode_of(adif_mode("LSB")), "SSB")

    def test_received_adif_is_fixed(self):
        (_, r, _), = parse_packet(b"<CALL:6>JA1ABC <FREQ:6>14.074 <MODE:3>USB <EOR>")
        self.assertEqual((r["MODE"], r["SUBMODE"], r["BAND"]), ("SSB", "USB", "20m"))
        r = fix_mode_band(rec(MODE="MFSK", SUBMODE="FT4"))                 # a SUBMODE came with it: as it is
        self.assertEqual((r["MODE"], r["SUBMODE"]), ("MFSK", "FT4"))


class Bands(unittest.TestCase):
    def test_edges(self):
        self.assertEqual(band_from_mhz(5.3), "60m")
        self.assertEqual(band_from_mhz(5.02), "")                          # 60m is 5.06-5.45
        self.assertEqual(band_from_mhz(0.136), "2190m")
        self.assertEqual(band_from_mhz(54.0), "6m")
        self.assertEqual(band_from_mhz(70.2), "4m")
        self.assertEqual(band_from_mhz(2400), "13cm")
        self.assertEqual((band_name("20M"), band_name("11m"), band_name("70m")), ("20m", "", ""))


class EditorAndNotes(unittest.TestCase):
    def setUp(self):
        self._saved = potacommon.DATA_DIR
        potacommon.DATA_DIR = tempfile.mkdtemp()

    def tearDown(self):
        potacommon.DATA_DIR = self._saved

    def test_editor_stores_adif_mode(self):
        uid = qsolog.upsert(rec(), None, "x")
        new = qsolog.update(uid, {"MODE": "USB"})
        r = next(x for x in qsolog.records(["20261020"]) if qsolog.make_uid(x) == new)
        self.assertEqual((r["MODE"], r["SUBMODE"]), ("SSB", "USB"))

    def test_problems(self):
        keys = lambda r: [k for k, _ in builder.problems(r, "JL1FVA")]  # noqa: E731
        self.assertEqual(keys(rec()), [])
        self.assertIn("b.note.badMode", keys(rec(MODE="DATA")))
        self.assertIn("b.note.noBand", keys(rec(BAND="")))
        self.assertIn("b.note.self", keys(rec(CALL="JL1FVA")))
        self.assertIn("b.note.badCall", keys(rec(CALL="JA1ÄBC")))
        self.assertIn("b.note.future", keys(rec(QSO_DATE="29991231")))
        self.assertIn("b.note.repeater", keys(rec(PROP_MODE="RPT")))
        self.assertIn("b.note.parkUnread", keys(rec(SIG_INFO="US1234")))
        self.assertEqual(keys(rec(SIG="WWFF", SIG_INFO="JAFF-0123")), [])


if __name__ == "__main__":
    unittest.main()
