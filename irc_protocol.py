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

# 상대가 무슨 프로그램으로 접속했는지 알아내는 표준 방법(CTCP VERSION).
# \x01VERSION\x01을 귓속말로 보내면 클라이언트가 알아서 NOTICE로 답한다 - 사람이
# 아무 말도 안 하고 있어도 되고, 대부분의 클라이언트는 화면에 띄우지도 않는다.
# 답을 안 주는 경우도 있다(응답을 꺼둔 사람) - 그때는 그냥 모르는 채로 둔다
VERSION_CTCP_TAG = "VERSION"

# IRC 한 줄은 CR-LF 포함 512바이트를 넘을 수 없다(RFC 1459). 실제 서버는 넘는 줄을
# 그냥 잘라버리므로, 아바타를 한 줄에 다 실으면 조용히 깨진다(실측: 2028바이트를
# 보내면 510바이트로 잘려서 도착 -> 아이콘도 안 오고 잘린 쓰레기가 채팅에 그대로 뜸).
# 그래서 base64를 여러 조각으로 나눠 보내고 받는 쪽에서 다시 합친다.
#
# 조각 하나에 실을 payload 길이는 보수적으로 잡음. 서버가 붙이는 프리픽스
# (:nick!user@host )는 우리가 길이를 모르고 호스트명이 길면 100바이트가 넘기도 함:
#   512 - CRLF(2) - 프리픽스(~106) - "PRIVMSG <채널> :"(~60) - CTCP 부대비용(~21) ≈ 323
AVATAR_CHUNK_PAYLOAD = 300
IRC_LINE_LIMIT = 512

# 실측(16x16 아이콘): 단색 144자, 보통 그림 188자 -> 대부분 한 조각으로 끝남.
# 전 픽셀이 다른 색인 최악의 경우에만 5조각 정도가 됨.


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


# IRC 한 줄은 CR-LF 포함 512바이트를 넘을 수 없다(RFC 1459). 받는 쪽에는 서버가
# ":닉!사용자@호스트 " 를 앞에 붙여서 오므로 그 몫(넉넉히 100바이트)도 빼둬야 한다.
# 실측: 한글 150자 = 468바이트, 받는 쪽 기준 509바이트로 아슬아슬하게 걸린다
MAX_MESSAGE_BYTES = 380
# 한 번에 이 줄 수를 넘기면 서버가 홍수로 보고 끊을 수 있다. 그보다 긴 글은 보내지 않고
# 사용자에게 알린다(잘려 나가거나 접속이 끊기는 것보다 낫다)
MAX_MESSAGE_LINES = 8


def split_message(text: str, limit: int = MAX_MESSAGE_BYTES) -> list:
    """긴 글을 IRC 한 줄에 들어갈 크기로 나눈다.

    - **글자 중간을 자르지 않는다**(한글은 한 글자가 3바이트라 바이트로 자르면 깨진다)
    - 가능하면 띄어쓰기에서 자른다(단어가 두 줄로 쪼개지면 읽기 나쁘다)
    - 띄어쓰기가 없으면(한글은 흔하다) 들어가는 만큼 자른다
    """
    if not text:
        return []
    pieces = []
    rest = text
    while rest:
        if len(rest.encode("utf-8")) <= limit:
            pieces.append(rest)
            break
        # 들어갈 수 있는 글자 수를 찾는다(바이트가 아니라 글자 단위로)
        cut = len(rest)
        while len(rest[:cut].encode("utf-8")) > limit:
            cut = int(cut * limit / len(rest[:cut].encode("utf-8"))) or 1
            while cut < len(rest) and len(rest[:cut + 1].encode("utf-8")) <= limit:
                cut += 1
        space = rest.rfind(" ", 1, cut + 1)
        if space > cut // 2:          # 너무 앞에서 끊기지 않을 때만 띄어쓰기를 쓴다
            cut = space
        pieces.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return [piece for piece in pieces if piece]


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


def format_ping(token: str) -> str:
    """우리가 서버에 "살아 있냐"고 물어보는 줄. 살아 있으면 곧 PONG이 돌아온다."""
    return f"PING :{token}"


def format_names(channel: str) -> str:
    return f"NAMES {channel}"


def format_notice(target: str, text: str) -> str:
    return f"NOTICE {target} :{text}"


def format_topic(channel: str, topic: str | None = None) -> str:
    # topic 없이 보내면 "지금 주제가 뭐냐"는 질의, 주면 변경 요청
    if topic:
        return f"TOPIC {channel} :{topic}"
    return f"TOPIC {channel}"


def format_whois(nick: str) -> str:
    return f"WHOIS {nick}"


def format_away(reason: str | None = None) -> str:
    # 사유 없이 보내면 자리비움 해제
    if reason:
        return f"AWAY :{reason}"
    return "AWAY"


