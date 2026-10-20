"""User-facing strings for the Python side, from the same dictionaries the UI uses (ui/i18n/<lang>.json).

t("recv.listening", where="...") formats the string of the current language; a key missing in
that language falls back to English, then Japanese, then the key itself.
"""
import json
import os
import sys

LANGS = ["ja", "en", "zh-CN", "zh-TW", "fr", "de", "es", "it", "pt-BR", "ko", "pl"]
_lang = "ja"
_cache = {}


def _dir():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "ui", "i18n")


def load(lang):
    if lang not in _cache:
        try:
            with open(os.path.join(_dir(), lang + ".json"), encoding="utf-8") as fh:
                _cache[lang] = json.load(fh)
        except (OSError, ValueError):
            _cache[lang] = {}
    return _cache[lang]


def available():
    """[(code, native name)] in display order."""
    return [(code, load(code).get("_name", code)) for code in LANGS]


def normalize(tag):
    """'ja-JP' -> 'ja', 'zh-Hant-TW' -> 'zh-TW', 'pt' -> 'pt-BR', unknown -> 'en'."""
    tag = (tag or "").replace("_", "-")
    low = tag.lower()
    if low in [c.lower() for c in LANGS]:
        return next(c for c in LANGS if c.lower() == low)
    if low.startswith("zh"):
        return "zh-TW" if any(x in low for x in ("hant", "tw", "hk", "mo")) else "zh-CN"
    if low.startswith("pt"):
        return "pt-BR"
    head = low.split("-")[0]
    return next((c for c in LANGS if c.split("-")[0] == head), "en")


def set_lang(lang):
    global _lang
    _lang = normalize(lang)
    return _lang


def get_lang():
    return _lang


def t(key, **kw):
    s = load(_lang).get(key) or load("en").get(key) or load("ja").get(key) or key
    if kw:
        try:
            return s.format(**kw)
        except (KeyError, IndexError, ValueError):
            return s
    return s
