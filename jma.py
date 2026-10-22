"""Japan only: the Japan Meteorological Agency's (気象庁) warnings and advisories (注意報・警報) at a park, from the JSON the
JMA's own pages read (www.jma.go.jp/bosai: not a documented API, it may change; the content is free to use with the
credit 「出典：気象庁ホームページ」). The park's municipality comes from GSI's reverse geocoder (国土地理院).

point -> municipality code (GSI muniCd, cached per point) -> the JMA's class20 areas (a ward of a designated city is
the city, which the JMA may split in two: then every part) -> their office (prefecture) -> its warnings file."""
import time
import urllib.parse

from potacommon import data_path, fetch_json, read_json, write_json

AREA_URL = "https://www.jma.go.jp/bosai/common/const/area.json"
# since the new system of late May 2026 (危険警報): data/r8/<office>.json, one latest report per kind (VPWW55 大雨, 58 暴風 ...);
# the old data/warning/<office>.json stopped on 2026-05-28
WARN_URL = "https://www.jma.go.jp/bosai/warning/data/r8/%s.json"
FORECAST_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/%s.json"   # 府県天気予報: 05 / 11 / 17 JST
GSI_URL = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress?"
AREA_MAX_AGE = 30 * 86400          # the area table rarely changes: fetched again after a month
GONE = {"解除", "発表警報・注意報はなし"}

# the JMA's codes -> 警戒レベル相当 (2 注意報 / 3 警報 / 4 危険警報 / 5 特別警報), as the JMA's own warning page lists them
# (its script's code table, read 2026-10-22). 大雨・土砂災害・高潮 have all four, 暴風・暴風雪・大雪・波浪 no 危険警報, the rest
# are 注意報 only. 洪水 (04 / 18) left this table: 氾濫 is its own information now.
CODES = {"10": 2, "03": 3, "43": 4, "33": 5,            # 大雨
         "29": 2, "09": 3, "49": 4, "39": 5,            # 土砂災害
         "19": 2, "08": 3, "48": 4, "38": 5,            # 高潮
         "15": 2, "05": 3, "35": 5,                     # 強風 / 暴風
         "13": 2, "02": 3, "32": 5,                     # 風雪 / 暴風雪
         "12": 2, "06": 3, "36": 5,                     # 大雪
         "16": 2, "07": 3, "37": 5,                     # 波浪
         "14": 2, "17": 2, "20": 2, "21": 2, "22": 2, "23": 2, "24": 2, "25": 2, "26": 2}   # 雷 融雪 濃霧 乾燥 なだれ 低温 霜 着氷 着雪


def _area_table():
    path = data_path("jma-area.json")
    have = read_json(path, None)
    if not have or "names" not in have or time.time() - have.get("at", 0) > AREA_MAX_AGE:
        a = fetch_json(AREA_URL, timeout=20)
        have = {"at": time.time(), "class20s": {k: v.get("parent") for k, v in a["class20s"].items()},
                "parents": {k: v.get("parent") for key in ("class15s", "class10s") for k, v in a[key].items()},
                "offices": list(a["offices"]), "class10s": list(a["class10s"]),
                "names": {k: v.get("name") for k, v in a["class20s"].items()}}
        write_json(path, have)
    return have


def areas(lat, lon):
    """(office code, [class20 codes]) for a point in Japan, or None. The point's municipality is cached."""
    cache_path = data_path("jma-points.json")
    cache = read_json(cache_path, {})
    key = "%.3f,%.3f" % (lat, lon)
    muni = cache.get(key)
    if muni is None:
        r = fetch_json(GSI_URL + urllib.parse.urlencode({"lat": round(lat, 5), "lon": round(lon, 5)}), timeout=15)
        muni = ((r or {}).get("results") or {}).get("muniCd") or ""
        cache[key] = muni
        write_json(cache_path, cache)
    if not muni:
        return None
    return resolve(muni, _area_table())


def resolve(muni, table):
    """GSI's municipality code -> (office, [class20 codes]) in the JMA's area table, or None."""
    c20 = table["class20s"]
    muni = muni.zfill(5)
    codes = [muni + "00"] if muni + "00" in c20 else \
        sorted(k for k in c20 if k.startswith(muni[:4] + "0"))      # a ward: its city (all the parts the JMA has)
    if not codes:
        return None
    office, seen = c20[codes[0]], set()
    while office and office not in table["offices"] and office not in seen:
        seen.add(office)
        office = table["parents"].get(office)
    return (office, codes) if office in table["offices"] else None


def class10(table, code):
    """The class10 area (一次細分区域, what the forecast is written for) a class20 area belongs to."""
    seen = set()
    while code and code not in table["class10s"] and code not in seen:
        seen.add(code)
        code = table["class20s"].get(code) or table["parents"].get(code)
    return code if code in table["class10s"] else None


