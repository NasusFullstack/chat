"""커스텀 JSON 프로토콜(server.py) 전략 - ProtocolPort 구현체.

메시지 타입 분기를 if/elif 사슬 대신 디스패치 테이블(_HANDLERS)로 둠: 새 메시지 타입을
지원하려면 핸들러 메서드 하나 추가하고 표에 한 줄 등록하면 되고, 기존 코드를 열어서
고칠 필요가 없음(OCP).
"""
import time

from chat_core import commands, events
from chat_core.protocols import wire_custom as wire
from chat_core.protocols.common_commands import CommonCommands


class CustomProtocol(CommonCommands):
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

    def request_unfurl(self, session, url: str) -> None:
        session.transport(wire.format_unfurl(url))

    # ---------- 슬래시 명령 ----------
    # 커스텀 서버(server.py)는 IRC처럼 NOTICE/WHOIS/MODE 같은 개념이 없어서, 서버를
    # 고치지 않고 흉내낼 수 있는 것만 지원한다. 지원 목록에 없는 명령은 세션이
    # "이 서버에서는 지원하지 않는 명령" 안내를 띄움(조용히 무시하면 먹통처럼 보임).
    def command_specs(self):
        return _SPECS

    def run_command(self, session, channel: str, name: str, args: str) -> bool:
        handler = _HANDLERS_BY_NAME.get(name)
        if handler is None:
            return False
        handler(self, session, channel, args)
        return True

    def _cmd_notice(self, session, channel: str, args: str) -> None:
        if not args:
            session.emit(events.CommandError(f"사용법: {commands.NOTICE.usage}"))
            return
        # 서버는 텍스트를 그대로 중계만 하므로, IRC와 같은 프레이밍을 태워 보내면
        # 받는 쪽 클라이언트가 알아서 공지 형태로 그려줌
        session.send_wire_chat(channel, commands.format_notice(args), args)

    def _cmd_names(self, session, channel: str, args: str) -> None:
        # 커스텀 서버는 참여자 목록을 변경 시마다 알아서 밀어주므로 재조회 요청이 없음.
        # 지금 세션이 알고 있는 목록을 다시 발행해서 화면만 갱신함
        target = args.strip() or channel
        if not target:
            session.emit(events.CommandError("참여자를 조회할 채널이 없습니다."))
            return
        session.replace_members(target, session.members.get(target, set()))

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

    def _on_unfurl_result(self, session, msg: dict):
        session.emit(events.UnfurlResult(
            url=msg.get("url", ""),
            title=msg.get("title", ""),
            description=msg.get("description", ""),
            image_url=msg.get("image_url", ""),
        ))

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
        wire.TYPE_UNFURL_RESULT: _on_unfurl_result,
        wire.TYPE_ERROR: _on_error,
    }


# 표를 클래스 밖에 두는 이유는 irc.py와 같음(상속받은 COMMON_COMMANDS는 클래스 본문
# 안에서는 아직 참조할 수 없음)
_COMMANDS = {
    **CommonCommands.COMMON_COMMANDS,
    commands.NOTICE: CustomProtocol._cmd_notice,
    commands.NAMES: CustomProtocol._cmd_names,
}
_SPECS = sorted(_COMMANDS, key=lambda spec: spec.name)
_HANDLERS_BY_NAME = {spec.name: handler for spec, handler in _COMMANDS.items()}
