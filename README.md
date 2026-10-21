# Potaroo

*旧名：POTA Upload Helper*

[日本語](README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [한국어](README.ko.md) · [Polski](README.pl.md)

POTA（Parks on the Air）のアクティベーションを、運用中からアップロードまで手伝うデスクトップアプリです。macOS と Windows で動きます。

FT8 などでは、相手が公園から運用しているのか、さらに 2fer なのかはその場では分かりません。このアプリは運用中に pota.app のスポットを記録し、ロガーから届いた QSO とその場で突き合わせて **P2P（Park to Park）と 2fer の候補を出し、あなたが確認して記録します**。運用を終えると、自分の公園ごと・UTC 日付ごとに pota.app へそのまま上げられるファイルを作ります。

![運用中の画面](docs/live.png)

## できること

- **運用中はバー表示**：公園番号を入れて記録を始めると、ウィンドウが小さな帯になってロガーの上に残ります（自分の公園、経過時間、QSO 数、直近の交信）。「広げる」で元の大きさに戻せます。公園から出ている局は 1 分ごとに記録するので、相手が QRT しても後から判定できます。
- **アクティベート中の局**：記録していないときでも、いま公園から出ている局を pota.app のスポットから一覧にします（1 分ごとに更新）。国（国旗つき）と地域、バンド、モード（CW／Phone／Data）、コールや公園番号の検索、2fer だけ、で絞れます。
- **ロガーから QSO を受信**：OpsLog や JTAlert と同じく UDP で受け取ります。N1MM 形式（RUMlogNG・N1MM Logger+・DXLog など）、WSJT-X / JTDX（マルチキャスト対応）、ADIF（JTAlert・GridTracker・Log4OM など）、QLog の QSO 変更通知。Windows では起動中の Turbo HAMLOG からも読み取ります。ロガーでの修正・削除も反映します。
- **P2P はその場で確認**：届いた QSO の相手が公園から出ていれば「P2P の可能性」と公園番号を出し、「はい」「いいえ」で決めます。スポットに出ていない相手（Phone や CW で公園番号を聞いたとき）は、その行に公園番号を直接入力します。勝手に P2P にはしません。
- **10 QSO で知らせる**：アクティベーション成立の瞬間に画面いっぱいに表示します。
- **終了でファイル作成**：「この公園での運用を終了」を押すと、その公園・その日のアップロード用ファイル（`JL1FVA@JP-1266-20261020.adi`）を保存先に書き、最初の画面に戻ります。次の公園に着いたら番号を入れるだけです。相手が 2fer なら QSO を公園の数だけ複製し、自分が 2fer なら公園ごとにファイルを分けます。
- **転送**：受け取ったデータをそのまま別のアプリへ流せます（RUMlog → このアプリ → OpsLog）。
- **作り直し**：「アップロード作成」タブでは、アプリのログやロガーの ADIF から過去の日付のファイルをまとめて作れます。

![アップロード作成](docs/build.png)

相手の公園は次の優先順で決めます。

1. **pota.app ハンターログ**（相手がアップロードした記録 = 確定）。時刻 ±5 分・同じバンドで照合
2. **運用中に確認・入力した公園**（アプリのログから作るとき）。確認していない QSO は P2P にしません
3. **運用中のスポット記録**（ADIF ファイルから作るときだけ。QSO の 30 分前〜10 分後のスポット）
4. ロガーの SIG_INFO / POTA_REF

使うのは公開 API（api.pota.app）だけで、ログインは不要です。ログの保管はロガーの仕事です。このアプリは判定とアップロード用ファイルの作成だけを受け持ち、ロガーのログは書き換えません。

## ダウンロード

[Releases](../../releases) から最新版を取ってください。

| OS | ファイル | 使い方 |
|---|---|---|
| macOS（Apple Silicon） | `Potaroo-macOS.dmg` | 開いて `Potaroo` を `Applications` にドラッグ |
| Windows 10 / 11 | `Potaroo-Setup.exe` | 実行するとユーザーごとの場所（管理者権限不要）にインストールされ、スタートメニューに入ります |

zip 版（`Potaroo-macOS.zip` / `Potaroo-Windows.zip`）も添付しています。アプリ内の更新はこの zip を使うので、Release からは消さないでください。

署名していないアプリなので、初回は警告が出ます。

- **macOS**：アプリを右クリック →「開く」→「開く」。開けないときは「システム設定 → プライバシーとセキュリティ」の下の方にある「このまま開く」
- **Windows**：「Windows によって PC が保護されました」→「詳細情報」→「実行」

**2 回目からはアプリの中で更新できます。** 起動時に新しい版があるかを確認し、左下に「v1.x.x が公開されています」と出たら「今すぐ更新」を押してください。ダウンロードして入れ替え、再起動します。確認はいつでも左下の「アップデートを確認」からできます。DMG の中のアプリをそのまま（`Applications` に入れずに）開いている場合は、macOS の仕組みで入れ替えができないので、新しいアプリを「ダウンロード」フォルダに置いて知らせます。

## ロガーとの接続

アプリの「ロガーとの接続」で受信口を作ります（いくつでも追加できます）。**QSO を UDP で送り出せるロガーなら使えます。** ロガー側で「QSO を UDP で送る」設定を開き、宛先を `127.0.0.1`、ポートを受信口と同じ番号にしてください。届いたパケットの形式はアプリが自動で判別します。

![ロガーとの接続](docs/settings.png)

| 形式 | ロガーの例 | 設定の場所 |
|---|---|---|
| N1MM（contactinfo XML） | RUMlogNG、N1MM Logger+、DXLog、Win-Test | RUMlogNG: Preferences → UDP の Contact info を N1MM に。N1MM Logger+: Config → Broadcast Data → Contacts |
| WSJT-X | WSJT-X、JTDX | Settings → Reporting の UDP Server。`224.0.0.1`（マルチキャスト）にすると他のアプリと同時に受け取れます |
| ADIF | JTAlert、GridTracker、Log4OM など | 各ソフトの「ADIF を UDP で送る」設定 |
| QLog（JSON） | QLog | Settings → Network → Notifications の **QSO Changes** に `127.0.0.1:ポート` |
| Turbo HAMLOG（Windows） | Turbo HAMLOG/Win | 受信口の種類を「Turbo HAMLOG」に。ポートは不要で、起動中の HAMLOG から読み取ります（JT_Linker・JT-Get's 経由の QSO も含む） |

ロガーで修正・削除した QSO もアプリに反映されます。Windows 11 で確認済みなのは WSJT-X、Log4OM 2、Turbo HAMLOG、QLog、N1MM Logger+ です（CW・SSB・FT8 の受信と修正・削除）。

**受け取れるのは同じパソコンのロガーからだけです。** 受信口は `127.0.0.1` で待ち受けるので、別のパソコンのロガーからは届きません。

**Windows で WSJT-X / JTDX のマルチキャストを使う場合**：Windows ではマルチキャストの受信口もループバック（`127.0.0.1`）で待ち受けます。WSJT-X の Settings → Reporting → **Outgoing interfaces** に **loopback** を含めてください。この組み合わせは Windows 11 で動作を確認しています。届かないときは [Issue](../../issues) で知らせてもらえると助かります。マルチキャストを使わず、WSJT-X の UDP Server を `127.0.0.1` にする方法なら確実に受け取れます（ただしその場合、ほかのアプリと同時には受け取れません）。

**WSJT-X と一緒に使うロガーの設定**（Windows 11 で確認。FT8 の途中に CW・SSB・FM を混ぜても、1 件ずつ正しく入ります）：

| ロガー | WSJT-X からの受け取り | アプリへの渡し方 |
|---|---|---|
| JT_Linker + Turbo HAMLOG | JT_Linker が WSJT-X のログファイルを見て HAMLOG に登録 | 受信口「Turbo HAMLOG」 |
| N1MM Logger+ | Config → Configure Ports → WSJT/JTDX Setup の Radio #1 を Enable（ユニキャストなら `127.0.0.1`、マルチキャストなら `224.0.0.1`、ポート 2237） | Broadcast Data → Contacts を `127.0.0.1:受信口のポート` |
| QLog | Settings → Network の Wsjtx Port 2237（マルチキャストなら Join Multicast をオンにして Multicast Address に `224.0.0.1`） | Notifications → QSO Changes を `127.0.0.1:受信口のポート` |

WSJT-X の QSO はアプリにも直接届き（WSJT-X の受信口）、ロガー経由の分と合わせて 1 件にまとまります。マルチキャストで複数のソフトに同時に配るときは、次の点に注意してください。

- **QLog と N1MM は、ほかのソフトより先に起動してください。** 2237 番をほかのソフトと共有する設定で開かないため、後から起動すると「使用中」になって受け取れません。
- **Turbo HAMLOG も 2237 番を開きます。** JT_Linker と併用すると HAMLOG が「2 回目の QSO」として登録を尋ねてくることがあります。そのときは「いいえ」にしてください。QLog・N1MM と同時には使えません（後から起動した HAMLOG がエラーになります）。

ほかのアプリ（OpsLog など）にも同じデータを渡したいときは、受信口の「転送先」にそのアプリのアドレスとポートを入れます。

**両方オンでも二重にはなりません**：WSJT-X の QSO は、WSJT-X から直接と、ロガーが受けて送り直した分の 2 回届きます（開始時刻と終了時刻で 1 分ほどずれます）。同じコール・同じバンドで時刻の差が 3 分以内なら同じ交信として 1 件にまとめ、P2P の判断や削除も両方に反映します。逆に、同じ局と同じバンドで 3 分以内に 2 回交信した場合も 1 件になります。

## データの保存場所

| OS | 場所 |
|---|---|
| macOS | `~/Library/Application Support/Potaroo/` |
| Windows | `%APPDATA%\Potaroo\` |

`qsolog.db`（受け取った QSO）、`spots-YYYYMMDD.jsonl`（スポット記録）、`sessions.json`（自分の運用時間と公園）、`hunter.json`（ハンターログの控え）、`settings.json`。
pota.app の公開プロフィールに出るハンターログは直近 25 件だけなので、記録中と作成のたびに `hunter.json` に追記して履歴を貯めます。

## 言語

日本語・English・简体中文・繁體中文・Français・Deutsch・Español・Italiano・Português (Brasil)・한국어・Polski。OS の言語に合わせて自動で選ばれ、「設定」の「言語」で切り替えられます。

## 利用規約・免責事項

このアプリは個人が趣味で作った無保証のソフトウェアです。**このアプリの使用によって生じたいかなる損害（pota.app へ誤った内容をアップロードしたこと、QSO の重複や欠落、ログやファイルの消失、ロガーやネットワーク設定への影響など）についても、作者は責任を負いません。** アップロードするファイルの内容は必ず自分で確認してください。P2P や 2fer の判定は推定で、正しさは保証されません。このアプリは Parks on the Air® および pota.app とは無関係です。全文は [TERMS.md](TERMS.md) にあり、アプリの初回起動時にも表示されます。

脆弱性の報告は [SECURITY.md](SECURITY.md) を見てください。

## ソースから動かす

```sh
pip install -r requirements.txt
python3 app.py
```

コマンドラインだけでも使えます（標準ライブラリのみ）。

```sh
python3 pota_spotlog.py --parks JP-1266,JP-1206
python3 pota_build.py export.adif --date 20261020
```

## 開発

```sh
scripts/dev.sh                                  # venv を作って起動（データは ./data に保存、本番ログは触らない）
scripts/dev.sh --debug                          # WebKit のインスペクタ付き
scripts/send_test_qso.py 22237 JS6UHQ/6         # 開発用の受信口にテスト QSO を流す（2237 には送らない）
python3 -m unittest discover -s tests
```

`VERSION`（`potacommon.py`）を上げて `main` に push すると、GitHub Actions が macOS / Windows 版を作って Release `v<VERSION>` に添付します。構成と設計上の決定は [CLAUDE.md](CLAUDE.md) にまとめています。

## License

MIT

国旗の表示には、Twemoji（CC-BY 4.0）の国旗だけを収めた [country-flag-emoji-polyfill](https://github.com/talkjs/country-flag-emoji-polyfill)（MIT）のフォントを同梱しています。
