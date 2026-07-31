# 춥채팅 - 아키텍처 및 작업 규칙

이 문서는 코드를 고치기 전에 알아야 할 구조와, 과거에 실제로 사고가 났던 지점들을 정리한 것이다.
"왜 이렇게 되어 있는지"를 모르고 고치면 재발하기 쉬운 것들이라 이유까지 같이 적었다.

## 전체 구조

```
chat_core/          도메인 코어 - Qt/asyncio/파일시스템을 전혀 모름
  ports.py            경계(포트) 정의: HistoryStorePort, ProtocolPort, TransportPort
  session.py          ChatSession - 상태(채널/멤버/닉네임/아바타/쿨타임)와 정책
  events.py           코어가 어댑터에 알리는 불변 이벤트들
  constants.py        아바타 크기 상한, @호출 쿨타임, 치트 명세(CHEAT_SPECS)
  commands.py         슬래시 명령 파싱/명세 + 행동(/me)·공지(/notice) CTCP 프레이밍
  history_adapter.py  HistoryStorePort 구현 (JSON 파일 / Null)
  protocols/
    custom.py           커스텀 JSON 프로토콜 전략
    irc.py              실제 IRC 프로토콜 전략
    common_commands.py  두 프로토콜이 동일하게 처리하는 명령(믹스인)
    wire_custom.py      커스텀 프로토콜 메시지 타입 상수 + dict 빌더

gui/                GUI 어댑터 (PySide6) - 화면만 담당
  startup_page.py     시작화면(큰 로고 + 진행 상태)
  update_flow.py      업데이트 진행을 시작화면에 표시하는 흐름
  cheat_overlay.py    'show me the money' 자원 오버레이
  battlecruiser.py    '배틀크루저 소환' 오버레이(방향키 조종)
cli_client.py       CLI 어댑터 (asyncio) - 터미널 출력만 담당
gui_client.py       GUI 진입점 (파사드)
server.py/store.py  서버 (클라이언트 구조와 무관, 이번 범위 밖)
irc_protocol.py     IRC 와이어 파싱/포맷 (순수, 상태 해석 없음)
```

핵심: **로그인/채널/멤버리스트/메시지 해석 같은 "무슨 일이 일어났는가"는 전부 `chat_core`가
판단하고, GUI/CLI는 "그래서 화면에 뭘 그릴까"만 한다.** 예전에는 이 판단 로직이 GUI와 CLI에
각각 따로 구현돼 있어서, CLI에만 있던 버그(멤버 목록에서 나간 사람이 안 지워짐, 아바타 CTCP가
채팅 텍스트로 샘)가 GUI에는 없는 식으로 갈라졌었다.

## SOLID 적용 지점 (지켜야 할 것)

### DIP - 코어는 추상에만 의존
`ChatSession`은 소켓도 파일도 직접 만지지 않는다. 전부 생성자로 주입받는다:
- `transport`: 실제 전송 콜러블 (GUI는 `ChatClient.send_cmd/send_irc`, CLI는 asyncio writer 래퍼)
- `history_store`: `HistoryStorePort` (기본 JSON 파일, 테스트는 `NullHistoryStore`나 가짜 객체)
- `on_event`: 이벤트 싱크

덕분에 코어 테스트는 Qt도 서버도 없이 순수하게 돌아간다. 테스트가 이걸 강제로 검증한다
(`chat_core/session.py` 소스에 `PySide6`/`asyncio`/`history_store` import가 있으면 실패).

### OCP - 프로토콜 추가 시 코어를 수정하지 않는다
`ChatSession`에는 `if protocol == "irc"` 같은 분기가 **하나도 없어야 한다**. 프로토콜별 차이는
전부 `ProtocolPort` 전략 객체가 가진다. 새 프로토콜은 클래스 하나 만들고
`session.py`의 `PROTOCOL_REGISTRY`에 한 줄 등록하면 끝.

프로토콜이 실제로 다르게 동작하는 대표 예:
- IRC는 보낸 메시지를 서버가 안 돌려주므로 **로컬 에코**를 해야 함 → `IrcProtocol.send_chat`
- 커스텀 서버는 돌려주므로 로컬 에코하면 **두 번 보임** → `CustomProtocol.send_chat`
- 커스텀 서버는 "채널 생성"과 "입장"이 별개 단계, IRC는 입장이 곧 생성

수신 메시지 분기도 if/elif 사슬 대신 `_HANDLERS` 디스패치 테이블을 쓴다(새 메시지 타입 지원 시
기존 코드를 안 건드리게).

