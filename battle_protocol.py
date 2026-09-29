"""배틀크루저 전투 규약 - 순수 처리만(소켓도 파일도 열지 않는다).

## 어떻게 붙는가
IRC로는 실시간이 안 된다. 한 줄 512바이트 제한에 더해, 서버가 홍수로 보고 끊거나
일부러 늦춘다(fake-lag). 그래서 전투 중에만 **중계 서버에 따로 붙는다.**

    나 ─┐
    A ──┼─> 중계 서버(jsserv)
    B ──┘

**평소에는 아무도 접속하지 않는다.** 치트를 친 순간에만 붙었다가 전투가 끝나면 끊는다.

직접 연결(P2P)도 검토했는데 두 가지가 걸려서 접었다. 하나는 상대에게 내 IP가 드러나는
것이고, 더 큰 건 **둘 다 공유기 뒤에 있으면 아예 안 붙는다**는 것이다(실사용의 절반이
그렇다). 중계로 가면 양쪽 다 밖으로 나가기만 하므로 둘 다 사라진다.

## 채팅으로는 방 번호만 오간다
주소는 어디에도 안 실린다. 채널에 CTCP 한 줄로 **방 번호**만 알린다.

    \\x01CHUPBATTLE ROOM <방번호>\\x01

방 번호는 난수라서, 채널 밖 사람은 알 수 없다(중계 서버에 붙어도 방을 못 찾는다).

## 지켜야 할 것 - 여기서 한 번에 정한다
받는 값은 **전부 남이 정한 값**이다. 중계 서버가 보낸 것도 마찬가지로 믿지 않는다.
판단을 화면 쪽에 두면 새 화면을 만들 때 또 빠뜨리므로(아이콘 CTCP 때 실제로 그랬다)
규칙을 이 파일에 모아둔다.

1. 방 번호가 맞아야 들어간다 - 채팅으로만 알려주므로 채널 밖 사람은 모른다
2. 정원 4명. 넘으면 거절한다
3. 한 줄 길이·초당 줄 수·전체 바이트에 상한. 넘으면 끊는다
4. 모르는 값/범위 밖 값은 조용히 버린다(예외를 던져 화면을 멈추지 않는다)
5. **남의 배는 못 움직인다** - 조작은 '어느 연결로 왔는가'로만 기록한다.
   보낸 쪽이 적어 보낸 자리 번호는 믿지 않는다
6. 글자는 표시용으로만 쓴다(길이 제한 + 제어문자 제거). 경로로도 명령으로도 쓰지 않는다

이 파일은 **중계 서버(jsserv 레포)와 같은 규약을 쓴다.** 고칠 일이 있으면 여기가
원본이고 그쪽이 사본이다 - 한쪽만 고치면 서로 말이 안 통한다.
"""
import json
import re
import secrets

# ---- 규모 상한 --------------------------------------------------------------
# 사람은 6명까지, 연습 상대(AI)를 6대까지 더 넣어 한 방에 12대가 싸운다.
# 자리 번호는 사람이 0~5, 연습 상대가 6~11로 나뉜다 - 번호만 보고도 누가 뭔지 알 수 있어야
# 서버가 "이 자리를 누가 조종할 수 있는가"를 판단할 수 있다
MAX_HUMANS = 6
MAX_BOTS = 6
MAX_PLAYERS = MAX_HUMANS + MAX_BOTS


def is_bot_slot(slot: int) -> bool:
    """연습 상대 자리인가(방장이 대신 조종한다)."""
    return MAX_HUMANS <= slot < MAX_PLAYERS
MAX_LINE_BYTES = 512      # 한 줄 상한(IRC와 같은 값으로 맞춰 둔다 - 넘을 이유가 없다)
MAX_LINES_PER_SEC = 30    # 한 연결이 초당 보낼 수 있는 줄 수
MAX_SESSION_BYTES = 4 * 1024 * 1024   # 한 연결이 한 판에 보낼 수 있는 전체 바이트
MAX_NICK_LEN = 24
MIN_PLAYERS = 2           # 혼자서는 전투가 안 된다(연습 상대를 넣으면 혼자서도 된다)

# 배 색은 **번호로만** 주고받는다(자유 글자로 받으면 화면에 그대로 그려질 값이 되므로).
# 실제 색은 화면 쪽 표에서 고른다 - 여기는 "몇 번인가"만 안다.
# 마지막 번호는 숨겨진 무지개(색이 계속 바뀐다). 규약 입장에서는 그냥 색 하나다
COLOR_COUNT = 21          # 20가지 + 숨겨진 무지개
RAINBOW_COLOR = COLOR_COUNT - 1

