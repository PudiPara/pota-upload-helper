# Potaroo

*Früher POTA Upload Helper*

[日本語](README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [한국어](README.ko.md) · [Polski](README.pl.md)

Eine Desktop-App für POTA-Aktivierer (Parks on the Air), die vom ersten QSO bis zum Upload hilft. Läuft auf macOS und Windows.

Bei FT8 sieht man nicht, ob die Gegenstation in einem Park steht, geschweige denn ob es ein 2fer ist. Diese App zeichnet während der Aktivierung die pota.app-Spots auf, gleicht sie mit den QSOs ab, die dein Logger schickt, und **schlägt P2P (Park-zu-Park) und 2fer vor – du bestätigst und speicherst**. Am Ende schreibt sie pro Park und UTC-Tag eine Datei, die direkt zu pota.app hochgeladen werden kann.

![Aktivierung](docs/live.png)

## Was sie kann

- **Leistenmodus während der Aktivierung**: Park eintippen, Aufzeichnung starten, und das Fenster wird zu einer schmalen Leiste über dem Logger (dein Park, Zeit, QSO-Zähler, letzte QSOs). „Vergrößern“ holt es zurück. Aus Parks gespottete Stationen werden jede Minute notiert und sind auch nach deren QRT noch beurteilbar.
- **Gerade aktiv**: auch ohne Aufzeichnung eine Liste der Stationen, die gerade aus Parks funken, aus den pota.app-Spots (jede Minute neu). Filter: Land (mit Flagge) und Region, Band, Mode (CW / Phone / Data), Rufzeichen oder Park, nur 2fer.
- **QSOs vom Logger**: per UDP wie bei OpsLog oder JTAlert. N1MM-Format (RUMlogNG, N1MM Logger+, DXLog …), WSJT-X / JTDX (Multicast möglich), ADIF (JTAlert, GridTracker, Log4OM …). Korrekturen und Löschungen im Logger werden übernommen.
- **P2P sofort bestätigen**: wurde die Gegenstation aus einem Park gespottet, zeigt die Zeile „Mögliches P2P“ mit der Referenz – Ja oder Nein. Steht die Station nicht in den Spots (Phone oder CW, der Park wird dir gesagt), tippst du die Referenz in die Zeile. Nichts wird von selbst zu P2P.
- **10 QSOs**: ein Vollbild-Banner, sobald die Aktivierung steht.
- **Beenden schreibt die Datei**: „Diesen Park beenden“ schreibt die Upload-Datei(en) für Park und Tag (`JL1FVA@JP-1266-20261020.adi`) und kehrt zur Parkeingabe zurück. Am nächsten Park nur die Referenz eintippen. Ihr 2fer → das QSO je Park wiederholt; dein 2fer → eine Datei je Park.
- **Weiterleitung**: empfangene Pakete können unverändert an ein anderes Programm gehen (RUMlog → diese App → OpsLog).
- **Neu erzeugen**: der Tab „Upload-Dateien“ baut Dateien vergangener Tage aus dem App-Log oder dem ADIF-Export des Loggers.

![Upload-Dateien](docs/build.png)

Der Park der Gegenstation wird in dieser Reihenfolge bestimmt:

1. **Hunter-Log von pota.app** (was sie hochgeladen hat = bestätigt), Abgleich ±5 Minuten auf demselben Band
2. **Was du während der Aktivierung bestätigt oder eingetippt hast** (beim Bauen aus dem App-Log). Unbestätigte QSOs sind kein P2P
3. **Während der Aktivierung aufgezeichnete Spots** (nur beim Bauen aus einer ADIF-Datei; Spots von 30 Minuten vor bis 10 Minuten nach dem QSO)
4. SIG_INFO / POTA_REF aus dem Logger

Es wird nur die öffentliche API (api.pota.app) benutzt, kein Login. Das Log bleibt im Logger: die App beurteilt und schreibt Upload-Dateien, sie verändert das Logger-Log nie.

## Download

Die neueste Version gibt es unter [Releases](../../releases).

| OS | Datei | So geht’s |
|---|---|---|
| macOS (Apple Silicon) | `Potaroo-macOS.dmg` | Öffnen und `Potaroo` nach `Applications` ziehen |
| Windows 10 / 11 | `Potaroo-Setup.exe` | Installiert pro Benutzer (keine Adminrechte) und legt einen Startmenü-Eintrag an |

Die Zips (`Potaroo-macOS.zip` / `Potaroo-Windows.zip`) hängen ebenfalls an; das Update in der App nutzt sie, bitte nicht aus einem Release löschen.

Die App ist nicht signiert, der erste Start zeigt eine Warnung.

- **macOS**: Rechtsklick auf die App → Öffnen → Öffnen. Geht es dann noch nicht: Systemeinstellungen → Datenschutz & Sicherheit → unten „Trotzdem öffnen“.
- **Windows**: „Der Computer wurde durch Windows geschützt“ → Weitere Informationen → Trotzdem ausführen.

**Danach aktualisiert sich die App selbst.** Beim Start prüft sie auf eine neue Version; steht in der Seitenleiste „v1.x.x ist verfügbar“, drücke „Jetzt aktualisieren“: herunterladen, austauschen, neu starten. „Nach Updates suchen“ geht jederzeit. Läuft die App direkt aus dem DMG (nicht nach `Applications` verschoben), verhindert macOS den Austausch; die neue App landet dann im Downloads-Ordner.

## Logger-Anbindung

Lege unter „Logger-Anbindung“ Empfänger an (beliebig viele). **Jeder Logger, der QSOs per UDP senden kann, funktioniert.** Öffne im Logger die Einstellung „QSOs per UDP senden“, trage `127.0.0.1` und den Port eines Empfängers ein. Die App erkennt das Format jedes Pakets.

![Logger-Anbindung](docs/settings.png)

| Format | Logger | Wo einstellen |
|---|---|---|
| N1MM (contactinfo-XML) | RUMlogNG, N1MM Logger+, DXLog, Win-Test | RUMlogNG: Preferences → UDP, Contact info auf N1MM. N1MM Logger+: Config → Broadcast Data → Contacts |
| WSJT-X | WSJT-X, JTDX | Settings → Reporting, UDP Server. Mit `224.0.0.1` (Multicast) empfangen andere Programme gleichzeitig |
| ADIF | JTAlert, GridTracker, Log4OM … | die Einstellung „ADIF per UDP senden“ des Programms |

**Nur Logger auf demselben Rechner können senden.** Die Empfänger lauschen auf `127.0.0.1`; ein Logger auf einem anderen PC erreicht sie nicht.

**WSJT-X / JTDX per Multicast unter Windows**: unter Windows lauscht auch der Multicast-Empfänger auf Loopback (`127.0.0.1`). In WSJT-X unter Settings → Reporting → **Outgoing interfaces** **loopback** einschließen. Diese Konfiguration wurde unter Windows 11 geprüft; kommt nichts an, bitte ein [Issue](../../issues) öffnen. WSJT-X mit UDP Server `127.0.0.1` (ohne Multicast) funktioniert immer, dann können aber andere Programme nicht gleichzeitig empfangen.

Sollen dieselben Daten an ein weiteres Programm (OpsLog …) gehen, trage dessen Adresse und Port unter „Weiterleiten an“ ein.

**Beide Empfänger an verdoppelt nichts**: ein WSJT-X-QSO kommt zweimal an, von WSJT-X und noch einmal vom Logger, der es empfangen hat (etwa eine Minute Abstand: Start- gegen Endzeit). Gleiches Rufzeichen, gleiches Band, unter 3 Minuten = ein Kontakt; P2P-Entscheidungen und Löschungen gelten für beide. Kehrseite: zwei Kontakte mit derselben Station auf demselben Band innerhalb von 3 Minuten werden ebenfalls zu einem.

## Daten

| OS | Ort |
|---|---|
| macOS | `~/Library/Application Support/Potaroo/` |
| Windows | `%APPDATA%\Potaroo\` |

`qsolog.db` (empfangene QSOs), `spots-YYYYMMDD.jsonl` (Spots), `sessions.json` (deine Aktivierungszeiten und Parks), `hunter.json` (Kopie des Hunter-Logs), `settings.json`.
Das öffentliche pota.app-Profil zeigt nur die letzten 25 Hunter-QSOs; die App ergänzt `hunter.json` während der Aufzeichnung und bei jedem Bauen, damit die Historie wächst.

## Sprachen

日本語, English, 简体中文, 繁體中文, Français, Deutsch, Español, Italiano, Português (Brasil), 한국어, Polski. Wird aus der Systemsprache gewählt, umschaltbar unter „Sprache“ in den Einstellungen.

## Nutzungsbedingungen und Haftungsausschluss

Hobby-Software einer Privatperson, bereitgestellt wie besehen. **Der Autor übernimmt keine Haftung für Schäden aus der Nutzung** (falsche Uploads zu pota.app, doppelte oder fehlende QSOs, verlorene Logs oder Dateien, Auswirkungen auf Logger- oder Netzwerkeinstellungen). Prüfe die Dateien immer vor dem Hochladen. Die P2P- und 2fer-Erkennung ist eine Schätzung ohne Gewähr. Keine Verbindung zu Parks on the Air® oder pota.app. Volltext in [TERMS.md](TERMS.md), auch beim ersten Start angezeigt.

Sicherheitsmeldungen: siehe [SECURITY.md](SECURITY.md).

## Aus dem Quellcode starten

```sh
pip install -r requirements.txt
python3 app.py
```

Die Kommandozeilenwerkzeuge laufen für sich (nur Standardbibliothek).

```sh
python3 pota_spotlog.py --parks JP-1266,JP-1206
python3 pota_build.py export.adif --date 20261020
```

## Entwicklung

```sh
scripts/dev.sh                                  # legt ein venv an und startet mit Daten in ./data (nie dein echtes Log)
scripts/dev.sh --debug                          # mit WebKit-Inspektor
scripts/send_test_qso.py 22237 JS6UHQ/6         # Test-QSO an einen Dev-Empfänger (nie an 2237)
python3 -m unittest discover -s tests
```

`VERSION` in `potacommon.py` erhöhen und nach `main` pushen: GitHub Actions baut macOS und Windows und hängt sie an Release `v<VERSION>`. Struktur und Entscheidungen: [CLAUDE.md](CLAUDE.md).

## License

MIT

Country flags are drawn with the flags-only font from [country-flag-emoji-polyfill](https://github.com/talkjs/country-flag-emoji-polyfill) (MIT), built from Twemoji (CC-BY 4.0).
