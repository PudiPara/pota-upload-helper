"""The weather at the parks while recording, from Open-Meteo (https://open-meteo.com): free for non-commercial use, no
key, fewer than 10,000 calls a day per IP; the data is CC BY 4.0, so wherever it shows, "Weather data by Open-Meteo.com"
links to it. The app asks at the start of a recording and every EVERY seconds after (app.py), for the parks' middle.

summarize() turns the answer into what the 運用中 page shows; alerts() is what is worth a notice: a thunderstorm, rain
or strong gusts within AHEAD hours."""
import datetime as dt
import urllib.parse

from potacommon import fetch_json

URL = "https://api.open-meteo.com/v1/forecast"
EVERY = 15 * 60        # seconds between two looks while recording: its "current" is 15-minute data (4 calls an hour)
JMA_EVERY = 5 * 60     # Japan: the JMA's warnings are looked at this often (a warning issued while on the air)
AHEAD = 3              # hours the alerts look ahead
RAIN = 60              # % precipitation probability worth a notice
TABLE = 13             # hours in the 天気 tab's table (now and the next 12)
GUST = 15.0            # m/s (54 km/h): a gust that takes antennas and canopies down


def group(code):
    """A WMO weather code -> clear / cloudy / overcast / fog / drizzle / rain / snow / showers / thunder."""
    code = int(code or 0)
    for top, name in ((1, "clear"), (2, "cloudy"), (3, "overcast"), (48, "fog"), (57, "drizzle"), (67, "rain"),
                      (77, "snow"), (82, "showers"), (86, "snow"), (99, "thunder")):
        if code <= top:
            return name
    return "cloudy"


WET = {"drizzle", "rain", "snow", "showers", "thunder"}
# the WMO code's own wording, with its strength: (name for the copy "wx.k.<name>", level 1 light / 2 moderate / 3 heavy)
KINDS = {0: ("clear", 0), 1: ("mainlyClear", 0), 2: ("partly", 0), 3: ("overcast", 0), 45: ("fog", 0), 48: ("fog", 0),
         51: ("drizzleLight", 1), 53: ("drizzle", 1), 55: ("drizzleHeavy", 2), 56: ("freezingDrizzle", 1), 57: ("freezingDrizzle", 2),
         61: ("rainLight", 1), 63: ("rain", 2), 65: ("rainHeavy", 3), 66: ("freezingRain", 1), 67: ("freezingRain", 3),
         71: ("snowLight", 1), 73: ("snow", 2), 75: ("snowHeavy", 3), 77: ("snowGrains", 1),
         80: ("showersLight", 1), 81: ("showers", 2), 82: ("showersHeavy", 3), 85: ("snowShowersLight", 1), 86: ("snowShowersHeavy", 3),
         95: ("thunder", 2), 96: ("thunderHail", 3), 99: ("thunderHail", 3)}


def kind(code):
    """A WMO weather code -> (name, level): "rainHeavy", 3. An unknown code reads as its group."""
    return KINDS.get(int(code or 0), (group(code), 2))


def fetch(lat, lon):
    """Ask Open-Meteo for (lat, lon). -> summarize() of the answer. Raises on a network error."""
    q = urllib.parse.urlencode({
        "latitude": round(lat, 3), "longitude": round(lon, 3), "timezone": "auto", "forecast_days": 2,
        "wind_speed_unit": "ms", "current": "temperature_2m,weather_code,wind_speed_10m,wind_gusts_10m",
        "hourly": "precipitation_probability,weather_code,wind_gusts_10m,temperature_2m,precipitation,wind_speed_10m,"
                  "wind_direction_10m,is_day", "daily": "sunrise,sunset"})
    return summarize(fetch_json(URL + "?" + q, timeout=15))


