"""서버 채팅(jsserv `/chat/ws`) 전략 - ProtocolPort 구현체.

IRC 가 못 하던 것들을 걷어낸 쪽이다. 여기서 달라지는 것만 적는다:

- **아이콘·표시이름을 따로 물어보지 않는다.** 참여자 목록에 같이 온다. IRC 는 CTCP 로
  주고받았고 아이콘은 300자씩 쪼개야 했다(조각이 빠지면 아무것도 안 떴다)
- **지난 기록을 서버가 바로 준다.** 들어가면 응답에 하루치가 실려 온다. IRC 모드는
  각자 올린 것을 중계 서버가 모아 중복을 거른 뒤 따로 받아와야 했다
- **"무슨 프로그램을 쓰나"를 묻지 않는다.** 우리 서버에는 우리 클라이언트만 붙는다
- **보낸 말을 서버가 돌려준다.** IRC 는 안 돌려줘서 각자 자기 말을 화면에 직접 올려야
  했고(로컬 에코), 그래서 "내 화면에만 있는 말"이 생길 여지가 있었다

메시지 타입 분기는 if/elif 사슬이 아니라 표(`_HANDLERS`)다 - 새 타입을 지원할 때
기존 코드를 안 열어도 되게(OCP, 다른 전략과 같은 규칙).
"""
import time

import battle_protocol
from chat_core import commands, constants, events
from chat_core.protocols import wire_server as wire
from chat_core.protocols.common_commands import CommonCommands