def forecast(lat, lon):
    """The JMA's forecast for the area of a point in Japan, or None: {"office", "at", "area", "days": [{"date", "weather",
    "wind", "wave"}], "pops": [{"at", "p"}], "temps": {"place", "list": [{"at", "t"}]}}. Raises on a network error."""
    where = areas(lat, lon)
    if not where:
        return None
    area = class10(_area_table(), where[1][0])
    data = fetch_json(FORECAST_URL % where[0], timeout=15)
    return read_forecast(data, area)


def read_forecast(data, area):
    """The JMA's forecast file -> the part for one class10 area (see forecast)."""
    if not isinstance(data, list) or not data:
        return None
    ts = data[0].get("timeSeries") or []
    def pick(series):
        items = series.get("areas") or []
        i = next((n for n, a in enumerate(items) if (a.get("area") or {}).get("code") == area), None)
        return i, (items[i] if i is not None else None)
    out = {"office": data[0].get("publishingOffice"), "at": data[0].get("reportDatetime"), "area": None, "days": [], "pops": [], "temps": None}
    if ts:
        i, a = pick(ts[0])
        if a:
            out["area"] = a["area"].get("name")
            for n, when in enumerate(ts[0].get("timeDefines") or []):
                get = lambda key: (a.get(key) or [None] * 9)[n] if n < len(a.get(key) or []) else None   # noqa: E731
                out["days"].append({"date": when[:10], "weather": (get("weathers") or "").replace("\u3000", " "),
                                    "wind": (get("winds") or "").replace("\u3000", " "), "wave": (get("waves") or "").replace("\u3000", " ")})
    if len(ts) > 1:
        _, a = pick(ts[1])
        if a:
            out["pops"] = [{"at": t, "p": p} for t, p in zip(ts[1].get("timeDefines") or [], a.get("pops") or []) if p != ""]
    if len(ts) > 2:
        # the temperatures are for a city of each area, listed in the order of the areas
        # ponytail: matched by position; the JMA names no link between an area and its city
        i, _ = pick(ts[0]) if ts else (None, None)
        cities = ts[2].get("areas") or []
        c = cities[i] if i is not None and i < len(cities) else (cities[0] if cities else None)
        if c:
            out["temps"] = {"place": (c.get("area") or {}).get("name"),
                            "list": [{"at": t, "t": v} for t, v in zip(ts[2].get("timeDefines") or [], c.get("temps") or []) if v != ""]}
    return out


# the prefectures by their JIS code (the first two digits of a municipality's code)
PREFECTURES = ("北海道 青森県 岩手県 宮城県 秋田県 山形県 福島県 茨城県 栃木県 群馬県 埼玉県 千葉県 東京都 神奈川県 新潟県 富山県 石川県 福井県 "
               "山梨県 長野県 岐阜県 静岡県 愛知県 三重県 滋賀県 京都府 大阪府 兵庫県 奈良県 和歌山県 鳥取県 島根県 岡山県 広島県 山口県 徳島県 香川県 "
               "愛媛県 高知県 福岡県 佐賀県 長崎県 熊本県 大分県 宮崎県 鹿児島県 沖縄県").split()


def place(lat, lon):
    """Where the warnings at a point in Japan are for: the prefecture and the municipality as the JMA calls it
    ("沖縄県沖縄市"; the parts of a split city joined: "神奈川県横浜市北部・横浜市南部"), or None."""
    where = areas(lat, lon)
    if not where:
        return None
    names = _area_table()["names"]
    pref = int(where[1][0][:2])
    return (PREFECTURES[pref - 1] if 1 <= pref <= 47 else "") + "・".join(dict.fromkeys(names.get(c) or c for c in where[1]))


def warnings(lat, lon):
    """The warnings and advisories in force at a point in Japan: [{"code", "level"}], the gravest first. [] outside
    Japan or with none. Raises on a network error."""
    where = areas(lat, lon)
    if not where:
        return []
    return in_force(fetch_json(WARN_URL % where[0], timeout=15), where[1])


def in_force(data, codes):
    """The JMA's warnings file (r8: a list of the latest report of each kind) -> [{"code", "level"}] in force in any of
    these class20 areas, the gravest first."""
    found = {}
    for report in data if isinstance(data, list) else []:
        for item in (report.get("warning") or {}).get("class20Items") or []:
            if item.get("areaCode") in codes:
                for k in item.get("kinds") or []:
                    c = k.get("code")
                    if c in CODES and k.get("status") not in GONE:
                        found[c] = CODES[c]
    return [{"code": c, "level": lv} for c, lv in sorted(found.items(), key=lambda x: (-x[1], x[0]))]
