"""커스텀 JSON 프로토콜의 메시지 타입/명령어 상수 + 전송용 dict 빌더 함수.

irc_protocol.py와 대칭되는 역할(순수 파싱/포맷팅, 상태 해석 없음) - server.py/store.py의
실제 메시지 타입과 대조해서 빠짐없이 뽑음. 이전에는 이 문자열들이 gui_client.py와
cli_client.py에 각각 리터럴로 중복돼있어서 오타 방지가 안 됐음.
"""

# 서버 -> 클라이언트 (msg["type"])
TYPE_AUTH_RESULT = "auth_result"
TYPE_CHANNEL_RESULT = "channel_result"
TYPE_LEAVE_RESULT = "leave_result"
TYPE_CHAT = "chat"
TYPE_SYSTEM = "system"
TYPE_USERLIST = "userlist"
TYPE_MEMBER_AVATAR = "member_avatar"
TYPE_MEMBER_NICKNAME = "member_nickname"
TYPE_ERROR = "error"

# 클라이언트 -> 서버 (msg["cmd"])
CMD_REGISTER = "register"
CMD_LOGIN = "login"
CMD_CREATE_CHANNEL = "create_channel"
CMD_JOIN = "join"
CMD_MSG = "msg"
CMD_LEAVE = "leave"
CMD_SET_AVATAR = "set_avatar"
CMD_SET_NICKNAME = "set_nickname"


def format_register(user_id: str, password: str) -> dict:
    return {"cmd": CMD_REGISTER, "id": user_id, "pw": password}


def format_login(user_id: str, password: str) -> dict:
    return {"cmd": CMD_LOGIN, "id": user_id, "pw": password}


def format_create_channel(channel: str, key: str = "") -> dict:
    return {"cmd": CMD_CREATE_CHANNEL, "channel": channel, "key": key}


def format_join(channel: str, key: str = "") -> dict:
    return {"cmd": CMD_JOIN, "channel": channel, "key": key}


def format_msg(channel: str, text: str) -> dict:
    return {"cmd": CMD_MSG, "channel": channel, "text": text}


def format_leave(channel: str) -> dict:
    return {"cmd": CMD_LEAVE, "channel": channel}


def format_set_avatar(avatar_b64: str) -> dict:
    return {"cmd": CMD_SET_AVATAR, "avatar": avatar_b64}


def format_set_nickname(nickname: str) -> dict:
    return {"cmd": CMD_SET_NICKNAME, "nickname": nickname}
