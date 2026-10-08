"""지금 **무엇을 열어두나** - 한 곳에서 정한다(위젯도 소켓도 모르는 순수 표).

당분간 막아둔 것들(2026-10-08 사용자 요청):

- **춥채팅 서버 / 친구 채팅 서버(커스텀)**: 로그인 화면 고르는 칸에 **보이기는 하되
  못 고른다.** 춥채팅 서버는 jsserv 에서 꺼뒀고(2026-10-06), 커스텀 서버는 띄워둔
  곳이 없다. 고를 수 있게 두면 "눌렀는데 안 붙는다"가 된다
- **사진·파일 올리기**: pdlab IRC 의 `#pdlab` 채널에서만 된다

되살리는 법: 아래 표 두 개만 고치면 된다. 화면 쪽은 이 표를 묻기만 하므로 손댈 곳이
없다. **모바일에도 같은 표가 있다**(`mobile/lib/core/availability.dart`) - 한쪽만 고치면
PC 와 폰이 다르게 막는다(`tests/test_availability.py` 가 둘을 대조한다).
"""

import os

# **검사는 막아둔 길까지 전부 시험한다.** 막아둔 동안 아무도 안 돌려보면 다시 열 때
# 깨진 걸 모른다 - 커스텀 서버로 붙는 검사가 수십 개다. 러너(tests/run_all.py)가
# 이 값을 켠다. 막혔는지 자체는 tests/test_availability.py 가 이 값을 끄고 본다
OPEN_ALL_ENV = "CHUPCHAT_OPEN_ALL"


def _open_all() -> bool:
    return os.environ.get(OPEN_ALL_ENV) == "1"


# 로그인 화면에서 고를 수 있는 쪽. 여기 없는 쪽은 **보이되 흐리게** 둔다
ENABLED_PROTOCOLS = frozenset({"irc"})

# 사진·파일을 올릴 수 있는 방 - (프로토콜, 서버 주소, 채널).
# 포트는 안 본다 - 같은 서버에 평문(6667)·보안(6697) 두 길로 붙을 수 있다
UPLOAD_ROOMS = frozenset({
    ("irc", "home.pdlab.kr", "#pdlab"),
})

# 막혔을 때 사람에게 보여줄 말. 왜 안 되는지 모르면 고장난 줄 안다
UPLOAD_BLOCKED_TEXT = "지금은 #pdlab 채널에서만 사진·파일을 올릴 수 있습니다."
PROTOCOL_BLOCKED_TEXT = "지금은 실제 IRC 서버만 쓸 수 있습니다."


def protocol_enabled(protocol: str) -> bool:
    """로그인 화면에서 이쪽을 고를 수 있나."""
    return _open_all() or protocol in ENABLED_PROTOCOLS


def upload_allowed(protocol: str, host: str, channel: str) -> bool:
    """이 방에서 사진·파일을 올릴 수 있나.

    **대소문자를 안 가린다** - IRC 는 채널 이름(#PDLab 과 #pdlab)도 서버 주소도
    대소문자를 안 가린다. 가리면 같은 방인데 어떤 때는 되고 어떤 때는 안 된다.
    """
    if _open_all():
        return True
    key = ((protocol or "").lower(), (host or "").strip().lower(),
           (channel or "").strip().lower())
    return key in UPLOAD_ROOMS
