"""The weather at the parks while recording, from Open-Meteo (https://open-meteo.com): free for non-commercial use, no
key, fewer than 10,000 calls a day per IP; the data is CC BY 4.0, so wherever it shows, "Weather data by Open-Meteo.com"
links to it. The app asks at the start of a recording and every EVERY seconds after (app.py), for the parks' middle.

summarize() turns the answer into what the 運用中 page shows; alerts() is what is worth a notice: a thunderstorm, rain
or strong gusts within AHEAD hours."""
import datetime as dt
import urllib.parse

from potacommon import fetch_json

URL = "https://api.open-meteo.com/v1/forecast"
EVERY = 30 * 60        # seconds between two looks while recording (its "current" is 15-minute data)
AHEAD = 3              # hours the alerts look ahead
RAIN = 60              # % precipitation probability worth a notice
GUST = 15.0            # m/s (54 km/h): a gust that takes antennas and canopies down


def group(code):
    """A WMO weather code -> clear / cloudy / overcast / fog / drizzle / rain / snow / showers / thunder."""
    code = int(code or 0)
    for top, name in ((0, "clear"), (2, "cloudy"), (3, "overcast"), (48, "fog"), (57, "drizzle"), (67, "rain"),
                      (77, "snow"), (82, "showers"), (86, "snow"), (99, "thunder")):
        if code <= top:
            return name
    return "cloudy"


WET = {"drizzle", "rain", "snow", "showers", "thunder"}


def fetch(lat, lon):
    """Ask Open-Meteo for (lat, lon). -> summarize() of the answer. Raises on a network error."""
    q = urllib.parse.urlencode({
        "latitude": round(lat, 3), "longitude": round(lon, 3), "timezone": "auto", "forecast_days": 2,
        "wind_speed_unit": "ms", "current": "temperature_2m,weather_code,wind_speed_10m,wind_gusts_10m",
        "hourly": "precipitation_probability,weather_code,wind_gusts_10m", "daily": "sunrise,sunset"})
    return summarize(fetch_json(URL + "?" + q, timeout=15))


def summarize(d):
    """Open-Meteo's answer -> {group, temp (°C), wind, gust (m/s), rain (% max over AHEAD h), sun: {kind, at "HH:MM"
    park local}, alerts: {thunder|rain|wind: value}}. Times stay in the park's own time (timezone=auto)."""
    cur, hourly, daily = d.get("current") or {}, d.get("hourly") or {}, d.get("daily") or {}
    now = (cur.get("time") or "")[:13]                     # "2026-10-22T17" - the hour we are in
    times = hourly.get("time") or []
    i = next((k for k, x in enumerate(times) if x[:13] >= now), len(times))
    ahead = range(i, min(i + AHEAD + 1, len(times)))
    pick = lambda key: [v for v in (hourly.get(key) or [None] * len(times))[ahead.start:ahead.stop] if v is not None]   # noqa: E731
    rain, codes, gusts = pick("precipitation_probability"), pick("weather_code"), pick("wind_gusts_10m")
    g = group(cur.get("weather_code"))
    # the next sunrise or sunset at the park
    events = sorted([(x, "sunrise") for x in daily.get("sunrise") or []] + [(x, "sunset") for x in daily.get("sunset") or []])
    nxt = next(((x, k) for x, k in events if x > (cur.get("time") or "")), None)
    out = {"group": g, "temp": cur.get("temperature_2m"), "wind": cur.get("wind_speed_10m"),
           "gust": cur.get("wind_gusts_10m"), "rain": max(rain) if rain else None,
           "sun": {"kind": nxt[1], "at": nxt[0][11:16]} if nxt else None, "alerts": {}}
    if g == "thunder" or any(group(c) == "thunder" for c in codes):
        out["alerts"]["thunder"] = True
    if g not in WET and rain and max(rain) >= RAIN:
        out["alerts"]["rain"] = max(rain)
    top = max([x for x in gusts + [cur.get("wind_gusts_10m")] if x is not None], default=0)
    if top >= GUST:
        out["alerts"]["wind"] = top
    out["at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def news(before, now):
    """The alerts in now that before did not have (a new one, or the first look): what to notify."""
    old = (before or {}).get("alerts") or {}
    return [k for k in (now or {}).get("alerts") or {} if k not in old]