def format_invite(nick: str, channel: str) -> str:
    return f"INVITE {nick} {channel}"


def format_kick(channel: str, nick: str, reason: str | None = None) -> str:
    if reason:
        return f"KICK {channel} {nick} :{reason}"
    return f"KICK {channel} {nick}"


def format_mode(target: str, mode_args: str) -> str:
    return f"MODE {target} {mode_args}"


def format_list() -> str:
    return "LIST"


def parse_names_reply(msg: IrcMessage) -> list[str]:
    names = msg.trailing.split()
    return [n.lstrip("@+%~&") for n in names]


def normalize_channel(name: str) -> str:
    name = name.strip()
    if name and name[0] not in "#&+!":
        name = "#" + name
    return name


def format_ctcp_version_request(nick: str) -> str:
    """그 사람에게 '무슨 프로그램 쓰세요?'라고 묻는 줄."""
    return format_privmsg(nick, f"{CTCP_DELIM}{VERSION_CTCP_TAG}{CTCP_DELIM}")


def format_ctcp_version_reply(nick: str, version: str) -> str:
    """물어온 사람에게 우리 프로그램 이름을 돌려주는 줄.

    답은 반드시 NOTICE로 보낸다 - PRIVMSG로 답하면 상대 클라이언트가 그걸 또 다른
    CTCP 요청으로 보고 되받아치며 무한 반복될 수 있어서, RFC가 NOTICE를 못박아 뒀다.
    """
    return format_notice(nick, f"{CTCP_DELIM}{VERSION_CTCP_TAG} {version}{CTCP_DELIM}")


def is_ctcp_version_request(text: str) -> bool:
    return text.strip(CTCP_DELIM).strip().upper() == VERSION_CTCP_TAG


def parse_ctcp_version_reply(text: str) -> str | None:
    """'VERSION WeeChat 4.4.2' -> 'WeeChat 4.4.2'. 아니면 None."""
    if len(text) < 2 or not (text.startswith(CTCP_DELIM) and text.endswith(CTCP_DELIM)):
        return None
    inner = text[1:-1]
    prefix = VERSION_CTCP_TAG + " "
    if not inner.upper().startswith(prefix):
        return None
    value = inner[len(prefix):].strip()
    return value or None


def format_ctcp_avatar(target: str, avatar_b64: str) -> list[str]:
    """아바타를 512바이트 안에 들어가는 여러 줄로 나눠 반환.

    형식: \\x01FCAVATAR <전송id> <번호>/<총개수> <조각>\\x01
    대부분의 아이콘은 한 줄로 끝나고, 큰 것만 여러 줄이 된다.
    """
    chunks = [avatar_b64[i:i + AVATAR_CHUNK_PAYLOAD]
              for i in range(0, len(avatar_b64), AVATAR_CHUNK_PAYLOAD)] or [""]
    # 같은 사람이 아이콘을 연달아 바꿔도 이전 전송과 안 섞이게 하는 짧은 식별자
    transfer_id = f"{abs(hash(avatar_b64)) % 0xFFFF:04x}"
    total = len(chunks)
    return [
        format_privmsg(
            target,
            f"{CTCP_DELIM}{AVATAR_CTCP_TAG} {transfer_id} {index}/{total} {chunk}{CTCP_DELIM}",
        )
        for index, chunk in enumerate(chunks, start=1)
    ]


def is_ctcp_frame(text: str) -> bool:
    """우리끼리 쓰는 숨김 프레임인지. 잘려서 해석에 실패해도 채팅으로 새면 안 되므로,
    '완성된 프레임인지'가 아니라 '프레임처럼 생겼는지'로 판단한다."""
    return text.startswith(CTCP_DELIM)


def parse_ctcp_avatar(text: str) -> tuple[str, int, int, str] | None:
    """아이콘 CTCP 프레임을 (전송id, 번호, 총개수, 조각)으로 분해. 아니면 None.

    예전 버전이 보내던 조각 없는 형식(\\x01FCAVATAR <b64>\\x01)도 그대로 받아준다
    (그 경우 1/1짜리 전송으로 취급). 안 그러면 구버전 친구의 아이콘이 안 보임.
    """
    if len(text) < 2 or not (text.startswith(CTCP_DELIM) and text.endswith(CTCP_DELIM)):
        return None
    inner = text[1:-1]
    prefix = AVATAR_CTCP_TAG + " "
    if not inner.startswith(prefix):
        return None
    body = inner[len(prefix):]

    parts = body.split(" ", 2)
    if len(parts) == 3 and "/" in parts[1]:
        index_text, _, total_text = parts[1].partition("/")
        if index_text.isdigit() and total_text.isdigit():
            index, total = int(index_text), int(total_text)
            if 1 <= index <= total:
                return parts[0], index, total, parts[2]
    # 구버전 형식: 조각 정보 없이 base64만 들어있음
    return "legacy", 1, 1, body
