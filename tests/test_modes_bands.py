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
        self.assertEqual(adif_mode("vara hf"), {"MODE": "DYNAMIC", "SUBMODE": "VARA HF"})
        self.assertEqual(adif_mode("VarAC"), {"MODE": "VARAC"})       # HF, FM or SAT: not guessed (noted at build)
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
        r = fix_mode_band(rec(MODE="DATA", SUBMODE="ft4"))                 # the SUBMODE decides the MODE
        self.assertEqual((r["MODE"], r["SUBMODE"]), ("MFSK", "FT4"))
        r = fix_mode_band(rec(MODE="C4FM", SUBMODE="C4FM"))                # import-only MODE
        self.assertEqual((r["MODE"], r["SUBMODE"]), ("DIGITALVOICE", "C4FM"))


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
        self.assertEqual(keys(rec(SIG_INFO="W2/WE-003")), [])             # a SOTA summit, not a park
        self.assertIn("b.note.badTime", keys(rec(TIME_ON="2460")))
        self.assertIn("b.note.badTime", keys(rec(TIME_ON="")))



class AsciiOut(unittest.TestCase):
    def test_written_values_are_ascii(self):
        path = os.path.join(tempfile.mkdtemp(), "x.adi")
        potacommon.write_adif(path, [{"CALL": "JA1ABC", "RST_RCVD": "５９", "OPERATOR": "山田",
                                      "GRIDSQUARE": "PM95", "MY_GRIDSQUARE": "東京", "SUBMODE": "ft4"}],
                              ["CALL", "RST_RCVD", "OPERATOR", "GRIDSQUARE", "MY_GRIDSQUARE"])
        body = open(path, "rb").read()
        body.decode("ascii")                                               # nothing outside ASCII
        self.assertIn(b"<RST_RCVD:2>59 ", body)
        self.assertIn(b"<GRIDSQUARE:4>PM95 ", body)
        self.assertNotIn(b"OPERATOR", body)
        self.assertNotIn(b"MY_GRIDSQUARE", body)
        self.assertEqual(potacommon.adif_value("GRIDSQUARE", "PM95XQ12"), "PM95XQ12")
        self.assertEqual(potacommon.adif_value("GRIDSQUARE", "PM9"), "")

    def test_build_upper_cases_modes(self):
        r = builder.records(recs=[rec(CALL="ja1abc", MODE="mfsk", SUBMODE="ft4x")])[0]
        self.assertEqual((r["CALL"], r["MODE"], r["SUBMODE"]), ("JA1ABC", "MFSK", "FT4X"))



class CountKey(unittest.TestCase):
    def test_what_counts_once(self):
        k = lambda **kw: potacommon.count_key(rec(**kw), "JP-0016")  # noqa: E731
        self.assertEqual(k(TIME_ON="010000"), k(TIME_ON="013000"))        # the same station again: once (#14)
        self.assertNotEqual(k(), k(BAND="20m"))
        self.assertNotEqual(k(), k(MODE="CW"))
        self.assertNotEqual(k(), k(CALL="JA1ABC/1"))                       # pota.app compares the call as written
        self.assertNotEqual(k(), k(QSO_DATE="20261021"))                   # a new UTC day: a new activation (#15)
        self.assertNotEqual(k(MY_POTA_LOCS={"JP-0016": "JP-KN"}), k(MY_POTA_LOCS={"JP-0016": "JP-SZ"}))



class HunterLog(unittest.TestCase):
    def test_nearest_entry_within_15_minutes(self):
        e = lambda m, p, band="40m": (m, band, p, {"callsign": "JA1ABC/P"})  # noqa: E731
        rover = [e(100, "JP-0001"), e(110, "JP-0002")]                   # the same station from two parks
        self.assertEqual([p for p, _ in builder.hunter_match(rover, 101, "40m")], ["JP-0001"])
        self.assertEqual([p for p, _ in builder.hunter_match(rover, 109, "40m")], ["JP-0002"])
        twofer = [e(100, "JP-0001"), e(100, "JP-0002")]
        self.assertEqual(sorted(p for p, _ in builder.hunter_match(twofer, 112, "40m")), ["JP-0001", "JP-0002"])
        self.assertEqual(builder.hunter_match(twofer, 116, "40m"), [])
        self.assertEqual(builder.hunter_match([e(100, "JP-0001", "")], 100, "20m")[0][0], "JP-0001")   # no band: any

    def test_call_notes(self):
        data = tempfile.mkdtemp()
        saved, potacommon.DATA_DIR = potacommon.DATA_DIR, data
        try:
            import json
            json.dump([{"date": "2026-10-20T01:05:00", "callsign": "JA1ABC/P", "band": "40M", "reference": "JP-0001"}],
                      open(os.path.join(data, "hunter.json"), "w"))
            recs = [rec(TIME_ON="011500", MY_SIG_INFO="JP-1206", STATION_CALLSIGN="JL1FVA/1")]
            notes = builder.build(None, ["20261020"], None, "JL1FVA", tempfile.mkdtemp(), offline=True, recs=recs,
                                  confirmed_only=True, log=lambda *a: None)["notes"]
        finally:
            potacommon.DATA_DIR = saved
        self.assertTrue(any("JL1FVA/1" in n for n in notes))                # the logger's call is not the one chosen
        self.assertTrue(any("JA1ABC/P" in n for n in notes))                # their upload writes the call otherwise



