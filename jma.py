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
THUNDER = "14"                      # 雷注意報


def _area_table():
    path = data_path("jma-area.json")
    have = read_json(path, None)
    if not have or time.time() - have.get("at", 0) > AREA_MAX_AGE:
        a = fetch_json(AREA_URL, timeout=20)
        have = {"at": time.time(), "class20s": {k: v.get("parent") for k, v in a["class20s"].items()},
                "parents": {k: v.get("parent") for key in ("class15s", "class10s") for k, v in a[key].items()},
                "offices": list(a["offices"])}
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
