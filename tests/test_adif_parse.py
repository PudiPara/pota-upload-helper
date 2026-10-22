"""Offline tests: ADI parsing reads each value by its length (#31) - tags inside a COMMENT stay there, the
header is skipped, entities are only decoded for ADIF carried in XML - and still copes with wrong lengths."""
import os
import struct
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", os.path.join(tempfile.mkdtemp(), "data"))   # DATA_DIR is fixed at import
from potacommon import parse_adif  # noqa: E402
from receiver import parse_packet  # noqa: E402


class ParseAdif(unittest.TestCase):
    def test_tags_inside_a_value(self):
        r = parse_adif("<CALL:6>JA1ABC<COMMENT:16>see <CALL:4>XXXX<EOR>")
        self.assertEqual(r, [{"CALL": "JA1ABC", "COMMENT": "see <CALL:4>XXXX"}])
        r = parse_adif("<CALL:6>JA1ABC<COMMENT:10>tnx <eor>!<MODE:2>CW<EOR>")
        self.assertEqual(r[0]["MODE"], "CW")
        r = parse_adif("<CALL:6>JA1ABC <COMMENT:22>my <SIG_INFO:7>JA-0001 <EOR>")
        self.assertNotIn("SIG_INFO", r[0])

    def test_header_types_case_and_last_record(self):
        r = parse_adif("WSJT-X log <adif_ver:5>3.1.0 <programid:6>WSJT-X <EOH>\r\n"
                       "<call:6:S>ja1abc <time_on:4>0102 <eor>\r\n<CALL:6>JA1DEF")
        self.assertEqual(r, [{"CALL": "ja1abc", "TIME_ON": "0102"}, {"CALL": "JA1DEF"}])

    def test_wrong_lengths_still_read_the_next_fields(self):
        r = parse_adif("<CALL:6>JA1ABC<NAME:12>山田太郎<MODE:3>FT8<EOR>")      # length in UTF-8 bytes
        self.assertEqual((r[0]["NAME"], r[0]["MODE"]), ("山田太郎", "FT8"))
        r = parse_adif("<CALL:6>JA1ABC <NAME:12>山田太郎<RST_SENT:3>599 <EOR>")    # overrun ends inside a tag
        self.assertEqual((r[0]["NAME"], r[0]["RST_SENT"]), ("山田太郎", "599"))

    def test_entities_are_text_in_adi(self):
        r = parse_adif("<CALL:6>JA1ABC<COMMENT:10>R&amp;R 73<MODE:3>FT8<EOR>")
        self.assertEqual((r[0]["COMMENT"], r[0]["MODE"]), ("R&amp;R 73", "FT8"))

    def test_large_file_is_linear(self):
        rec = "<CALL:6>JA1ABC <QSO_DATE:8>20261020 <TIME_ON:6>010203 <BAND:3>40m <MODE:3>FT8 <EOR>\n"
        t = time.time()
        self.assertEqual(len(parse_adif(rec * 20000)), 20000)
        self.assertLess(time.time() - t, 5)


class Packets(unittest.TestCase):
    def test_wsjtx_header_not_in_the_record(self):
        def qs(s):
            b = s.encode()
            return struct.pack(">I", len(b)) + b
        adif = "<adif_ver:5>3.1.0<programid:6>WSJT-X<EOH><call:6>JA1ABC <band:3>40m <mode:3>FT8 <eor>"
        (action, r, _), = parse_packet(struct.pack(">III", 0xADBCCBDA, 2, 12) + qs("WSJT-X") + qs(adif))
        self.assertNotIn("PROGRAMID", r)
        self.assertEqual(r["CALL"], "JA1ABC")

    def test_plain_adif_keeps_ampersands(self):
        (_, r, _), = parse_packet(b"<CALL:6>JA1ABC <COMMENT:10>R&amp;R 73 <MODE:3>FT8 <EOR>")
        self.assertEqual(r["COMMENT"], "R&amp;R 73")

    def test_adif_in_xml_is_decoded_once(self):
        x = b'<?xml version="1.0"?><adif>&lt;CALL:6&gt;JA1ABC &lt;COMMENT:3&gt;R&amp;R &lt;EOR&gt;</adif>'
        (_, r, _), = parse_packet(x)
        self.assertEqual((r["CALL"], r["COMMENT"]), ("JA1ABC", "R&R"))


if __name__ == "__main__":
    unittest.main()
