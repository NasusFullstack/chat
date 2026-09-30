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


def group_id(protocol: str, host: str, port: int) -> str:
    """이모티콘을 같이 쓰는 무리 - 같은 채팅 서버에 붙어 있는 사람들."""
    return _place("group", protocol, host, port, "")


# 지금 어느 채팅 서버에 붙어 있는가. **창이 접속할 때마다 여기에 적어둔다.**
#
# 모듈에 값을 두는 게 마뜩잖지만, 이모티콘을 저장하는 자리(채팅에 뜬 그림의 우클릭
# 메뉴)는 화면 맨 끝에 있는 부품이라 접속 정보를 알 길이 없다. 거기까지 값을 들고
# 내려가려면 부품 네댓 개의 생성자를 다 고쳐야 하는데, 그건 "부품은 자기 일만 안다"는
# 규칙을 더 크게 어기는 일이다. 어차피 한 번에 한 서버에만 붙으므로 사실도 하나뿐이다.
_current_group = ""


def set_current_group(group: str):
    global _current_group
    _current_group = group or ""


def current_group() -> str:
    return _current_group


# 우리 서버에 올린 파일 주소인가, 그렇다면 그 파일의 id는 무엇인가.
# 채팅에 뜬 주소를 보고 "이건 파일 카드로 그려야 한다"를 판단하는 데 쓴다
_FILE_PREFIX = f"{SERVER}/files/"


def file_id_from(url: str) -> str:
    """우리 서버 파일 주소면 그 id, 아니면 빈 값."""
    if not url or not url.startswith(_FILE_PREFIX):
        return ""
    rest = url[len(_FILE_PREFIX):]
    file_id = rest.split("/", 1)[0].split("?", 1)[0]
    # id는 24자리 16진수다. 여기서 걸러야 /files/emoji 같은 다른 경로를 파일로 오인하지 않는다
    if len(file_id) != ID_CHARS or any(c not in "0123456789abcdef" for c in file_id):
        return ""
    return file_id


def meta_url(file_id: str) -> str:
    return f"{SERVER}/files/{file_id}/meta"
