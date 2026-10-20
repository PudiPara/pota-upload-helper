# CLAUDE.md — POTA Upload Helper

Talk to the owner in Japanese. UI copy is in `ui/i18n/*.json` (ja is the master). Personal and
station details are in `CLAUDE.local.md` (git-ignored); keep them out of this file.

## What it is
A desktop app (macOS Apple Silicon + Windows, pywebview) for POTA activators. The flow:
type the park → the window becomes a small always-on-top **bar** above the logger → each QSO the
logger sends over UDP appears in the bar → if the other station was spotted at a park the row asks
「P2P の可能性 … はい / いいえ」 (never automatic); with no spot the operator types the park →
10 QSOs shows a banner → 「この公園での運用を終了」 writes this park's pota.app upload file(s) and
returns to the park prompt. Logging stays in the logger; this app never writes the logger's log.

## Modules and what each one owns
| module | owns | must not |
|---|---|---|
| `potacommon.py` | stdlib helpers used everywhere: pota.app fetch (urllib, curl fallback), ADIF read/write, `base_call`, `split_parks`, `parks_in`, data dir + settings, `VERSION`, **the band table and mode groups** | know about spots, the log, or the UI |
| `spots.py` | everything a pota.app spot means: `parks_of` (reference + references in the comment), `their_parks_at` (which park a station was at around a QSO; `SPOT_BEFORE/AFTER`, `TWOFER_GAP`), `candidate_for` (the P2P candidate for a received QSO), `summarize` (the アクティベート中 page rows incl. band/mode group), `SpotLogger` (records `spots-YYYYMMDD.jsonl` + `sessions.json` while activating), `load_spots/load_sessions` | decide P2P for the upload (builder) or store decisions (qsolog) |
| `qsolog.py` | the SQLite log of received QSOs, dedupe of WSJT-X vs logger copies (±3 min, base call, band), the operator's P2P decision (`P2P_DECISION` yes/no/manual/log + `SIG_INFO`), `set_p2p` applied to all copies, `between` for a session window | parse UDP or talk to pota.app |
| `receiver.py` | UDP listeners and packet parsing (N1MM XML, WSJT-X msg 12, ADIF text/XML), raw forwarding, listener state as **codes** + `describe_state` for the UI | store anything |
| `builder.py` | upload files: hunter log (`hunter.json`), choosing activation QSOs (session window / MY_SIG_INFO / override), `build()` with `confirmed_only` for app-log records, one file per (my park, UTC date), their 2fer duplicated per park | guess from spots for app-log records (only the operator's decision + hunter log count) |
| `updater.py` | GitHub Releases check, download, swap (.app / .exe), relaunch, cleanup | UI text (it raises translated errors only) |
| `window.py` | `BarMode`: shrink/move/on-top the pywebview window and restore it | anything else |
| `i18n.py` | `t(key, **kw)` from `ui/i18n/<lang>.json` with en → ja fallback | — |
| `app.py` | `Api`: the JS bridge, sectioned (settings / listeners / activation / spots page / build / updates / misc). Validates input, translates errors, delegates. | contain radio logic; if a rule about spots, decisions or files is needed, it goes in the module above |
| `ui/` | `index.html` (static text via `data-i18n*`), `app.js` (`t()` for dynamic text; draws what Python computed), `app.css` (design tokens), `i18n/` | compute bands, 2fer or decisions itself |
| `tests/` | offline unit tests: `python3 -m unittest discover -s tests` | network |
| `scripts/` | `dev.sh` (run from source with `./data`), `send_test_qso.py` (dev-only ports), `make_icons.py` | — |
| `installer/windows.iss`, `assets/` | Inno Setup script; icon sources and generated `.icns/.ico` | — |

Boundaries to keep: a rule lives in exactly one module and the others call it. Both Python and JS
need `base_call`/`split_parks`; that duplication is accepted and the two must match. The UI never
re-derives data (band, mode group, candidate parks) that Python already sent.

## Decisions (and why)
- **P2P is confirmed by the operator, never automatic.** Spots are a hint; the hunter log (the other
  side's upload) is the only verified source and still overrides at build time, with a note.
- **2fer rules**: a station's parks = the spot's reference + references in its comment, merged over its
  spots within `TWOFER_GAP` (15 min). At build time, parks from *separate* spots near the QSO are a
  2fer but `sure=False` (could be a rover) → a note. pota.app does not accept multi-value references, so
  their 2fer = the QSO repeated per park; my 2fer = one file per park.
- **Duplicates**: WSJT-X reports a QSO at its start, the logger at its end; same base call + band within
  3 min = one contact in the log, the live list and the count. Decisions and deletes hit all copies.
- **No write-back to the logger.** RUMlogNG ignores a UDP record whose time/band/mode already exist and
  its AppleScript only logs new QSOs; its ADIF import with "No Dupes + Update QSO record" works but is
  manual every time, so the owner dropped the feature. Decisions live only in the app log and files.
- **Listeners bind to 127.0.0.1** (`receiver.bind_address`): only loggers on the same computer can feed QSOs in (CodeQL alert "binding a socket to all network interfaces"). Multicast listeners bind the group (Windows: the wildcard, membership filters). A logger on another PC is not supported; if that is ever wanted, make it an explicit per-listener option, not the default.
- **Window close ≠ finish.** `finish_live` stops, builds and resets; `shutdown` only stops threads.
- **Bar mode** is a resize/move/on-top of the one window (pywebview can't do a second window cheaply);
  `window.confirm` is unavailable in the web view, so "finish with unconfirmed" needs a second press.
- **Updates** compare `VERSION` with the latest release tag and download the OS zip; installers (DMG,
  Inno Setup per-user in `{localappdata}\Programs`) exist for first installs. Bump `VERSION` for every
  release (the tag and the updater key on it).
- **Terms**: `terms.body` in each dictionary, modal on first launch until `settings.terms_accepted ==
  TERMS_VERSION` (app.js), also `TERMS.md` and README. The app is not affiliated with POTA.
- **Languages**: ja, en, zh-CN, zh-TW, fr, de, es, it, pt-BR, ko, pl; same keys in every file (check with a
  key diff before committing); language from `navigator.language` on first run, switchable in the rail.
- **Example park references** in copy: JP-1266, and JP-1266,JP-1206 for a 2fer.

## Design system (keep it)
"Park trail sign": green only for the signs (plates, the running header, primary buttons, active nav
mark); surfaces neutral. Tokens in `ui/app.css :root` (light and dark). Park references are always
plates (`plate()` in app.js); 2fer = plates joined by an amber `+`. Type scale 11.5 / 12.5 / 13.5 / 15 /
17 / 20 / 26. Rows: line 1 who/where, line 2 details. Escape every network/user string with `esc()`.

## Data and files
macOS `~/Library/Application Support/POTA Upload Helper/`, Windows `%APPDATA%\POTA Upload Helper\`
(override `POTA_HELPER_DATA`): `qsolog.db`, `spots-YYYYMMDD.jsonl`, `sessions.json`, `hunter.json`,
`settings.json`. Output: `CALL@PARK-YYYYMMDD.adi` + `report.txt` in the chosen folder. Never commit data.

## Working on it
- `scripts/dev.sh [--debug]` runs from source with `POTA_HELPER_DATA=./data`; tests are offline.
- CI (`.github/workflows/build.yml`): every push to `main` builds both OSes (PyInstaller, icon, macOS
  Info.plist with `NSLocalNetworkUsageDescription` + ad-hoc re-sign, DMG, Inno Setup) and updates the
  GitHub Release `v<VERSION>`.
- macOS 15+ needs the "Local Network" permission to receive multicast; the usage string is in the
  bundle. Translocated copies (opened from the DMG without moving to Applications) cannot self-update.
- Desktop-control tools: background `app_*` screenshots walk the accessibility tree and that walk has
  pressed buttons in the web view (accepted the terms modal, changed the language select). Use the
  full-screen tools when a state matters.
- Before adding a feature, write one line here: which module owns the new rule and what it must not
  touch. Prefer extending the owning module over a shortcut in `app.py` or `app.js`.

## Not done
Nearby parks from the current location (map/list to pick from); code signing / notarization; Intel
mac build; an English README.
