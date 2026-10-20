# POTA Upload Helper

[日本語](README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [한국어](README.ko.md) · [Polski](README.pl.md)

一款給 POTA（Parks on the Air）啟用者的桌面程式，從開始運用一路協助到上傳。支援 macOS 與 Windows。

在 FT8 等模式下，很難當場知道對方是否在公園，更別說是否 2fer。本程式在運用期間記錄 pota.app 的 spot，與日誌軟體送來的 QSO 當場比對，**提出 P2P（公園對公園）與 2fer 的候選，由你確認後記錄**。運用結束時，依自己的公園與 UTC 日期產生可直接上傳到 pota.app 的檔案。

![運用中](docs/live.png)

## 功能

- **運用中以工具列顯示**：輸入公園編號開始記錄後，視窗縮成一條橫列，留在日誌軟體上方（自己的公園、經過時間、QSO 數、最近的通聯）。「展開」可恢復原大小。每分鐘記錄從公園發射的電台，對方 QRT 後仍能判斷。
- **正在啟用的電台**：即使沒在記錄，也能看到此刻在公園發射的電台列表（來自 pota.app spot，每分鐘更新）。可依地區（日本／全球）、波段、模式（CW／Phone／Data）、呼號或公園編號、只看 2fer 篩選。
- **從日誌軟體接收 QSO**：和 OpsLog、JTAlert 一樣透過 UDP 接收。N1MM 格式（RUMlogNG、N1MM Logger+、DXLog 等）、WSJT-X / JTDX（支援群播）、ADIF（JTAlert、GridTracker、Log4OM 等）。日誌軟體中的修改與刪除也會同步。
- **當場確認 P2P**：若對方正從公園發射，該列會顯示「可能是 P2P」與公園編號，按「是」「否」決定。對方不在 spot 上時（Phone 或 CW 口頭告知公園），直接在該列輸入公園編號。不會自動記為 P2P。
- **10 QSO 提醒**：啟用成功的瞬間全螢幕顯示。
- **結束即產生檔案**：按「結束本公園的運用」，把該公園當天的上傳檔案（`JL1FVA@JP-1266-20261020.adi`）寫到儲存位置並回到初始畫面。到下一個公園只需輸入編號。對方是 2fer 時依公園數複製 QSO；自己是 2fer 時依公園分檔。
- **轉送**：收到的資料可原樣轉給其他程式（RUMlog → 本程式 → OpsLog）。
- **重新產生**：「產生上傳檔案」頁可從程式日誌或日誌軟體匯出的 ADIF 批次產生過去日期的檔案。

![產生上傳檔案](docs/build.png)

對方的公園依以下優先順序決定：

1. **pota.app 獵人日誌**（對方上傳的記錄 = 確定）。依時間 ±5 分鐘、同一波段比對
2. **運用中確認或輸入的公園**（從程式日誌產生時）。未確認的 QSO 不記為 P2P
3. **運用中的 spot 記錄**（僅從 ADIF 檔產生時。QSO 前 30 分鐘到後 10 分鐘的 spot）
4. 日誌軟體中的 SIG_INFO / POTA_REF

只使用公開 API（api.pota.app），不需登入。保存日誌是日誌軟體的工作；本程式只負責判斷與產生上傳檔案，不會改寫日誌軟體的日誌。

## 下載

請從 [Releases](../../releases) 取得最新版。

| 系統 | 檔案 | 用法 |
|---|---|---|
| macOS（Apple Silicon） | `POTA-Upload-Helper-macOS.dmg` | 開啟後把 `POTA Upload Helper` 拖到 `Applications` |
| Windows 10 / 11 | `POTA-Upload-Helper-Setup.exe` | 執行後安裝到目前使用者（不需管理員權限），並加入開始功能表 |

同時附有 zip 版（`POTA-Upload-Helper-macOS.zip` / `POTA-Upload-Helper-Windows.zip`）。程式內更新使用這些 zip，請勿從 Release 刪除。

程式未簽署，首次開啟會有警告。

- **macOS**：右鍵點選程式 →「打開」→「打開」。仍無法開啟時，到「系統設定 → 隱私權與安全性」底部按「強制打開」
- **Windows**：「Windows 已保護你的電腦」→「其他資訊」→「仍要執行」

**之後可在程式內更新。** 啟動時會檢查新版本，左下角出現「v1.x.x 已發布」時按「立即更新」，會下載、替換並重新啟動。隨時可用左下角的「檢查更新」。如果直接從 DMG 裡執行（未放入 `Applications`），macOS 不允許就地替換，新版本會放到「下載項目」資料夾並提示。

## 連接日誌軟體

在「連接日誌軟體」中建立接收口（數量不限）。**只要能透過 UDP 送出 QSO 的日誌軟體都可以。** 在日誌軟體中開啟「透過 UDP 傳送 QSO」設定，目標設為 `127.0.0.1`，連接埠與接收口相同。程式會自動辨識封包格式。

![連接日誌軟體](docs/settings.png)

| 格式 | 日誌軟體範例 | 設定位置 |
|---|---|---|
| N1MM（contactinfo XML） | RUMlogNG、N1MM Logger+、DXLog、Win-Test | RUMlogNG：Preferences → UDP，Contact info 選 N1MM。N1MM Logger+：Config → Broadcast Data → Contacts |
| WSJT-X | WSJT-X、JTDX | Settings → Reporting 的 UDP Server。設為 `224.0.0.1`（群播）可與其他程式同時接收 |
| ADIF | JTAlert、GridTracker、Log4OM 等 | 各軟體的「透過 UDP 傳送 ADIF」設定 |

**只接收同一台電腦上的日誌軟體。** 接收口在 `127.0.0.1` 上監聽，其他電腦上的日誌軟體無法送過來。

**在 Windows 上使用 WSJT-X / JTDX 群播時**：Windows 上群播接收口也在回送位址（`127.0.0.1`）上監聽。請在 WSJT-X 的 Settings → Reporting → **Outgoing interfaces** 中勾選 **loopback**。這種組合已在 Windows 11 上驗證；收不到時請透過 [Issue](../../issues) 告訴我們。把 WSJT-X 的 UDP Server 設為 `127.0.0.1`（不用群播）一定能收到，但這樣其他程式就無法同時接收。

若要把同樣的資料傳給其他程式（如 OpsLog），在接收口的「轉送到」填入其位址與連接埠。

**兩個接收口都開也不會重複**：WSJT-X 的 QSO 會到達兩次，一次直接來自 WSJT-X，一次來自收到它的日誌軟體（開始時間與結束時間相差約 1 分鐘）。同一呼號、同一波段且相差 3 分鐘以內視為同一次通聯，P2P 判斷與刪除也同時套用。反之，與同一電台在同一波段 3 分鐘內通聯兩次也會合併為一筆。

## 資料儲存位置

| 系統 | 位置 |
|---|---|
| macOS | `~/Library/Application Support/POTA Upload Helper/` |
| Windows | `%APPDATA%\POTA Upload Helper\` |

`qsolog.db`（收到的 QSO）、`spots-YYYYMMDD.jsonl`（spot 記錄）、`sessions.json`（自己的運用時段與公園）、`hunter.json`（獵人日誌副本）、`settings.json`。
pota.app 公開資料只顯示最近 25 筆獵人日誌，因此程式在記錄中與每次產生時附加到 `hunter.json` 以累積歷史。

## 語言

日本語、English、简体中文、繁體中文、Français、Deutsch、Español、Italiano、Português (Brasil)、한국어、Polski。依系統語言自動選擇，可在側欄「語言」切換。

## 使用條款與免責聲明

本程式是個人業餘開發、不提供任何保證的軟體。**對於使用本程式造成的任何損失（向 pota.app 上傳錯誤內容、QSO 重複或遺漏、日誌或檔案遺失、對日誌軟體或網路設定的影響等），作者概不負責。** 上傳前請務必自行檢查檔案內容。P2P 與 2fer 的判斷只是推測，不保證正確。本程式與 Parks on the Air® 及 pota.app 無關。全文見 [TERMS.md](TERMS.md)，首次啟動時也會顯示。

安全性問題請見 [SECURITY.md](SECURITY.md)。

## 從原始碼執行

```sh
pip install -r requirements.txt
python3 app.py
```

命令列工具可單獨使用（僅標準函式庫）。

```sh
python3 pota_spotlog.py --parks JP-1266,JP-1206
python3 pota_build.py export.adif --date 20261020
```

## 開發

```sh
scripts/dev.sh                                  # 建立 venv 並啟動（資料存在 ./data，不碰正式日誌）
scripts/dev.sh --debug                          # 附 WebKit 檢閱器
scripts/send_test_qso.py 22237 JS6UHQ/6         # 向開發用接收口送出測試 QSO（不要送到 2237）
python3 -m unittest discover -s tests
```

提升 `potacommon.py` 中的 `VERSION` 並推送到 `main`，GitHub Actions 會建置 macOS / Windows 版並附加到 Release `v<VERSION>`。結構與設計決定見 [CLAUDE.md](CLAUDE.md)。

## License

MIT