**슬래시 명령도 같은 규칙**을 따른다. `ChatSession`에는 `if name == "whois"` 같은 분기가 없고,
프로토콜 전략이 `command_specs()` / `run_command()`를 갖는다:
- 두 프로토콜이 똑같이 처리하는 것(`/help /me /join /part /nick`)은 `common_commands.py` 믹스인
- 프로토콜마다 다른 것은 각자 구현 (`/notice`는 IRC에선 진짜 NOTICE, 커스텀에선 프레이밍 채팅)
- IRC만 되는 것(`/whois /topic /mode /kick /raw` 등)은 `irc.py`에만 등록

자동완성 목록과 `/help` 출력이 **같은 `command_specs()`를 출처로 쓴다** - 새 명령을 추가하면
목록과 도움말에 자동으로 함께 나타난다. 커스텀 서버가 못 하는 명령을 치면 조용히 무시하지 않고
"이 서버에서는 지원하지 않는 명령" 안내를 띄운다(무시하면 먹통처럼 보임).

치트도 마찬가지로 `constants.CHEAT_SPECS` 표 + `MainWindow._CHEAT_EFFECTS` 표다. 모르는 치트
id는 조용히 무시되므로 구버전 클라이언트가 같은 채널에 있어도 죽지 않는다.

### SRP
`gui/`는 역할별로 나뉘어 있다: `theme`(상수/QSS), `helpers`(순수 함수), `network`(소켓),
`widgets`(메시지/로그뷰), `pages`(화면), `main_window`(조정), `themed_dialogs`, `profile_dialog`,
`title_bar`, `cheat_overlay`.

## 화면 흐름 (부팅 순서)

```
시작화면(로고) --업데이트 확인/적용--> 로그인 --> 채널 선택 --> 채팅
```

`MainWindow.start_boot_sequence()`가 이 흐름을 주도한다. `QStackedWidget`에 담긴 순서도
실제 흐름 순서와 같게 맞춰뒀다(읽기 쉬우라고).

- 업데이트 진행 상황은 시작화면에 표시한다. 예전엔 로그인 화면이 먼저 뜨고 그 위에 모달
  진행창이 덮치는 구조라 흐름이 어색했다.
- **로그인 전 화면 판정은 `_is_pre_login()`을 쓸 것.** `currentWidget() is login_page`만
  보면 시작화면 단계에서 걸리는 자동로그인이 성공해도 채널 화면으로 안 넘어간다
  (시작화면을 도입했을 때 실제로 이 버그가 났다).
- `LoggedIn` 이벤트는 IRC 닉네임 변경 때도 발생한다(내 식별자가 바뀌는 건 같으므로).
  그래서 화면 전환은 반드시 "아직 로그인 전일 때만" 해야 한다.

## 상태의 단일 출처 (중복 보관 금지)

`MainWindow`는 `my_id` / `_protocol_mode` / `_my_avatar_b64` / `pending_mode`를 **직접 갖지
않고 세션에서 파생**시킨다(전부 `@property`). 예전엔 세션과 윈도우가 같은 사실을 각자
기억해서 어긋날 여지가 있었다. 새 상태를 추가할 때도 "이미 세션이 아는 사실인가"를 먼저
확인할 것.

`ChatPage._members` / `_nicknames` / `_avatar_pixmaps`는 예외로 남겨둔 **화면 렌더링용
캐시**다. 값의 출처는 도메인 이벤트뿐이고, 여기서 뭘 판단하지는 않는다.

## 절대 어기면 안 되는 규칙들 (전부 실제 사고 이력 있음)

### 1. `gui/` 하위 모듈에서 `import gui_client`는 반드시 함수 본문 안에서
테스트가 `g.themed_question = 가짜함수` 식으로 몽키패치하는 함수가 5개 있다:
`themed_get_text`, `themed_question`, `themed_warning`, `_flash_taskbar_icon`, `_shake_window`.

- `from gui.themed_dialogs import themed_question`처럼 직접 바인딩하면 → 몽키패치가 안 먹힘
- 파일 **맨 위**에서 `import gui_client` 하면 → PyInstaller 빌드에서 순환참조 크래시
  (`cannot import name 'X' from partially initialized module`). 로컬 CPython과 로컬
  PyInstaller에서는 통과하는데 **CI가 빌드한 exe에서만 터졌다.** 즉 로컬 빌드 테스트만으로는
  안심할 수 없다.
- 정답: 호출하는 **메서드 본문 안에서** `import gui_client` 후 `gui_client.themed_question(...)`

### 2. 자동 업데이트는 인스톨러 방식 (폴더 통째 move 금지)
예전 방식은 설치 폴더를 통째로 `move`해서 교체했는데, **폴더 안 파일이 단 하나라도 열려 있으면
move 전체가 "Access is denied"로 실패한다**(실측 확인). 백신 실시간 검사가 DLL 하나만 잡고
있어도 재시도가 전부 실패해서 "설치는 되는데 패치만 계속 안 되는" 증상이 났다.

