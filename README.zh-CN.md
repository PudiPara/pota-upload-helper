# POTA Upload Helper

[日本語](README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [한국어](README.ko.md) · [Polski](README.pl.md)

一款面向 POTA（Parks on the Air）激活者的桌面应用，从运用开始一直帮到上传。支持 macOS 和 Windows。

在 FT8 等模式下，很难当场知道对方是否在公园里，更不用说是否 2fer。本应用在运用期间记录 pota.app 的 spot，和日志软件发来的 QSO 当场比对，**给出 P2P（公园对公园）和 2fer 的候选，由你确认后记录**。运用结束时，按自己的公园和 UTC 日期生成可直接上传到 pota.app 的文件。

![运用中](docs/live.png)

## 功能

- **运用中以工具条显示**：输入公园编号开始记录后，窗口缩成一条横栏，留在日志软件上方（自己的公园、经过时间、QSO 数、最近的通联）。“展开”可恢复原大小。每分钟记录从公园发射的电台，对方 QRT 后仍能判断。
- **正在激活的电台**：即使不在记录，也能看到此刻在公园发射的电台列表（来自 pota.app spot，每分钟更新）。可按地区（日本／全球）、波段、模式（CW／Phone／Data）、呼号或公园编号、只看 2fer 筛选。
- **从日志软件接收 QSO**：和 OpsLog、JTAlert 一样通过 UDP 接收。N1MM 格式（RUMlogNG、N1MM Logger+、DXLog 等）、WSJT-X / JTDX（支持组播）、ADIF（JTAlert、GridTracker、Log4OM 等）。日志软件中的修改和删除也会同步。
- **当场确认 P2P**：若对方正从公园发射，该行会显示“可能是 P2P”和公园编号，按“是”“否”决定。对方不在 spot 上时（Phone 或 CW 口头告知公园），直接在该行输入公园编号。不会自动记为 P2P。
- **10 QSO 提醒**：激活成功的瞬间全屏显示。
- **结束即生成文件**：按“结束本公园的运用”，把该公园当天的上传文件（`JL1FVA@JP-1266-20261020.adi`）写到保存位置并回到初始画面。到下一个公园只需输入编号。对方是 2fer 时按公园数复制 QSO；自己是 2fer 时按公园分文件。
- **转发**：收到的数据可原样转给其他程序（RUMlog → 本应用 → OpsLog）。
- **重新生成**：“生成上传文件”页可从应用日志或日志软件导出的 ADIF 批量生成过去日期的文件。

![生成上传文件](docs/build.png)

对方的公园按以下优先级决定：

1. **pota.app 猎人日志**（对方上传的记录 = 确定）。按时间 ±5 分钟、同一波段比对
2. **运用中确认或输入的公园**（从应用日志生成时）。未确认的 QSO 不记为 P2P
3. **运用中的 spot 记录**（仅从 ADIF 文件生成时。QSO 前 30 分钟到后 10 分钟的 spot）
4. 日志软件中的 SIG_INFO / POTA_REF

只使用公开 API（api.pota.app），无需登录。保存日志是日志软件的工作；本应用只负责判断和生成上传文件，不会改写日志软件的日志。

## 下载

请从 [Releases](../../releases) 获取最新版。

| 系统 | 文件 | 用法 |
|---|---|---|
| macOS（Apple Silicon） | `POTA-Upload-Helper-macOS.dmg` | 打开后把 `POTA Upload Helper` 拖到 `Applications` |
| Windows 10 / 11 | `POTA-Upload-Helper-Setup.exe` | 运行后安装到当前用户（无需管理员权限），并加入开始菜单 |

同时附有 zip 版（`POTA-Upload-Helper-macOS.zip` / `POTA-Upload-Helper-Windows.zip`）。应用内更新使用这些 zip，请不要从 Release 中删除。

应用未签名，首次打开会有警告。

- **macOS**：右键点击应用 →“打开”→“打开”。仍无法打开时，到“系统设置 → 隐私与安全性”底部点“仍要打开”
- **Windows**：“Windows 已保护你的电脑”→“更多信息”→“仍要运行”

**之后可在应用内更新。** 启动时会检查新版本，左下角出现“v1.x.x 已发布”时按“立即更新”，会下载、替换并重新启动。随时可用左下角的“检查更新”。如果直接从 DMG 里运行（未放入 `Applications`），macOS 不允许就地替换，新版本会放到“下载”文件夹并提示。

## 连接日志软件

在“连接日志软件”中创建接收口（数量不限）。**只要能通过 UDP 发送 QSO 的日志软件都可以。** 在日志软件中打开“通过 UDP 发送 QSO”设置，目标设为 `127.0.0.1`，端口与接收口相同。应用会自动识别数据包格式。

![连接日志软件](docs/settings.png)

| 格式 | 日志软件示例 | 设置位置 |
|---|---|---|
| N1MM（contactinfo XML） | RUMlogNG、N1MM Logger+、DXLog、Win-Test | RUMlogNG：Preferences → UDP，Contact info 选 N1MM。N1MM Logger+：Config → Broadcast Data → Contacts |
| WSJT-X | WSJT-X、JTDX | Settings → Reporting 的 UDP Server。设为 `224.0.0.1`（组播）可与其他程序同时接收 |
| ADIF | JTAlert、GridTracker、Log4OM 等 | 各软件的“通过 UDP 发送 ADIF”设置 |

若要把同样的数据传给其他程序（如 OpsLog），在接收口的“转发到”填入其地址和端口。

**两个接收口都开也不会重复**：WSJT-X 的 QSO 会到达两次，一次直接来自 WSJT-X，一次来自收到它的日志软件（开始时间和结束时间相差约 1 分钟）。同一呼号、同一波段且相差 3 分钟以内视为同一次通联，P2P 判断和删除也同时作用。反之，与同一电台在同一波段 3 分钟内通联两次也会合并为一条。

## 数据保存位置

| 系统 | 位置 |
|---|---|
| macOS | `~/Library/Application Support/POTA Upload Helper/` |
| Windows | `%APPDATA%\POTA Upload Helper\` |

`qsolog.db`（收到的 QSO）、`spots-YYYYMMDD.jsonl`（spot 记录）、`sessions.json`（自己的运用时段和公园）、`hunter.json`（猎人日志副本）、`settings.json`。
pota.app 公开资料只显示最近 25 条猎人日志，因此应用在记录中和每次生成时追加到 `hunter.json` 以积累历史。

## 语言

日本語、English、简体中文、繁體中文、Français、Deutsch、Español、Italiano、Português (Brasil)、한국어、Polski。按系统语言自动选择，可在侧栏“语言”中切换。

## 使用条款与免责声明

本应用是个人业余开发、不提供任何保证的软件。**对于使用本应用造成的任何损失（向 pota.app 上传错误内容、QSO 重复或缺失、日志或文件丢失、对日志软件或网络设置的影响等），作者概不负责。** 上传前请务必自行检查文件内容。P2P 与 2fer 的判断只是推测，不保证正确。本应用与 Parks on the Air® 及 pota.app 无关。全文见 [TERMS.md](TERMS.md)，首次启动时也会显示。

安全问题请见 [SECURITY.md](SECURITY.md)。

## 从源码运行

```sh
pip install -r requirements.txt
python3 app.py
```

命令行工具可单独使用（仅标准库）。

```sh
python3 pota_spotlog.py --parks JP-1266,JP-1206
python3 pota_build.py export.adif --date 20261020
```

## 开发

```sh
scripts/dev.sh                                  # 创建 venv 并启动（数据保存在 ./data，不碰正式日志）
scripts/dev.sh --debug                          # 带 WebKit 检查器
scripts/send_test_qso.py 22237 JS6UHQ/6         # 向开发用接收口发送测试 QSO（不要发到 2237）
python3 -m unittest discover -s tests
```

提升 `potacommon.py` 中的 `VERSION` 并推送到 `main`，GitHub Actions 会构建 macOS / Windows 版并附加到 Release `v<VERSION>`。结构和设计决定见 [CLAUDE.md](CLAUDE.md)。

## License

MIT
