# POTA Upload Helper

[日本語](README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [한국어](README.ko.md) · [Polski](README.pl.md)

Um app de desktop para ativadores POTA (Parks on the Air) que ajuda desde a hora de ir ao ar até o upload. Funciona em macOS e Windows.

Em FT8 você não sabe se a outra estação está num parque, muito menos se é um 2fer. Este app grava os spots do pota.app enquanto você ativa, cruza com os QSOs que seu programa de log envia e **sugere P2P (parque a parque) e 2fer para você confirmar e gravar**. Ao terminar, escreve um arquivo por parque e dia UTC, pronto para subir no pota.app.

![Em ativação](docs/live.png)

## O que faz

- **Modo barra durante a ativação**: digite o parque, comece a gravar e a janela vira uma faixa pequena que fica sobre o log (seu parque, tempo, QSOs, últimos QSOs). «Expandir» traz de volta. Estações spotadas de parques são anotadas a cada minuto, então dá para julgar mesmo depois do QRT.
- **Ativando agora**: mesmo sem gravar, uma lista das estações no ar de parques, dos spots do pota.app (a cada minuto). Filtros: região (Japão / mundo), banda, modo (CW / Phone / Data), indicativo ou parque, só 2fer.
- **QSOs do seu log**: por UDP como OpsLog ou JTAlert. Formato N1MM (RUMlogNG, N1MM Logger+, DXLog…), WSJT-X / JTDX (multicast), ADIF (JTAlert, GridTracker, Log4OM…). Correções e exclusões no log são refletidas.
- **P2P confirmado na hora**: se a outra estação foi spotada de um parque, a linha mostra «Possível P2P» com a referência; responda sim ou não. Se não está nos spots (fonia ou CW, quando te falam o parque), digite a referência na linha. Nada vira P2P sozinho.
- **10 QSOs**: um banner em tela cheia quando a ativação é concluída.
- **Encerrar grava o arquivo**: «Encerrar este parque» grava o arquivo de upload do parque e do dia (`JL1FVA@JP-1266-20261020.adi`) e volta à tela inicial. No próximo parque, só digite a referência. O 2fer deles → o QSO repetido por parque; o seu 2fer → um arquivo por parque.
- **Encaminhamento**: pacotes recebidos podem ser repassados sem alteração a outro programa (RUMlog → este app → OpsLog).
- **Gerar de novo**: a aba «Arquivos de upload» gera arquivos de dias passados a partir do log do app ou do ADIF exportado do log.

![Arquivos de upload](docs/build.png)

O parque da outra estação é decidido nesta ordem:

1. **Log de caçador do pota.app** (o que ela subiu = verificado), cruzado a ±5 minutos na mesma banda
2. **O que você confirmou ou digitou ao ativar** (ao gerar do log do app). QSOs sem confirmar não são P2P
3. **Spots gravados ao ativar** (só ao gerar de um ADIF; spots de 30 minutos antes até 10 depois do QSO)
4. SIG_INFO / POTA_REF do log

Só a API pública (api.pota.app) é usada, sem login. O log fica no seu programa de log: este app só julga e grava arquivos de upload, nunca altera o log.

## Download

Pegue a versão mais recente em [Releases](../../releases).

| SO | Arquivo | Como |
|---|---|---|
| macOS (Apple Silicon) | `POTA-Upload-Helper-macOS.dmg` | Abra e arraste `POTA Upload Helper` para `Applications` |
| Windows 10 / 11 | `POTA-Upload-Helper-Setup.exe` | Instala por usuário (sem administrador) e cria uma entrada no menu Iniciar |

Os zips (`POTA-Upload-Helper-macOS.zip` / `POTA-Upload-Helper-Windows.zip`) também vão anexados; o atualizador interno usa eles, não apague de uma Release.

O app não é assinado, então a primeira abertura mostra um aviso.

- **macOS**: clique direito no app → Abrir → Abrir. Se ainda recusar, Ajustes do Sistema → Privacidade e Segurança → «Abrir mesmo assim» embaixo.
- **Windows**: «O Windows protegeu o computador» → Mais informações → Executar mesmo assim.

**Daí em diante o app se atualiza sozinho.** Ele verifica ao iniciar; quando a barra lateral disser «v1.x.x está disponível», aperte «Atualizar agora»: baixa, substitui e reinicia. «Verificar atualizações» faz isso a qualquer hora. Se você roda o app direto do DMG (sem mover para `Applications`), o macOS impede a troca e o novo app fica na pasta Downloads.

## Conexão com o log

Crie entradas em «Conexão com o log» (quantas quiser). **Qualquer programa que envie QSOs por UDP serve.** No programa, abra a opção «enviar QSOs por UDP», aponte para `127.0.0.1` e para a porta de uma entrada. O app reconhece o formato de cada pacote.

![Conexão com o log](docs/settings.png)

| Formato | Programas | Onde |
|---|---|---|
| N1MM (XML contactinfo) | RUMlogNG, N1MM Logger+, DXLog, Win-Test | RUMlogNG: Preferences → UDP, Contact info em N1MM. N1MM Logger+: Config → Broadcast Data → Contacts |
| WSJT-X | WSJT-X, JTDX | Settings → Reporting, UDP Server. Com `224.0.0.1` (multicast) outros programas recebem junto |
| ADIF | JTAlert, GridTracker, Log4OM… | a opção «enviar ADIF por UDP» do programa |

Para repassar os mesmos dados a outro programa (OpsLog…), coloque o endereço e a porta dele em «Encaminhar para».

**Duas entradas ligadas não duplicam nada**: um QSO do WSJT-X chega duas vezes, do WSJT-X e do log que o recebeu (cerca de um minuto de diferença: hora de início e de fim). Mesmo indicativo, mesma banda, menos de 3 minutos = um só contato; decisões P2P e exclusões valem para os dois. Em contrapartida, dois contatos com a mesma estação na mesma banda em menos de 3 minutos também viram um.

## Dados

| SO | Local |
|---|---|
| macOS | `~/Library/Application Support/POTA Upload Helper/` |
| Windows | `%APPDATA%\POTA Upload Helper\` |

`qsolog.db` (QSOs recebidos), `spots-YYYYMMDD.jsonl` (spots), `sessions.json` (suas ativações e parques), `hunter.json` (cópia do log de caçador), `settings.json`.
O perfil público do pota.app mostra só os últimos 25 QSOs de caçador; o app acrescenta ao `hunter.json` durante a gravação e a cada geração para guardar o histórico.

## Idiomas

日本語, English, 简体中文, 繁體中文, Français, Deutsch, Español, Italiano, Português (Brasil), 한국어, Polski. Escolhido pelo idioma do sistema, trocável em «Idioma» na barra lateral.

## Termos de uso e isenção de responsabilidade

Software amador de uma pessoa, fornecido como está. **O autor não se responsabiliza por nenhum dano decorrente do uso** (uploads errados ao pota.app, QSOs duplicados ou perdidos, perda de logs ou arquivos, efeitos no log ou na rede). Sempre confira os arquivos antes de subir. A detecção de P2P e 2fer é uma estimativa sem garantia. Sem vínculo com Parks on the Air® ou pota.app. Texto completo em [TERMS.md](TERMS.md), mostrado também na primeira abertura.

Avisos de segurança: veja [SECURITY.md](SECURITY.md).

## Rodar do código-fonte

```sh
pip install -r requirements.txt
python3 app.py
```

As ferramentas de linha de comando funcionam sozinhas (só biblioteca padrão).

```sh
python3 pota_spotlog.py --parks JP-1266,JP-1206
python3 pota_build.py export.adif --date 20261020
```

## Desenvolvimento

```sh
scripts/dev.sh                                  # cria um venv e roda com dados em ./data (nunca seu log real)
scripts/dev.sh --debug                          # com o inspetor WebKit
scripts/send_test_qso.py 22237 JS6UHQ/6         # envia um QSO de teste a uma entrada de desenvolvimento (nunca para 2237)
python3 -m unittest discover -s tests
```

Suba `VERSION` em `potacommon.py` e faça push em `main`: o GitHub Actions compila macOS e Windows e anexa na Release `v<VERSION>`. Estrutura e decisões de projeto: [CLAUDE.md](CLAUDE.md).

## License

MIT
