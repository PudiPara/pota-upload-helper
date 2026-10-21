# CLAUDE.md — Potaroo (formerly POTA Upload Helper)

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
| `hamlog.py` | Turbo HAMLOG (Windows): ask a running HAMLOG through its published WM_COPYDATA API (Th527API: 116 = record count, 119 = one record) on a message-only window; `parse_record` (JST unless the time ends in U) | write to HAMLOG; use Hamlog50.DLL |
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
- **P2P is confirmed by the operator by default.** Spots are a hint; the hunter log (the other side's
  upload) is the only verified source and still overrides at build time, with a note. `settings.p2p_auto`
  (設定 → P2P) records the spot candidate as "yes" without asking (`app.py _on_qso`, all copies) - but
  only when `spots.candidate_info` says `auto`: no QRT by the activator before the QSO (they may be
  calling from home), a spot within `FRESH` (10 min), and the 2fer not pieced from separate spots.
  Otherwise the row still asks はい / いいえ, with the reason as a small tag (`P2P_NOTE`).
- **One 設定 page** holds callsigns, the P2P switch, the UDP listeners (ロガーとの接続), language and app
  items; the rail has four views. QSO rows sort by `ts` (date + TIME_ON to the second) sent by Python.
- **2fer rules**: a station's parks = the spot's reference + references in its comment, merged over its
  spots within `TWOFER_GAP` (15 min), plus its pota.app spot history (`spot/comments/{activator}/{park}`,
  `spots.history_parks`): the activator's own comments count always, other spotters' only when they say
  2fer/3fer (a hunter's "P2P from US-1234" is the hunter's park). The アクティベート中 page fills the
  history on a worker (rows are `pending` until then); a received QSO fetches it synchronously. At build time, parks from *separate* spots near the QSO are a
  2fer but `sure=False` (could be a rover) → a note. pota.app does not accept multi-value references, so
  their 2fer = the QSO repeated per park; my 2fer = one file per park.
- **Duplicates**: WSJT-X reports a QSO at its start, the logger at its end; same base call + band + mode
  (SUBMODE first, as pota.app stores it) + my parks within 3 min = one contact in the log, the live list and the count.
  Decisions and deletes hit all copies. pota.app's own key is CALL+MODE+QSO_DATE+BAND+parks, so another
  mode on the same band is a second QSO.
- **One instance**: `potacommon.lock_instance` (lock file in DATA_DIR); a second start calls
  `window.focus_running` and exits.
- **No write-back to the logger.** RUMlogNG ignores a UDP record whose time/band/mode already exist and
  its AppleScript only logs new QSOs; its ADIF import with "No Dupes + Update QSO record" works but is
  manual every time, so the owner dropped the feature. Decisions live only in the app log and files.
- **Turbo HAMLOG** has no UDP output and locks HAMLOG.HDB while running, so a listener of kind
  "hamlog" polls it every 2 s (`Receiver._run_hamlog`); on first contact it also takes the records of the
  last 12 h. Those read-back records (HAMLOG or the listener restarted) arrive as "backfill": `app._on_qso`
  skips any the log already knows (`qsolog.known`, deleted ones too), so a restart never re-stamps an
  earlier session's QSOs with the current parks or revives a delete. `hamlog.Client` registers its window
  class once with one module procedure (`_dispatch` -> `_CLIENTS[hwnd]`); a per-client procedure left a
  second client (保存して受信し直す) answering the first, and it never saw HAMLOG again. API terms (Th527API
  Readme): only for tools for Turbo HAMLOG - this is one; tell the author (JG1MOU) once it ships.
