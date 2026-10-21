"""Turbo HAMLOG's record text (WM_COPYDATA command 119) -> an ADIF-like record in UTC."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hamlog  # noqa: E402

RAW = "1\r\nJA1HML\r\n26/10/21\r\n10:47J\r\n599\r\n579\r\n7\r\nCW\r\n\r\n\r\nJ\r\nTEST\r\n\r\nJP-1206\r\nP2P JP-1234\r\n0\r\n"


class ParseRecord(unittest.TestCase):
    def test_jst_record(self):
        r = hamlog.parse_record(RAW)
        self.assertEqual((r["CALL"], r["QSO_DATE"], r["TIME_ON"], r["BAND"], r["MODE"], r["RST_SENT"], r["RST_RCVD"]),
                         ("JA1HML", "20261021", "014700", "40m", "CW", "599", "579"))

    def test_utc_and_day_change(self):
        r = hamlog.parse_record(RAW.replace("10:47J", "23:59U").replace("\r\n7\r\n", "\r\n7.015\r\n"))
        self.assertEqual((r["QSO_DATE"], r["TIME_ON"], r["FREQ"]), ("20261021", "235900", "7.015000"))
        r = hamlog.parse_record(RAW.replace("10:47J", "08:30J"))
        self.assertEqual((r["QSO_DATE"], r["TIME_ON"]), ("20261020", "233000"))   # JST morning = UTC previous day

    def test_ssb_and_empty(self):
        self.assertEqual(hamlog.parse_record(RAW.replace("\r\nCW\r\n", "\r\nLSB\r\n"))["MODE"], "SSB")
        self.assertIsNone(hamlog.parse_record("1\r\n\r\n\r\n"))


if __name__ == "__main__":
    unittest.main()