def summarize(d):
    """Open-Meteo's answer -> {group, temp (°C), wind, gust (m/s), rain (% max over AHEAD h), sun: {kind, at "HH:MM"
    park local}, alerts: {thunder|rain|wind: value}}. Times stay in the park's own time (timezone=auto)."""
    cur, hourly, daily = d.get("current") or {}, d.get("hourly") or {}, d.get("daily") or {}
    now = (cur.get("time") or "")[:13]                     # "2026-10-22T17" - the hour we are in
    times = hourly.get("time") or []
    i = next((k for k, x in enumerate(times) if x[:13] >= now), len(times))
    hours = list(range(i, min(i + AHEAD + 1, len(times))))          # hours[0] = the hour we are in
    col = lambda key: hourly.get(key) or [None] * len(times)          # noqa: E731
    pr, cd, gu = col("precipitation_probability"), col("weather_code"), col("wind_gusts_10m")
    first = lambda ok: next((n for n, j in enumerate(hours) if ok(j)), None)   # noqa: E731 - hours from now
    rain = [pr[j] for j in hours if pr[j] is not None]
    g = group(cur.get("weather_code"))
    k, level = kind(cur.get("weather_code"))
    # the next sunrise or sunset at the park
    events = sorted([(x, "sunrise") for x in daily.get("sunrise") or []] + [(x, "sunset") for x in daily.get("sunset") or []])
    nxt = next(((x, e) for x, e in events if x > (cur.get("time") or "")), None)
    out = {"group": g, "kind": k, "level": level, "temp": cur.get("temperature_2m"), "wind": cur.get("wind_speed_10m"),
           "gust": cur.get("wind_gusts_10m"), "rain": max(rain) if rain else None,
           "sun": {"kind": nxt[1], "at": nxt[0][11:16]} if nxt else None, "alerts": {}}
    # alerts: {name: {"in": hours from now (0 = now / this hour), ...}} - the first hour it shows within AHEAD
    t_in = 0 if g == "thunder" else first(lambda j: cd[j] is not None and group(cd[j]) == "thunder")
    if t_in is not None:
        out["alerts"]["thunder"] = {"in": t_in}
    r_in = None if g in WET else first(lambda j: (pr[j] or 0) >= RAIN)
    if r_in is not None:
        out["alerts"]["rain"] = {"in": r_in, "p": max(rain)}
    gusts = [gu[j] for j in hours if gu[j] is not None]
    w_in = 0 if (cur.get("wind_gusts_10m") or 0) >= GUST else first(lambda j: (gu[j] or 0) >= GUST)
    if w_in is not None:
        out["alerts"]["wind"] = {"in": w_in, "g": max(gusts + [cur.get("wind_gusts_10m") or 0])}
    # the 天気 tab's table: the next TABLE hours from the one we are in, park time
    hk = lambda key, j: (hourly.get(key) or [None] * len(times))[j]          # noqa: E731
    out["hours"] = [{"t": times[j][11:16], "date": times[j][:10], "kind": kind(hk("weather_code", j))[0],
                     "group": group(hk("weather_code", j)), "day": hk("is_day", j) != 0, "temp": hk("temperature_2m", j),
                     "mm": hk("precipitation", j), "pop": hk("precipitation_probability", j), "wind": hk("wind_speed_10m", j),
                     "dir": hk("wind_direction_10m", j)} for j in range(i, min(i + TABLE, len(times)))]
    out["at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def add_jma_forecast(w, fc):
    """Japan: the JMA's own forecast for the park's area (jma.forecast) beside the numbers, for the 天気 tab."""
    w["jma_forecast"] = fc
    return w


def add_jma(w, found, place=None):
    """Japan: the JMA's warnings in force (jma.warnings) are the only alerts - w["jma"], each one an alert "jma:<code>"
    ({level}), notified when new. The forecast's own (thunder / rain / wind from Open-Meteo) are dropped: under the
    Meteorological Service Act only the JMA warns in Japan (art. 23) and forecasting needs a licence (art. 17), so a
    park in Japan gets the JMA's word, credited, and Open-Meteo's present conditions only: its hourly table and the
    rain chance ahead are forecasts, so they go too (the JMA's 府県天気予報 is the forecast there)."""
    w["jma"] = found
    w["jma_place"] = place                      # the municipality the warnings are for
    w["alerts"] = {"jma:" + x["code"]: {"level": x["level"]} for x in found}
    w["hours"], w["rain"] = [], None
    return w


def news(before, now):
    """The alerts in now that before did not have (a new one, or the first look): what to notify."""
    old = (before or {}).get("alerts") or {}
    return [k for k in (now or {}).get("alerts") or {} if k not in old]
