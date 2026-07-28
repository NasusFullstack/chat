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
