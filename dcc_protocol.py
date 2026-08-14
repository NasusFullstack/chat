"""파일을 사람끼리 직접 주고받는 규약(DCC) - 순수 문자열 처리만.

IRC에는 파일 전송이 없다. 대신 **서로의 주소를 채팅으로 알려주고 직접 연결**하는 방식이
오래전부터 쓰인다(DCC). 서버는 "나 이 파일 보낼게, 내 주소는 여기야" 한 줄만 전달하고,
**파일 자체는 서버를 거치지 않는다.** 그래서 몇십 MB도 서버에 부담이 없다.

    \\x01DCC SEND 파일이름 아이피(숫자) 포트 크기\\x01

주소를 숫자 하나로 적는 것이 규약이다(옛날 방식이라 그렇다). 예: 127.0.0.1 -> 2130706433

이 파일은 **글자만 다룬다** - 소켓도 파일도 열지 않는다. 그래야 네트워크 없이 시험할 수 있다.
"""
import ipaddress
import os
import re

DCC_TAG = "DCC"
CTCP_DELIM = "\x01"

# 파일 이름에 공백이 있으면 따옴표로 감싼다(규약)
_SEND_RE = re.compile(
    r'^DCC\s+SEND\s+(?:"([^"]+)"|(\S+))\s+(\d+)\s+(\d+)\s+(\d+)\s*$', re.IGNORECASE)

# 받은 이름을 그대로 쓰면 안 된다 - 상대가 정한 이름이라 경로가 섞여 들어올 수 있다
_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def ip_to_number(ip: str) -> int:
    """127.0.0.1 -> 2130706433 (규약이 요구하는 형식)."""
    return int(ipaddress.IPv4Address(ip))


def number_to_ip(number) -> str:
    """2130706433 -> 127.0.0.1. 이상한 값이면 빈 문자열."""
    try:
        return str(ipaddress.IPv4Address(int(number)))
    except (ValueError, ipaddress.AddressValueError, TypeError):
        return ""


def safe_filename(name: str) -> str:
    """상대가 보낸 이름을 그대로 믿지 않는다.

    경로가 섞여 있으면(`..\\..\\Windows\\system32\\...`) 엉뚱한 곳에 파일을 쓰게 된다.
    폴더 부분을 버리고, 파일 이름에 쓸 수 없는 글자도 지운다.
    """
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = _UNSAFE_NAME.sub("_", name).strip(". ")
    return name[:120] or "받은파일"


def format_send(filename: str, ip: str, port: int, size: int) -> str:
    """보내겠다는 알림 한 줄(CTCP)."""
    name = os.path.basename(filename)
    if " " in name:
        name = f'"{name}"'
    return f"{CTCP_DELIM}DCC SEND {name} {ip_to_number(ip)} {int(port)} {int(size)}{CTCP_DELIM}"


def parse_send(text: str) -> dict | None:
    """상대가 보낸 알림을 해석한다. 우리 것이 아니거나 이상하면 None.

    이상한 값(포트 0, 크기 음수, 사설망 주소 등)은 여기서 걸러낸다 - 이 판단을 화면 쪽에
    두면 나중에 다른 화면을 만들 때 또 빠뜨린다.
    """
    if not text or not text.startswith(CTCP_DELIM) or not text.endswith(CTCP_DELIM):
        return None
    match = _SEND_RE.match(text[1:-1].strip())
    if not match:
        return None
    quoted, bare, ip_number, port, size = match.groups()
    ip = number_to_ip(ip_number)
    port = int(port)
    size = int(size)
    if not ip or not (0 < port <= 65535) or size <= 0:
        return None
    return {
        "filename": safe_filename(quoted or bare),
        "ip": ip,
        "port": port,
        "size": size,
    }


def is_dcc(text: str) -> bool:
    return bool(text) and text.startswith(CTCP_DELIM + DCC_TAG + " ")
