"""Offline tests: Open-Meteo's answer -> the weather line and the alerts worth a notice (weather.py)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POTAROO_DATA", os.path.join(tempfile.mkdtemp(), "data"))   # another test module may own it

import weather  # noqa: E402


def answer(codes=(1, 1, 1, 1, 1), rain=(0, 0, 0, 0, 0), gusts=(3, 3, 3, 3, 3), now_code=1):
    hours = ["2026-10-22T%02d:00" % h for h in range(15, 20)]
    return {"current": {"time": "2026-10-22T16:45", "temperature_2m": 17.9, "weather_code": now_code,
                        "wind_speed_10m": 2.4, "wind_gusts_10m": gusts[0]},
            "hourly": {"time": hours, "weather_code": list(codes), "precipitation_probability": list(rain),
                       "wind_gusts_10m": list(gusts)},
            "daily": {"sunrise": ["2026-10-22T05:54", "2026-10-23T05:55"], "sunset": ["2026-10-22T16:58", "2026-10-23T16:57"]}}


class WeatherTest(unittest.TestCase):
    def test_line(self):
        w = weather.summarize(answer(rain=(90, 0, 10, 30, 20)))    # 15:00 is behind us: from the hour we are in
        self.assertEqual((w["group"], w["temp"], w["rain"], w["sun"]), ("cloudy", 17.9, 30, {"kind": "sunset", "at": "16:58"}))
        self.assertEqual(w["alerts"], {})

    def test_alerts(self):
        self.assertEqual(weather.summarize(answer(codes=(1, 1, 1, 95, 1)))["alerts"], {"thunder": True})
        self.assertEqual(weather.summarize(answer(rain=(0, 10, 70, 0, 0)))["alerts"], {"rain": 70})
        self.assertEqual(weather.summarize(answer(rain=(0, 10, 70, 0, 0), now_code=61))["alerts"], {})   # raining already
        self.assertEqual(weather.summarize(answer(gusts=(3, 3, 3, 16.5, 3)))["alerts"], {"wind": 16.5})

    def test_news(self):
        calm, storm = {"alerts": {}}, {"alerts": {"thunder": True, "rain": 70}}
        self.assertEqual(weather.news(None, storm), ["thunder", "rain"])         # the first look
        self.assertEqual(weather.news(storm, storm), [])                         # nothing new
        self.assertEqual(weather.news(calm, {"alerts": {"wind": 16}}), ["wind"])

    def test_groups(self):
        self.assertEqual([weather.group(c) for c in (0, 2, 3, 45, 53, 63, 75, 81, 86, 96)],
                         ["clear", "cloudy", "overcast", "fog", "drizzle", "rain", "snow", "showers", "snow", "thunder"])


if __name__ == "__main__":
    unittest.main()