class ServerProtocol(CommonCommands):
    name = "server"

    # 쪼개지 않고 한 줄로 보낸다. 서버가 받아주는 만큼이다(jsserv features/chat.py)
    avatar_limit = 6000

    # ---------- 의도(내보내기) ----------
    def start_auth(self, session, user_id: str, password: str, mode: str) -> None:
        if mode == "register":
            session.transport(wire.format_register(user_id, password))
        else:
            session.transport(wire.format_login(user_id, password))

    def create_channel(self, session, channel: str, key: str) -> None:
        """**따로 만들 것이 없다.** 들어가면 서버가 만든다(IRC 와 같은 느낌).

        옛 커스텀 서버는 '만들기'와 '들어가기'가 별개 단계였는데, 그 때문에 화면이
        두 응답을 구분해야 했다. 여기서는 한 가지뿐이다.
        """
        session.transport(wire.format_join(channel, key))

    def join(self, session, channel: str, key: str) -> None:
        session.transport(wire.format_join(channel, key))

    def leave(self, session, channel: str) -> None:
        session.transport(wire.format_leave(channel))

    def send_chat(self, session, channel: str, text: str) -> None:
        """**로컬 에코를 하지 않는다.** 서버가 돌려주므로 여기서 또 올리면 두 번 보인다."""
        session.transport(wire.format_msg(channel, text))

    def publish_avatar(self, session, avatar_b64: str) -> None:
        session.transport(wire.format_set_avatar(avatar_b64))

    def publish_nickname(self, session, nickname: str) -> None:
        session.transport(wire.format_set_nickname(nickname))

    def request_client_version(self, session, user_id: str) -> None:
        """우리 서버에는 우리 클라이언트만 붙으므로 묻지 않고 바로 정한다."""
        session.apply_client_version(user_id, constants.our_client_version())

    def request_client_versions_in_channel(self, session, channel: str) -> None:
        """위와 같은 이유로 물어볼 일이 없다."""

    def reclaim_nickname(self, session) -> None:
        """계정으로 들어가므로 이름이 밀릴 일이 없다."""

    def keepalive(self, session) -> None:
        """연결이 끊기면 바로 알아채므로 따로 물어볼 것이 없다."""

    def disconnect_gracefully(self, session, reason: str) -> None:
        """끊기는 즉시 서버가 알아채므로 따로 알릴 것이 없다."""

    def announce_battle_room(self, session, channel: str, room: str) -> None:
        """전투 방 번호를 채널에 알린다.

        CTCP 가 없으므로 채팅으로 보내되, 받는 쪽이 아래에서 걸러내 글자로는 안 보인다.
        """
        session.transport(wire.format_msg(
            channel, battle_protocol.format_room_notice(room)))

    # ---------- 슬래시 명령 ----------
    def command_specs(self):
        return _SPECS

    def run_command(self, session, channel: str, name: str, args: str) -> bool:
        handler = _HANDLERS_BY_NAME.get(name)
        if handler is None:
            return False
        handler(self, session, channel, args)
        return True

    def _cmd_whisper(self, session, channel: str, args: str) -> None:
        """`/msg 사람 할말` - 귓속말. **IRC 와 달리 서버에 남고 알림도 된다.**"""
        who, _, text = args.partition(" ")
        if not who or not text.strip():
            session.emit(events.CommandError("쓰는 법: /msg 사람 할말"))
            return
        session.transport(wire.format_whisper(who, text.strip()))

    # ---------- 수신 처리 ----------
    def handle_incoming(self, session, raw) -> None:
        handler = self._HANDLERS.get(raw.get("type"))
        if handler is not None:
            handler(self, session, raw)

    def _on_auth_result(self, session, msg: dict):
        if not msg.get("ok"):
            session.emit(events.AuthFailed(msg.get("text", "실패")))
            return
        if msg.get("made"):
            session.emit(events.RegisterSucceeded())
            return
        session.set_identity(msg.get("id") or session.pending_user_id)
        # 서버가 들고 있던 내 이름과 아이콘을 그대로 되살린다 - 기기를 바꿔도 따라온다
        if msg.get("nick"):
            session.apply_nickname(session.my_id, msg["nick"])
        if msg.get("avatar"):
            session.apply_avatar(session.my_id, msg["avatar"])

    def _on_channel_result(self, session, msg: dict):
        channel = msg.get("channel", "")
        if not msg.get("ok"):
            session.emit(events.ChannelJoinFailed(channel, msg.get("text", "실패")))
            return
        session.enter_channel(channel, msg.get("text", "입장 완료"))
        # **지난 기록이 응답에 실려 온다.** 중계 서버에 따로 받아올 것이 없다
        for line in msg.get("history", []) or []:
            sender = line.get("sender", "?")
            session.deliver_message(
                channel, sender, line.get("text", ""),
                mine=(sender == session.my_id), ts=line.get("ts", time.time()),
                record_history=False)
        self._apply_users(session, channel, msg.get("users", []))

    def _on_leave_result(self, session, msg: dict):
        channel = msg.get("channel", "")
        if msg.get("ok"):
            session.forget_channel(channel)
            session.emit(events.ChannelLeft(channel))
        else:
            session.emit(events.ChannelLeaveFailed(channel, msg.get("text", "실패")))

    def _on_chat(self, session, msg: dict):
        sender = msg.get("sender", "?")
        channel = msg.get("channel", "")
        text = msg.get("text", "")
        # 우리끼리 쓰는 숨김 프레임은 **채팅으로 새면 안 된다**(CLAUDE.md 2-2)
        if battle_protocol.is_battle_notice(text):
            room = battle_protocol.parse_room_notice(text)
            if room and sender != session.my_id and channel:
                session.emit(events.BattleRoomOpened(channel, sender, room))
            return
        session.deliver_message(channel, sender, text,
                                mine=(sender == session.my_id),
                                ts=msg.get("ts", time.time()))

    def _on_whisper(self, session, msg: dict):
        """귓속말 - **IRC 에서는 기록도 알림도 안 되던 것이다.**

        보이는 자리는 지금 보고 있는 채널이다. 받는 쪽도 보내는 쪽도 같은 자리에 남아야
        대화가 이어져 보인다.
        """
        channel = session.active_channel
        if not channel:
            return
        sender = msg.get("sender", "?")
        mine = sender == session.my_id
        who = msg.get("to", "") if mine else sender
        session.deliver_message(
            channel, f"{who} (귓속말)", msg.get("text", ""),
            mine=mine, ts=msg.get("ts", time.time()))

    def _on_system(self, session, msg: dict):
        channel = msg.get("channel") or session.active_channel
        if channel:
            session.emit(events.SystemNotice(
                channel, msg.get("text", ""), ts=msg.get("ts") or time.time()))

    def _on_userlist(self, session, msg: dict):
        channel = msg.get("channel") or session.active_channel
        if channel:
            self._apply_users(session, channel, msg.get("users", []))

    def _apply_users(self, session, channel: str, users) -> None:
        """참여자 목록 - **아이콘과 표시이름이 같이 온다.**

        IRC 는 아이디만 와서 나머지를 CTCP 로 따로 물어봐야 했고, 그 과정에서 서버가
        폭주로 보고 끊는 일이 있었다. 여기서는 받은 것을 그대로 쓴다.
        """
        ids = []
        for one in users or []:
            if not isinstance(one, dict):
                continue
            user_id = one.get("id", "")
            if not user_id:
                continue
            ids.append(user_id)
            if one.get("nick"):
                session.apply_nickname(user_id, one["nick"])
            if one.get("avatar"):
                session.apply_avatar(user_id, one["avatar"])
            session.apply_client_version(user_id, constants.our_client_version())
        session.replace_members(channel, ids)

    def _on_member_avatar(self, session, msg: dict):
        user_id = msg.get("id", "")
        if user_id:
            session.apply_avatar(user_id, msg.get("avatar"))

    def _on_member_nickname(self, session, msg: dict):
        user_id = msg.get("id", "")
        if user_id:
            session.apply_nickname(user_id, msg.get("nick"))

    def _on_error(self, session, msg: dict):
        session.emit(events.GenericError(msg.get("text", "오류")))

    _HANDLERS = {
        wire.TYPE_AUTH_RESULT: _on_auth_result,
        wire.TYPE_CHANNEL_RESULT: _on_channel_result,
        wire.TYPE_LEAVE_RESULT: _on_leave_result,
        wire.TYPE_CHAT: _on_chat,
        wire.TYPE_WHISPER: _on_whisper,
        wire.TYPE_SYSTEM: _on_system,
        wire.TYPE_USERLIST: _on_userlist,
        wire.TYPE_MEMBER_AVATAR: _on_member_avatar,
        wire.TYPE_MEMBER_NICKNAME: _on_member_nickname,
        wire.TYPE_ERROR: _on_error,
    }


# 표를 클래스 밖에 두는 이유는 irc.py / custom.py 와 같다(상속받은 COMMON_COMMANDS 는
# 클래스 본문 안에서는 아직 참조할 수 없다)
_COMMANDS = {
    **CommonCommands.COMMON_COMMANDS,
    commands.MSG: ServerProtocol._cmd_whisper,
}
_SPECS = sorted(_COMMANDS, key=lambda spec: spec.name)
_HANDLERS_BY_NAME = {spec.name: handler for spec, handler in _COMMANDS.items()}
