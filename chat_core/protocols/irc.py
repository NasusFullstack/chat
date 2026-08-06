"""실제 IRC 서버 프로토콜 전략 - ProtocolPort 구현체.

와이어 파싱/포맷팅 자체는 기존 irc_protocol.py(순수 모듈)를 그대로 재사용하고, 여기서는
"그 메시지가 세션 상태에 어떤 의미인지"만 다룸. 커스텀 프로토콜과 마찬가지로 명령 분기는
디스패치 테이블(_HANDLERS)로 둬서 새 IRC 명령 지원이 기존 코드 수정 없이 추가되게 함(OCP).
"""
import time

import irc_protocol
from chat_core import commands, constants, events
from chat_core.protocols.common_commands import CommonCommands

# 서버가 명령에 대한 답으로 돌려주는 숫자 응답 중 사용자에게 그대로 보여줄 것들.
# (MOTD/서버통계 같은 접속 직후 잡음은 여기 없으므로 조용히 무시됨)
# 아직 다 안 온 아이콘 전송을 몇 건까지 들고 있을지. 조각이 유실되면 그 전송은 영영
# 완성되지 않으므로, 상한 없이 두면 조용히 메모리가 쌓임
MAX_PENDING_AVATARS = 32

INFO_NUMERICS = {
    "301",  # RPL_AWAY - 상대가 자리비움
    "305", "306",  # 내 자리비움 해제/설정
    "311", "312", "313", "317", "318", "319", "330", "338", "671",  # WHOIS 응답들
    "321", "322", "323",  # LIST 응답들
    "324",  # 채널 모드
    "331", "332", "333",  # 채널 주제
    "341",  # INVITE 전송 확인
}


