import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTA_HELPER_DATA", tempfile.mkdtemp())

from receiver import parse_packet  # noqa: E402
import qsolog  # noqa: E402


def qs(s):
    b = s.encode()
    return struct.pack(">I", len(b)) + b


class ReceiverTest(unittest.TestCase):
    def test_n1mm(self):
        x = (b'<?xml version="1.0"?><contactinfo><call>JA1AAA/P</call><timestamp>2026-10-20 02:26:05</timestamp>'
             b'<txfreq>704100</txfreq><mode>FT8</mode><snt>-05</snt><rcv>-10</rcv><ID>abc</ID></contactinfo>')
        (act, rec, uid), = parse_packet(x)
        self.assertEqual((act, uid, rec["CALL"], rec["BAND"], rec["TIME_ON"]), ("upsert", "abc", "JA1AAA/P", "40m", "022605"))

    def test_n1mm_delete(self):
        (act, rec, uid), = parse_packet(b"<?xml version='1.0'?><contactdelete><call>JA1AAA</call>"
                                        b"<timestamp>2026-10-20 02:26:05</timestamp></contactdelete>")
        self.assertEqual(act, "delete")

    def test_wsjtx(self):
        pkt = struct.pack(">III", 0xADBCCBDA, 2, 12) + qs("WSJT-X") + qs(
            "<call:6>JA2BBB <qso_date:8>20261020 <time_on:6>023000 <band:3>40m <mode:3>FT8 <eor>")
        self.assertEqual(parse_packet(pkt)[0][1]["CALL"], "JA2BBB")

    def test_adif_in_xml(self):
        r = parse_packet(b"<?xml version='1.0'?><QsoLoggedInfoAdif><Adif>&lt;CALL:6&gt;JA3CCC &lt;EOR&gt;</Adif></QsoLoggedInfoAdif>")
        self.assertEqual(r[0][1]["CALL"], "JA3CCC")

    def test_log_dedupe_and_delete(self):
        qsolog.upsert({"CALL": "JA4DDD/P", "QSO_DATE": "20261021", "TIME_ON": "010605", "BAND": "40m"}, "x1", "n1mm")
        qsolog.upsert({"CALL": "JA4DDD", "QSO_DATE": "20261021", "TIME_ON": "010500", "BAND": "40m"}, None, "wsjtx")
        self.assertEqual(len(qsolog.records(["20261021"])), 1)
        qsolog.delete("x1")
        self.assertEqual(len(qsolog.records(["20261021"])), 0)


if __name__ == "__main__":
    unittest.main()
