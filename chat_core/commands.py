"""슬래시 명령(/me, /notice ...)의 파싱과 명세 - 프로토콜과 무관한 부분만.

명령을 실제로 "실행"하는 건 프로토콜 전략이 담당한다. 프로토콜마다 실제로 할 수 있는 게
다르기 때문(예: /whois는 IRC 서버만 답할 수 있고, 커스텀 서버는 그런 개념 자체가 없음).
여기 있는 건 어느 프로토콜에서나 같은 것들뿐이다:

- 입력 문자열이 명령인지 판별하고 이름/인자로 분해
- 명령 목록 메타데이터(CommandSpec) - 자동완성 목록과 /help 출력이 같은 출처를 쓰게 함
- 행동(/me)/공지(/notice) 메시지의 CTCP 프레이밍

프레이밍을 굳이 쓰는 이유: 커스텀 서버(server.py)는 채팅 텍스트를 해석하지 않고 그대로
중계만 하므로, IRC가 쓰는 것과 같은 \\x01태그 내용\\x01 형식을 그대로 태워 보내면 수신
쪽 렌더링 코드를 프로토콜별로 따로 만들 필요가 없다(IRC의 실제 CTCP ACTION과도 호환됨).
"""
from dataclasses import dataclass

COMMAND_PREFIX = "/"

CTCP_DELIM = "\x01"
ACTION_TAG = "ACTION"  # IRC 표준 CTCP - 다른 IRC 클라이언트도 그대로 알아봄
NOTICE_TAG = "FCNOTICE"  # 커스텀 서버에는 NOTICE 개념이 없어서 우리끼리 쓰는 태그

KIND_CHAT = "chat"
KIND_ACTION = "action"
KIND_NOTICE = "notice"

# 이모티콘 표시. 문장 중간에 섞여 들어가므로 \x01...\x01(CTCP)은 쓸 수 없다 - 그건 "이 줄
# 전체가 숨김 프레임"이라는 뜻이라 아바타 처리 경로에 걸려 채팅이 통째로 사라진다.
# 대신 유니코드 사용자 영역(어떤 글꼴에도 정의가 없어 일반 문자와 절대 안 겹치는 구간)을
# 여는/닫는 기호로 쓴다. 우리 클라이언트는 이 자리에 작은 그림을 그리고, 다른 IRC
# 클라이언트에서는 알 수 없는 글자 하나로 보인다(그림은 안 보이지만 대화는 안 깨짐).
EMOJI_OPEN = "\ue000"
EMOJI_CLOSE = "\ue001"


def format_emoji(url: str) -> str:
    """메시지에 넣을 이모티콘 표시. 주소만 실어 보낸다(보관함 목록은 안 보냄)."""
    return f"{EMOJI_OPEN}{url}{EMOJI_CLOSE}"


def split_emoji_parts(text: str) -> list[tuple[str, str]]:
    """메시지를 [("text", 글자), ("emoji", 주소), ...] 로 분해.

    표시가 없으면 [("text", 원문)] 하나만 나온다. 짝이 안 맞는 표시(잘렸거나 남의
    클라이언트가 흉내낸 경우)는 그냥 글자로 취급해서 대화가 사라지지 않게 한다.
    """
    if EMOJI_OPEN not in text:
        return [("text", text)]
    parts: list[tuple[str, str]] = []
    rest = text
    while True:
        before, sep, after = rest.partition(EMOJI_OPEN)
        if not sep:
            if before:
                parts.append(("text", before))
            break
        url, close, remainder = after.partition(EMOJI_CLOSE)
        if not close:
            # 닫는 표시가 없음 - 원문 그대로 보여준다
            parts.append(("text", before + EMOJI_OPEN + after))
            break
        if before:
            parts.append(("text", before))
        parts.append(("emoji", url) if url else ("text", ""))
        rest = remainder
    return [p for p in parts if p[1] or p[0] == "emoji"]


@dataclass(frozen=True)
class CommandSpec:
    """자동완성 목록과 /help가 공유하는 명령 설명. 여기 없는 명령은 자동완성에도 안 뜸."""
    name: str
    usage: str
    help: str

    @property
    def token(self) -> str:
        return COMMAND_PREFIX + self.name


