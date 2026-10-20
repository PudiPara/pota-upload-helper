"""Offline tests: the operator's P2P decisions survive logger re-sends and drive the build."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp()
os.environ.setdefault("POTA_HELPER_DATA", os.path.join(TMP, "data"))   # another test module may own it

from potacommon import read_adif  # noqa: E402
import builder  # noqa: E402
import potacommon  # noqa: E402
import qsolog  # noqa: E402
import spots  # noqa: E402


def rec(call, t, **kw):
    d = dict(CALL=call, QSO_DATE="20261020", TIME_ON=t, BAND="40m", MODE="FT8")
    d.update(kw)
    return d


class P2PDecisionTest(unittest.TestCase):
    def setUp(self):
        # the other test modules share one data dir (DATA_DIR is fixed at import): use a private one
        data = tempfile.mkdtemp()
        self._saved = (potacommon.DATA_DIR, builder.DATA_DIR, qsolog.DATA_DIR, spots.DATA_DIR)
        potacommon.DATA_DIR = builder.DATA_DIR = qsolog.DATA_DIR = spots.DATA_DIR = data
        with open(os.path.join(data, "spots-20261020.jsonl"), "w") as fh:
            fh.write(json.dumps({"seen": "2026-10-20T04:00:00", "spotTime": "2026-10-20T04:00:00",
                                 "activator": "JS6UHQ/6", "base": "JS6UHQ", "parks": ["JP-0157", "JP-1788"]}) + "\n")
        json.dump([], open(os.path.join(data, "hunter.json"), "w"))

    def tearDown(self):
        potacommon.DATA_DIR, builder.DATA_DIR, qsolog.DATA_DIR, spots.DATA_DIR = self._saved

    def test_candidate_then_yes_survives_resend(self):
        r = rec("JS6UHQ/6", "040828")
        cand = spots.candidate_for(r)
        self.assertEqual(cand, ["JP-0157", "JP-1788"])
        r["P2P_CANDIDATE"] = ",".join(cand)
        uid = qsolog.upsert(r, None, "WSJT-X")
        self.assertEqual(qsolog.records()[0].get("P2P_DECISION"), None)
        updated = qsolog.set_p2p(uid, "yes", "JP-0157,JP-1788")
        self.assertEqual(updated[0]["SIG_INFO"], "JP-0157,JP-1788")
        # the logger sends the same QSO a minute later (end time), richer, without a decision
        qsolog.upsert(rec("JS6UHQ/6", "040915", RST_SENT="-05", RST_RCVD="-10", NAME="X"), "id-1", "RUMlog")
        recs = qsolog.records()
        self.assertEqual(len(recs), 1)                          # deduped
        self.assertEqual(recs[0].get("P2P_DECISION"), "yes")    # decision kept on the surviving copy
        # same uid re-sent: decision carried over
        qsolog.upsert(rec("JS6UHQ/6", "040828"), None, "WSJT-X")
        self.assertEqual(qsolog.records()[0].get("SIG_INFO"), "JP-0157,JP-1788")

    def test_no_and_manual(self):
        uid = qsolog.upsert(rec("JA1AAA", "041000", P2P_CANDIDATE="JP-0001"), None, "x")
        qsolog.set_p2p(uid, "no", "")
        r = qsolog.records()[0]
        self.assertEqual((r.get("P2P_DECISION"), r.get("SIG_INFO")), ("no", None))
        qsolog.set_p2p(uid, "manual", "jp-0002")
        r = qsolog.records()[0]
        self.assertEqual((r.get("P2P_DECISION"), r.get("SIG_INFO"), r.get("SIG")), ("manual", "JP-0002", "POTA"))
        qsolog.set_p2p(uid, "", "")
        self.assertNotIn("P2P_DECISION", qsolog.records()[0])

    def test_build_uses_only_confirmed(self):
        recs = [rec("JS6UHQ/6", "040828", P2P_CANDIDATE="JP-0157,JP-1788"),      # candidate, never answered
                rec("JA0WSJ", "041500", TIME_OFF="041612", P2P_DECISION="yes", SIG="POTA", SIG_INFO="JP-0005", POTA_REF="JP-0005"),
                rec("JA1AAA", "041000", P2P_DECISION="yes", SIG="POTA", SIG_INFO="JP-0001", POTA_REF="JP-0001"),
                rec("JA2BBB", "041100", P2P_DECISION="no", P2P_CANDIDATE="JP-0009"),
                rec("JA3CCC", "041200", P2P_DECISION="manual", SIG="POTA", SIG_INFO="JP-0003,JP-0004", POTA_REF="JP-0003,JP-0004")]
        out = os.path.join(TMP, "out")
        res = builder.build(None, None, "JP-1281", "JL1FVA", out, offline=True, recs=recs, confirmed_only=True)
        self.assertEqual(res["files"], ["JL1FVA@JP-1281-20261020.adi"])
        by = {}
        for r in read_adif(os.path.join(out, res["files"][0])):
            by.setdefault(r["CALL"], []).append(r.get("SIG_INFO"))
        self.assertEqual(by["JS6UHQ/6"], [None])                       # spots alone never make a P2P
        self.assertEqual(by["JA1AAA"], ["JP-0001"])
        self.assertEqual(by["JA2BBB"], [None])
        self.assertEqual(sorted(by["JA3CCC"]), ["JP-0003", "JP-0004"])  # typed 2fer -> two records
        self.assertTrue(any("JS6UHQ/6" in n and "確認していない" in n for n in res["notes"]))
        srcs = {p["call"]: p["source"] for f in res["summary"] for p in f["p2p"]}
        self.assertEqual(srcs, {"JA1AAA": "confirmed", "JA3CCC": "manual", "JA0WSJ": "confirmed"})
        # the legacy path (ADIF from the logger) still guesses from spots
        res2 = builder.build(None, None, "JP-1281", "JL1FVA", out, offline=True, recs=recs[:1])
        self.assertEqual(res2["summary"][0]["p2p"][0]["parks"], ["JP-0157", "JP-1788"])


if __name__ == "__main__":
    unittest.main()


class ModeIsPartOfTheKey(unittest.TestCase):
    """pota.app counts CALL + BAND + MODE (+ date, parks) as one QSO: the same station on the
    same band in another mode minutes later is a second contact, not a duplicate copy."""

    def test_same_band_other_mode_is_a_second_qso(self):
        qsolog.upsert(rec("JA1MOD", "051000", MODE="CW"), "m-1", "RUMlog")
        qsolog.upsert(rec("JA1MOD", "051200", MODE="SSB"), "m-2", "RUMlog")
        calls = [r["CALL"] for r in qsolog.records() if r["CALL"] == "JA1MOD"]
        self.assertEqual(len(calls), 2)

    def test_ft4_copies_still_merge(self):
        qsolog.upsert(rec("JA1FT4", "052000", MODE="MFSK", SUBMODE="FT4"), None, "WSJT-X")
        qsolog.upsert(rec("JA1FT4", "052100", MODE="MFSK", SUBMODE="FT4"), "m-3", "RUMlog")
        self.assertEqual(len([r for r in qsolog.records() if r["CALL"] == "JA1FT4"]), 1)

    def test_lock_instance_is_exclusive(self):
        import potacommon
        self.assertTrue(potacommon.lock_instance())
        first = potacommon._instance_lock
        self.assertFalse(potacommon.lock_instance())     # a second copy would be refused
        first.close()
