"""표준 IRC(RFC 1459/2812) 클라이언트용 메시지 파싱/생성 - 순수 함수만, 소켓 I/O는 각 클라이언트가 담당
- GUI(gui_client.py)와 CLI(cli_client.py)가 공용으로 사용
"""
from dataclasses import dataclass

RPL_WELCOME = "001"
ERR_ERRONEUSNICKNAME = "432"
ERR_NICKNAMEINUSE = "433"
ERR_NICKCOLLISION = "436"
RPL_NAMREPLY = "353"
RPL_ENDOFNAMES = "366"

NICK_COLLISION_NUMERICS = {ERR_ERRONEUSNICKNAME, ERR_NICKNAMEINUSE, ERR_NICKCOLLISION}
CHANNEL_JOIN_ERROR_NUMERICS = {"403", "405", "471", "473", "474", "475"}

MAX_NICK_RETRIES = 3

# 아이콘 동기화: 실제 IRC 서버는 우리가 고칠 수 없으므로, PRIVMSG 안에 CTCP처럼
# \x01태그 내용\x01 형태로 숨겨 보내는 방식으로 우리 클라이언트끼리만 아이콘을 주고받음
# (예: /me 명령이 쓰는 ACTION CTCP와 같은 방식). 우리 클라이언트가 아닌 사람에게는
# 낯선 CTCP 요청으로 보일 뿐 - 대부분의 클라이언트는 조용히 무시/숨김 처리함.
CTCP_DELIM = "\x01"
AVATAR_CTCP_TAG = "FCAVATAR"


@dataclass
class IrcMessage:
    prefix: str | None
    command: str
    params: list[str]
    raw: str

    @property
    def source_nick(self) -> str:
        if not self.prefix:
            return ""
        if "!" in self.prefix:
            return self.prefix.split("!", 1)[0]
        return self.prefix

    @property
    def trailing(self) -> str:
        return self.params[-1] if self.params else ""


def parse_line(line: str) -> IrcMessage:
    raw = line
    line = line.strip("\r\n")

    # IRCv3 메시지 태그(@key=value;...)는 협상하지 않으므로 건너뜀
    if line.startswith("@"):
        _, _, line = line.partition(" ")

    prefix = None
    if line.startswith(":"):
        prefix, _, line = line[1:].partition(" ")

    if " :" in line:
        head, _, trailing = line.partition(" :")
        parts = head.split()
        params = parts + [trailing]
    elif line.startswith(":"):
        params = [line[1:]]
    else:
        params = line.split()

    command = params[0] if params else ""
    params = params[1:]

    return IrcMessage(prefix=prefix, command=command, params=params, raw=raw)


def encode_line(text: str) -> bytes:
    return (text + "\r\n").encode("utf-8", errors="replace")


def format_pass(password: str) -> str:
    return f"PASS {password}"


def format_nick(nick: str) -> str:
    return f"NICK {nick}"


def format_user(username: str, realname: str) -> str:
    return f"USER {username} 0 * :{realname}"


def format_join(channel: str, key: str | None = None) -> str:
    if key:
        return f"JOIN {channel} {key}"
    return f"JOIN {channel}"


def format_privmsg(target: str, text: str) -> str:
    return f"PRIVMSG {target} :{text}"


def format_part(channel: str, reason: str | None = None) -> str:
    if reason:
        return f"PART {channel} :{reason}"
    return f"PART {channel}"


def format_quit(reason: str | None = None) -> str:
    if reason:
        return f"QUIT :{reason}"
    return "QUIT"


def format_pong(token: str) -> str:
    return f"PONG :{token}"


def format_names(channel: str) -> str:
    return f"NAMES {channel}"


def parse_names_reply(msg: IrcMessage) -> list[str]:
    names = msg.trailing.split()
    return [n.lstrip("@+%~&") for n in names]


def normalize_channel(name: str) -> str:
    name = name.strip()
    if name and name[0] not in "#&+!":
        name = "#" + name
    return name


def format_ctcp_avatar(target: str, avatar_b64: str) -> str:
    return format_privmsg(target, f"{CTCP_DELIM}{AVATAR_CTCP_TAG} {avatar_b64}{CTCP_DELIM}")


def parse_ctcp_avatar(text: str) -> str | None:
    """PRIVMSG의 trailing 텍스트가 우리 아이콘 CTCP 태그면 base64 부분을 반환, 아니면 None"""
    if len(text) < 2 or not (text.startswith(CTCP_DELIM) and text.endswith(CTCP_DELIM)):
        return None
    inner = text[1:-1]
    prefix = AVATAR_CTCP_TAG + " "
    if not inner.startswith(prefix):
        return None
    return inner[len(prefix):]