class Leftovers(unittest.TestCase):       # #35
    def setUp(self):
        self._saved = potacommon.DATA_DIR
        potacommon.DATA_DIR = tempfile.mkdtemp()

    def tearDown(self):
        potacommon.DATA_DIR = self._saved

    def test_no_time_is_no_time(self):
        self.assertIsNone(potacommon.rec_minutes(rec(TIME_ON="")))
        notes = builder.build(None, ["20261020"], None, "JL1FVA", tempfile.mkdtemp(), offline=True,
                              recs=[rec(TIME_ON="", MY_SIG_INFO="JP-1206")], confirmed_only=True, log=lambda *a: None)["notes"]
        self.assertTrue(any("JA1ABC" in n and "HHMM" in n for n in notes))

    def test_review_leftovers(self):
        keys = lambda r: [k for k, _ in builder.problems(r, "JL1FVA")]  # noqa: E731
        self.assertIn("b.note.badDate", keys(rec(QSO_DATE="2026101")))
        self.assertIsNone(potacommon.rec_minutes(rec(QSO_DATE="2026101")))
        self.assertIn("b.note.badMode", keys(rec(MODE="SSB", SUBMODE="XYZ")))
        r = builder.records(recs=[rec(OPERATOR="jl1fva", STATION_CALLSIGN="jl1fva")])[0]
        self.assertEqual((r["OPERATOR"], r["STATION_CALLSIGN"]), ("JL1FVA", "JL1FVA"))
        self.assertNotIn("OPERATOR", builder.records(recs=[rec(OPERATOR="山田")])[0])
        self.assertNotIn("FREQ", fix_mode_band(rec(FREQ="14.074.000")))
        path = os.path.join(tempfile.mkdtemp(), "bom.adx")
        open(path, "w", encoding="utf-8-sig").write('<?xml version="1.0"?><ADX><RECORDS><RECORD><CALL>JA1ABC</CALL></RECORD></RECORDS></ADX>')
        self.assertEqual(potacommon.read_adif(path)[0]["CALL"], "JA1ABC")

    def test_decimal_comma(self):
        self.assertEqual(band_from_mhz("14,074"), "20m")
        self.assertEqual(fix_mode_band(rec(FREQ="7,074", BAND=""))["FREQ"], "7.074")

    def test_adx(self):
        x = ('<?xml version="1.0"?><ADX><HEADER><ADIF_VER>3.1.8</ADIF_VER></HEADER><RECORDS><RECORD><CALL>JA1ABC</CALL>'
             '<QSO_DATE>20261020</QSO_DATE><TIME_ON>0102</TIME_ON><BAND>40m</BAND><MODE>USB</MODE>'
             '<APP PROGRAMID="RUM" FIELDNAME="QSL" TYPE="S">W</APP></RECORD></RECORDS></ADX>')
        (_, r, _), = parse_packet(x.encode())
        self.assertEqual((r["CALL"], r["MODE"], r["SUBMODE"], r["APP_RUM_QSL"]), ("JA1ABC", "SSB", "USB", "W"))
        path = os.path.join(tempfile.mkdtemp(), "log.adx")
        open(path, "w", encoding="utf-8").write(x)
        self.assertEqual(potacommon.read_adif(path)[0]["TIME_ON"], "0102")

    def test_contact_over_0000z_is_one(self):
        qsolog.upsert(rec(QSO_DATE="20261020", TIME_ON="235900", MY_SIG_INFO="JP-1206"), None, "WSJT-X")     # its start
        qsolog.upsert(rec(QSO_DATE="20261021", TIME_ON="000100", MY_SIG_INFO="JP-1206", RST_SENT="-05"), None, "RUMlog")
        both = qsolog.records(["20261020", "20261021"])
        self.assertEqual([(r["QSO_DATE"], r["TIME_ON"]) for r in both], [("20261020", "235900")])   # the day it started
        self.assertEqual(both[0]["RST_SENT"], "-05")                                               # the richer copy
        self.assertEqual(qsolog.records(["20261021"]), [])
        self.assertEqual(len(qsolog.twins(qsolog.make_uid(rec(QSO_DATE="20261021", TIME_ON="000100")))), 1)


if __name__ == "__main__":
    unittest.main()