# ---- 조작 -------------------------------------------------------------------
# 누른 키를 비트 하나씩으로 적는다. 숫자 하나라 검사도 쉽다(범위 밖이면 버린다)
KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, KEY_FIRE = 1, 2, 4, 8, 16
KEY_MASK = KEY_LEFT | KEY_RIGHT | KEY_UP | KEY_DOWN | KEY_FIRE

# **포탄은 주고받지 않는다.** 발사도 키 하나로 보내고, 받은 쪽이 같은 계산을 해서
# 같은 포탄을 그린다. 포탄 하나하나를 실어 보내면 줄 수가 몇 배로 늘어나는데,
# 배틀크루저는 이미 '눌린 키 -> 물리 계산 -> 위치'로만 움직이므로 그럴 이유가 없다.
# 대신 계산이 모두에게 같아야 하므로, 판정은 **자기 배에 대해서만** 한다(아래 HIT 설명)

# 틱 번호 상한 - 한 판이 이보다 길어질 수 없다(약 60fps로 9시간)
MAX_TICK = 2_000_000

# 체력 상한 - 보고에 실린 값이 말이 되는지 보는 데 쓴다(실제 값은 battle_sim이 정한다)
MAX_HP = 5000

CTCP_DELIM = "\x01"
BATTLE_TAG = "CHUPBATTLE"

_ROOM_RE = re.compile(r"^CHUPBATTLE\s+ROOM\s+([0-9a-f]{8,64})\s*$", re.IGNORECASE)
_ROOM_OK = re.compile(r"^[0-9a-f]{8,64}$")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def new_room() -> str:
    """이 판에만 쓰는 방 번호(난수). 이걸 모르면 방에 못 들어온다."""
    return secrets.token_hex(12)


def is_room_id(value) -> bool:
    return isinstance(value, str) and bool(_ROOM_OK.match(value.lower()))


def safe_nick(nick: str) -> str:
    """상대가 보낸 이름은 화면에 그리기만 한다 - 제어문자를 걷어내고 길이를 자른다.

    IRC 색/굵게 제어문자가 그대로 들어오면 화면이 깨지고(실제로 겪었다), 긴 이름은
    전투 화면을 밀어낸다.
    """
    cleaned = _CONTROL_CHARS.sub("", nick or "").strip()
    return cleaned[:MAX_NICK_LEN] or "손님"


# ---- 채팅에 올리는 한 줄(방 번호만) ------------------------------------------
def format_room_notice(room: str) -> str:
    """"이 방으로 와라" - 채널에 올리는 CTCP 한 줄. **주소는 담기지 않는다.**"""
    return f"{CTCP_DELIM}{BATTLE_TAG} ROOM {room}{CTCP_DELIM}"


def parse_room_notice(text: str) -> str:
    """채널에서 받은 한 줄에서 방 번호를 꺼낸다. 우리 것이 아니면 빈 문자열."""
    if not text or not text.startswith(CTCP_DELIM) or not text.endswith(CTCP_DELIM):
        return ""
    match = _ROOM_RE.match(text[1:-1].strip())
    return match.group(1).lower() if match else ""


def is_battle_notice(text: str) -> bool:
    return bool(text) and text.startswith(f"{CTCP_DELIM}{BATTLE_TAG} ")


# ---- 중계 서버와 주고받는 줄 -------------------------------------------------
# 무엇이 올 수 있는지를 표로 못 박는다. 표에 없는 종류는 버린다(새 종류를 추가할 때
# 검사를 빠뜨리지 않게 - 검사 없는 종류는 애초에 통과하지 못한다)
JOIN, WELCOME, DENY, JOINED, LEFT = "join", "welcome", "deny", "joined", "left"
START, STARTED = "start", "started"
INPUT, PEER_INPUT = "in", "peer"
# 연습 상대(AI) 자리를 대신 조종하는 것. **방을 연 사람만** 보낼 수 있고, **AI 자리에만**
# 먹힌다(서버가 둘 다 확인한다). 남의 배를 못 움직인다는 규칙은 그대로다.
#
# 왜 이 예외가 필요한가: AI가 모두의 화면에서 **똑같이** 움직여야 한다. 각자 계산하면
# 조작이 도착하는 시점이 사람마다 달라 AI 위치가 갈린다. 그래서 한 사람(방장)이
# 계산해서 그 결과를 모두에게 넘긴다 - 사람 배를 다루는 방식과 같다
BOT_INPUT = "botin"
BOT_HIT, BOT_DEAD = "bothit", "botdead"
HIT, PEER_HIT = "hit", "peerhit"
DEAD, PEER_DEAD = "dead", "peerdead"
BYE = "bye"

# 맞았다/격추됐다는 **자기 배에 대해서만** 말한다(보내는 쪽은 `by`만 적는다).
# 중계 서버가 '어느 연결로 왔는가'를 보고 자리 번호를 붙여 모두에게 넘긴다.
# 그래서 "쟤가 죽었다"고 남의 배를 대신 신고할 수 없다


