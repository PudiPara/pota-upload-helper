# POTA Upload Helper

[日本語](README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [한국어](README.ko.md) · [Polski](README.pl.md)

Un’app desktop per gli attivatori POTA (Parks on the Air) che aiuta da quando vai in aria fino all’upload. Funziona su macOS e Windows.

In FT8 non puoi sapere se l’altra stazione è in un parco, figuriamoci se è un 2fer. Questa app registra gli spot di pota.app mentre attivi, li confronta con i QSO che il tuo programma di log invia e **propone P2P (parco a parco) e 2fer, che tu confermi e registri**. Alla fine scrive un file per parco e giorno UTC, pronto da caricare su pota.app.

![In attivazione](docs/live.png)

## Cosa fa

- **Modalità barra durante l’attivazione**: digita il parco, avvia la registrazione e la finestra diventa una striscia che resta sopra il log (il tuo parco, il tempo, i QSO, gli ultimi QSO). «Espandi» la riporta grande. Le stazioni spottate dai parchi vengono annotate ogni minuto, così si giudicano anche dopo il loro QRT.
- **Attivi adesso**: anche senza registrare, l’elenco delle stazioni in aria dai parchi, dagli spot di pota.app (ogni minuto). Filtri: regione (Giappone / mondo), banda, modo (CW / Phone / Data), nominativo o parco, solo 2fer.
- **QSO dal tuo log**: via UDP come OpsLog o JTAlert. Formato N1MM (RUMlogNG, N1MM Logger+, DXLog…), WSJT-X / JTDX (multicast), ADIF (JTAlert, GridTracker, Log4OM…). Correzioni e cancellazioni nel log vengono riportate.
- **P2P confermato subito**: se l’altra stazione è stata spottata da un parco, la riga mostra «Possibile P2P» con il riferimento; rispondi sì o no. Se non è negli spot (fonia o CW, quando ti dicono il parco), digita il riferimento nella riga. Niente diventa P2P da solo.
- **10 QSO**: un banner a tutto schermo quando l’attivazione è completata.
- **Termina scrive il file**: «Termina questo parco» scrive il file di upload del parco e del giorno (`JL1FVA@JP-1266-20261020.adi`) e torna all’inizio. Al parco successivo basta digitarne il riferimento. Il loro 2fer → il QSO ripetuto per parco; il tuo 2fer → un file per parco.
- **Inoltro**: i pacchetti ricevuti possono essere passati così come sono a un altro programma (RUMlog → questa app → OpsLog).
- **Rigenera**: la scheda «File di upload» crea i file dei giorni passati dal log dell’app o dall’ADIF esportato dal log.

![File di upload](docs/build.png)

Il parco dell’altra stazione è deciso in quest’ordine:

1. **Log hunter di pota.app** (ciò che ha caricato = verificato), confrontato a ±5 minuti sulla stessa banda
2. **Ciò che hai confermato o digitato durante l’attivazione** (generando dal log dell’app). I QSO non confermati non sono P2P
3. **Spot registrati durante l’attivazione** (solo generando da un file ADIF; spot da 30 minuti prima a 10 dopo il QSO)
4. SIG_INFO / POTA_REF dal log

Si usa solo l’API pubblica (api.pota.app), senza login. Il log resta nel tuo programma: questa app giudica e scrive i file di upload, non modifica mai il log.

## Download

Prendi l’ultima versione da [Releases](../../releases).

| SO | File | Come |
|---|---|---|
| macOS (Apple Silicon) | `POTA-Upload-Helper-macOS.dmg` | Aprilo e trascina `POTA Upload Helper` in `Applications` |
| Windows 10 / 11 | `POTA-Upload-Helper-Setup.exe` | Installa per utente (senza diritti di amministratore) e aggiunge una voce al menu Start |

Sono allegati anche gli zip (`POTA-Upload-Helper-macOS.zip` / `POTA-Upload-Helper-Windows.zip`); l’aggiornamento interno li usa, non cancellarli da una Release.

L’app non è firmata: al primo avvio compare un avviso.

- **macOS**: clic destro sull’app → Apri → Apri. Se rifiuta ancora, Impostazioni di Sistema → Privacy e sicurezza → «Apri comunque» in basso.
- **Windows**: «PC protetto da Windows» → Ulteriori informazioni → Esegui comunque.

**Da lì in poi l’app si aggiorna da sola.** Controlla all’avvio; quando la barra laterale dice «v1.x.x è disponibile», premi «Aggiorna ora»: scarica, sostituisce e riavvia. «Cerca aggiornamenti» lo fa in qualsiasi momento. Se esegui l’app direttamente dal DMG (senza spostarla in `Applications`), macOS impedisce la sostituzione e la nuova app viene messa in Download.

## Collegamento al log

Crea ascolti in «Collegamento al log» (quanti vuoi). **Va bene qualsiasi programma che invii i QSO via UDP.** Nel programma apri l’impostazione «invia QSO via UDP», punta a `127.0.0.1` e alla porta di un ascolto. L’app riconosce il formato di ogni pacchetto.

![Collegamento al log](docs/settings.png)

| Formato | Programmi | Dove |
|---|---|---|
| N1MM (XML contactinfo) | RUMlogNG, N1MM Logger+, DXLog, Win-Test | RUMlogNG: Preferences → UDP, Contact info su N1MM. N1MM Logger+: Config → Broadcast Data → Contacts |
| WSJT-X | WSJT-X, JTDX | Settings → Reporting, UDP Server. Con `224.0.0.1` (multicast) altri programmi ricevono insieme |
| ADIF | JTAlert, GridTracker, Log4OM… | l’impostazione «invia ADIF via UDP» del programma |

**Possono inviare solo i programmi di log dello stesso computer.** Gli ascolti stanno su `127.0.0.1`; un log su un altro PC non li raggiunge.

**Multicast di WSJT-X / JTDX su Windows**: su Windows anche l’ascolto multicast sta su loopback (`127.0.0.1`). In WSJT-X, Settings → Reporting → **Outgoing interfaces**, includi **loopback**. Questa configurazione è stata verificata su Windows 11; se non arriva nulla, apri una [issue](../../issues). Impostare l’UDP Server di WSJT-X su `127.0.0.1` (senza multicast) funziona sempre, ma allora gli altri programmi non ricevono insieme.

Per passare gli stessi dati a un altro programma (OpsLog…), inserisci il suo indirizzo e porta in «Inoltra a».

**Due ascolti attivi non raddoppiano nulla**: un QSO di WSJT-X arriva due volte, da WSJT-X e dal log che l’ha ricevuto (circa un minuto di differenza: ora di inizio e di fine). Stesso nominativo, stessa banda, meno di 3 minuti = un solo collegamento; decisioni P2P e cancellazioni valgono per entrambi. Rovescio: due collegamenti con la stessa stazione sulla stessa banda entro 3 minuti diventano uno.

## Dati

| SO | Posizione |
|---|---|
| macOS | `~/Library/Application Support/POTA Upload Helper/` |
| Windows | `%APPDATA%\POTA Upload Helper\` |

`qsolog.db` (QSO ricevuti), `spots-YYYYMMDD.jsonl` (spot), `sessions.json` (le tue attivazioni e parchi), `hunter.json` (copia del log hunter), `settings.json`.
Il profilo pubblico di pota.app mostra solo gli ultimi 25 QSO hunter; l’app aggiunge a `hunter.json` durante la registrazione e a ogni generazione per conservare lo storico.

## Lingue

日本語, English, 简体中文, 繁體中文, Français, Deutsch, Español, Italiano, Português (Brasil), 한국어, Polski. Scelta dalla lingua di sistema, modificabile in «Lingua» nella barra laterale.

## Condizioni d’uso ed esclusione di responsabilità

Software amatoriale di un privato, così com’è. **L’autore non risponde di alcun danno derivante dall’uso** (upload errati su pota.app, QSO duplicati o mancanti, perdita di log o file, effetti sul log o sulla rete). Controlla sempre i file prima di caricarli. Il riconoscimento di P2P e 2fer è una stima senza garanzie. Nessun legame con Parks on the Air® o pota.app. Testo completo in [TERMS.md](TERMS.md), mostrato anche al primo avvio.

Segnalazioni di sicurezza: vedi [SECURITY.md](SECURITY.md).

## Avvio dai sorgenti

```sh
pip install -r requirements.txt
python3 app.py
```

Gli strumenti a riga di comando funzionano da soli (solo libreria standard).

```sh
python3 pota_spotlog.py --parks JP-1266,JP-1206
python3 pota_build.py export.adif --date 20261020
```

## Sviluppo

```sh
scripts/dev.sh                                  # crea un venv e avvia con i dati in ./data (mai il tuo log vero)
scripts/dev.sh --debug                          # con l’ispettore WebKit
scripts/send_test_qso.py 22237 JS6UHQ/6         # invia un QSO di prova a un ascolto di sviluppo (mai a 2237)
python3 -m unittest discover -s tests
```

Alza `VERSION` in `potacommon.py` e fai push su `main`: GitHub Actions compila macOS e Windows e li allega alla Release `v<VERSION>`. Struttura e decisioni di progetto: [CLAUDE.md](CLAUDE.md).

## License

MIT