- **Listeners bind to 127.0.0.1** (`receiver.bind_address`): only loggers on the same computer can feed QSOs in (CodeQL alert "binding a socket to all network interfaces"). Multicast listeners bind the group with membership on the default interface (macOS/Linux, verified with WSJT-X); on Windows they bind 127.0.0.1 and join on loopback, so WSJT-X must list loopback under Outgoing interfaces (verified on Windows 11 with a multicast sender on loopback; sending on the default NIC does not arrive). Nothing binds every interface. A logger on another PC is not supported; if that is ever wanted, make it an explicit per-listener option, not the default.
- **`Api` state is private** (`self._window`, `self._logger`, …): pywebview exposes every public attribute
  of the js_api object and (6.x) walks them recursively; on Windows that walk entered the WinForms window
  and froze the app on 「記録を始める」. `tests/test_api_private.py` enforces it.
- **Editor** (アップロード作成 → 中身を見る): `Api.activation_qsos` lists one day's activation QSOs via
  `builder.find_activation_qsos`; app-log rows are edited cell by cell (`qsolog.update` retires the old
  uid and stores the record under the new key, `qsolog.delete_uid`), ADIF files are view-only.
- **Deleting an activation** (アップロード作成, app log only): `qsolog.delete_activation(date)` soft-deletes
  that UTC day's QSOs that carry my park; two presses in the UI since `window.confirm` is unavailable.
- **A QSO's own parks win.** `builder.find_activation_qsos`: override (手で上書き) → the record's
  MY_POTA_REF/MY_SIG_INFO (set while recording) → the sessions.json window it fell in. Windows carry a
  ±5 min margin and overlap when sessions follow each other quickly, so they are a fallback only.
- **The live list is the day's QSOs at the current parks** (`Api.session_qsos(start, parks)` + the poll
  filter in app.js): a park shared by several sessions keeps its count; the header shows the smallest
  park count with a per-park breakdown when they differ. Rows sort by `ts`, ties by arrival (`seq`).
- **Upload hours**: POTA asks for no log uploads 03-11 UTC; every results box (`uploadHoursHtml` in app.js, top of `resultsHtml`) says so in local time, amber while it is that time now.
- **Results list every QSO** (`summary[].rows`, P2P rows with plates and source; a "P2P only" switch) and
  the pota.app line count (`records`) next to the QSO count when their 2fer doubled lines.
- **A running session survives a restart**: `start_live` stores `settings.live` (id, parks, call, start),
  `Api._resume_live` restarts the SpotLogger on it (`SpotLogger.start(resume=...)` keeps the id and
  start), `finish_live` / `stop_live` clear it.
- **Parks across prefectures / states** (JP-0016, US-4239): `Api.park_locations` = the locations all
  entered parks share (pota.app `locationDesc`); one → shown fixed, several → the operator picks before
  recording. The session stores `{park: location}` for the multi-location parks; each QSO carries it as
  `MY_POTA_LOCS`, and the builder writes one file per (park, date, location) with `MY_STATE` and the
  documented name `CALL@PARK-DATE-LOCATION.adi`. Single-location parks are unchanged.
- **Window close ≠ finish.** `finish_live` stops, builds **the whole UTC day** (every park of the day gets
  its file with all of its QSOs, so a park shared by several sessions is never cut down to the last
  session) and resets; `shutdown` only stops threads.
- **設定 → 常に最前面** (`settings.on_top`): the window is created on top when set; `Api.set_on_top` →
  `BarMode.set_on_top`. Leaving bar mode restores this setting instead of always clearing on-top.