def encode(message: dict) -> bytes:
    """한 줄로 만든다. 상한을 넘으면 빈 값(보내는 쪽에서 막는다)."""
    line = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(line) + 1 > MAX_LINE_BYTES:
        return b""
    return line + b"\n"


def _as_int(value, low: int, high: int):
    """정수이고 범위 안이면 그 값, 아니면 None.

    bool을 따로 막는 이유: 파이썬에서 True는 정수 1로 통과해버린다.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if low <= value <= high else None


def decode(line: bytes) -> dict | None:
    """받은 한 줄을 해석하고 **전부 검사한다.** 조금이라도 이상하면 None.

    걸러야 할 것: 너무 긴 줄, 깨진 글자, JSON이 아닌 것, 표에 없는 종류,
    범위를 벗어난 숫자, 자료형이 다른 값.
    """
    if not line or len(line) > MAX_LINE_BYTES:
        return None
    try:
        message = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(message, dict):
        return None
    checker = _CHECKERS.get(message.get("t"))
    return checker(message) if checker is not None else None


def _check_join(message):
    """방에 들어가겠다 - 방 번호와 함께 쓰고 싶은 색을 말한다.

    정원(cap)은 **방을 처음 연 사람만** 정할 수 있다(중계 서버가 그렇게 다룬다).
    나중에 들어온 사람이 적어 보내도 무시된다.
    """
    room = message.get("room")
    if not is_room_id(room):
        return None
    color = _as_int(message.get("color"), 0, COLOR_COUNT - 1)
    cap = _as_int(message.get("cap"), MIN_PLAYERS, MAX_HUMANS)
    bots = _as_int(message.get("bots"), 0, MAX_BOTS)
    return {
        "t": JOIN,
        "room": room.lower(),
        "nick": safe_nick(message.get("nick", "")),
        "color": 0 if color is None else color,
        # 사람 정원과 연습 상대 수는 **방을 연 사람만** 정한다(서버가 그렇게 다룬다)
        "cap": MAX_HUMANS if cap is None else cap,
        "bots": 0 if bots is None else bots,
    }


def _player_entry(entry):
    if not isinstance(entry, dict):
        return None
    slot = _as_int(entry.get("slot"), 0, MAX_PLAYERS - 1)
    color = _as_int(entry.get("color"), 0, COLOR_COUNT - 1)
    if slot is None:
        return None
    return {"slot": slot, "nick": safe_nick(entry.get("nick", "")),
            "color": 0 if color is None else color}


def _check_welcome(message):
    slot = _as_int(message.get("slot"), 0, MAX_PLAYERS - 1)
    tick = _as_int(message.get("tick"), 0, MAX_TICK)
    cap = _as_int(message.get("cap"), MIN_PLAYERS, MAX_HUMANS)
    color = _as_int(message.get("color"), 0, COLOR_COUNT - 1)
    players = message.get("players")
    if slot is None or tick is None or cap is None or color is None:
        return None
    if not isinstance(players, list) or len(players) > MAX_PLAYERS:
        return None
    cleaned = []
    for entry in players:
        parsed = _player_entry(entry)
        if parsed is None:
            return None
        cleaned.append(parsed)
    bots = _as_int(message.get("bots"), 0, MAX_BOTS)
    return {"t": WELCOME, "slot": slot, "tick": tick, "cap": cap,
            "color": color, "players": cleaned, "bots": 0 if bots is None else bots,
            "started": bool(message.get("started"))}


def _check_deny(message):
    why = message.get("why")
    return {"t": DENY, "why": safe_nick(why) if isinstance(why, str) else "들어갈 수 없습니다"}


def _check_joined(message):
    entry = _player_entry(message)
    return None if entry is None else {"t": JOINED, **entry}


def _check_start(_message):
    """시작하자 - 방을 연 사람만 보낼 수 있다(중계 서버가 확인한다)."""
    return {"t": START}


def _check_started(_message):
    return {"t": STARTED}


def _check_left(message):
    slot = _as_int(message.get("slot"), 0, MAX_PLAYERS - 1)
    if slot is None:
        return None
    return {"t": LEFT, "slot": slot}


def _check_input(message):
    tick = _as_int(message.get("tick"), 0, MAX_TICK)
    keys = _as_int(message.get("keys"), 0, KEY_MASK)
    if tick is None or keys is None:
        return None
    # 자리 번호는 **일부러 안 받는다.** 중계 서버가 '어느 연결로 왔는가'로 정한다
    # (남의 배를 움직이겠다고 적어 보내도 소용없게)
    return {"t": INPUT, "tick": tick, "keys": keys}


def _check_peer_input(message):
    slot = _as_int(message.get("slot"), 0, MAX_PLAYERS - 1)
    tick = _as_int(message.get("tick"), 0, MAX_TICK)
    keys = _as_int(message.get("keys"), 0, KEY_MASK)
    if slot is None or tick is None or keys is None:
        return None
    return {"t": PEER_INPUT, "slot": slot, "tick": tick, "keys": keys}


def _own_report(kind):
    """'내 배가 누구에게 당했다' - 자리 번호를 안 받는다(남의 배를 대신 신고 못 하게).

    **남은 체력을 같이 보낸다.** 처음에는 "맞았다"만 보냈는데, 받는 쪽이 얼마나
    깎을지 몰라 최대치를 깎았다. 기를 모은 정도에 따라 70~260으로 달라지므로,
    약하게 두 대 맞은 배가 남의 화면에서만 죽어 **보이지도 맞지도 않는 유령**이 됐다.
    남은 체력을 그대로 실어 보내면 받는 쪽은 그 값으로 맞추기만 하면 되고,
    중간에 한 줄을 놓쳐도 다음 보고에서 저절로 맞는다.
    """
    def check(message):
        by = _as_int(message.get("by"), 0, MAX_PLAYERS - 1)
        hp = _as_int(message.get("hp"), 0, MAX_HP)
        return None if by is None or hp is None else {"t": kind, "by": by, "hp": hp}
    return check


def _relayed_report(kind):
    """중계 서버가 자리 번호를 붙여 넘겨준 것."""
    def check(message):
        slot = _as_int(message.get("slot"), 0, MAX_PLAYERS - 1)
        by = _as_int(message.get("by"), 0, MAX_PLAYERS - 1)
        hp = _as_int(message.get("hp"), 0, MAX_HP)
        if slot is None or by is None or hp is None:
            return None
        return {"t": kind, "slot": slot, "by": by, "hp": hp}
    return check


def _bot_report(kind, with_keys: bool):
    """방장이 연습 상대 대신 보내는 것 - 여기서는 **AI 자리인지만** 본다.

    보낸 사람이 정말 방장인지는 서버가 판단한다(연결을 아는 건 서버뿐이다).
    """
    def check(message):
        slot = _as_int(message.get("slot"), 0, MAX_PLAYERS - 1)
        if slot is None or not is_bot_slot(slot):
            return None
        if with_keys:
            tick = _as_int(message.get("tick"), 0, MAX_TICK)
            keys = _as_int(message.get("keys"), 0, KEY_MASK)
            if tick is None or keys is None:
                return None
            return {"t": kind, "slot": slot, "tick": tick, "keys": keys}
        by = _as_int(message.get("by"), 0, MAX_PLAYERS - 1)
        hp = _as_int(message.get("hp"), 0, MAX_HP)
        if by is None or hp is None:
            return None
        return {"t": kind, "slot": slot, "by": by, "hp": hp}
    return check


def _check_bye(_message):
    return {"t": BYE}


_CHECKERS = {
    JOIN: _check_join,
    WELCOME: _check_welcome,
    DENY: _check_deny,
    JOINED: _check_joined,
    LEFT: _check_left,
    START: _check_start,
    STARTED: _check_started,
    INPUT: _check_input,
    PEER_INPUT: _check_peer_input,
    BOT_INPUT: _bot_report(BOT_INPUT, with_keys=True),
    BOT_HIT: _bot_report(BOT_HIT, with_keys=False),
    BOT_DEAD: _bot_report(BOT_DEAD, with_keys=False),
    HIT: _own_report(HIT),
    PEER_HIT: _relayed_report(PEER_HIT),
    DEAD: _own_report(DEAD),
    PEER_DEAD: _relayed_report(PEER_DEAD),
    BYE: _check_bye,
}


class RateWindow:
    """한 연결이 너무 빨리 보내는지 본다(시계를 주입받아 시험할 수 있게).

    넉넉히 두면 의미가 없고 빡빡하게 두면 잠깐 몰릴 때 억울하게 끊긴다.
    그래서 '초당 몇 줄'을 1초 창으로 센다.
    """

    def __init__(self, limit_per_sec: int = MAX_LINES_PER_SEC):
        self.limit = max(1, int(limit_per_sec))
        self._stamps = []
        self.total_bytes = 0

    def allow(self, now: float, size: int = 0) -> bool:
        """이 줄을 받아도 되는가. 안 되면 부르는 쪽이 연결을 끊는다."""
        self.total_bytes += max(0, int(size))
        if self.total_bytes > MAX_SESSION_BYTES:
            return False
        self._stamps = [t for t in self._stamps if now - t < 1.0]
        if len(self._stamps) >= self.limit:
            return False
        self._stamps.append(now)
        return True
