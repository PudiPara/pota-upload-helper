# POTA Upload Helper

[日本語](README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [한국어](README.ko.md) · [Polski](README.pl.md)

POTA(Parks on the Air) 활성화를 운용 중부터 업로드까지 돕는 데스크톱 앱입니다. macOS와 Windows에서 동작합니다.

FT8 등에서는 상대가 공원에서 운용 중인지, 더구나 2fer인지 그 자리에서 알 수 없습니다. 이 앱은 운용 중에 pota.app 스팟을 기록하고, 로거에서 온 QSO와 그 자리에서 대조해 **P2P(공원 대 공원)와 2fer 후보를 제시하며, 당신이 확인해 기록합니다**. 운용을 마치면 내 공원별·UTC 날짜별로 pota.app에 바로 올릴 수 있는 파일을 만듭니다.

![운용 중](docs/live.png)

## 할 수 있는 일

- **운용 중에는 바 표시**: 공원 번호를 넣고 기록을 시작하면 창이 작은 띠가 되어 로거 위에 남습니다(내 공원, 경과 시간, QSO 수, 최근 교신). ‘펼치기’로 원래 크기로 돌아갑니다. 공원에서 나오는 국을 1분마다 기록하므로 상대가 QRT해도 나중에 판정할 수 있습니다.
- **활성화 중인 국**: 기록하지 않을 때도 지금 공원에서 나오는 국을 pota.app 스팟으로 목록화합니다(1분마다 갱신). 지역(일본/전 세계), 밴드, 모드(CW/Phone/Data), 호출부호나 공원 번호 검색, 2fer만으로 필터링합니다.
- **로거에서 QSO 수신**: OpsLog나 JTAlert처럼 UDP로 받습니다. N1MM 형식(RUMlogNG, N1MM Logger+, DXLog 등), WSJT-X/JTDX(멀티캐스트 지원), ADIF(JTAlert, GridTracker, Log4OM 등). 로거에서의 수정·삭제도 반영됩니다.
- **P2P는 그 자리에서 확인**: 도착한 QSO의 상대가 공원에서 나오고 있으면 ‘P2P 가능성’과 공원 번호를 보여 주고 ‘예’ ‘아니오’로 정합니다. 스팟에 없는 상대(Phone이나 CW로 공원 번호를 들은 경우)는 그 행에 번호를 직접 입력합니다. 자동으로 P2P로 만들지 않습니다.
- **10 QSO 알림**: 활성화 성공 순간 화면 가득 표시합니다.
- **종료하면 파일 생성**: ‘이 공원 운용 종료’를 누르면 그 공원·그날의 업로드 파일(`JL1FVA@JP-1266-20261020.adi`)을 저장 위치에 쓰고 처음 화면으로 돌아갑니다. 다음 공원에 도착하면 번호만 넣으면 됩니다. 상대가 2fer면 QSO를 공원 수만큼 복제하고, 내가 2fer면 공원별로 파일을 나눕니다.
- **전달**: 받은 데이터를 그대로 다른 앱에 흘릴 수 있습니다(RUMlog → 이 앱 → OpsLog).
- **다시 만들기**: ‘업로드 파일 만들기’ 탭에서 앱 로그나 로거의 ADIF로 과거 날짜의 파일을 한꺼번에 만들 수 있습니다.

![업로드 파일 만들기](docs/build.png)

상대 공원은 다음 우선순위로 정합니다.

1. **pota.app 헌터 로그**(상대가 업로드한 기록 = 확정). 시각 ±5분·같은 밴드로 대조
2. **운용 중에 확인·입력한 공원**(앱 로그로 만들 때). 확인하지 않은 QSO는 P2P로 하지 않음
3. **운용 중의 스팟 기록**(ADIF 파일로 만들 때만. QSO 30분 전~10분 후의 스팟)
4. 로거의 SIG_INFO / POTA_REF

공개 API(api.pota.app)만 사용하며 로그인은 필요 없습니다. 로그 보관은 로거의 일입니다. 이 앱은 판정과 업로드 파일 생성만 맡고 로거의 로그를 고치지 않습니다.

## 다운로드

[Releases](../../releases)에서 최신판을 받으세요.

| OS | 파일 | 사용법 |
|---|---|---|
| macOS(Apple Silicon) | `POTA-Upload-Helper-macOS.dmg` | 열어서 `POTA Upload Helper`를 `Applications`로 드래그 |
| Windows 10 / 11 | `POTA-Upload-Helper-Setup.exe` | 실행하면 사용자별 위치(관리자 권한 불필요)에 설치되고 시작 메뉴에 들어갑니다 |

zip판(`POTA-Upload-Helper-macOS.zip` / `POTA-Upload-Helper-Windows.zip`)도 첨부되어 있습니다. 앱 내 업데이트가 이 zip을 쓰므로 Release에서 지우지 마세요.

서명하지 않은 앱이라 처음에는 경고가 나옵니다.

- **macOS**: 앱을 우클릭 → ‘열기’ → ‘열기’. 열리지 않으면 ‘시스템 설정 → 개인정보 보호 및 보안’ 아래쪽의 ‘그래도 열기’
- **Windows**: ‘Windows의 PC 보호’ → ‘추가 정보’ → ‘실행’

**두 번째부터는 앱 안에서 업데이트할 수 있습니다.** 시작할 때 새 버전을 확인하고, 왼쪽 아래에 ‘v1.x.x이 공개되었습니다’가 나오면 ‘지금 업데이트’를 누르세요. 내려받아 교체하고 다시 시작합니다. 확인은 언제든 왼쪽 아래 ‘업데이트 확인’으로 할 수 있습니다. DMG 안의 앱을 그대로(`Applications`에 넣지 않고) 열고 있으면 macOS 구조상 교체할 수 없어 새 앱을 ‘다운로드’ 폴더에 두고 알려 줍니다.

## 로거 연결

앱의 ‘로거 연결’에서 수신을 만듭니다(몇 개든 추가 가능). **QSO를 UDP로 내보낼 수 있는 로거라면 쓸 수 있습니다.** 로거에서 ‘QSO를 UDP로 보내기’ 설정을 열어 대상을 `127.0.0.1`, 포트를 수신과 같은 번호로 맞추세요. 패킷 형식은 앱이 자동으로 판별합니다.

![로거 연결](docs/settings.png)

| 형식 | 로거 예 | 설정 위치 |
|---|---|---|
| N1MM(contactinfo XML) | RUMlogNG, N1MM Logger+, DXLog, Win-Test | RUMlogNG: Preferences → UDP의 Contact info를 N1MM으로. N1MM Logger+: Config → Broadcast Data → Contacts |
| WSJT-X | WSJT-X, JTDX | Settings → Reporting의 UDP Server. `224.0.0.1`(멀티캐스트)로 하면 다른 앱과 동시에 받을 수 있습니다 |
| ADIF | JTAlert, GridTracker, Log4OM 등 | 각 소프트웨어의 ‘ADIF를 UDP로 보내기’ 설정 |

**같은 컴퓨터의 로거에서만 받을 수 있습니다.** 수신은 `127.0.0.1`에서 대기하므로 다른 컴퓨터의 로거에서는 도착하지 않습니다.

**Windows에서 WSJT-X / JTDX 멀티캐스트를 쓰는 경우**: Windows에서는 멀티캐스트 수신도 루프백(`127.0.0.1`)에서 대기합니다. WSJT-X의 Settings → Reporting → **Outgoing interfaces**에 **loopback**을 포함하세요. 이 조합은 Windows 11에서 동작을 확인했습니다. 도착하지 않으면 [Issue](../../issues)로 알려 주세요. 멀티캐스트 대신 WSJT-X의 UDP Server를 `127.0.0.1`로 하면 확실히 받을 수 있습니다(다만 그 경우 다른 앱과 동시에는 받을 수 없습니다).

같은 데이터를 다른 앱(OpsLog 등)에도 넘기려면 수신의 ‘전달 대상’에 그 앱의 주소와 포트를 넣습니다.

**둘 다 켜도 중복되지 않습니다**: WSJT-X의 QSO는 WSJT-X에서 직접, 그리고 그것을 받은 로거에서 다시 보내는 것까지 두 번 도착합니다(시작 시각과 종료 시각으로 1분쯤 차이). 같은 호출부호·같은 밴드·3분 이내면 같은 교신으로 한 건으로 합치고, P2P 판단과 삭제도 둘 다에 반영합니다. 반대로 같은 국과 같은 밴드에서 3분 안에 두 번 교신해도 한 건이 됩니다.

## 데이터 저장 위치

| OS | 위치 |
|---|---|
| macOS | `~/Library/Application Support/POTA Upload Helper/` |
| Windows | `%APPDATA%\POTA Upload Helper\` |

`qsolog.db`(받은 QSO), `spots-YYYYMMDD.jsonl`(스팟 기록), `sessions.json`(내 운용 시간과 공원), `hunter.json`(헌터 로그 사본), `settings.json`.
pota.app 공개 프로필에는 최근 25건의 헌터 로그만 나오므로, 기록 중과 생성 때마다 `hunter.json`에 추가해 이력을 쌓습니다.

## 언어

日本語, English, 简体中文, 繁體中文, Français, Deutsch, Español, Italiano, Português (Brasil), 한국어, Polski. OS 언어에 맞춰 자동으로 선택되며 사이드바의 ‘언어’에서 바꿀 수 있습니다.

## 이용 약관·면책 사항

이 앱은 개인이 취미로 만든 무보증 소프트웨어입니다. **이 앱을 사용하여 발생한 어떠한 손해(pota.app에 잘못된 내용을 업로드, QSO 중복이나 누락, 로그나 파일 손실, 로거나 네트워크 설정에 미치는 영향 등)에 대해서도 제작자는 책임지지 않습니다.** 업로드할 파일 내용은 반드시 직접 확인하세요. P2P와 2fer 판정은 추정이며 정확성을 보증하지 않습니다. 이 앱은 Parks on the Air® 및 pota.app과 무관합니다. 전문은 [TERMS.md](TERMS.md)에 있으며 앱 첫 실행 때도 표시됩니다.

보안 문제 신고는 [SECURITY.md](SECURITY.md)를 보세요.

## 소스에서 실행

```sh
pip install -r requirements.txt
python3 app.py
```

명령줄 도구만으로도 쓸 수 있습니다(표준 라이브러리만).

```sh
python3 pota_spotlog.py --parks JP-1266,JP-1206
python3 pota_build.py export.adif --date 20261020
```

## 개발

```sh
scripts/dev.sh                                  # venv를 만들어 실행(데이터는 ./data에 저장, 실제 로그는 건드리지 않음)
scripts/dev.sh --debug                          # WebKit 인스펙터 포함
scripts/send_test_qso.py 22237 JS6UHQ/6         # 개발용 수신에 테스트 QSO 보내기(2237로는 보내지 않음)
python3 -m unittest discover -s tests
```

`potacommon.py`의 `VERSION`을 올려 `main`에 push하면 GitHub Actions가 macOS/Windows판을 만들어 Release `v<VERSION>`에 첨부합니다. 구조와 설계 결정은 [CLAUDE.md](CLAUDE.md)에 정리되어 있습니다.

## License

MIT
