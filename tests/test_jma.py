"""Offline tests: the JMA's area table and warnings file -> the warnings in force at a park (jma.py), and how they join
the weather (weather.add_jma)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", os.path.join(tempfile.mkdtemp(), "data"))   # another test module may own it

import jma  # noqa: E402
import weather  # noqa: E402

TABLE = {"class20s": {"1322500": "130015", "1410011": "140011", "1410012": "140012", "0110000": "016011"},
         "parents": {"130015": "130010", "130010": "130000", "140011": "140010", "140012": "140010", "140010": "140000",
                     "016011": "016010", "016010": "016000"},
         "offices": ["130000", "140000", "016000"]}


TABLE10 = dict(TABLE, class10s=["130010"])


class JmaTest(unittest.TestCase):
    def test_resolve(self):
        self.assertEqual(jma.resolve("13225", TABLE), ("130000", ["1322500"]))
        self.assertEqual(jma.resolve("14103", TABLE), ("140000", ["1410011", "1410012"]))   # a ward of Yokohama: the city's parts
        self.assertEqual(jma.resolve("1101", TABLE), ("016000", ["0110000"]))               # Sapporo's ward, code without its 0
        self.assertIsNone(jma.resolve("99999", TABLE))

    def test_in_force(self):
        # the r8 file: the latest report of each kind; a 解除 is not in force, a step down (特別警報から警報) is the new one
        data = [{"dataTypeCode": "VPWW58", "warning": {"class10Items": [{"areaCode": "140010", "kinds": [{"code": "05", "status": "発表"}]}],
                 "class20Items": [{"areaCode": "1410011", "kinds": [{"code": "05", "status": "特別警報から警報"}]},
                                  {"areaCode": "1322500", "kinds": [{"status": "発表警報・注意報はなし"}]}]}},
                {"dataTypeCode": "VPWW55", "warning": {"class20Items": [{"areaCode": "1410012", "kinds": [{"code": "43", "status": "発表"}]},
                                                                        {"areaCode": "1410011", "kinds": [{"code": "14", "status": "継続"},
                                                                                                          {"code": "20", "status": "解除"}]}]}}]
        self.assertEqual(jma.in_force(data, ["1410011", "1410012"]),
                         [{"code": "43", "level": 4}, {"code": "05", "level": 3}, {"code": "14", "level": 2}])
        self.assertEqual(jma.in_force(data, ["1322500"]), [])
        self.assertEqual(jma.in_force({"areaTypes": []}, ["1322500"]), [])                 # the old format: nothing

    def test_read_forecast(self):
        data = [{"publishingOffice": "沖縄気象台", "reportDatetime": "2026-10-22T17:00:00+09:00", "timeSeries": [
            {"timeDefines": ["2026-10-22T17:00:00+09:00", "2026-10-23T00:00:00+09:00"],
             "areas": [{"area": {"name": "本島中南部", "code": "471010"}, "weathers": ["雨", "くもり"], "winds": ["東の風", "南の風"], "waves": ["６メートル", "７メートル"]},
                       {"area": {"name": "本島北部", "code": "471020"}, "weathers": ["雨　時々　くもり", "晴れ"], "winds": ["北の風", "東の風"], "waves": ["５メートル", "６メートル"]}]},
            {"timeDefines": ["2026-10-22T18:00:00+09:00", "2026-10-23T00:00:00+09:00"],
             "areas": [{"area": {"code": "471010"}, "pops": ["90", "70"]}, {"area": {"code": "471020"}, "pops": ["80", ""]}]},
            {"timeDefines": ["2026-10-23T00:00:00+09:00", "2026-10-23T09:00:00+09:00"],
             "areas": [{"area": {"name": "那覇"}, "temps": ["26", "29"]}, {"area": {"name": "名護"}, "temps": ["25", "28"]}]}]}]
        fc = jma.read_forecast(data, "471020")
        self.assertEqual((fc["area"], fc["days"][0]["weather"], fc["days"][1]["wave"]), ("本島北部", "雨 時々 くもり", "６メートル"))
        self.assertEqual(fc["pops"], [{"at": "2026-10-22T18:00:00+09:00", "p": "80"}])
        self.assertEqual(fc["temps"]["place"], "名護")                                   # the area's city, by position
        self.assertEqual(jma.class10(TABLE10, "1322500"), "130010")

    def test_add_jma(self):
        w = weather.add_jma({"alerts": {"rain": {"in": 1, "p": 70}, "thunder": {"in": 0}}}, [{"code": "14", "level": 2}])
        self.assertEqual(w["alerts"], {"jma:14": {"level": 2}})              # Japan: the JMA's only, not the forecast's
        self.assertEqual(weather.news({"alerts": {"rain": {}}}, w), ["jma:14"])
        self.assertEqual(weather.add_jma({"alerts": {"thunder": {"in": 0}}}, [])["alerts"], {})


if __name__ == "__main__":
    unittest.main()
