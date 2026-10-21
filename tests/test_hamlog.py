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


class DeletionsFollowHamlog(unittest.TestCase):
    def test_a_deleted_record_is_reported_and_numbers_are_not_ids(self):
        import receiver
        recs = [hamlog.parse_record(RAW.replace("JA1HML", c)) for c in ("JA1AAA", "JA1BBB", "JA1CCC")]

        class Fake:                      # HAMLOG after JA1BBB was deleted: the rest renumbered
            def record(self, i):
                left = [recs[0], recs[2]]
                return left[i - 1] if 1 <= i <= len(left) else None
        got = []
        r = receiver.Receiver([], lambda a, rec, uid, name: got.append((a, rec["CALL"], uid)))
        seen = list(recs)
        r._hamlog_deleted(Fake(), seen, 2, "Turbo HAMLOG")
        self.assertEqual(got, [("delete", "JA1BBB", None)])
        self.assertEqual([x["CALL"] for x in seen], ["JA1AAA", "JA1CCC"])


class ReadBackAfterRestart(unittest.TestCase):
    def test_read_back_records_are_backfill_and_new_ones_upsert(self):
        import datetime as dt
        import receiver
        now = dt.datetime.utcnow()
        def rec(call, mins_ago):
            t = now - dt.timedelta(minutes=mins_ago)
            return {"CALL": call, "QSO_DATE": t.strftime("%Y%m%d"), "TIME_ON": t.strftime("%H%M%S"), "BAND": "40m", "MODE": "CW"}
        log = [rec("JA1OLD", 60 * 24), rec("JA1AAA", 30), rec("JA1BBB", 20)]
        got = []
        r = receiver.Receiver([], lambda a, rc, uid, name: got.append((a, rc["CALL"])))
        r.HAMLOG_POLL = 0

        class Fake:
            calls = 0
            def count(self):
                Fake.calls += 1
                if Fake.calls == 2:
                    log.append(rec("JA1NEW", 0))      # logged while we watch
                if Fake.calls == 3:
                    r._stop.set()
                return len(log)
            def record(self, i):
                return log[i - 1] if 1 <= i <= len(log) else None
        r._poll_hamlog(Fake(), "Turbo HAMLOG", lambda *a, **k: None)
        self.assertEqual(got, [("backfill", "JA1AAA"), ("backfill", "JA1BBB"), ("upsert", "JA1NEW")])


@unittest.skipUnless(os.name == "nt", "Windows only")
class ClientAfterRestart(unittest.TestCase):
    def test_a_second_client_gets_its_own_replies(self):
        import ctypes
        for text in ("first", "second"):          # a listener restart makes a new Client
            c = hamlog.Client()
            buf = ctypes.create_string_buffer(text.encode() + b"\0")
            cds = c.CDS(0, len(buf), ctypes.cast(buf, ctypes.c_void_p))
            res = ctypes.c_size_t(0)
            c.u.SendMessageTimeoutW(c.hwnd, hamlog.WM_COPYDATA, 0, ctypes.addressof(cds), 2, 1000, ctypes.byref(res))
            self.assertEqual(c._reply, text)
            c.close()


if __name__ == "__main__":
    unittest.main()