지금은 `FriendChat_Setup.exe`를 받아 `/VERYSILENT`로 실행한다. Inno Setup은 파일 단위로
처리해서 같은 상황에서도 성공하고, 용량도 zip보다 작다. zip 방식은 인스톨러 자산이 없는
옛 릴리즈 대비 폴백으로만 남겨둠.

관련해서 같이 지켜야 할 것:
- 배치 스크립트에서 `timeout /t N`은 **콘솔 없는 환경에서 즉시 실패**한다(`--windowed` exe가
  띄운 자식 프로세스가 그렇다). 지연은 `ping -n N+1 127.0.0.1 >nul`로 한다.
- 배치 파일은 `encoding="utf-8-sig"`로 저장하고 `chcp 65001`을 넣는다. 설치 경로에 한글
  ("춥채팅")이 있어서 안 하면 경로가 깨진다.
- 같은 버전으로 3번 연속 업데이트 시도가 실패하면 더 이상 재시도하지 않는다
  (`MAX_UPDATE_ATTEMPTS`). 없으면 "패치 화면만 뜨고 앱은 영영 못 켜는" 무한루프에 빠진다.
- 앱 창을 **먼저 띄우고** 그 다음에 업데이트를 확인한다. 반대로 하면 업데이트가 실패하는
  환경에서 앱을 한 번도 못 보여준다.

### 3. 채팅 메시지 줄바꿈 폭은 탭바 기준으로 미리 밀어넣는다
숨겨진 탭은 자기 `viewport().width()`가 실제 화면 폭과 다르다. 탭을 전환하는 순간에 폭을
다시 계산하면 메시지가 눈앞에서 재배치되며 스크롤이 위로 튄다. 그래서 항상 보이는
`self.tabs` 폭을 기준으로 채널 추가/창 리사이즈 시점에 모든 탭에 미리 반영한다
(`ChatPage._push_wrap_width` → `ChannelLogView.set_container_width`).

### 4. 탭 안읽음 표시는 아이콘으로 (글자색 금지)
`QTabBar::tab { color: ... }`가 QSS에 있으면 `setTabTextColor()`가 **절대 안 먹는다**
(스타일시트가 항상 이김). 그래서 안읽음 깜빡임은 `setTabIcon()`으로 한다.

### 5. disabled 탭은 클릭 이벤트를 못 받는다
"+" 채널 추가 탭을 `setTabEnabled(False)`로 뒀더니 눌러도 아무 반응이 없었다. enabled로 두고,
클릭으로 선택되면 다음 이벤트 루프 틱에 원래 탭으로 되돌린다(`QTimer.singleShot(0, ...)`).
`tabBarClicked` 직후 Qt가 내부적으로 한 번 더 `setCurrentIndex`를 호출하기 때문에 즉시
되돌리면 덮어써진다.

### 6. 테스트는 "핸들러 직접 호출"이 아니라 실제 경로로
위 5번 버그는 테스트가 핸들러를 직접 호출해서 **놓쳤다**. UI 상호작용은
`QTest.mouseClick`처럼 실제 이벤트 경로로 검증한다.

## 테스트

`C:\Users\dbwls\AppData\Local\Temp\claude\...\scratchpad\` 아래에 있다(저장소에는 없음).
- `test_chat_core_session.py` - 코어 단위 테스트. **Qt/소켓/파일 없이** 돌아감. OCP/DIP 위반을
  소스 검사로 잡는 항목도 포함.
- GUI 테스트는 `QT_QPA_PLATFORM=offscreen` + 실제 `server.py`/IRC 테스트 데몬을 띄워서 돌린다.
- CLI 테스트는 stdin을 파이프로 밀어넣어 프롬프트 순서/출력 문구를 그대로 검증한다.
  → **CLI 출력 문구를 바꾸면 테스트가 깨진다.** 문구도 계약이라고 생각할 것.

서버 포트 규약: `server.py <평문포트> <SSL포트>`. 테스트마다 기대하는 포트가 다르다
(평문 17667, SSL 17697 / e2e는 SSL 16668).

**테스트 사이에 `server_data.json`, `history.json`을 지울 것.** 계정/채널이 누적되면
"이미 존재하는 아이디" 때문에 입력 순서가 밀려서 엉뚱하게 실패한다(실제로 여러 번 헤맸음).

## 배포

태그를 푸시하면 GitHub Actions가 빌드해서 릴리즈에 올린다.
```
version.py 수정 → 커밋 → git tag vX.Y.Z → git push origin vX.Y.Z
```
릴리즈 자산: `FriendChat_Setup.exe`(설치/업데이트용), `FriendChat_GUI.zip`(구버전 폴백용).
둘 다 계속 올려야 한다.

**로컬 빌드가 성공해도 CI 빌드 exe는 따로 확인할 것** (1번 규칙의 순환참조 사고가 정확히
이 차이에서 났다). 릴리즈 zip을 받아서 실제로 실행해보는 게 확실하다.
