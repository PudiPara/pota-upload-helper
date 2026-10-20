# POTA Upload Helper

[日本語](README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [한국어](README.ko.md) · [Polski](README.pl.md)

Una app de escritorio para activadores POTA (Parks on the Air) que ayuda desde que sales al aire hasta la subida. Funciona en macOS y Windows.

En FT8 no puedes saber si la otra estación está en un parque, y menos si es un 2fer. Esta app graba los spots de pota.app mientras activas, los cruza con los QSO que envía tu programa de log y **propone P2P (parque a parque) y 2fer para que tú los confirmes y guardes**. Al terminar, escribe un archivo por parque y día UTC listo para subir a pota.app.

![En activación](docs/live.png)

## Qué hace

- **Modo barra mientras activas**: escribe tu parque, empieza a grabar y la ventana se convierte en una franja pequeña que queda sobre el log (tu parque, tiempo, QSO, últimos QSO). «Ampliar» la devuelve. Las estaciones spoteadas desde parques se anotan cada minuto, así se pueden juzgar aunque hagan QRT.
- **Activando ahora**: aun sin grabar, una lista de las estaciones que están en el aire desde parques, según los spots de pota.app (cada minuto). Filtros: región (Japón / mundo), banda, modo (CW / Phone / Data), indicativo o parque, solo 2fer.
- **QSO desde tu log**: por UDP como OpsLog o JTAlert. Formato N1MM (RUMlogNG, N1MM Logger+, DXLog…), WSJT-X / JTDX (multicast), ADIF (JTAlert, GridTracker, Log4OM…). Las correcciones y borrados en el log se reflejan.
- **P2P confirmado al momento**: si la otra estación fue spoteada desde un parque, la fila muestra «Posible P2P» con la referencia; responde sí o no. Si no está en los spots (fonía o CW, cuando te dicen el parque), escribe la referencia en la fila. Nada pasa a P2P solo.
- **10 QSO**: un cartel a pantalla completa cuando la activación se completa.
- **Terminar escribe el archivo**: «Terminar este parque» escribe el archivo de subida del parque y el día (`JL1FVA@JP-1266-20261020.adi`) y vuelve a la pantalla inicial. En el siguiente parque, solo escribe su referencia. Su 2fer → el QSO repetido por parque; tu 2fer → un archivo por parque.
- **Reenvío**: los paquetes recibidos se pueden pasar tal cual a otro programa (RUMlog → esta app → OpsLog).
- **Regenerar**: la pestaña «Archivos de subida» genera archivos de días pasados desde el log de la app o desde el ADIF exportado del log.

![Archivos de subida](docs/build.png)

El parque de la otra estación se decide en este orden:

1. **Log de cazador de pota.app** (lo que subió = verificado), cruzado a ±5 minutos en la misma banda
2. **Lo que confirmaste o escribiste al activar** (al generar desde el log de la app). Los QSO sin confirmar no son P2P
3. **Spots grabados al activar** (solo al generar desde un ADIF; spots desde 30 minutos antes hasta 10 después del QSO)
4. SIG_INFO / POTA_REF del log

Solo se usa la API pública (api.pota.app), sin iniciar sesión. El log se queda en tu programa de log: esta app solo juzga y escribe archivos de subida, nunca modifica el log.

## Descarga

Coge la última versión en [Releases](../../releases).

| SO | Archivo | Cómo |
|---|---|---|
| macOS (Apple Silicon) | `POTA-Upload-Helper-macOS.dmg` | Ábrelo y arrastra `POTA Upload Helper` a `Applications` |
| Windows 10 / 11 | `POTA-Upload-Helper-Setup.exe` | Instala por usuario (sin permisos de administrador) y crea una entrada en el menú Inicio |

También se adjuntan los zip (`POTA-Upload-Helper-macOS.zip` / `POTA-Upload-Helper-Windows.zip`); la actualización interna los usa, no los borres de una Release.

La app no está firmada, así que la primera vez aparece un aviso.

- **macOS**: clic derecho en la app → Abrir → Abrir. Si sigue sin abrir, Ajustes del Sistema → Privacidad y seguridad → «Abrir de todos modos» abajo.
- **Windows**: «Windows protegió tu PC» → Más información → Ejecutar de todas formas.

**A partir de ahí la app se actualiza sola.** Comprueba al arrancar; cuando la barra lateral diga «v1.x.x está disponible», pulsa «Actualizar ahora»: descarga, reemplaza y reinicia. «Buscar actualizaciones» lo hace en cualquier momento. Si ejecutas la app desde el DMG (sin moverla a `Applications`), macOS impide el reemplazo y la nueva app se deja en Descargas.

## Enlace con el log

Crea entradas en «Enlace con el log» (las que quieras). **Sirve cualquier programa que envíe sus QSO por UDP.** En el programa, abre la opción «enviar QSO por UDP», apunta a `127.0.0.1` y al puerto de una entrada. La app reconoce el formato de cada paquete.

![Enlace con el log](docs/settings.png)

| Formato | Programas | Dónde |
|---|---|---|
| N1MM (XML contactinfo) | RUMlogNG, N1MM Logger+, DXLog, Win-Test | RUMlogNG: Preferences → UDP, Contact info en N1MM. N1MM Logger+: Config → Broadcast Data → Contacts |
| WSJT-X | WSJT-X, JTDX | Settings → Reporting, UDP Server. Con `224.0.0.1` (multicast) otros programas reciben a la vez |
| ADIF | JTAlert, GridTracker, Log4OM… | la opción «enviar ADIF por UDP» del programa |

**Solo los programas de log del mismo ordenador pueden enviar.** Las entradas escuchan en `127.0.0.1`; un log en otro PC no las alcanza.

**Multicast de WSJT-X / JTDX en Windows**: en Windows la entrada multicast también escucha en loopback (`127.0.0.1`). En WSJT-X, Settings → Reporting → **Outgoing interfaces**, incluye **loopback**. Esta configuración se ha comprobado en Windows 11; si no llega nada, abre un [issue](../../issues). Poner el UDP Server de WSJT-X en `127.0.0.1` (sin multicast) siempre funciona, pero entonces otros programas no pueden recibir a la vez.

Para pasar los mismos datos a otro programa (OpsLog…), pon su dirección y puerto en «Reenviar a».

**Dos entradas activas no duplican nada**: un QSO de WSJT-X llega dos veces, de WSJT-X y del log que lo recibió (con un minuto de diferencia: hora de inicio y de fin). Mismo indicativo, misma banda, menos de 3 minutos = un solo contacto; las decisiones P2P y los borrados se aplican a ambos. A cambio, dos contactos con la misma estación en la misma banda en menos de 3 minutos también se funden en uno.

## Datos

| SO | Ubicación |
|---|---|
| macOS | `~/Library/Application Support/POTA Upload Helper/` |
| Windows | `%APPDATA%\POTA Upload Helper\` |

`qsolog.db` (QSO recibidos), `spots-YYYYMMDD.jsonl` (spots), `sessions.json` (tus activaciones y parques), `hunter.json` (copia del log de cazador), `settings.json`.
El perfil público de pota.app solo muestra los últimos 25 QSO de cazador; la app añade a `hunter.json` mientras graba y en cada generación para conservar el historial.

## Idiomas

日本語, English, 简体中文, 繁體中文, Français, Deutsch, Español, Italiano, Português (Brasil), 한국어, Polski. Se elige según el idioma del sistema y se cambia en «Idioma» en la barra lateral.

## Condiciones de uso y exención de responsabilidad

Software de aficionado de un particular, tal cual. **El autor no se hace responsable de ningún daño derivado de su uso** (subidas erróneas a pota.app, QSO duplicados o perdidos, pérdida de logs o archivos, efectos en el log o la red). Revisa siempre los archivos antes de subirlos. La detección de P2P y 2fer es una estimación sin garantía. Sin relación con Parks on the Air® ni pota.app. Texto completo en [TERMS.md](TERMS.md), mostrado también al primer arranque.

Avisos de seguridad: ver [SECURITY.md](SECURITY.md).

## Ejecutar desde el código fuente

```sh
pip install -r requirements.txt
python3 app.py
```

Las herramientas de línea de comandos funcionan solas (solo biblioteca estándar).

```sh
python3 pota_spotlog.py --parks JP-1266,JP-1206
python3 pota_build.py export.adif --date 20261020
```

## Desarrollo

```sh
scripts/dev.sh                                  # crea un venv y arranca con datos en ./data (nunca tu log real)
scripts/dev.sh --debug                          # con el inspector de WebKit
scripts/send_test_qso.py 22237 JS6UHQ/6         # envía un QSO de prueba a una entrada de desarrollo (nunca a 2237)
python3 -m unittest discover -s tests
```

Sube `VERSION` en `potacommon.py` y haz push a `main`: GitHub Actions compila macOS y Windows y los adjunta a la Release `v<VERSION>`. Estructura y decisiones de diseño: [CLAUDE.md](CLAUDE.md).

## License

MIT
