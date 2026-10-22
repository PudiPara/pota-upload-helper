# Security policy / セキュリティポリシー

## 日本語

### 対象バージョン

最新の Release（[Releases](../../releases) の一番上）だけが対象です。古い版は修正しません。アプリ内の「アップデートを確認」で最新版に更新できます。

### 脆弱性の報告

公開の Issue には書かず、GitHub の **Security → Report a vulnerability**（プライベートな脆弱性報告）から送ってください。再現手順、影響、使っている OS とアプリのバージョンを添えてもらえると助かります。個人が趣味で保守しているので返信には数日かかることがありますが、受け取ったことと対応の見込みは必ず返します。

### このアプリが外部とやり取りするもの

- **送信先**：`api.pota.app`（スポット、公園情報、ハンターログの取得）と `api.github.com` / `github.com`（更新の確認とダウンロード）、`tile.openstreetmap.org`（地図のタイル）だけです。QSO やログを外部に送ることはありません。
- **受信**：設定した UDP ポートでロガーからの QSO を待ち受けます。通常の受信口は `127.0.0.1` だけで待ち受けるので、同じパソコンのロガーからしか受け取りません。マルチキャストの受信口（WSJT-X の `224.0.0.1` など）は、macOS ではそのグループ、Windows ではループバックで待ち受けます。どの受信口も全インターフェースでは待ち受けません。受け取った内容は解析して SQLite に保存するだけで、実行はしません。
- **更新**：ダウンロード元は `https://github.com/PudiPara/potaroo/releases/download/` 配下に限定しています。バイナリには署名がないため、Releases ページから取ったものであることを確認してください。
- **保存先**：すべてのデータはこのパソコンの中（README の「データの保存場所」）にあります。アップロード用ファイルには自分と相手のコールサイン、時刻、公園番号が含まれます。

## English

### Supported versions

Only the latest Release (the top entry under [Releases](../../releases)) is supported; older versions are not patched. The app's "Check for updates" takes you to the latest version.

### Reporting a vulnerability

Please do not open a public issue. Use GitHub's **Security → Report a vulnerability** (private vulnerability reporting) on this repository. Steps to reproduce, impact, your OS and the app version help a lot. This is hobby software maintained by one person, so a reply can take a few days, but you will always get an acknowledgement and an outlook.

### What the app talks to

- **Outbound**: only `api.pota.app` (spots, park info, hunter log) and `api.github.com` / `github.com` (update check and download), `tile.openstreetmap.org` (map tiles). QSOs and logs are never sent anywhere.
- **Inbound**: the configured UDP ports receive QSOs from your logger. Ordinary listeners bind to `127.0.0.1` only, so they accept packets from loggers on the same computer and nothing from the network. A multicast listener (WSJT-X on `224.0.0.1`, …) binds the group on macOS and loopback on Windows. No listener binds all interfaces. Received packets are parsed and stored in SQLite, never executed.
- **Updates**: downloads are restricted to `https://github.com/PudiPara/potaroo/releases/download/`. The binaries are unsigned, so make sure you got them from the Releases page.
- **Storage**: all data stays on your computer (see "Data" in the README). Upload files contain your and the other station's callsigns, times and park references.