def parse_command(text: str) -> tuple[str, str] | None:
    """'/me 춤춘다' -> ('me', '춤춘다'). 명령이 아니면 None.

    '//abc'처럼 슬래시를 두 개 쓰면 명령이 아니라 '/abc'라는 평문을 보내겠다는 뜻이므로
    여기서는 None을 돌려주고, 앞 슬래시 하나를 떼는 건 escape_literal()이 담당한다.
    """
    if not text.startswith(COMMAND_PREFIX):
        return None
    body = text[1:]
    if not body or body[0].isspace() or body.startswith(COMMAND_PREFIX):
        return None
    name, _, args = body.partition(" ")
    return name.lower(), args.strip()


def escape_literal(text: str) -> str:
    """'//공지사항' -> '/공지사항' (명령으로 해석되지 않게 하는 탈출 표기)"""
    if text.startswith(COMMAND_PREFIX * 2):
        return text[1:]
    return text


def _frame(tag: str, text: str) -> str:
    return f"{CTCP_DELIM}{tag} {text}{CTCP_DELIM}"


def _unframe(tag: str, text: str) -> str | None:
    if not text or len(text) < 2 or not (text.startswith(CTCP_DELIM)
                                         and text.endswith(CTCP_DELIM)):
        return None
    inner = text[1:-1]
    prefix = tag + " "
    if not inner.startswith(prefix):
        return None
    return inner[len(prefix):]


def format_action(text: str) -> str:
    return _frame(ACTION_TAG, text)


def format_notice(text: str) -> str:
    return _frame(NOTICE_TAG, text)


def classify_message(text: str) -> tuple[str, str]:
    """수신한 채팅 텍스트를 (종류, 표시할 본문)으로 분해.

    ChatSession.deliver_message가 이 함수 하나만 거치면 두 프로토콜 모두 같은 규칙으로
    행동/공지 메시지를 구분하게 됨.
    """
    # 서버가 보낸 값은 통제할 수 없다 - 비어 있거나 글자가 아닐 수도 있다(실제로 겪었다:
    # {"type": "chat", "text": null} 한 줄에 앱이 터졌다)
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    action = _unframe(ACTION_TAG, text)
    if action is not None:
        return KIND_ACTION, action
    notice = _unframe(NOTICE_TAG, text)
    if notice is not None:
        return KIND_NOTICE, notice
    return KIND_CHAT, text


# ==================== 명령 명세 ====================
# 여기 정의만 하고, 어떤 프로토콜이 어떤 걸 지원하는지는 각 프로토콜 전략이 고름(OCP).

HELP = CommandSpec("help", "/help", "사용할 수 있는 명령 목록을 봅니다")
ME = CommandSpec("me", "/me <행동>", "행동 메시지를 보냅니다 (예: /me 커피 마시는 중)")
NOTICE = CommandSpec("notice", "/notice <내용>", "채널에 공지 형태로 보냅니다")
MSG = CommandSpec("msg", "/msg <닉네임> <내용>", "귓속말을 보냅니다")
JOIN = CommandSpec("join", "/join <채널> [비밀번호]", "다른 채널에 입장합니다")
PART = CommandSpec("part", "/part [채널]", "채널에서 나갑니다 (생략하면 지금 채널)")
NICK = CommandSpec("nick", "/nick <닉네임>", "닉네임을 바꿉니다")
NAMES = CommandSpec("names", "/names [채널]", "참여자 목록을 새로 받아옵니다")
TOPIC = CommandSpec("topic", "/topic [내용]", "채널 주제를 보거나 바꿉니다")
WHOIS = CommandSpec("whois", "/whois <닉네임>", "상대 정보를 조회합니다")
AWAY = CommandSpec("away", "/away [사유]", "자리비움을 켜거나(사유 입력) 끕니다(생략)")
INVITE = CommandSpec("invite", "/invite <닉네임> [채널]", "채널로 초대합니다")
KICK = CommandSpec("kick", "/kick <닉네임> [사유]", "채널에서 내보냅니다 (권한 필요)")
MODE = CommandSpec("mode", "/mode <대상> <모드>", "채널/사용자 모드를 바꿉니다")
LIST = CommandSpec("list", "/list", "서버의 채널 목록을 봅니다")
QUIT = CommandSpec("quit", "/quit [사유]", "서버 접속을 끊습니다")
RAW = CommandSpec("raw", "/raw <원문>", "IRC 명령을 그대로 보냅니다 (고급)")
