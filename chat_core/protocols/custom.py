"""커스텀 JSON 프로토콜(server.py) 전략 - ProtocolPort 구현체.

메시지 타입 분기를 if/elif 사슬 대신 디스패치 테이블(_HANDLERS)로 둠: 새 메시지 타입을
지원하려면 핸들러 메서드 하나 추가하고 표에 한 줄 등록하면 되고, 기존 코드를 열어서
고칠 필요가 없음(OCP).
"""
import time

from chat_core import events
from chat_core.protocols import wire_custom as wire


class CustomProtocol:
    name = "custom"

    # ---------- 의도(내보내기) ----------
    def start_auth(self, session, user_id: str, password: str, mode: str) -> None:
        if mode == "register":
            session.transport(wire.format_register(user_id, password))
        else:
            session.transport(wire.format_login(user_id, password))

    def create_channel(self, session, channel: str, key: str) -> None:
        session.transport(wire.format_create_channel(channel, key))

    def join(self, session, channel: str, key: str) -> None:
        session.transport(wire.format_join(channel, key))

    def leave(self, session, channel: str) -> None:
        session.transport(wire.format_leave(channel))

    def send_chat(self, session, channel: str, text: str) -> None:
        # 커스텀 프로토콜은 서버가 보낸 메시지를 그대로 되돌려주므로 로컬 에코를 하지 않음
        # (하면 내 메시지가 두 번 보임)
        session.transport(wire.format_msg(channel, text))

    def publish_avatar(self, session, avatar_b64: str) -> None:
        session.transport(wire.format_set_avatar(avatar_b64))

    def publish_nickname(self, session, nickname: str) -> None:
        # 서버 승인 없이 바로 반영해도 되는 표시용 닉네임이라 낙관적으로 먼저 적용
        session.apply_nickname(session.my_id, nickname)
        session.transport(wire.format_set_nickname(nickname))

    def normalize_channel(self, channel: str) -> str:
        return channel

    # ---------- 수신 처리 ----------
    def handle_incoming(self, session, raw) -> None:
        handler = self._HANDLERS.get(raw.get("type"))
        if handler is not None:
            handler(self, session, raw)

    def _on_auth_result(self, session, msg: dict):
        if not msg.get("ok"):
            session.emit(events.AuthFailed(msg.get("text", "실패")))
            return
        if session.pending_auth_mode == "register":
            session.emit(events.RegisterSucceeded())
        else:
            session.set_identity(session.pending_user_id)

    def _on_channel_result(self, session, msg: dict):
        channel = msg.get("channel", "")
        if not msg.get("ok"):
            session.emit(events.ChannelJoinFailed(channel, msg.get("text", "실패")))
            return
        # 서버는 "생성"과 "입장"을 별개 단계로 처리함 - 생성 응답에는 입장 처리를 하면 안 됨
        if "채널 생성" in msg.get("text", ""):
            session.emit(events.ChannelCreated(channel, msg.get("text", "")))
        else:
            session.enter_channel(channel, msg.get("text", "입장 성공"))

    def _on_leave_result(self, session, msg: dict):
        channel = msg.get("channel", "")
        if msg.get("ok"):
            session.forget_channel(channel)
            session.emit(events.ChannelLeft(channel))
        else:
            session.emit(events.ChannelLeaveFailed(channel, msg.get("text", "실패")))

    def _on_chat(self, session, msg: dict):
        sender = msg.get("from", "?")
        channel = msg.get("channel", "")
        text = msg.get("text", "")
        ts = msg.get("ts", time.time())
        session.deliver_message(channel, sender, text, mine=(sender == session.my_id), ts=ts)

    def _on_system(self, session, msg: dict):
        channel = msg.get("channel") or session.active_channel
        if channel:
            session.emit(events.SystemNotice(channel, msg.get("text", "")))

    def _on_userlist(self, session, msg: dict):
        channel = msg.get("channel") or session.active_channel
        if channel:
            session.replace_members(channel, msg.get("users", []))

    def _on_member_avatar(self, session, msg: dict):
        user_id = msg.get("user_id", "")
        if user_id:
            session.apply_avatar(user_id, msg.get("avatar"))

    def _on_member_nickname(self, session, msg: dict):
        user_id = msg.get("user_id", "")
        if user_id:
            session.apply_nickname(user_id, msg.get("nickname"))

    def _on_error(self, session, msg: dict):
        session.emit(events.GenericError(msg.get("text", "오류")))

    _HANDLERS = {
        wire.TYPE_AUTH_RESULT: _on_auth_result,
        wire.TYPE_CHANNEL_RESULT: _on_channel_result,
        wire.TYPE_LEAVE_RESULT: _on_leave_result,
        wire.TYPE_CHAT: _on_chat,
        wire.TYPE_SYSTEM: _on_system,
        wire.TYPE_USERLIST: _on_userlist,
        wire.TYPE_MEMBER_AVATAR: _on_member_avatar,
        wire.TYPE_MEMBER_NICKNAME: _on_member_nickname,
        wire.TYPE_ERROR: _on_error,
    }
