"""서버 채팅(jsserv `/chat/ws`)의 메시지 타입과 보낼 dict 만들기.

`wire_custom.py`와 대칭이고, 순수 파싱/포맷만 한다(상태 해석 없음).

## 옛 커스텀 서버(server.py)와 뭐가 다른가
둘 다 JSON 한 줄을 주고받지만 **담기는 것이 다르다.** 옛 쪽은 IRC 때 하던 방식을
그대로 옮겨놔서, 아이콘·표시이름을 따로 주고받고 지난 기록은 아예 없었다.
여기서는 서버가 그걸 들고 있으므로 한 번에 온다:

| | 옛 커스텀 | 서버 채팅 |
|---|---|---|
| 참여자 목록 | 아이디만 | 아이디 + 표시이름 + 아이콘 |
| 들어갈 때 | 입장 응답만 | 응답 + **지난 기록**(하루치) |
| 한 줄 | 길이 제한이 애매 | 4000자, 서버가 알려줌 |
| 귓속말 | 없음 | 있음 |
| 줄마다 id | 없음 | 있음(나중에 답장·수정·삭제에 쓴다) |

그래서 전략도 따로 둔다(`protocols/server.py`) - 한쪽을 고칠 때 다른 쪽이 안 깨지게.
"""

# 서버 -> 클라이언트 (msg["type"])
TYPE_AUTH_RESULT = "auth_result"
TYPE_CHANNEL_RESULT = "channel_result"
TYPE_LEAVE_RESULT = "leave_result"
TYPE_CHAT = "chat"
TYPE_WHISPER = "whisper"
TYPE_SYSTEM = "system"
TYPE_USERLIST = "userlist"
TYPE_MEMBER_AVATAR = "member_avatar"
TYPE_MEMBER_NICKNAME = "member_nickname"
TYPE_ERROR = "error"
TYPE_PONG = "pong"
TYPE_CHANNEL_LIST = "channel_list"

# 클라이언트 -> 서버 (msg["cmd"])
CMD_PING = "ping"
CMD_CHANNELS = "channels"
CMD_REGISTER = "register"
CMD_LOGIN = "login"
CMD_JOIN = "join"
CMD_LEAVE = "leave"
CMD_MSG = "msg"
CMD_WHISPER = "whisper"
CMD_SET_AVATAR = "set_avatar"
CMD_SET_NICKNAME = "set_nickname"


def format_register(user_id: str, password: str) -> dict:
    return {"cmd": CMD_REGISTER, "id": user_id, "pw": password}


def format_login(user_id: str, password: str) -> dict:
    return {"cmd": CMD_LOGIN, "id": user_id, "pw": password}


def format_join(channel: str, key: str = "") -> dict:
    """들어간다. **없으면 서버가 만든다** - IRC 처럼 입장이 곧 생성이다."""
    return {"cmd": CMD_JOIN, "channel": channel, "key": key}


def format_leave(channel: str) -> dict:
    return {"cmd": CMD_LEAVE, "channel": channel}


def format_msg(channel: str, text: str) -> dict:
    return {"cmd": CMD_MSG, "channel": channel, "text": text}


def format_whisper(to: str, text: str) -> dict:
    return {"cmd": CMD_WHISPER, "to": to, "text": text}


def format_set_avatar(avatar_b64: str) -> dict:
    """**쪼개지 않는다.** IRC 는 한 줄 512바이트라 300자씩 나눠 보내야 했다."""
    return {"cmd": CMD_SET_AVATAR, "avatar": avatar_b64}


def format_set_nickname(nickname: str) -> dict:
    """**한글도 된다.** IRC 서버는 한글 닉네임을 거절했다."""
    return {"cmd": CMD_SET_NICKNAME, "nick": nickname}


def format_ping() -> dict:
    """살아 있나. 서버는 pong 으로 답한다.

    **대화가 없어도 뭔가 오가게 하는 것이 목적이다.** 이것이 없으면 조용한 연결을
    우리가 죽은 것으로 보고 끊는다(실측 2026-10-02: 170초마다 그랬다).
    """
    return {"cmd": CMD_PING}


def format_channels() -> dict:
    """서버에 어떤 방이 있는지 달라고 한다.

    **비밀번호는 안 온다** - 걸렸다는 사실만 온다(서버가 안 보낸다).
    """
    return {"cmd": CMD_CHANNELS}
