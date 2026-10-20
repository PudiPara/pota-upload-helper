# POTA Upload Helper

[日本語](README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [한국어](README.ko.md) · [Polski](README.pl.md)

Une application de bureau pour les activateurs POTA (Parks on the Air), qui aide du début de l’activation jusqu’à l’envoi. Fonctionne sous macOS et Windows.

En FT8, impossible de savoir sur le moment si la station en face est dans un parc, et encore moins si c’est un 2fer. Cette application enregistre les spots pota.app pendant l’activation, les confronte aux QSO envoyés par votre logger et **propose le P2P (parc à parc) et le 2fer, que vous confirmez et enregistrez**. À la fin, elle écrit un fichier par parc et par jour UTC, prêt à être envoyé sur pota.app.

![En activation](docs/live.png)

## Ce qu’elle fait

- **Mode barre pendant l’activation** : saisissez votre parc, démarrez l’enregistrement, et la fenêtre devient une petite barre qui reste au-dessus du logger (votre parc, le temps écoulé, le nombre de QSO, les derniers QSO). « Agrandir » la ramène. Les stations spottées depuis des parcs sont notées chaque minute, donc jugeables même après leur QRT.
- **Activations en cours** : même sans enregistrer, la liste des stations actuellement en l’air depuis un parc, d’après les spots pota.app (actualisée chaque minute). Filtres : pays (avec drapeau) et région, bande, mode (CW / Phone / Data), indicatif ou parc, 2fer seulement.
- **QSO depuis votre logger** : reçus en UDP comme OpsLog ou JTAlert. Format N1MM (RUMlogNG, N1MM Logger+, DXLog…), WSJT-X / JTDX (multicast pris en charge), ADIF (JTAlert, GridTracker, Log4OM…). Les corrections et suppressions dans le logger sont reprises.
- **P2P confirmé sur le moment** : si la station en face a été spottée depuis un parc, la ligne affiche « P2P possible » avec la référence ; répondez oui ou non. Pour une station absente des spots (en phonie ou CW, quand elle vous donne son parc), tapez la référence dans la ligne. Rien ne devient P2P tout seul.
- **10 QSO** : une bannière plein écran au moment où l’activation est validée.
- **Terminer écrit le fichier** : « Terminer ce parc » écrit le ou les fichiers d’envoi du parc et du jour (`JL1FVA@JP-1266-20261020.adi`) et revient à la saisie du parc. Au parc suivant, tapez juste sa référence. Leur 2fer → le QSO répété par parc ; votre 2fer → un fichier par parc.
- **Relais** : les paquets reçus peuvent être retransmis tels quels à un autre programme (RUMlog → cette application → OpsLog).
- **Régénérer** : l’onglet « Fichiers d’envoi » construit les fichiers des jours passés à partir du journal de l’application ou de l’export ADIF du logger.

![Fichiers d’envoi](docs/build.png)

Le parc de la station en face est déterminé dans cet ordre :

1. **Journal chasseur pota.app** (ce qu’elle a envoyé = vérifié), rapproché à ±5 minutes sur la même bande
2. **Ce que vous avez confirmé ou saisi pendant l’activation** (génération depuis le journal de l’application). Les QSO non confirmés ne sont pas P2P
3. **Spots enregistrés pendant l’activation** (seulement depuis un fichier ADIF ; spots de 30 minutes avant à 10 minutes après le QSO)
4. SIG_INFO / POTA_REF du logger

Seule l’API publique (api.pota.app) est utilisée, sans connexion. Le journal reste dans votre logger : l’application juge et écrit les fichiers d’envoi, elle ne modifie jamais le journal du logger.

## Téléchargement

Prenez la dernière version dans [Releases](../../releases).

| OS | Fichier | Comment |
|---|---|---|
| macOS (Apple Silicon) | `POTA-Upload-Helper-macOS.dmg` | Ouvrez-le et glissez `POTA Upload Helper` dans `Applications` |
| Windows 10 / 11 | `POTA-Upload-Helper-Setup.exe` | Installe pour l’utilisateur (sans droits admin) et ajoute une entrée au menu Démarrer |

Les zips (`POTA-Upload-Helper-macOS.zip` / `POTA-Upload-Helper-Windows.zip`) sont joints aussi ; la mise à jour intégrée les utilise, ne les supprimez pas d’une Release.

L’application n’est pas signée : le premier lancement affiche un avertissement.

- **macOS** : clic droit sur l’application → Ouvrir → Ouvrir. Si elle refuse encore, Réglages Système → Confidentialité et sécurité → « Ouvrir quand même » en bas.
- **Windows** : « Windows a protégé votre ordinateur » → Informations complémentaires → Exécuter quand même.

**Ensuite l’application se met à jour elle-même.** Elle vérifie au démarrage ; quand la barre latérale annonce « v1.x.x est disponible », appuyez sur « Mettre à jour » : téléchargement, remplacement, redémarrage. « Rechercher une mise à jour » le fait à tout moment. Si vous lancez l’application directement depuis le DMG (sans la déplacer dans `Applications`), macOS empêche le remplacement sur place : la nouvelle version est alors déposée dans Téléchargements.

## Lien avec le logger

Créez des entrées dans « Lien avec le logger » (autant que vous voulez). **Tout logger capable d’envoyer ses QSO en UDP convient.** Dans le logger, ouvrez le réglage « envoyer les QSO en UDP », visez `127.0.0.1` et le port d’une entrée. L’application reconnaît le format de chaque paquet.

![Lien avec le logger](docs/settings.png)

| Format | Loggers | Où régler |
|---|---|---|
| N1MM (XML contactinfo) | RUMlogNG, N1MM Logger+, DXLog, Win-Test | RUMlogNG : Preferences → UDP, Contact info en N1MM. N1MM Logger+ : Config → Broadcast Data → Contacts |
| WSJT-X | WSJT-X, JTDX | Settings → Reporting, UDP Server. `224.0.0.1` (multicast) permet à d’autres programmes de recevoir en même temps |
| ADIF | JTAlert, GridTracker, Log4OM… | le réglage « envoyer l’ADIF en UDP » du programme |

**Seuls les loggers du même ordinateur peuvent envoyer.** Les entrées écoutent sur `127.0.0.1` ; un logger sur un autre PC ne peut pas les atteindre.

**Multicast WSJT-X / JTDX sous Windows** : sous Windows, l’entrée multicast écoute aussi sur la boucle locale (`127.0.0.1`). Dans WSJT-X, Settings → Reporting → **Outgoing interfaces**, incluez **loopback**. Cette configuration a été vérifiée sous Windows 11 ; si rien n’arrive, ouvrez une [issue](../../issues). Mettre l’UDP Server de WSJT-X sur `127.0.0.1` (sans multicast) fonctionne toujours, mais les autres programmes ne peuvent alors pas recevoir en même temps.

Pour transmettre les mêmes données à un autre programme (OpsLog…), indiquez son adresse et son port dans « Relayer vers ».

**Deux entrées actives ne doublent rien** : un QSO WSJT-X arrive deux fois, de WSJT-X puis du logger qui l’a reçu (environ une minute d’écart : heure de début contre heure de fin). Même indicatif, même bande, moins de 3 minutes = un seul contact ; décisions P2P et suppressions s’appliquent aux deux. Revers : deux contacts avec la même station sur la même bande en moins de 3 minutes n’en font qu’un.

## Données

| OS | Emplacement |
|---|---|
| macOS | `~/Library/Application Support/POTA Upload Helper/` |
| Windows | `%APPDATA%\POTA Upload Helper\` |

`qsolog.db` (QSO reçus), `spots-YYYYMMDD.jsonl` (spots), `sessions.json` (vos créneaux d’activation et parcs), `hunter.json` (copie du journal chasseur), `settings.json`.
Le profil public pota.app ne montre que les 25 derniers QSO chasseur ; l’application complète `hunter.json` pendant l’enregistrement et à chaque génération pour garder l’historique.

## Langues

日本語, English, 简体中文, 繁體中文, Français, Deutsch, Español, Italiano, Português (Brasil), 한국어, Polski. Choisie d’après la langue du système, modifiable sous « Langue » dans les réglages.

## Conditions d’utilisation et non-responsabilité

Logiciel amateur d’un particulier, fourni tel quel. **L’auteur décline toute responsabilité pour tout dommage lié à son utilisation** (envoi erroné à pota.app, QSO en double ou manquants, perte de journaux ou de fichiers, effets sur le logger ou les réglages réseau). Vérifiez toujours les fichiers avant de les envoyer. La détection P2P et 2fer est une estimation, sans garantie. Sans lien avec Parks on the Air® ni pota.app. Texte complet dans [TERMS.md](TERMS.md), affiché aussi au premier lancement.

Signalement de sécurité : voir [SECURITY.md](SECURITY.md).

## Lancer depuis les sources

```sh
pip install -r requirements.txt
python3 app.py
```

Les outils en ligne de commande fonctionnent seuls (bibliothèque standard uniquement).

```sh
python3 pota_spotlog.py --parks JP-1266,JP-1206
python3 pota_build.py export.adif --date 20261020
```

## Développement

```sh
scripts/dev.sh                                  # crée un venv et lance avec les données dans ./data (jamais votre vrai journal)
scripts/dev.sh --debug                          # avec l’inspecteur WebKit
scripts/send_test_qso.py 22237 JS6UHQ/6         # envoie un QSO de test à une entrée de dev (jamais sur 2237)
python3 -m unittest discover -s tests
```

Augmentez `VERSION` dans `potacommon.py` et poussez sur `main` : GitHub Actions construit macOS et Windows et les joint à la Release `v<VERSION>`. Structure et décisions de conception : [CLAUDE.md](CLAUDE.md).

## License

MIT

Country flags are drawn with the flags-only font from [country-flag-emoji-polyfill](https://github.com/talkjs/country-flag-emoji-polyfill) (MIT), built from Twemoji (CC-BY 4.0).
