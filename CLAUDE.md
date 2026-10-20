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
- Logger: RUMlogNG (Mac). Prefs → UDP has two "Contact info" outputs, both **N1MM** now: `127.0.0.1:2333` → OpsLog (inbound "RUMlog N1MM"), `127.0.0.1:12060` → QSO Upload Utility (HamQTH/HRDlog). Club Log is synced by RUMlog itself.
- WSJT-X sends to multicast `224.0.0.1:2237`; RUMlog and GridTracker listen there.
- Planned wiring (not done yet, ask before changing): RUMlog `2333` → this app's N1MM listener on 2333 with forward to `127.0.0.1:2335`, and OpsLog's inbound moved to 2335.
- RUMlog ADIF exports omit `<SIG>POTA` on hunted parks (only SIG_INFO) — tools must not rely on SIG.

## Ideas not done yet
- Optional pota.app logged-in hunter log import (full history beyond the public last 25).
- App icon (`--icon`), code signing / notarization, Intel mac build.
- Bump `VERSION` in `potacommon.py` for every release (CI uses it as the tag).
