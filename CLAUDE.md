# CLAUDE.md — POTA Upload Helper

Owner: JL1FVA (藤原 雅也). Talk to the owner in Japanese. UI copy is Japanese.

## What this is
Desktop app (macOS Apple Silicon + Windows) for POTA activators. The owner's intended flow (agreed 2026-10-20):
open the logger and this app → type the park → the window becomes a small always-on-top **bar** above the logger →
each QSO arrives over UDP → if the other station was spotted at a park the row asks 「P2P の可能性 … はい / いいえ」
(never automatic); with no spot (Phone/CW) the operator types the park into the row → at 10 QSOs a full-window banner →
「この公園での運用を終了」 stops recording, writes this park's upload file(s) to the out dir and returns to the park prompt
for the next park. Logging itself stays in the logger; this app never writes the logger's log.
- **運用中**: records POTA spots every 60 s (api.pota.app/spot/activator) so the other station's park(s) are known even after they QRT. `Api.set_bar` shrinks/moves the window (`BAR_W×BAR_H`, `on_top`); `Api.finish_live` = stop + `builder.build(confirmed_only=True)` on the session's QSOs.
- **ロガーとの接続**: receives QSOs over UDP like OpsLog (N1MM XML, WSJT-X binary msg 12 incl. multicast, ADIF / ADIF-in-XML), optional raw forwarding to another app. QSOs go to the app's SQLite log with `P2P_CANDIDATE` (from spots) and, once answered, `P2P_DECISION` = yes | no | manual | log (log = SIG_INFO came from the logger). `qsolog.set_p2p` applies a decision to the WSJT-X and logger copies of the same contact; `upsert` carries a decision over when the logger re-sends.
- **アップロード作成**: writes one ADIF per (my park, UTC date), named `CALL@PARK-YYYYMMDD.adi`, ready for pota.app. P2P park(s) from: 1) pota.app public hunter log (verified), 2) the operator's decision (app log, `confirmed_only`), 3) recorded spots (ADIF-file builds only), 4) SIG_INFO/POTA_REF in the log. Their 2fer → QSO duplicated per park; my 2fer → one file per park (Cartesian product). POTA uploads do not accept multi-value refs (as of 2024).
- **Writing parks back to the logger**: not possible over UDP. RUMlogNG's "QSOs received from Flex / ADIF" (Save QSO) ignores a record whose time/band/mode already exist (no update, no dupe) and its AppleScript only fills the entry form for a *new* QSO. What works is its ADIF import with "No Dupes" + "Update QSO record" (fields chosen by the user: My Park = MY_SIG_INFO, P2P = SIG_INFO, POTA = MY_SIG), so `build()` writes `logger_update.adi`: one line per QSO, parks comma-joined (the 2-row split is only for pota.app), TIME_ON = TIME_OFF for WSJT-X copies because RUMlogNG logs those at the end time.
- Not done yet: nearby parks from the current location (map / list to pick from) — the owner wants it after the flow above is solid.

## Layout
| file | role |
|---|---|
| `app.py` | pywebview window + `Api` class (JS bridge: `window.pywebview.api.*`) |
| `ui/index.html`, `ui/app.css`, `ui/app.js` | the whole UI (no framework, no build step) |
| `builder.py` | `build()` / `list_activations()` / `live_p2p()` – P2P matching and file output |
| `spotlogger.py` | `SpotLogger` thread – spots → `spots-YYYYMMDD.jsonl`, sessions → `sessions.json` |
| `receiver.py` | `Receiver` UDP listeners + `parse_packet()` |
| `qsolog.py` | SQLite log; dedupes the same QSO from WSJT-X and the logger (±3 min, base call, band); honours logger edits/deletes |
| `potacommon.py` | API fetch (urllib, falls back to `curl`), ADIF read/write, `base_call`, `split_parks`, data dir, settings, `VERSION` |
| `updater.py` | in-app update from GitHub Releases: `check()` (latest release via api.github.com, asset per OS), `install()` (download, macOS: swap the `.app` and relaunch via `open -n`; Windows: a cmd helper swaps the `.exe` after exit), `cleanup()` removes `*.old` at start. Only from a frozen build; translocated macOS copies get the new app in ~/Downloads instead |
| `pota_build.py`, `pota_spotlog.py` | CLI wrappers |
| `tests/` | `python3 -m unittest discover -s tests` (offline) |
| `.github/workflows/build.yml` | every push to `main` builds macOS `.app` + Windows `.exe` (PyInstaller) and creates/updates the GitHub Release `v<VERSION>` |

