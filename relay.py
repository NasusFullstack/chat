"""중계 서버(jsserv)의 주소와 자리 이름 - 순수 모듈(Qt도 네트워크도 모름).

## 왜 따로 두는가
중계 서버 주소가 전투(`gui/battle/net.py`)와 파일 올리기(`gui/uploader.py`)에 각각
적혀 있었다. 여기에 채팅 기록과 프로필까지 붙으면 네 군데가 되는데, 서버를 옮기는 날
하나만 빠뜨려도 그 기능만 조용히 안 된다. 한 곳에서 정한다.

## 자리 이름(id)을 왜 해시로 만드는가
중계 서버는 **빌려 쓰는 남의 서버**다. 거기에 `#우리방`이나 `몽키` 같은 이름을 그대로
적으면, 우리가 어느 채팅방을 쓰고 누가 있는지가 그 디스크에 남는다. 해시로 바꿔 보내면
서버는 "24자짜리 자리" 하나로만 알고, 우리는 같은 값을 다시 계산할 수 있으므로 아쉬울
것이 없다.

서버 주소까지 넣고 해시하므로 **서버가 다르면 같은 이름이라도 다른 자리**가 된다
(어느 IRC 서버에나 있는 `#general`이 한 자리에 뒤섞이면 안 된다).

IRC는 채널 이름과 닉네임의 대소문자를 구분하지 않는다. 그래서 `#General`과 `#general`이
다른 자리가 되지 않도록 낮춰서 해시한다.
"""
import hashlib

SERVER = "https://jsserv.pdlab.kr"
WS_SERVER = "wss://jsserv.pdlab.kr"

BATTLE_URL = f"{WS_SERVER}/battle/ws"
FILES_URL = f"{SERVER}/files"
LOGS_URL = f"{SERVER}/logs"
PROFILES_URL = f"{SERVER}/profiles"

# 서버가 받아주는 자리 이름 길이. 서버 쪽 정규식(^[0-9a-f]{24}$)과 같아야 한다
ID_CHARS = 24


def _place(kind: str, protocol: str, host: str, port: int, name: str) -> str:
    raw = f"{kind}|{protocol}|{host.casefold()}|{int(port)}|{name.casefold()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:ID_CHARS]


def room_id(protocol: str, host: str, port: int, channel: str) -> str:
    """그 서버 그 채널의 기록이 쌓이는 자리."""
    return _place("room", protocol, host, port, channel)


def who_id(protocol: str, host: str, port: int, nick: str) -> str:
    """그 서버의 그 사람 프로필이 놓이는 자리."""
    return _place("who", protocol, host, port, nick)
