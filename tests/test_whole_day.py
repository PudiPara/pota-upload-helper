"""運用終了 writes the whole UTC day: a park shared by several sessions of one day keeps every QSO."""
import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("POTAROO_DATA", os.path.join(tempfile.mkdtemp(), "data"))   # another test module may own it
sys.modules.setdefault("webview", types.SimpleNamespace(OPEN_DIALOG=1, FOLDER_DIALOG=2))  # app.py imports it
sys.path.insert(0, ROOT)
import app  # noqa: E402
app.weather.fetch = lambda lat, lon: (_ for _ in ()).throw(OSError("offline test"))   # tests stay offline
import potacommon  # noqa: E402
import qsolog  # noqa: E402


class FinishBuildsTheWholeDay(unittest.TestCase):
    def test_shared_park_file_keeps_every_session(self):
        out = tempfile.mkdtemp(prefix="pota-day-")
        potacommon.save_settings({"out": out, "call": "JL1FVA"})
        api = app.Api.__new__(app.Api)
        sessions = [("JP-1206,JP-1266", "2026-01-03T00:00:00", "2026-01-03T00:30:00", "JA1AAA"),
                    ("JP-1206,JP-1946", "2026-01-03T01:00:00", "2026-01-03T01:30:00", "JA1BBA")]
        for i, (parks, start, end, call) in enumerate(sessions):
            qsolog.upsert({"CALL": call, "QSO_DATE": "20260103", "TIME_ON": start[11:13] + "1000", "BAND": "40m",
                           "MODE": "CW", "MY_SIG": "POTA", "MY_SIG_INFO": parks}, "day-%d" % i, "x")
            api._logger = types.SimpleNamespace(stop=lambda: None,
                                                session={"start": start, "end": end, "parks": parks.split(","), "call": "JL1FVA"})
            r = api.finish_live(online=False)
            self.assertTrue(r["ok"], r)
        out = os.path.join(out, "20260103")                                       # the day's own folder
        shared = open(os.path.join(out, "JL1FVA@JP-1206-20260103.adi"), encoding="utf-8").read()
        self.assertIn("JA1AAA", shared); self.assertIn("JA1BBA", shared)          # both sessions
        first = open(os.path.join(out, "JL1FVA@JP-1266-20260103.adi"), encoding="utf-8").read()
        self.assertIn("JA1AAA", first); self.assertNotIn("JA1BBA", first)          # only its own session


class JmaWithoutOpenMeteo(unittest.TestCase):
    def test_warnings_go_out_when_open_meteo_fails(self):
        api = app.Api.__new__(app.Api)
        api._lock, api._weather = app.threading.Lock(), None
        saved = app.jma.warnings, app.jma.place, app.jma.forecast, app.jma.feed_news
        app.jma.feed_news = lambda lat, lon: False                       # offline: the feed has nothing new
        app.jma.warnings = lambda lat, lon: [{"code": "14", "level": 2}]
        app.jma.place = lambda lat, lon: "沖縄県沖縄市"
        app.jma.forecast = lambda lat, lon: None
        stop = types.SimpleNamespace(is_set=lambda: False, wait=lambda s: setattr(stop, "is_set", lambda: True))
        try:
            api._weather_loop((26.3, 127.8), stop, japan=True)          # weather.fetch is offline here: it fails
        finally:
            app.jma.warnings, app.jma.place, app.jma.forecast, app.jma.feed_news = saved
        self.assertEqual((api._weather["alerts"], api._weather["new"]), ({"jma:14": {"level": 2}}, ["jma:14"]))


class JmaFeed(unittest.TestCase):
    def test_a_new_bulletin_from_the_park_office(self):
        feed = lambda *ids: "".join("<entry><id>https://www.data.jma.go.jp/developer/xml/data/%s.xml</id></entry>" % i for i in ids)
        saved = app.jma.areas, app.jma._feed_text, dict(app.jma._feed)
        app.jma.areas = lambda lat, lon: ("471000", ["4721100"])
        texts = iter([feed("20261022120000_0_VPWW53_471000"),                            # the first look: noted only
                      feed("20261022120000_0_VPWW53_471000", "20261022121000_0_VPWW53_014100"),   # another office
                      None,                                                               # unchanged (304)
                      feed("20261022121000_0_VPWW53_014100", "20261022122000_0_VPWW55_471000")])  # ours: 大雨
        app.jma._feed_text = lambda: next(texts)
        app.jma._feed.update(seen=None)
        try:
            self.assertEqual([app.jma.feed_news(26.3, 127.8) for _ in range(4)], [False, False, False, True])
        finally:
            app.jma.areas, app.jma._feed_text = saved[0], saved[1]
            app.jma._feed.clear(); app.jma._feed.update(saved[2])


