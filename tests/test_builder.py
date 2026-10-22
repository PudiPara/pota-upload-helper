"""Offline tests: P2P from hunter log and spots, their 2fer, own 2fer."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp()
os.environ["POTAROO_DATA"] = os.path.join(TMP, "data")

from potacommon import base_call, data_path, read_adif, split_parks, write_adif  # noqa: E402
import builder  # noqa: E402


def qso(call, t, band="40m", mode="FT8", **kw):
    d = dict(CALL=call, QSO_DATE="20261020", TIME_ON=t, BAND=band, MODE=mode, RST_SENT="-05", RST_RCVD="-10")
    d.update(kw)
    return d


class BuilderTest(unittest.TestCase):
    def setUp(self):
        data = data_path()          # DATA_DIR: an earlier test module may have set it
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
        import spots as spm
        from spots import summarize as summarize_spots
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
        self.assertEqual((rows["JS6UHQ"]["country"], rows["JS6UHQ"]["region"]), ("JP", "as"))   # prefix and its continent
        self.assertEqual([round(x) for x in rows["JR5JAQ"]["at"]], [round(x) for x in spm.middle([spm.park_at("JP-2100"), spm.park_at("JP-2101")])])   # the map
        spots[0]["locationDesc"] = "JP-13"
        self.assertEqual(summarize_spots(spots, now)[0]["location"], "JP-13")
        self.assertFalse(rows["JS6UHQ"]["qrt"])
        spots[0]["comments"] = "QRT tnx"
        self.assertTrue(summarize_spots(spots, now)[0]["qrt"])                    # the newest spot says QRT

    def test_bands_and_modes(self):
        from potacommon import band_from_khz, band_from_mhz, mode_group
        self.assertEqual(band_from_khz("7041"), "40m")
        self.assertEqual(band_from_khz("21049"), "15m")
        self.assertEqual(band_from_mhz(432.1), "70cm")
        self.assertEqual(band_from_khz("abc"), "")
        self.assertEqual([mode_group(m) for m in ("CW", "SSB", "ft8", "", None)], ["cw", "phone", "data", "", ""])

    def test_parks_of_and_their_parks_at(self):
        import spots
        self.assertEqual(spots.parks_of({"reference": "JP-1788", "comments": "2fer JP-0157 and jp-1788 again"}), ["JP-1788", "JP-0157"])
        one = [(100, ["JP-0001"], {})]
        self.assertEqual(spots.their_parks_at(one, 110), (["JP-0001"], True))        # within SPOT_AFTER
        self.assertEqual(spots.their_parks_at(one, 150), ([], True))                 # too long after
        rover = [(100, ["JP-0001"], {}), (104, ["JP-0002"], {})]
        self.assertEqual(spots.their_parks_at(rover, 108), (["JP-0001", "JP-0002"], False))   # separate spots: unsure
        twofer = [(100, ["JP-0001", "JP-0002"], {})]
        self.assertEqual(spots.their_parks_at(twofer, 108), (["JP-0001", "JP-0002"], True))   # one spot says both

    def test_helpers(self):
        self.assertEqual(base_call("JS2PHO/2"), "JS2PHO")
        self.assertEqual(base_call("7J1/K1ABC"), "K1ABC")
        self.assertEqual(split_parks("jp-1281, JP-1285;JP-1281"), ["JP-1281", "JP-1285"])

    def test_build(self):
        res = builder.build(self.adif, ["20261020"], None, "JL1FVA", self.out, offline=True)
        self.assertEqual(sorted(res["files"]), ["JL1FVA@JP-1281-20261020.adi", "JL1FVA@JP-1285-20261020.adi"])
        self.assertEqual(res["out_dir"], os.path.join(self.out, "20261020"))      # this build's files in a folder of their own
        self.assertTrue(os.path.exists(os.path.join(self.out, "report.txt")))      # the report beside it, not in it
        recs = read_adif(os.path.join(res["out_dir"], "JL1FVA@JP-1281-20261020.adi"))
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


class RecordedParksBeatSessionWindows(unittest.TestCase):
    def test_next_session_window_does_not_steal_earlier_qsos(self):
        from builder import find_activation_qsos
        from potacommon import minutes
        recs = [{"CALL": "JA1AAA", "QSO_DATE": "20260105", "TIME_ON": "130130", "BAND": "20m", "MODE": "FT8",
                 "MY_SIG": "POTA", "MY_SIG_INFO": "JP-1206,JP-1266"},
                {"CALL": "JA1BBB", "QSO_DATE": "20260105", "TIME_ON": "130300", "BAND": "20m", "MODE": "FT8"}]   # no parks: window decides
        t = lambda hhmm: minutes("20260105", hhmm)
        sessions = [(t("1257"), t("1309"), ["JP-1206", "JP-1266"]), (t("1259"), t("1310"), ["JP-1206", "JP-1946"])]  # widened, overlapping
        got = {r["CALL"]: sorted(mp) for r, _, mp in find_activation_qsos(recs, sessions=sessions)}
        self.assertEqual(got["JA1AAA"], ["JP-1206", "JP-1266"])
        self.assertEqual(got["JA1BBB"], ["JP-1206", "JP-1946"])


class SummaryListsEveryQso(unittest.TestCase):
    def test_rows_and_lines(self):
        import tempfile, builder
        out = tempfile.mkdtemp()
        recs = [{"CALL": "EI4HQ", "QSO_DATE": "20260107", "TIME_ON": "010000", "BAND": "20m", "MODE": "FT8", "MY_SIG": "POTA", "MY_SIG_INFO": "JP-1266",
                 "P2P_DECISION": "yes", "SIG": "POTA", "SIG_INFO": "IE-0023,IE-0141", "POTA_REF": "IE-0023,IE-0141"},
                {"CALL": "JA1TST", "QSO_DATE": "20260107", "TIME_ON": "010500", "BAND": "20m", "MODE": "FT8", "MY_SIG": "POTA", "MY_SIG_INFO": "JP-1266"}]
        recs.append(dict(recs[1], TIME_ON="010900"))                              # JA1TST again, same band and mode: a dupe for pota.app
        f = builder.build(None, None, None, "JL1FVA", out, offline=True, recs=recs, confirmed_only=True, log=lambda *a: None)["summary"][0]
        self.assertEqual((f["qsos"], f["records"], f["unique"]), (3, 4, 3))        # 4 lines; pota.app keeps 3 (EI4HQ x2 by SIG_INFO, JA1TST once)
        self.assertEqual([(r["call"], r["parks"]) for r in f["rows"]], [("EI4HQ", ["IE-0023", "IE-0141"]), ("JA1TST", []), ("JA1TST", [])])


class ParksFromSpotHistory(unittest.TestCase):
    def test_activator_comment_and_fer_comments_only(self):
        import datetime as dt
        from spots import parks_from_history
        now = dt.datetime(2026, 10, 20, 13, 50, tzinfo=dt.timezone.utc)
        hist = [{"spotTime": "2026-10-20T13:45:47", "spotter": "K9DEG", "comments": "2-fer: US-8423 US-4708"},
                {"spotTime": "2026-10-20T13:41:34", "spotter": "KC4JAB", "comments": "pota on"},
                {"spotTime": "2026-10-20T13:30:00", "spotter": "N0HUNT", "comments": "P2P from US-1234"},     # the hunter's park: ignored
                {"spotTime": "2026-10-20T13:20:53", "spotter": "WB1ANA", "comments": "2-fer: US-8423 US-4708"},
                {"spotTime": "2026-10-20T09:00:00", "spotter": "WB1ANA", "comments": "also US-9999"}]        # hours ago: another activation
        self.assertEqual(parks_from_history(hist, "WB1ANA", "US-8423", now), ["US-8423", "US-4708"])
        self.assertEqual(parks_from_history(hist[1:3], "WB1ANA", "US-8423", now), ["US-8423"])


class ActivationRowsCountPerPark(unittest.TestCase):
    def test_per_park_and_what_pota_keeps(self):
        from builder import list_activations
        q = lambda call, t, parks, **kw: dict({"CALL": call, "QSO_DATE": "20260108", "TIME_ON": t, "BAND": "20m", "MODE": "FT8",
                                              "MY_SIG": "POTA", "MY_SIG_INFO": parks}, **kw)
        recs = [q("JA1AAA", "010000", "JP-1206,JP-1266"), q("JA1BBB", "010100", "JP-1206,JP-1266"),
                q("JA1AAA", "020000", "JP-1206,JP-1946")]                       # same station again from another overlap
        d, parks, n, per, pota = list_activations(recs=recs, )[0]
        self.assertEqual((d, parks, n), ("20260108", "JP-1206,JP-1266,JP-1946", 3))
        self.assertEqual(per, {"JP-1206": 2, "JP-1266": 2, "JP-1946": 1})        # the 10-QSO count: JA1AAA once at JP-1206 (#14)
        self.assertEqual(pota, {"JP-1206": 2, "JP-1266": 2, "JP-1946": 1})       # JA1AAA counts once for JP-1206


class ParkAcrossPrefectures(unittest.TestCase):
    def test_one_file_per_location_with_my_state(self):
        import tempfile, builder
        out = tempfile.mkdtemp()
        q = lambda call, t, loc: {"CALL": call, "QSO_DATE": "20260109", "TIME_ON": t, "BAND": "40m", "MODE": "CW",
                                  "MY_SIG": "POTA", "MY_SIG_INFO": "JP-0016,JP-1206", "MY_POTA_LOCS": {"JP-0016": loc}}
        recs = [q("JA1AAA", "010000", "JP-TK"), q("JA1BBB", "030000", "JP-KN")]
        res = builder.build(None, None, None, "JL1FVA", out, offline=True, recs=recs, confirmed_only=True, log=lambda *a: None)
        files, out = {f["file"]: f for f in res["summary"]}, res["out_dir"]
        self.assertEqual(sorted(files), ["JL1FVA@JP-0016-20260109-JP-KN.adi", "JL1FVA@JP-0016-20260109-JP-TK.adi",
                                         "JL1FVA@JP-1206-20260109.adi"])
        self.assertIn("<MY_STATE:2>TK", open(os.path.join(out, "JL1FVA@JP-0016-20260109-JP-TK.adi"), encoding="utf-8").read())
        self.assertEqual(files["JL1FVA@JP-1206-20260109.adi"]["qsos"], 2)      # the one-prefecture park keeps one file


class NoOverlapNote(unittest.TestCase):
    def test_comment_says_parks_do_not_overlap(self):
        from spots import says_no_overlap
        jp0016 = "「富士箱根伊豆国立公園」　　真鶴半島県立自然公園(JP-1296)と重なる指定地域はありません。\nThis park does NOT overlap with JP-1296."
        self.assertTrue(says_no_overlap(jp0016, "JP-1296"))
        self.assertTrue(says_no_overlap("This park does NOT overlap with JP-1296.", "JP-1296"))
        self.assertFalse(says_no_overlap(jp0016, "JP-1206"))                       # another park: no note
        self.assertFalse(says_no_overlap("Overlaps with JP-1296 at the cape.", "JP-1296"))


class CandidateAfterQrt(unittest.TestCase):
    def setUp(self):
        import spots
        self.spots = spots
        self._load, self._hist = spots.load_spots, spots.history_info
        spots.history_info = lambda *a, **k: {"parks": [], "times": []}

    def tearDown(self):
        self.spots.load_spots, self.spots.history_info = self._load, self._hist

    def _with(self, spotlist):
        from potacommon import iso_minutes
        rows = [(iso_minutes(t), ["US-6818"], {"activator": "KD9NYE", "spotter": who, "reference": "US-6818",
                                                 "spotTime": t, "comments": c}) for t, who, c in spotlist]
        self.spots.load_spots = lambda: {"KD9NYE": rows}

    def info(self, hhmm):
        return self.spots.candidate_info({"CALL": "KD9NYE", "QSO_DATE": "20260110", "TIME_ON": hhmm + "00"})

    def test_fresh_spot_is_auto(self):
        self._with([("2026-01-10T13:10:00", "W1AW", "599")])
        self.assertEqual((self.info("1315")["auto"], self.info("1315")["note"]), (True, ""))

    def test_after_their_qrt_is_asked(self):
        self._with([("2026-01-10T13:10:00", "W1AW", "599"), ("2026-01-10T13:12:00", "KD9NYE", "QRT thanks all")])
        i = self.info("1315")
        self.assertEqual((i["parks"], i["auto"], i["note"]), (["US-6818"], False, "qrt"))

    def test_old_spot_is_asked(self):
        self._with([("2026-01-10T12:50:00", "W1AW", "599")])
        self.assertEqual((self.info("1315")["auto"], self.info("1315")["note"]), (False, "stale"))