class IrcProtocol(CommonCommands):
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
            self._send_avatar(session, channel, avatar_b64)

    @staticmethod
    def _send_avatar(session, target: str, avatar_b64: str) -> None:
        """아이콘을 512바이트에 맞춰 나눠 보냄. 대부분 한 줄로 끝남(실측 144~188자).

        조각이 여러 개여도 한 번에 내보냄 - 아이콘 변경은 자주 일어나는 일이 아니고,
        최악의 경우에도 5줄이라 IRC 서버의 연속 전송 허용치 안에 들어감."""
        for line in irc_protocol.format_ctcp_avatar(target, avatar_b64):
            session.transport(line)

    def publish_nickname(self, session, nickname: str) -> None:
        # IRC는 닉네임이 곧 접속 식별자라 서버가 승인해야 확정됨 - 낙관적으로 먼저 바꾸지 않고
        # NICK 요청 후 서버 응답(NICK 반영 / 충돌 오류)을 기다림
        session.nick_change_pending = True
        session.transport(irc_protocol.format_nick(nickname))

    def normalize_channel(self, channel: str) -> str:
        return irc_protocol.normalize_channel(channel)

    # ---------- 슬래시 명령 ----------
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
        session.transport(irc_protocol.format_notice(channel, args))
        # NOTICE는 서버가 나에게 되돌려주지 않으므로 내 화면에도 직접 남김
        session.emit(events.SystemNotice(channel, f"[공지 보냄] {args}"))

    def _cmd_msg(self, session, channel: str, args: str) -> None:
        nick, _, text = args.partition(" ")
        if not nick or not text.strip():
            session.emit(events.CommandError(f"사용법: {commands.MSG.usage}"))
            return
        session.transport(irc_protocol.format_privmsg(nick, text.strip()))
        session.emit(events.SystemNotice(channel, f"{nick}님에게 귓속말: {text.strip()}"))

    def _cmd_names(self, session, channel: str, args: str) -> None:
        target = self.normalize_channel(args) if args else channel
        if not target:
            session.emit(events.CommandError("참여자를 조회할 채널이 없습니다."))
            return
        session.transport(irc_protocol.format_names(target))

    def _cmd_topic(self, session, channel: str, args: str) -> None:
        if not channel:
            session.emit(events.CommandError("채널에 먼저 입장하세요."))
            return
        session.transport(irc_protocol.format_topic(channel, args or None))

    def _cmd_whois(self, session, channel: str, args: str) -> None:
        if not args:
            session.emit(events.CommandError(f"사용법: {commands.WHOIS.usage}"))
            return
        session.transport(irc_protocol.format_whois(args.split()[0]))

    def _cmd_away(self, session, channel: str, args: str) -> None:
        session.transport(irc_protocol.format_away(args or None))

    def _cmd_invite(self, session, channel: str, args: str) -> None:
        nick, _, target = args.partition(" ")
        target = self.normalize_channel(target) if target.strip() else channel
        if not nick or not target:
            session.emit(events.CommandError(f"사용법: {commands.INVITE.usage}"))
            return
        session.transport(irc_protocol.format_invite(nick, target))

    def _cmd_kick(self, session, channel: str, args: str) -> None:
        nick, _, reason = args.partition(" ")
        if not nick or not channel:
            session.emit(events.CommandError(f"사용법: {commands.KICK.usage}"))
            return
        session.transport(irc_protocol.format_kick(channel, nick, reason.strip() or None))

    def _cmd_mode(self, session, channel: str, args: str) -> None:
        target, _, rest = args.partition(" ")
        if not target or not rest.strip():
            session.emit(events.CommandError(f"사용법: {commands.MODE.usage}"))
            return
        session.transport(irc_protocol.format_mode(target, rest.strip()))

    def _cmd_list(self, session, channel: str, args: str) -> None:
        session.transport(irc_protocol.format_list())

    def _cmd_quit(self, session, channel: str, args: str) -> None:
        session.transport(irc_protocol.format_quit(args or None))

    def _cmd_raw(self, session, channel: str, args: str) -> None:
        if not args:
            session.emit(events.CommandError(f"사용법: {commands.RAW.usage}"))
            return
        session.transport(args)

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
        elif self._is_reportable_numeric(raw.command):
            # /whois, /list, /topic 같은 명령의 응답과 각종 오류(4xx/5xx)를 그대로 보여줌.
            # 이게 없으면 명령은 나가는데 답이 화면에 아무것도 안 떠서 먹통처럼 보임
            session.emit(events.SystemNotice(session.active_channel, self._numeric_text(raw)))

    @staticmethod
    def _is_reportable_numeric(command: str) -> bool:
        if command in INFO_NUMERICS:
            return True
        return command.isdigit() and 400 <= int(command) <= 599

    @staticmethod
    def _numeric_text(msg) -> str:
        # 숫자 응답은 첫 파라미터가 항상 내 닉네임이라 빼고, 나머지를 사람이 읽을 수 있게 이어붙임
        parts = [p for p in msg.params[1:] if p]
        return " ".join(parts) if parts else msg.raw.strip()

    def _on_topic(self, session, msg):
        channel = msg.params[0] if msg.params else session.active_channel
        session.emit(events.SystemNotice(
            channel, f"{msg.source_nick}님이 주제를 바꿨습니다: {msg.trailing}"
        ))

    def _on_kick(self, session, msg):
        channel = msg.params[0] if msg.params else ""
        target = msg.params[1] if len(msg.params) > 1 else ""
        reason = msg.trailing if len(msg.params) > 2 else ""
        session.remove_member(channel, target)
        suffix = f" ({reason})" if reason else ""
        session.emit(events.SystemNotice(channel, f"{target}님이 내보내졌습니다{suffix}."))
        if target == session.my_id:
            session.forget_channel(channel)
            session.emit(events.ChannelLeft(channel))

    def _on_invite(self, session, msg):
        channel = msg.trailing or (msg.params[1] if len(msg.params) > 1 else "")
        session.emit(events.SystemNotice(
            session.active_channel, f"{msg.source_nick}님이 {channel}(으)로 초대했습니다."
        ))

    def _on_mode(self, session, msg):
        target = msg.params[0] if msg.params else ""
        rest = " ".join(msg.params[1:])
        session.emit(events.SystemNotice(
            target if target.startswith("#") else session.active_channel,
            f"{msg.source_nick or '서버'}: 모드 {target} {rest}".strip(),
        ))

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

    @staticmethod
    def _names_key(session, channel: str) -> str:
        """IRC 채널 이름은 대소문자를 구분하지 않는다.

        서버가 353과 366에서 다른 표기로 돌려주면(`#pdlab` / `#PDLab`) 버퍼 키가 어긋나
        모아둔 이름이 통째로 유실된다. 내가 들어가 있는 채널 이름으로 맞춰준다.
        """
        for joined in session.joined_channels:
            if joined.lower() == channel.lower():
                return joined
        return channel

    def _on_namreply(self, session, msg):
        channel = msg.params[2] if len(msg.params) > 2 else ""
        key = self._names_key(session, channel)
        session.irc_names_buffer.setdefault(key, []).extend(irc_protocol.parse_names_reply(msg))

    def _on_endofnames(self, session, msg):
        # NAMREPLY는 여러 줄로 쪼개져 오므로 모아뒀다가 ENDOFNAMES에서 한 번에 확정함.
        # 이 버퍼링을 안 하고 NAMREPLY마다 누적만 하면(예전 CLI가 그랬음) 채널을 나간 사람이
        # 멤버 목록에서 영영 안 지워지는 버그가 생김
        channel = msg.params[1] if len(msg.params) > 1 else ""
        key = self._names_key(session, channel)
        members = session.irc_names_buffer.pop(key, [])
        if not members:
            # 353 없이 366만 날아오는 경우가 있다(다른 데서 NAMES를 부르거나, 요청이
            # 겹쳐서 두 번째 366이 빈 버퍼를 만나거나). 그걸 그대로 반영하면 **참여자
            # 목록이 통째로 비어버린다** - "참여자가 다 사라져서 빈 공간으로 보인다"는
            # 제보의 원인. 내가 들어가 있는 채널이 빈 목록일 수는 없으므로(최소한 내가
            # 있다) 빈 결과는 반영하지 않는다.
            return
        session.replace_members(key, sorted(set(members)))

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
                self._send_avatar(session, channel, my_avatar)
        else:
            session.add_member(channel, nick)
            session.emit(events.SystemNotice(channel, f"{nick}님이 입장했습니다."))
            my_avatar = session.avatars.get(session.my_id)
            if my_avatar:
                # 새로 들어온 사람에게만 1:1로 알려줌(채널 전체에 다시 뿌릴 필요 없음)
                self._send_avatar(session, nick, my_avatar)

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

    def request_client_version(self, session, user_id: str) -> None:
        session.transport(irc_protocol.format_ctcp_version_request(user_id))

    def request_client_versions_in_channel(self, session, channel: str) -> None:
        """채널 전체에 **한 줄**로 물어본다.

        개인 메시지를 여러 명에게 보내는 것을 막아둔 서버(실제 사례: UnrealIRCd의
        "Multi-target messaging is not allowed")에서 쓰는 우회로다. 대상이 채널 하나뿐이라
        그 규칙에 걸리지 않고, 답할 수 있는 클라이언트는 각자 NOTICE로 답한다.

        대신 채널에 있는 모두의 클라이언트에 요청이 한 번 도달하므로 **꼭 필요할 때
        한 번만** 쓴다(개인별로 묻는 길이 막혔을 때, 채널당 한 번).
        """
        session.transport(irc_protocol.format_ctcp_version_request(channel))

    def _on_privmsg(self, session, msg):
        sender = msg.source_nick
        target = msg.params[0] if msg.params else ""
        text = msg.trailing
        if irc_protocol.is_ctcp_version_request(text):
            # 남이 우리에게 "무슨 프로그램 쓰냐"고 물어온 것 - 예의상 답한다.
            # (이 답이 있어야 우리 사용자끼리도 서로를 알아본다)
            session.transport(
                irc_protocol.format_ctcp_version_reply(sender, constants.our_client_version()))
            return
        if irc_protocol.is_ctcp_frame(text):
            # 우리끼리 쓰는 숨김 프레임은 채팅으로 표시하거나 기록에 남기지 않음.
            # 해석에 실패해도 여기서 끝내는 게 중요함 - 서버가 512바이트에서 잘라버린
            # 프레임을 그냥 흘려보내면 잘린 base64 쓰레기가 채널에 그대로 뜬다
            # (실측으로 확인한 실제 증상)
            self._handle_avatar_frame(session, sender, text)
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

    def _handle_avatar_frame(self, session, sender: str, text: str):
        """조각난 아이콘 프레임을 모아서 다 오면 반영.

        조각이 하나라도 빠지면(잘렸거나 유실) 아무 것도 하지 않는다 - 아이콘이 안 보이는
        건 사소하지만, 깨진 데이터를 아이콘이라고 우기면 더 이상하므로.
        """
        parsed = irc_protocol.parse_ctcp_avatar(text)
        if parsed is None:
            return  # 잘렸거나 우리가 모르는 CTCP - 조용히 버림(채팅으로 새면 안 됨)
        # 이 프레임은 우리 클라이언트만 보낸다. 즉 **한 줄도 안 물어보고** 상대가 춥채팅인
        # 것을 알 수 있다 - 물어보기가 막힌 서버에서도 우리끼리는 서로 알아본다
        if sender not in session.client_versions:
            session.apply_client_version(sender, constants.our_client_version())
        transfer_id, index, total, chunk = parsed
        if total == 1:
            session.apply_avatar(sender, chunk)
            return

        key = (sender, transfer_id)
        parts = session.irc_avatar_chunks.setdefault(key, {})
        parts[index] = chunk
        if len(parts) < total:
            # 아직 덜 왔음. 미완성 전송이 계속 쌓이면 메모리를 먹으므로 상한을 둠
            if len(session.irc_avatar_chunks) > MAX_PENDING_AVATARS:
                oldest = next(iter(session.irc_avatar_chunks))
                session.irc_avatar_chunks.pop(oldest, None)
            return
        session.irc_avatar_chunks.pop(key, None)
        session.apply_avatar(sender, "".join(parts[i] for i in range(1, total + 1)))

    def _on_notice(self, session, msg):
        version = irc_protocol.parse_ctcp_version_reply(msg.trailing)
        if version is not None:
            # 우리가 물어본 것에 대한 답 - 채팅창에 띄우지 않고 조용히 기록만 한다
            session.apply_client_version(msg.source_nick, version)
            return
        if irc_protocol.is_ctcp_frame(msg.trailing):
            # 우리가 모르는 CTCP 응답(예: "ERRMSG that is an unknown CTCP query").
            # 기계끼리 주고받는 말이라 사람에게 보여줄 것이 아니다 - 실제로 이게 채팅창에
            # 그대로 뜬 적이 있다
            return
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
        "TOPIC": _on_topic,
        "KICK": _on_kick,
        "INVITE": _on_invite,
        "MODE": _on_mode,
        "ERROR": _on_error,
    }