- **Bar mode** is a resize/move/on-top of the one window (pywebview can't do a second window cheaply);
  `window.confirm` is unavailable in the web view, so "finish with unconfirmed" needs a second press.
  On Windows the window calls are posted to the UI thread with `BeginInvoke` and not awaited
  (`window._run_steps`): the API thread holds the GIL during a WinForms call that messages the UI
  thread, which is waiting for the GIL to answer JavaScript -> deadlock.
- **Updates** are checked right after start (`promptUpdate` in app.js): a newer release opens a modal
  (今すぐ更新 / あとで; after the terms modal if that is up); the 設定 page has the same box. They
  compare `VERSION` with the latest release tag and download the OS zip; installers (DMG,
  Inno Setup per-user in `{localappdata}\Programs`) exist for first installs. Bump `VERSION` for every
  release (the tag and the updater key on it).
- **Updater on Windows**: `update.cmd` waits for this PID, swaps the exe, waits 2 s and starts the new
  one through `explorer.exe` (a fresh process tree, like a double-click). It runs
  with `CREATE_NO_WINDOW` only (detached, its wait loop never ends) and with `updater.child_env()`:
  the PyInstaller bootloader's `_PYI_*` variables must not reach the new exe, or it skips unpacking
  and fails with "Failed to load Python DLL" once our temp folder is gone.
- **Terms**: `terms.body` in each dictionary, modal on first launch until `settings.terms_accepted ==
  TERMS_VERSION` (app.js), also `TERMS.md` and README. The app is not affiliated with POTA.
- **Languages**: ja, en, zh-CN, zh-TW, fr, de, es, it, pt-BR, ko, pl; same keys in every file (check with a
  key diff before committing); language from `navigator.language` on first run, switchable in the rail.
- **Flags and countries** (アクティベート中): a station's country is its first park's prefix (ISO 3166 alpha-2),
  sent by `spots.summarize` with `region` (continent from `spots.continent_of`) for the region filter. The
  UI draws the flag from regional indicators with `ui/fonts/TwemojiCountryFlags.woff2` (78 KB, flags only:
  Windows has no flag glyphs) and names the country with `Intl.DisplayNames` in the UI language.
- **Name**: Potaroo since 2.0.0 (was POTA Upload Helper; POTA did not answer whether "POTA" may be in the
  name, so it is not). Kept on purpose: the macOS bundle id `com.jl1fva.pota-upload-helper` (Local Network
  permission is tied to it), the Inno Setup AppId (installing over 1.x upgrades it),
  and release copies named `POTA-Upload-Helper-*.zip` (1.x's updater looks for them). An update keeps the
  installed file name (`POTA Upload Helper.exe/.app`) so shortcuts keep working.
- **Repository**: `PudiPara/potaroo` since 2.0.2 (was `pota-upload-helper`; GitHub redirects the old name, and
  2.0.1+ accept download URLs under either name - 2.0.0 and older refuse the new one and need a manual install).
- **Example park references** in copy: JP-1266, and JP-1266,JP-1206 for a 2fer.

## Design system (keep it)
"Park trail sign": green only for the signs (plates, the running header, primary buttons, active nav
mark); surfaces neutral. Tokens in `ui/app.css :root` (light and dark). Park references are always
plates (`plate()` in app.js); 2fer = plates joined by an amber `+`. Type scale 11.5 / 12.5 / 13.5 / 15 /
17 / 20 / 26. Rows: line 1 who/where, line 2 details. Escape every network/user string with `esc()`.
Icon (`assets/icon.svg`, same shapes as the rail's `brand-mark` in index.html): one flat cream potoroo
silhouette sitting up on its haunches on the green plate, its raised tail as the antenna with amber arcs;
no character details (eye and nose dots only). Rebuild: SVG -> transparent 1024 PNG (headless Edge
`--default-background-color=00000000 --screenshot`) -> `scripts/make_icons.py`.

## Data and files
macOS `~/Library/Application Support/Potaroo/`, Windows `%APPDATA%\Potaroo\`
(override `POTAROO_DATA`; until 2.0.0 the folder was `POTA Upload Helper`, `potacommon._moved` renames it on first start): `qsolog.db`, `spots-YYYYMMDD.jsonl`, `sessions.json`, `hunter.json`,
`settings.json`. Output: `CALL@PARK-YYYYMMDD.adi` + `report.txt` in the chosen folder. Never commit data.

## Working on it
- `scripts/dev.sh [--debug]` runs from source with `POTAROO_DATA=./data`; tests are offline.
- `scripts/dev_web.py` serves ui/ at http://127.0.0.1:8765/ and forwards `pywebview.api` calls to a real
  `Api` over HTTP (no listeners, no window): check UI changes there in a browser. Computer use only for
  sending QSOs from loggers and for freezes. Keep the dev desktop app (./data, port 22237) running.
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