Data dir: macOS `~/Library/Application Support/POTA Upload Helper/`, Windows `%APPDATA%\POTA Upload Helper\` (override with `POTA_HELPER_DATA`). Never commit logs/data (`.gitignore` blocks `*.adi`, `*.adif`, `data/`, `out/`).

## Design system (keep it)
"Park trail-sign" identity. Tokens in `ui/app.css :root`: pine `#173F30`, paper `#EDF1EB`, ink `#1D2621`, moss `#6E8A77`, amber `#D9962B` (= 2fer). Park refs are always rendered as plates (`plate()` in app.js); 2fer = plates joined by an amber `+`. System fonts (Hiragino / Yu Gothic UI), tabular numerals, dark mode via `prefers-color-scheme`. Escape every network/user string with `esc()` before inserting HTML.

## Status (2026-10-20)
- v1.0.0 released; CI green on macOS and Windows.
- Verified from source on the owner's Mac (python 3.9 from Xcode CLT, pywebview 6.2.1): all three views, folder dialog, spot recording with park name + 2fer plates, live P2P from UDP QSOs, upload build (2fer duplicated per park, `logger_p2p_fix.adi`), clean exit on window close. Nothing in the core flow was broken.
- 2026-10-20 (later): bar mode, per-row P2P confirmation / manual entry, 10-QSO banner, 終了 → build. Verified from source: bar above RUMlogNG, はい / 手入力 both land in the ADIF as 確認済み / 手入力, unanswered candidates are left non-P2P with a note, window grows back on 終了. `window.confirm` is not available in the embedded view - 終了 with unanswered candidates needs a second press instead.
- Changes after that check: `FileDialog` constants (the bare `OPEN_DIALOG`/`FOLDER_DIALOG` are deprecated in pywebview 6), and CI now writes `NSLocalNetworkUsageDescription` into the macOS Info.plist and re-signs ad hoc, so macOS 15+ shows the "Local Network" prompt needed to receive multicast from WSJT-X. Not yet confirmed with the Release build: ask the owner whether WSJT-X QSOs arrive in the `.app`; if not, System Settings → Privacy → Local Network is the first place to look.
- Verified against the owner's real log: activation 2026-05-06 JP-1281 → 62 QSO, 11 P2P (9 were missing in RUMlog), JI1IKC/P 2fer JP-1206+JP-1946 split correctly; 35 activations total = pota.app count.

## Developing on the owner's Mac
- `scripts/dev.sh` runs from source with `POTA_HELPER_DATA=./data` (git-ignored) so the real log is untouched. `scripts/dev.sh --debug` opens the WebKit inspector.
- RUMlogNG, the Release `.app` and other loggers on this Mac all listen on UDP 2237 (and 2333/2334). Never send test packets there — a unicast packet lands in one of them and RUMlogNG would log it. Give the dev app its own listener port (`data/settings.json`, e.g. 22237) and use `scripts/send_test_qso.py 22237 CALL [--n1mm|--delete]`.
- `python3` here is Xcode's (3.9). If it says the Xcode license is not agreed, run `sudo xcodebuild -license accept` once.
- `gh` is not logged in on this Mac; CI/Release status must be read on github.com (or `gh auth login`).

## Owner's station context
- Logger: RUMlogNG (Mac). Prefs → UDP has two "Contact info N1MM" outputs: `127.0.0.1:2333` → OpsLog (inbound "RUMlog N1MM"), and since 2026-10-20 `127.0.0.1:2334` → **this app's "RUMlogNG (N1MM)" listener** (it used to go to QSO Upload Utility on 12060 for HamQTH/HRDlog; the owner disabled that and Club Log real-time sync (Prefs → Databases) so test QSOs never reach online services - re-enable both when testing is over).
- WSJT-X sends to multicast `224.0.0.1:2237`; RUMlog, GridTracker, a QSLWorld bridge script and this app all listen there. A WSJT-X QSO therefore reaches the app twice (WSJT-X copy at start time, RUMlog's N1MM copy at end time, no `<ID>`); `qsolog.dedupe` and the live list merge them (±3 min, base call, band).
- Verified end to end 2026-10-20 with real loggers: RUMlog manual QSO (Save QSO) and WSJT-X 「Log QSO」 both appeared in the bar with the right spot candidates (JS6UHQ/6 2fer JP-0157+JP-1788, JM7GTK/P JP-1028) and ended up as 確認済み in the ADIF. RUMlog manual entries take the rig's mode (`DATA-U`), which is not a valid ADIF mode - only a test artefact, real entries carry SSB/CW/FT8.
- OpsLog still receives everything RUMlog logs (2333), so test QSOs land there too.
- RUMlog ADIF exports omit `<SIG>POTA` on hunted parks (only SIG_INFO) — tools must not rely on SIG.

## Ideas not done yet
- Optional pota.app logged-in hunter log import (full history beyond the public last 25).
- App icon (`--icon`), code signing / notarization, Intel mac build.
- Bump `VERSION` in `potacommon.py` for every release (CI uses it as the tag, the in-app updater compares it with the latest release tag). 1.1.0 = bar mode + P2P confirmation + updater.
