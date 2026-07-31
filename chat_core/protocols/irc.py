"""실제 IRC 서버 프로토콜 전략 - ProtocolPort 구현체.

와이어 파싱/포맷팅 자체는 기존 irc_protocol.py(순수 모듈)를 그대로 재사용하고, 여기서는
"그 메시지가 세션 상태에 어떤 의미인지"만 다룸. 커스텀 프로토콜과 마찬가지로 명령 분기는
디스패치 테이블(_HANDLERS)로 둬서 새 IRC 명령 지원이 기존 코드 수정 없이 추가되게 함(OCP).
"""
import time

import irc_protocol
from chat_core import events


class IrcProtocol:
    name = "irc"

    # ---------- 의도(내보내기) ----------
    def start_auth(self, session, user_id: str, password: str, mode: str) -> None:
        """IRC는 회원가입 개념이 없음 - mode와 무관하게 등록(registration) 핸드셰이크를 함"""
        session.pending_irc_nick = user_id
        session.irc_password = password
        session.irc_identified = False
        session.irc_nick_retries = 0
        if password:
            session.transport(irc_protocol.format_pass(password))
        session.transport(irc_protocol.format_nick(user_id))
        session.transport(irc_protocol.format_user(user_id, user_id))

    def create_channel(self, session, channel: str, key: str) -> None:
        """IRC는 채널 생성이 곧 입장임(먼저 들어간 사람이 채널을 만듦)"""
        self.join(session, channel, key)

    def join(self, session, channel: str, key: str) -> None:
        session.transport(irc_protocol.format_join(self.normalize_channel(channel), key or None))

    def leave(self, session, channel: str) -> None:
        session.transport(irc_protocol.format_part(channel))

    def send_chat(self, session, channel: str, text: str) -> None:
        session.transport(irc_protocol.format_privmsg(channel, text))
        # IRC 서버는 내가 보낸 메시지를 나에게 다시 돌려주지 않으므로 직접 로컬 에코를 해야 함
        # (커스텀 프로토콜과 달라지는 지점 - 이 차이를 세션이 아니라 프로토콜이 알고 있음)
        session.deliver_message(channel, session.my_id, text, mine=True, ts=time.time())

    def publish_avatar(self, session, avatar_b64: str) -> None:
        # 실제 IRC 서버는 아이콘 개념이 없으므로 PRIVMSG 안에 CTCP처럼 숨겨서
        # 우리 클라이언트끼리만 알아보게 보냄(내가 입장한 모든 채널에)
        for channel in session.joined_channels:
            session.transport(irc_protocol.format_ctcp_avatar(channel, avatar_b64))

    def publish_nickname(self, session, nickname: str) -> None:
        # IRC는 닉네임이 곧 접속 식별자라 서버가 승인해야 확정됨 - 낙관적으로 먼저 바꾸지 않고
        # NICK 요청 후 서버 응답(NICK 반영 / 충돌 오류)을 기다림
        session.nick_change_pending = True
        session.transport(irc_protocol.format_nick(nickname))

    def normalize_channel(self, channel: str) -> str:
        return irc_protocol.normalize_channel(channel)

    # ---------- 수신 처리 ----------
    def handle_incoming(self, session, raw) -> None:
        handler = self._HANDLERS.get(raw.command)
        if handler is not None:
            handler(self, session, raw)
            return
        if raw.command in irc_protocol.NICK_COLLISION_NUMERICS:
            self._on_nick_collision(session, raw)
        elif raw.command in irc_protocol.CHANNEL_JOIN_ERROR_NUMERICS:
            session.emit(events.ChannelJoinFailed("", raw.trailing or "채널 입장에 실패했습니다."))

    def _on_ping(self, session, msg):
        # 연결 유지의 핵심 - UI 상태와 무관하게 즉시 응답해야 서버가 끊지 않음
        session.transport(irc_protocol.format_pong(msg.trailing))

    def _on_welcome(self, session, msg):
        # 서버가 001 응답 첫 파라미터로 실제로 확정된 닉네임을 알려줌 - 우리가 보낸 닉네임과
        # 다를 수 있음(길이 제한/치환 등). 이걸 안 읽고 우리가 보낸 값을 쓰면 엉뚱한 이름이 남음
        confirmed = msg.params[0] if msg.params else session.pending_irc_nick
        session.set_identity(confirmed)
        if session.irc_password and not session.irc_identified:
            session.irc_identified = True
            session.transport(
                irc_protocol.format_privmsg("NickServ", f"IDENTIFY {session.irc_password}")
            )

    def _on_nick_collision(self, session, msg):
        if session.nick_change_pending:
            # 접속 후 명시적으로 요청한 닉네임 변경이 거부된 경우 - 연결은 끊지 않고 실패만 알림
            session.nick_change_pending = False
            session.emit(events.NicknameChangeFailed(msg.trailing or "이미 사용 중인 닉네임입니다."))
            return
        if not session.my_id and session.irc_nick_retries < irc_protocol.MAX_NICK_RETRIES:
            # 아직 등록(RPL_WELCOME) 전이면 밑줄을 붙여 자동 재시도
            session.irc_nick_retries += 1
            session.pending_irc_nick += "_"
            session.emit(events.NicknameRetrying(session.pending_irc_nick))
            session.transport(irc_protocol.format_nick(session.pending_irc_nick))
        else:
            session.emit(events.AuthFailed("사용 가능한 닉네임이 없습니다. 다른 닉네임으로 다시 시도하세요."))

    def _on_namreply(self, session, msg):
        channel = msg.params[2] if len(msg.params) > 2 else ""
        session.irc_names_buffer.setdefault(channel, []).extend(irc_protocol.parse_names_reply(msg))

    def _on_endofnames(self, session, msg):
        # NAMREPLY는 여러 줄로 쪼개져 오므로 모아뒀다가 ENDOFNAMES에서 한 번에 확정함.
        # 이 버퍼링을 안 하고 NAMREPLY마다 누적만 하면(예전 CLI가 그랬음) 채널을 나간 사람이
        # 멤버 목록에서 영영 안 지워지는 버그가 생김
        channel = msg.params[1] if len(msg.params) > 1 else ""
        members = session.irc_names_buffer.pop(channel, [])
        session.replace_members(channel, sorted(set(members)))

    def _on_join(self, session, msg):
        nick = msg.source_nick
        channel = msg.trailing or (msg.params[0] if msg.params else "")
        if nick == session.my_id:
            session.add_member(channel, nick)
            session.enter_channel(channel, f"{channel} 입장 완료")
            session.transport(irc_protocol.format_names(channel))
            my_avatar = session.avatars.get(session.my_id)
            if my_avatar:
                # 방금 입장한 채널의 기존 멤버들에게 내 아이콘을 알려줌
                session.transport(irc_protocol.format_ctcp_avatar(channel, my_avatar))
        else:
            session.add_member(channel, nick)
            session.emit(events.SystemNotice(channel, f"{nick}님이 입장했습니다."))
            my_avatar = session.avatars.get(session.my_id)
            if my_avatar:
                # 새로 들어온 사람에게만 1:1로 알려줌(채널 전체에 다시 뿌릴 필요 없음)
                session.transport(irc_protocol.format_ctcp_avatar(nick, my_avatar))

    def _on_part(self, session, msg):
        nick = msg.source_nick
        channel = msg.params[0] if msg.params else ""
        session.remove_member(channel, nick)
        session.emit(events.SystemNotice(channel, f"{nick}님이 나갔습니다."))
        if nick == session.my_id:
            session.forget_channel(channel)
            session.emit(events.ChannelLeft(channel))

    def _on_quit(self, session, msg):
        # QUIT은 채널 정보가 없으므로 그 닉네임이 있던 모든 채널에 반영
        nick = msg.source_nick
        for channel in list(session.members.keys()):
            if nick in session.members.get(channel, set()):
                session.remove_member(channel, nick)
                session.emit(events.SystemNotice(channel, f"{nick}님이 접속을 종료했습니다."))

    def _on_nick(self, session, msg):
        old_nick = msg.source_nick
        new_nick = msg.trailing or (msg.params[0] if msg.params else "")
        if old_nick == session.my_id:
            session.nick_change_pending = False
            session.set_identity(new_nick)
        for channel in list(session.members.keys()):
            if old_nick in session.members.get(channel, set()):
                session.remove_member(channel, old_nick)
                session.add_member(channel, new_nick)
                session.emit(events.SystemNotice(
                    channel, f"{old_nick}님이 {new_nick}(으)로 닉네임을 변경했습니다."
                ))

    def _on_privmsg(self, session, msg):
        sender = msg.source_nick
        target = msg.params[0] if msg.params else ""
        text = msg.trailing
        avatar_b64 = irc_protocol.parse_ctcp_avatar(text)
        if avatar_b64 is not None:
            # 아이콘 교환용 CTCP - 채팅으로 표시하거나 기록에 남기지 않고 캐시만 갱신.
            # (예전 CLI는 이 검사가 없어서 이 프레임이 깨진 채팅 텍스트로 그대로 샜음)
            session.apply_avatar(sender, avatar_b64)
            return
        ts = time.time()
        if target == session.my_id:
            # 귓속말은 별도 채널이 없으므로 지금 보고 있는 채널에 표시(기존 동작 유지)
            if session.active_channel:
                session.deliver_message(
                    session.active_channel, f"{sender} (귓속말)", text,
                    mine=False, ts=ts, record_history=False,
                )
        else:
            session.deliver_message(target, sender, text, mine=False, ts=ts)

    def _on_notice(self, session, msg):
        # 등록 전에는 채널이 없으므로 빈 채널로 보냄 - 어댑터가 로그인 화면 등에 표시
        channel = session.active_channel if session.my_id else ""
        session.emit(events.SystemNotice(channel, msg.trailing))

    def _on_error(self, session, msg):
        session.emit(events.ConnectionClosed(msg.trailing or ""))

    _HANDLERS = {
        "PING": _on_ping,
        irc_protocol.RPL_WELCOME: _on_welcome,
        irc_protocol.RPL_NAMREPLY: _on_namreply,
        irc_protocol.RPL_ENDOFNAMES: _on_endofnames,
        "JOIN": _on_join,
        "PART": _on_part,
        "QUIT": _on_quit,
        "NICK": _on_nick,
        "PRIVMSG": _on_privmsg,
        "NOTICE": _on_notice,
        "ERROR": _on_error,
    }
