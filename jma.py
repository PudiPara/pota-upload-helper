"""Japan only: the Japan Meteorological Agency's (気象庁) warnings and advisories (注意報・警報) at a park, from the JSON the
JMA's own pages read (www.jma.go.jp/bosai: not a documented API, it may change; the content is free to use with the
credit 「出典：気象庁ホームページ」). The park's municipality comes from GSI's reverse geocoder (国土地理院).

point -> municipality code (GSI muniCd, cached per point) -> the JMA's class20 areas (a ward of a designated city is
the city, which the JMA may split in two: then every part) -> their office (prefecture) -> its warnings file."""
import time
import urllib.parse

from potacommon import data_path, fetch_json, read_json, write_json

AREA_URL = "https://www.jma.go.jp/bosai/common/const/area.json"
WARN_URL = "https://www.jma.go.jp/bosai/warning/data/warning/%s.json"
GSI_URL = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress?"
AREA_MAX_AGE = 30 * 86400          # the area table rarely changes: fetched again after a month
GONE = {"解除", "発表警報・注意報はなし"}

# the JMA's codes -> (name for the copy "jma.<code>", level): 3 emergency (特別警報), 2 warning (警報), 1 advisory (注意報)
CODES = {"33": 3, "32": 3, "35": 3, "36": 3, "37": 3, "38": 3,
         "02": 2, "03": 2, "04": 2, "05": 2, "06": 2, "07": 2, "08": 2,
         "10": 1, "12": 1, "13": 1, "14": 1, "15": 1, "16": 1, "17": 1, "18": 1, "19": 1, "20": 1, "21": 1, "22": 1,
         "23": 1, "24": 1, "25": 1, "26": 1}
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
    """The JMA's warnings file -> [{"code", "level"}] in force in any of these class20 areas, the gravest first."""
    found = {}
    for t in data.get("areaTypes") or []:
        for a in t.get("areas") or []:
            if a.get("code") in codes:
                for w in a.get("warnings") or []:
                    c = w.get("code")
                    if c in CODES and w.get("status") not in GONE:
                        found[c] = CODES[c]
    return [{"code": c, "level": lv} for c, lv in sorted(found.items(), key=lambda x: (-x[1], x[0]))]
