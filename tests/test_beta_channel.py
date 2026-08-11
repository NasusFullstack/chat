"""테스트(베타) 버전이 정식 버전과 확실히 갈라져 있는가.

왜 이 검사가 필요한가: v2.1.0이 실행 즉시 죽는 상태로 **정식 배포**돼서 모든 사용자의
앱이 안 켜졌다. 그 뒤로 "정식에 바로 올리지 말고 테스트 버전을 먼저 돌린다"는 규칙이
생겼는데, 그 분리가 실제로 되어 있지 않으면 규칙만 있고 안전장치는 없는 셈이 된다.

여기서 확인하는 것:
1. 정식 배포 워크플로가 베타 태그를 물지 않는가 (물면 테스트 버전이 정식으로 나간다)
2. 베타 릴리즈는 prerelease로 올라가는가 (정식 사용자의 자동 업데이트는 prerelease를
   보지 못한다 - GitHub의 /releases/latest가 원래 그렇다)
3. 베타는 설치 파일을 만들지 않는가 (설치된 정식 버전을 건드릴 일이 없어야 한다)
4. 앱이 스스로 베타인 걸 알고, 제목/중복실행 자리/자동 업데이트를 다르게 처리하는가
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

import importlib
import io

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def read(rel):
    with io.open(_os.path.join(_REPO, rel), encoding="utf-8") as fp:
        return fp.read()


# ---------- 1~3) 배포 설정 ----------
stable = read(".github/workflows/release.yml")
beta = read(".github/workflows/release-beta.yml")

check("정식 배포가 베타 태그를 걸러낸다", "'!v*-beta*'" in stable,
      "release.yml에서 베타 태그를 제외해야 테스트 버전이 정식으로 안 나간다")
check("베타 워크플로는 베타 태그에서만 돈다", "'v*-beta*'" in beta)
check("베타는 prerelease로 올린다(자동 업데이트에 안 잡히게)", "--prerelease" in beta)
check("베타는 설치 파일을 만들지 않는다(정식 설치를 안 건드림)",
      "installer.iss" not in beta and "Inno" not in beta)
check("베타 실행 파일 이름이 정식과 다르다", "FriendChat_GUI_Beta" in beta)
check("정식은 예전처럼 설치 파일과 zip을 함께 올린다",
      "FriendChat_Setup.exe" in stable and "FriendChat_GUI.zip" in stable)

# ---------- 4) 앱이 스스로 아는가 ----------
import version  # noqa: E402

check("지금 버전 표기로 베타 여부를 판단한다",
      version.IS_BETA == ("beta" in version.APP_VERSION.lower()),
      (version.APP_VERSION, version.IS_BETA))

# 베타인 척하고 모듈들을 다시 읽어 실제로 갈라지는지 본다
real_version = version.APP_VERSION
try:
    version.APP_VERSION = "9.9.9-beta.1"
    version.IS_BETA = True

    import gui.theme as theme  # noqa: E402
    import single_instance  # noqa: E402

    importlib.reload(theme)
    importlib.reload(single_instance)
    check(f"베타면 제목에 표시가 붙는다({theme.APP_TITLE})", "베타" in theme.APP_TITLE,
          theme.APP_TITLE)
    check(f"베타면 중복실행 자리가 다르다({single_instance.INSTANCE_KEY})",
          single_instance.INSTANCE_KEY.endswith("-beta"), single_instance.INSTANCE_KEY)

    import gui.update_flow as update_flow  # noqa: E402

    importlib.reload(update_flow)

    class _FakePage:
        def set_status(self, _text):
            raise AssertionError("베타인데 업데이트를 시작하려 했다")

    # 배포본인 척해야 업데이트 경로까지 들어간다(소스 실행은 원래 건너뜀)
    was_frozen = getattr(_sys, "frozen", False)
    _sys.frozen = True
    try:
        started = update_flow.check_and_apply(_FakePage())
    finally:
        if was_frozen:
            _sys.frozen = was_frozen
        else:
            del _sys.frozen
    check("베타는 자동 업데이트를 하지 않는다(정식 버전으로 덮이면 안 됨)", started is False,
          started)
finally:
    version.APP_VERSION = real_version
    version.IS_BETA = "beta" in real_version.lower()
    import gui.theme as theme  # noqa: E402

    importlib.reload(theme)
    import single_instance  # noqa: E402

    importlib.reload(single_instance)
    import gui.update_flow as update_flow  # noqa: E402

    importlib.reload(update_flow)

check(f"되돌린 뒤 제목이 정상({theme.APP_TITLE})", "베타" not in theme.APP_TITLE
      or version.IS_BETA, theme.APP_TITLE)

# ---------- 5) 끊을 때 서버에 알리는가 ----------
# 안 알리고 소켓만 닫으면 채널 목록에 유령처럼 남아 있다가 한참 뒤 "Ping timeout"으로 나간다
from chat_core.session import build_session  # noqa: E402

irc_sent = []
irc_session = build_session("irc", "h", 1, transport=irc_sent.append, on_event=lambda e: None)
irc_session.my_id = "몽키"
irc_session.disconnect_gracefully("종료")
check(f"IRC는 나가기 전에 QUIT을 보낸다({irc_sent})",
      len(irc_sent) == 1 and irc_sent[0].startswith("QUIT"), irc_sent)
check("남긴 말도 함께 보낸다", "종료" in irc_sent[0], irc_sent)

custom_sent = []
custom_session = build_session("custom", "h", 1, transport=custom_sent.append,
                               on_event=lambda e: None)
custom_session.my_id = "몽키"
custom_session.disconnect_gracefully("종료")
check("우리 서버에는 따로 보낼 것이 없다(끊기면 바로 앎)", not custom_sent, custom_sent)

not_logged_in = []
fresh = build_session("irc", "h", 1, transport=not_logged_in.append, on_event=lambda e: None)
fresh.disconnect_gracefully("종료")
check("로그인 전에는 아무 것도 안 보낸다(보낼 상대가 없음)", not not_logged_in, not_logged_in)

print("=== 검증 결과 (테스트 배포 채널 분리) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