if __name__ == "__main__":
    unittest.main()


class ResumeAfterRestart(unittest.TestCase):
    def test_the_recorded_session_comes_back(self):
        potacommon.save_settings({"live": None})
        api = app.Api.__new__(app.Api)
        api._lock = __import__("threading").Lock(); api._events = []; api._status = ""; api._logger = None
        api._spots_cache = (0, []); api._parks = {}; api._qso_events = []; api._receiver = None; api._recv_status = {}
        r = api.start_live("JP-1206,JP-1266", "JL1FVA"); self.assertTrue(r["ok"])
        api._logger.stop()                                   # the app closes while recording (shutdown, not finish)
        fresh = app.Api.__new__(app.Api)
        fresh._lock = api._lock; fresh._events = []; fresh._status = ""; fresh._logger = None
        fresh._resume_live()
        self.assertEqual((fresh._logger.parks, fresh._logger.session["start"], fresh._logger.session["id"]),
                         (["JP-1206", "JP-1266"], r["start"], api._logger.session["id"]))
        fresh.stop_live()
        self.assertIsNone(potacommon.load_settings().get("live"))


class DeleteWhatTheListShows(unittest.TestCase):
    def test_qsos_counted_by_the_session_window_are_deleted_too(self):
        import json
        sess = os.path.join(potacommon.DATA_DIR, "sessions.json")
        old = open(sess, encoding="utf-8").read() if os.path.exists(sess) else None
        json.dump([{"id": "w", "call": "JL1FVA", "parks": ["JP-0016"], "start": "2026-01-11T01:00:00", "end": "2026-01-11T02:00:00"}],
                  open(sess, "w", encoding="utf-8"))
        try:
            qsolog.upsert({"CALL": "JA1WIN", "QSO_DATE": "20260111", "TIME_ON": "013000", "BAND": "40m", "MODE": "CW"}, None, "x")
            api = app.Api.__new__(app.Api)
            self.assertEqual(api.delete_activation("20260111")["n"], 1)
            self.assertEqual([r for r in qsolog.records(["20260111"]) if r["CALL"] == "JA1WIN"], [])
        finally:
            if old is None:
                os.remove(sess)
            else:
                open(sess, "w", encoding="utf-8").write(old)



class AppDataDeletes(unittest.TestCase):
    def setUp(self):
        self.api = app.Api.__new__(app.Api)
        self.api._logger = None; self.api._hunted = (0, None)
        qsolog.clear()

    def test_a_contact_goes_with_its_copy(self):
        uid = qsolog.upsert({"CALL": "JA1DUP", "QSO_DATE": "20260104", "TIME_ON": "010000", "BAND": "40m", "MODE": "FT8",
                             "MY_SIG_INFO": "JP-1206"}, None, "WSJT-X")
        qsolog.upsert({"CALL": "JA1DUP", "QSO_DATE": "20260104", "TIME_ON": "010100", "BAND": "40m", "MODE": "FT8",
                       "MY_SIG_INFO": "JP-1206"}, "x1", "logger")
        self.assertTrue(self.api.delete_qso(uid)["ok"])
        self.assertEqual(qsolog.history(), [])                     # the logger's copy does not come back

    def test_no_wipe_while_a_session_is_open(self):
        qsolog.upsert({"CALL": "JA1KEEP", "QSO_DATE": "20260104", "TIME_ON": "020000", "BAND": "40m", "MODE": "CW"}, None, "x")
        potacommon.save_settings({"live": {"parks": ["JP-1206"], "start": "2026-01-04T00:00:00"}})   # spot thread gone
        self.assertFalse(self.api.clear_app_data()["ok"])
        self.assertEqual(qsolog.count(), 1)
        potacommon.save_settings({"live": None})
        self.assertTrue(self.api.clear_app_data()["ok"])
        self.assertEqual(qsolog.count(), 0)
