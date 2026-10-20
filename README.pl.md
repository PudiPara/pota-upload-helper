# POTA Upload Helper

[日本語](README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [한국어](README.ko.md) · [Polski](README.pl.md)

Aplikacja desktopowa dla aktywatorów POTA (Parks on the Air), która pomaga od wyjścia w eter aż po wysyłkę. Działa na macOS i Windows.

W FT8 nie wiesz, czy druga stacja jest w parku, a tym bardziej czy to 2fer. Ta aplikacja zapisuje spoty z pota.app podczas aktywacji, zestawia je z QSO wysyłanymi przez twój program logujący i **proponuje P2P (park do parku) oraz 2fer, które ty potwierdzasz i zapisujesz**. Po zakończeniu tworzy jeden plik na park i dzień UTC, gotowy do wysłania na pota.app.

![Aktywacja](docs/live.png)

## Co potrafi

- **Tryb paska podczas aktywacji**: wpisz park, włącz zapis, a okno zmienia się w wąski pasek nad programem logującym (twój park, czas, liczba QSO, ostatnie QSO). „Rozwiń” przywraca je. Stacje spotowane z parków są notowane co minutę, więc można je ocenić nawet po ich QRT.
- **Aktywni teraz**: nawet bez zapisu lista stacji nadających z parków, ze spotów pota.app (co minutę). Filtry: region (Japonia / świat), pasmo, emisja (CW / Phone / Data), znak lub park, tylko 2fer.
- **QSO z programu logującego**: przez UDP jak OpsLog czy JTAlert. Format N1MM (RUMlogNG, N1MM Logger+, DXLog…), WSJT-X / JTDX (multicast), ADIF (JTAlert, GridTracker, Log4OM…). Poprawki i usunięcia w logu są uwzględniane.
- **P2P potwierdzane od razu**: jeśli druga stacja była spotowana z parku, wiersz pokazuje „Możliwe P2P” z oznaczeniem; odpowiedz tak lub nie. Gdy stacji nie ma w spotach (fonia lub CW, gdy podają park), wpisz oznaczenie w wierszu. Nic nie staje się P2P samo.
- **10 QSO**: baner na cały ekran w chwili zaliczenia aktywacji.
- **Zakończenie zapisuje plik**: „Zakończ ten park” zapisuje plik(i) do wysłania dla parku i dnia (`JL1FVA@JP-1266-20261020.adi`) i wraca do pola parku. W kolejnym parku wystarczy wpisać oznaczenie. Ich 2fer → QSO powtórzone dla każdego parku; twój 2fer → osobny plik na park.
- **Przekazywanie**: odebrane pakiety można przekazać bez zmian do innego programu (RUMlog → ta aplikacja → OpsLog).
- **Ponowne tworzenie**: zakładka „Pliki do wysłania” buduje pliki z minionych dni z logu aplikacji lub z eksportu ADIF programu logującego.

![Pliki do wysłania](docs/build.png)

Park drugiej stacji ustalany jest w tej kolejności:

1. **Log huntera z pota.app** (to, co wysłała = potwierdzone), dopasowanie ±5 minut na tym samym paśmie
2. **To, co potwierdziłeś lub wpisałeś podczas aktywacji** (przy budowaniu z logu aplikacji). Niepotwierdzone QSO nie są P2P
3. **Spoty zapisane podczas aktywacji** (tylko przy budowaniu z pliku ADIF; spoty od 30 minut przed do 10 minut po QSO)
4. SIG_INFO / POTA_REF z logu

Używane jest tylko publiczne API (api.pota.app), bez logowania. Log zostaje w twoim programie: ta aplikacja tylko ocenia i zapisuje pliki do wysłania, nigdy nie zmienia logu.

## Pobieranie

Najnowszą wersję znajdziesz w [Releases](../../releases).

| System | Plik | Jak |
|---|---|---|
| macOS (Apple Silicon) | `POTA-Upload-Helper-macOS.dmg` | Otwórz i przeciągnij `POTA Upload Helper` do `Applications` |
| Windows 10 / 11 | `POTA-Upload-Helper-Setup.exe` | Instaluje dla użytkownika (bez uprawnień administratora) i dodaje wpis do menu Start |

Dołączone są też zipy (`POTA-Upload-Helper-macOS.zip` / `POTA-Upload-Helper-Windows.zip`); aktualizator w aplikacji z nich korzysta, nie usuwaj ich z wydania.

Aplikacja nie jest podpisana, więc pierwsze uruchomienie pokaże ostrzeżenie.

- **macOS**: kliknij aplikację prawym przyciskiem → Otwórz → Otwórz. Jeśli nadal odmawia, Ustawienia systemowe → Prywatność i ochrona → „Otwórz mimo to” na dole.
- **Windows**: „System Windows ochronił ten komputer” → Więcej informacji → Uruchom mimo to.

**Potem aplikacja aktualizuje się sama.** Sprawdza przy starcie; gdy pasek boczny pokaże „Dostępna jest v1.x.x”, naciśnij „Aktualizuj teraz”: pobranie, podmiana, ponowne uruchomienie. „Sprawdź aktualizacje” działa w każdej chwili. Jeśli uruchamiasz aplikację prosto z DMG (bez przeniesienia do `Applications`), macOS nie pozwala na podmianę i nowa aplikacja trafia do folderu Pobrane.

## Połączenie z logiem

Utwórz odbiorniki w „Połączenie z logiem” (ile chcesz). **Zadziała każdy program, który wysyła QSO przez UDP.** W programie otwórz ustawienie „wysyłaj QSO przez UDP”, wskaż `127.0.0.1` i port odbiornika. Aplikacja rozpoznaje format każdego pakietu.

![Połączenie z logiem](docs/settings.png)

| Format | Programy | Gdzie |
|---|---|---|
| N1MM (XML contactinfo) | RUMlogNG, N1MM Logger+, DXLog, Win-Test | RUMlogNG: Preferences → UDP, Contact info jako N1MM. N1MM Logger+: Config → Broadcast Data → Contacts |
| WSJT-X | WSJT-X, JTDX | Settings → Reporting, UDP Server. Z `224.0.0.1` (multicast) inne programy odbierają równocześnie |
| ADIF | JTAlert, GridTracker, Log4OM… | ustawienie „wysyłaj ADIF przez UDP” programu |

**Wysyłać mogą tylko programy logujące z tego samego komputera.** Odbiorniki nasłuchują na `127.0.0.1`; log na innym PC do nich nie dotrze.

**Multicast WSJT-X / JTDX w Windows**: w Windows odbiornik multicast także nasłuchuje na loopback (`127.0.0.1`). W WSJT-X, Settings → Reporting → **Outgoing interfaces**, zaznacz **loopback**. Ta konfiguracja została sprawdzona w Windows 11; jeśli nic nie dociera, zgłoś [issue](../../issues). Ustawienie UDP Server WSJT-X na `127.0.0.1` (bez multicastu) działa zawsze, ale wtedy inne programy nie odbierają równocześnie.

Aby przekazać te same dane innemu programowi (OpsLog…), wpisz jego adres i port w „Przekaż do”.

**Dwa włączone odbiorniki niczego nie dublują**: QSO z WSJT-X przychodzi dwa razy, z WSJT-X i z logu, który je odebrał (około minuty różnicy: czas początku i końca). Ten sam znak, to samo pasmo, mniej niż 3 minuty = jedna łączność; decyzje P2P i usunięcia dotyczą obu. Druga strona medalu: dwie łączności z tą samą stacją na tym samym paśmie w ciągu 3 minut też stają się jedną.

## Dane

| System | Miejsce |
|---|---|
| macOS | `~/Library/Application Support/POTA Upload Helper/` |
| Windows | `%APPDATA%\POTA Upload Helper\` |

`qsolog.db` (odebrane QSO), `spots-YYYYMMDD.jsonl` (spoty), `sessions.json` (twoje aktywacje i parki), `hunter.json` (kopia logu huntera), `settings.json`.
Publiczny profil pota.app pokazuje tylko 25 ostatnich QSO huntera; aplikacja dopisuje do `hunter.json` podczas zapisu i przy każdym budowaniu, by zachować historię.

## Języki

日本語, English, 简体中文, 繁體中文, Français, Deutsch, Español, Italiano, Português (Brasil), 한국어, Polski. Wybierany według języka systemu, do zmiany w „Język” na pasku bocznym.

## Warunki użytkowania i wyłączenie odpowiedzialności

Hobbystyczne oprogramowanie osoby prywatnej, dostarczane tak jak jest. **Autor nie ponosi odpowiedzialności za żadne szkody wynikłe z użytkowania** (błędne wysyłki do pota.app, zdublowane lub brakujące QSO, utrata logów lub plików, wpływ na program logujący lub sieć). Zawsze sprawdzaj pliki przed wysłaniem. Wykrywanie P2P i 2fer to szacunek bez gwarancji. Brak powiązań z Parks on the Air® i pota.app. Pełny tekst w [TERMS.md](TERMS.md), pokazywany też przy pierwszym uruchomieniu.

Zgłoszenia bezpieczeństwa: zobacz [SECURITY.md](SECURITY.md).

## Uruchomienie ze źródeł

```sh
pip install -r requirements.txt
python3 app.py
```

Narzędzia wiersza poleceń działają samodzielnie (tylko biblioteka standardowa).

```sh
python3 pota_spotlog.py --parks JP-1266,JP-1206
python3 pota_build.py export.adif --date 20261020
```

## Rozwój

```sh
scripts/dev.sh                                  # tworzy venv i uruchamia z danymi w ./data (nigdy twój prawdziwy log)
scripts/dev.sh --debug                          # z inspektorem WebKit
scripts/send_test_qso.py 22237 JS6UHQ/6         # testowe QSO do odbiornika deweloperskiego (nigdy na 2237)
python3 -m unittest discover -s tests
```

Podnieś `VERSION` w `potacommon.py` i wypchnij na `main`: GitHub Actions zbuduje macOS i Windows i dołączy je do wydania `v<VERSION>`. Struktura i decyzje projektowe: [CLAUDE.md](CLAUDE.md).

## License

MIT
