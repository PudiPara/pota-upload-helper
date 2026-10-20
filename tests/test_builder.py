"""Offline tests: P2P from hunter log and spots, their 2fer, own 2fer."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp()
os.environ["POTA_HELPER_DATA"] = os.path.join(TMP, "data")

from potacommon import base_call, read_adif, split_parks, write_adif  # noqa: E402
import builder  # noqa: E402


def qso(call, t, band="40m", mode="FT8", **kw):
    d = dict(CALL=call, QSO_DATE="20261020", TIME_ON=t, BAND=band, MODE=mode, RST_SENT="-05", RST_RCVD="-10")
    d.update(kw)
    return d


class BuilderTest(unittest.TestCase):
    def setUp(self):
        data = os.environ["POTA_HELPER_DATA"]
        os.makedirs(data, exist_ok=True)
        json.dump([{"date": "2026-10-20T01:05:00", "callsign": "JA1AAA/P", "band": "40M", "mode": "DATA",
                    "reference": "JP-0001"},
                   {"date": "2026-10-20T01:20:00", "callsign": "JA2BBB", "band": "40M", "mode": "DATA",
                    "reference": "JP-0002"},
                   {"date": "2026-10-20T01:20:00", "callsign": "JA2BBB", "band": "40M", "mode": "DATA",
                    "reference": "JP-0003"}],
                  open(os.path.join(data, "hunter.json"), "w"))
        with open(os.path.join(data, "spots-20261020.jsonl"), "w") as fh:
            fh.write(json.dumps({"seen": "2026-10-20T01:30:00", "spotTime": "2026-10-20T01:28:00",
                                 "activator": "JA3CCC/3", "base": "JA3CCC", "parks": ["JP-0004", "JP-0005"]}) + "\n")
        json.dump([{"id": "x", "call": "JL1FVA", "parks": ["JP-1281", "JP-1285"],
                    "start": "2026-10-20T01:00", "end": "2026-10-20T02:00"}],
                  open(os.path.join(data, "sessions.json"), "w"))
        self.adif = os.path.join(TMP, "log.adi")
        recs = [qso("JA1AAA", "010600"), qso("JA2BBB/1", "012100"), qso("JA3CCC", "013000"),
                qso("JA9ZZZ", "014000")] + [qso("JR%dXX" % i, "0150%02d" % i) for i in range(8)]
        write_adif(self.adif, recs, ["CALL", "QSO_DATE", "TIME_ON", "BAND", "MODE"])
        self.out = os.path.join(TMP, "out")

    def test_summarize_spots(self):
        import datetime as dt
        from spotlogger import summarize_spots
        now = dt.datetime(2026, 10, 20, 4, 50, tzinfo=dt.timezone.utc)
        spots = [{"activator": "JS6UHQ/6", "reference": "JP-1788", "spotTime": "2026-10-20T04:41:00", "frequency": "21049", "mode": "SSB", "comments": "2fer JP-0157"},
                 {"activator": "JR5JAQ/P", "reference": "JP-2100", "spotTime": "2026-10-20T04:34:12", "frequency": "7001", "mode": "CW", "comments": "RBN"},
                 {"activator": "JR5JAQ/P", "reference": "JP-2101", "spotTime": "2026-10-20T04:30:00", "frequency": "7001", "mode": "CW", "comments": ""},
                 {"activator": "JA1OLD", "reference": "JP-0001", "spotTime": "2026-10-20T03:00:00", "frequency": "7041", "mode": "FT8", "comments": ""},
                 {"activator": "JA1OLD", "reference": "JP-0002", "spotTime": "2026-10-20T02:00:00", "frequency": "7041", "mode": "FT8", "comments": ""}]
        rows = {r["base"]: r for r in summarize_spots(spots, now)}
        self.assertEqual((rows["JS6UHQ"]["parks"], rows["JS6UHQ"]["twofer"]), (["JP-1788", "JP-0157"], True))   # comment
        self.assertEqual((rows["JR5JAQ"]["parks"], rows["JR5JAQ"]["twofer"]), (["JP-2100", "JP-2101"], True))   # two spots, 4 min apart
        self.assertEqual((rows["JA1OLD"]["parks"], rows["JA1OLD"]["twofer"]), (["JP-0001"], False))            # an hour apart: moved on
        self.assertEqual([r["base"] for r in summarize_spots(spots, now)], ["JS6UHQ", "JR5JAQ", "JA1OLD"])  # newest first
        self.assertEqual(rows["JS6UHQ"]["ago"], 9)

    def test_helpers(self):
        self.assertEqual(base_call("JS2PHO/2"), "JS2PHO")
        self.assertEqual(base_call("7J1/K1ABC"), "K1ABC")
        self.assertEqual(split_parks("jp-1281, JP-1285;JP-1281"), ["JP-1281", "JP-1285"])

    def test_build(self):
        res = builder.build(self.adif, ["20261020"], None, "JL1FVA", self.out, offline=True)
        self.assertEqual(sorted(res["files"]), ["JL1FVA@JP-1281-20261020.adi", "JL1FVA@JP-1285-20261020.adi"])
        recs = read_adif(os.path.join(self.out, "JL1FVA@JP-1281-20261020.adi"))
        by = {}
        for r in recs:
            by.setdefault(r["CALL"], []).append(r.get("SIG_INFO"))
        self.assertEqual(by["JA1AAA"], ["JP-0001"])                    # hunter log
        self.assertEqual(sorted(by["JA2BBB/1"]), ["JP-0002", "JP-0003"])  # their 2fer (hunter log)
        self.assertEqual(sorted(by["JA3CCC"]), ["JP-0004", "JP-0005"])  # their 2fer (spot comment)
        self.assertEqual(by["JA9ZZZ"], [None])                          # not P2P
        self.assertEqual(len(recs), 14)   # 12 QSOs + 2 extra for the 2fers
        self.assertTrue(all(r["MY_SIG_INFO"] == "JP-1281" for r in recs))
        self.assertFalse([f for f in os.listdir(self.out) if f.startswith("logger_")])   # nothing for the logger


if __name__ == "__main__":
    unittest.main()