# 실제 IRC 서버가 상대라 표준 명령을 거의 다 그대로 쓸 수 있음.
# 표를 클래스 밖에 두는 이유: 클래스 본문 안에서는 위에서 정의한 메서드를 참조할 수 있지만
# 상속받은 COMMON_COMMANDS(부모 클래스 속성)는 아직 이름공간에 없어서 합칠 수 없음.
_COMMANDS = {
    **CommonCommands.COMMON_COMMANDS,
    commands.NOTICE: IrcProtocol._cmd_notice,
    commands.MSG: IrcProtocol._cmd_msg,
    commands.NAMES: IrcProtocol._cmd_names,
    commands.TOPIC: IrcProtocol._cmd_topic,
    commands.WHOIS: IrcProtocol._cmd_whois,
    commands.AWAY: IrcProtocol._cmd_away,
    commands.INVITE: IrcProtocol._cmd_invite,
    commands.KICK: IrcProtocol._cmd_kick,
    commands.MODE: IrcProtocol._cmd_mode,
    commands.LIST: IrcProtocol._cmd_list,
    commands.QUIT: IrcProtocol._cmd_quit,
    commands.RAW: IrcProtocol._cmd_raw,
}
_SPECS = sorted(_COMMANDS, key=lambda spec: spec.name)
_HANDLERS_BY_NAME = {spec.name: handler for spec, handler in _COMMANDS.items()}
