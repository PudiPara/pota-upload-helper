# POTA Upload Helper

[日本語](README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [한국어](README.ko.md) · [Polski](README.pl.md)

A desktop app for POTA (Parks on the Air) activators that helps from the moment you go on the air until the upload. Runs on macOS and Windows.

On FT8 you cannot tell whether the other station is in a park, let alone a 2fer. This app records pota.app spots while you activate, matches them against the QSOs your logger sends, and **suggests P2P (park-to-park) and 2fer for you to confirm and record**. When you finish, it writes one file per park and UTC day, ready to upload to pota.app.

![On the air](docs/live.png)

## What it does

- **Bar mode while activating**: type your park and start recording; the window becomes a small strip that stays above your logger (your park, elapsed time, QSO count, recent QSOs). "Expand" brings it back. Stations spotted from parks are noted every minute, so they can still be judged after they go QRT.
- **Activating now**: even when not recording, a list of stations currently on the air from parks, from pota.app spots (refreshed every minute). Filter by country (with flags) and region, band, mode (CW / Phone / Data), callsign or park search, and 2fer only.
- **QSOs from your logger**: received over UDP like OpsLog or JTAlert. N1MM format (RUMlogNG, N1MM Logger+, DXLog…), WSJT-X / JTDX (multicast supported), ADIF (JTAlert, GridTracker, Log4OM…). Edits and deletions in the logger are reflected.
- **P2P confirmed on the spot**: if the other station was spotted from a park, the row shows "Possible P2P" with the park reference; answer yes or no. For stations not on the spots (Phone or CW, where they tell you the park), type the reference into the row. Nothing becomes P2P automatically.
- **10 QSOs**: a full-screen banner the moment the activation is complete.
- **Finish writes the file**: "Finish this park" writes the upload file(s) for that park and day (`JL1FVA@JP-1266-20261020.adi`) and returns to the park prompt. At the next park, just type its number. Their 2fer → the QSO repeated per park; your 2fer → one file per park.
- **Forwarding**: received packets can be relayed unchanged to another program (RUMlog → this app → OpsLog).
- **Rebuild**: the "Upload files" tab builds files for past days from the app's log or from your logger's ADIF export.

![Upload files](docs/build.png)

The other station's park is decided in this order:

1. **pota.app hunter log** (what they uploaded = verified), matched within ±5 minutes on the same band
2. **What you confirmed or typed while activating** (when building from the app's log). Unconfirmed QSOs are not P2P
3. **Spots recorded while activating** (only when building from an ADIF file; spots from 30 minutes before to 10 minutes after the QSO)
4. SIG_INFO / POTA_REF from the logger

Only the public API (api.pota.app) is used; no login. Logging stays in your logger: this app only judges and writes upload files, and never changes the logger's log.

## Download

Get the latest version from [Releases](../../releases).

| OS | File | How |
|---|---|---|
| macOS (Apple Silicon) | `POTA-Upload-Helper-macOS.dmg` | Open it and drag `POTA Upload Helper` to `Applications` |
| Windows 10 / 11 | `POTA-Upload-Helper-Setup.exe` | Installs per user (no admin rights) and adds a Start menu entry |

The zips (`POTA-Upload-Helper-macOS.zip` / `POTA-Upload-Helper-Windows.zip`) are attached too; the in-app updater uses them, so please do not delete them from a Release.

The app is not code-signed, so the first launch shows a warning.

- **macOS**: right-click the app → Open → Open. If it still refuses, System Settings → Privacy & Security → "Open Anyway" near the bottom.
- **Windows**: "Windows protected your PC" → More info → Run anyway.

**From then on the app updates itself.** It checks for a new release on start; when the sidebar says "v1.x.x is available", press "Update now" to download, swap and restart. "Check for updates" in the sidebar does it any time. If you run the app straight from the DMG (without moving it to `Applications`), macOS prevents an in-place swap, so the new app is placed in your Downloads folder instead.

## Logger link

Create listeners under "Logger link" (as many as you like). **Any logger that can send QSOs over UDP works.** In the logger, open its "send QSOs over UDP" setting, point it at `127.0.0.1` and the port of a listener. The app detects the format of each packet.

![Logger link](docs/settings.png)

| Format | Loggers | Where to set it |
|---|---|---|
| N1MM (contactinfo XML) | RUMlogNG, N1MM Logger+, DXLog, Win-Test | RUMlogNG: Preferences → UDP, Contact info as N1MM. N1MM Logger+: Config → Broadcast Data → Contacts |
| WSJT-X | WSJT-X, JTDX | Settings → Reporting, UDP Server. `224.0.0.1` (multicast) lets other programs receive at the same time |
| ADIF | JTAlert, GridTracker, Log4OM, … | the program's "send ADIF over UDP" setting |

**Only loggers on the same computer can send to it.** Listeners bind to `127.0.0.1`, so a logger on another PC cannot reach them.

**WSJT-X / JTDX multicast on Windows**: on Windows the multicast listener also binds loopback (`127.0.0.1`). In WSJT-X, Settings → Reporting → **Outgoing interfaces**, include **loopback**. This setup was verified on Windows 11; if nothing arrives, please open an [issue](../../issues). Setting WSJT-X's UDP Server to `127.0.0.1` (no multicast) always works, but then other programs cannot receive at the same time.

To pass the same data on to another program (OpsLog, …), put its address and port in the listener's "Forward to".

**Both listeners on never doubles anything**: a WSJT-X QSO arrives twice, from WSJT-X and again from the logger that received it (about a minute apart: start vs end time). Same callsign, same band, less than 3 minutes apart = one contact; P2P decisions and deletions apply to both. The flip side: two contacts with the same station on the same band within 3 minutes also become one.

## Data

| OS | Location |
|---|---|
| macOS | `~/Library/Application Support/POTA Upload Helper/` |
| Windows | `%APPDATA%\POTA Upload Helper\` |

`qsolog.db` (received QSOs), `spots-YYYYMMDD.jsonl` (spot records), `sessions.json` (your activation windows and parks), `hunter.json` (hunter log copy), `settings.json`.
pota.app's public profile only shows the last 25 hunter QSOs, so the app appends to `hunter.json` while recording and on every build to keep the history.

## Languages

日本語, English, 简体中文, 繁體中文, Français, Deutsch, Español, Italiano, Português (Brasil), 한국어, Polski. Chosen from the OS language, switchable under "Language" in Settings.

## Terms of use and disclaimer

This is hobby software by an individual, provided as is. **The author accepts no liability for any damage arising from its use** (wrong uploads to pota.app, duplicated or missing QSOs, lost logs or files, effects on your logger or network settings). Always check the files before uploading. P2P and 2fer detection is an estimate; correctness is not guaranteed. Not affiliated with Parks on the Air® or pota.app. Full text in [TERMS.md](TERMS.md), also shown on first launch.

Security reports: see [SECURITY.md](SECURITY.md).

## Run from source

```sh
pip install -r requirements.txt
python3 app.py
```

The command-line tools work on their own (standard library only).

```sh
python3 pota_spotlog.py --parks JP-1266,JP-1206
python3 pota_build.py export.adif --date 20261020
```

## Development

```sh
scripts/dev.sh                                  # creates a venv and runs with data in ./data (never your real log)
scripts/dev.sh --debug                          # with the WebKit inspector
scripts/send_test_qso.py 22237 JS6UHQ/6         # send a test QSO to a dev-only listener (never to 2237)
python3 -m unittest discover -s tests
```

Bump `VERSION` in `potacommon.py` and push to `main`: GitHub Actions builds macOS and Windows and attaches them to Release `v<VERSION>`. Structure and design decisions are in [CLAUDE.md](CLAUDE.md).

## License

MIT

Country flags are drawn with the flags-only font from [country-flag-emoji-polyfill](https://github.com/talkjs/country-flag-emoji-polyfill) (MIT), built from Twemoji (CC-BY 4.0).
