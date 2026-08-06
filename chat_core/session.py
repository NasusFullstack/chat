"""ChatSession - 채팅 세션의 상태와 정책을 담당하는 순수 파이썬 도메인 코어.

Qt에도 asyncio에도 파일시스템에도 직접 의존하지 않음:
- 전송은 transport 포트(콜러블)로 위임 - 소켓을 직접 안 만짐
- 기록 저장은 HistoryStorePort로 위임 - 파일 형식을 모름
- 프로토콜별 차이는 ProtocolPort 전략 객체로 위임 - 이 파일에는 "irc냐 custom이냐"를
  비교하는 분기가 하나도 없음(OCP: 새 프로토콜 추가 시 이 파일은 안 건드림)

어댑터(GUI/CLI)는 build_session()으로 세션을 만든 뒤:
1. 사용자 행동을 의도 메서드(login/join_channel/send_message...) 호출로 변환하고,
2. 소켓에서 받은 원시 메시지를 handle_incoming()에 넘기고,
3. on_event로 오는 chat_core.events 인스턴스를 자기 방식대로 렌더링하면 됨.
"""
import time

from chat_core import commands, constants, events
from chat_core.constants import (
    AVATAR_MAX_B64_CHARS, MENTION_COOLDOWN_SEC, MENTION_TOKEN_RE, find_cheat,
)
from chat_core.history_adapter import JsonFileHistoryStore
from chat_core.protocols.custom import CustomProtocol
from chat_core.protocols.irc import IrcProtocol

# 프로토콜 이름 -> 전략 클래스. 새 프로토콜은 여기 한 줄만 추가하면 되고,
# ChatSession 본문은 전혀 안 건드려도 됨(OCP의 실질적 확인 지점).
PROTOCOL_REGISTRY = {
    CustomProtocol.name: CustomProtocol,
    IrcProtocol.name: IrcProtocol,
}


def build_session(protocol_mode: str, host: str, port: int, transport, on_event,
                  history_store=None) -> "ChatSession":
    """조립 지점(composition root) - 문자열 프로토콜 이름을 실제 전략 객체로 바꿔 주입함.

    history_store를 안 주면 기본 JSON 파일 저장소를 씀. 테스트에서는 NullHistoryStore나
    가짜 객체를 넣어서 파일 I/O 없이 순수하게 검증할 수 있음.
    """
    protocol_cls = PROTOCOL_REGISTRY.get(protocol_mode)
    if protocol_cls is None:
        raise ValueError(f"지원하지 않는 프로토콜: {protocol_mode}")
    return ChatSession(
        protocol=protocol_cls(),
        host=host,
        port=port,
        transport=transport,
        on_event=on_event,
        history_store=history_store or JsonFileHistoryStore(),
    )


class ChatSession:
    def __init__(self, protocol, host: str, port: int, transport, on_event, history_store):
        self.protocol = protocol  # ProtocolPort
        self.host = host
        self.port = port
        self._transport = transport  # TransportPort
        self._emit = on_event  # EventSink
        self._history = history_store  # HistoryStorePort

        self.my_id = ""
        self.joined_channels: set[str] = set()
        self.active_channel = ""
        self.members: dict[str, set[str]] = {}
        self.nicknames: dict[str, str] = {}
        self.avatars: dict[str, str] = {}
        # 그 사람이 무슨 프로그램으로 접속했는지(CTCP VERSION 응답 그대로).
        # 답을 안 주는 사람도 있으므로 "모름"이 정상 상태다
        self.client_versions: dict[str, str] = {}
        # (채널, 호출 대상 user_id) -> 마지막으로 그 사람을 @호출해서 실제로 전송한 시각
        self.mention_cooldowns: dict[tuple[str, str], float] = {}
        # (채널, 치트 id) -> 마지막으로 그 치트를 실제로 전송한 시각 (채널당 쿨타임, 사람 무관)
        self.cheat_cooldowns: dict[tuple[str, str], float] = {}

        # 프로토콜 구현체가 자기 진행 상태를 여기에 보관함(세션은 의미를 해석하지 않고
        # 저장 공간만 제공 - 프로토콜별 필드를 세션 코드가 알 필요가 없게)
        self.pending_auth_mode = ""
        self.pending_user_id = ""
        self.pending_irc_nick = ""
        self.irc_password = ""
        self.irc_identified = False
        self.irc_names_buffer: dict[str, list[str]] = {}
        # (보낸사람, 전송id) -> {조각번호: 조각}. IRC는 한 줄이 512바이트로 제한돼서
        # 아이콘을 여러 줄로 나눠 받기 때문에 다 모일 때까지 여기 담아둠
        self.irc_avatar_chunks: dict[tuple[str, str], dict[int, str]] = {}
        self.irc_nick_retries = 0
        self.nick_change_pending = False

    @property
    def protocol_mode(self) -> str:
        return self.protocol.name

    # ==================== 프로토콜 구현체가 쓰는 협력 API ====================

    def transport(self, payload):
        self._transport(payload)

    def emit(self, event):
        self._emit(event)

    def set_identity(self, user_id: str):
        """로그인/IRC 등록이 확정돼서 내 식별자가 정해졌을 때(닉네임 변경 포함)"""
        self.my_id = user_id
        self._emit(events.LoggedIn(user_id))
        # 내가 무슨 프로그램을 쓰는지는 물어볼 필요가 없다 - 우리 자신이니까.
        # 이걸 안 해두면 참여자 목록에서 나만 로고가 비어 보인다
        self.apply_client_version(user_id, constants.our_client_version())

    def enter_channel(self, channel: str, text: str):
        self.joined_channels.add(channel)
        self.active_channel = channel
        history = self._history.load_history(self.protocol.name, self.host, self.port, channel)
        self._emit(events.ChannelJoined(channel, text, history))

    def forget_channel(self, channel: str):
        self.joined_channels.discard(channel)
        self.members.pop(channel, None)
        if self.active_channel == channel:
            self.active_channel = next(iter(self.joined_channels), "")

    def deliver_message(self, channel: str, sender: str, text: str, mine: bool, ts: float,
                        record_history: bool = True):
        # /me, /notice로 보낸 메시지는 CTCP 프레이밍이 씌워져 오므로 여기서 벗겨냄.
        # 두 프로토콜이 같은 프레이밍을 쓰기 때문에 이 한 곳만 거치면 됨
        kind, body = commands.classify_message(text)
        is_mention = (not mine) and self._is_mentioned(body)
        self._emit(events.MessageReceived(channel, sender, body, mine, ts, is_mention, kind))
        if record_history:
            self._history.append_message(
                self.protocol.name, self.host, self.port, channel, sender, body, ts
            )
        # 치트 효과를 누가 보는지는 치트마다 다름(CheatSpec.for_everyone).
        # 보여주는 연출은 채널 전원이 보고, 조종하는 것은 친 사람만 봄 - 여기에
        # 치트별 분기를 두지 않고 명세를 그대로 따름
        cheat = find_cheat(body)
        if cheat is not None and (cheat.for_everyone or mine):
            self._emit(events.CheatActivated(channel, cheat.id))

    def replace_members(self, channel: str, users) -> None:
        self.members[channel] = set(users)
        self._emit(events.UserlistUpdated(channel, sorted(self.members[channel])))

    def add_member(self, channel: str, nick: str):
        self.members.setdefault(channel, set()).add(nick)
        self._emit(events.UserlistUpdated(channel, sorted(self.members[channel])))

    def remove_member(self, channel: str, nick: str):
        self.members.setdefault(channel, set()).discard(nick)
        self._emit(events.UserlistUpdated(channel, sorted(self.members[channel])))

    def apply_avatar(self, user_id: str, avatar_b64):
        if avatar_b64:
            self.avatars[user_id] = avatar_b64
        else:
            self.avatars.pop(user_id, None)
        self._emit(events.AvatarUpdated(user_id, avatar_b64))

    def apply_client_version(self, user_id: str, version: str):
        """그 사람이 쓰는 프로그램을 알아냈을 때."""
        if not version:
            return
        self.client_versions[user_id] = version
        self._emit(events.ClientVersionUpdated(user_id, version))

    def forget_client_version(self, user_id: str):
        """그 사람이 무슨 프로그램을 쓰는지 다시 알아봐야 할 때(예: 새로 접속해 들어옴)."""
        self.client_versions.pop(user_id, None)

    def request_client_version(self, user_id: str):
        """그 사람에게 무슨 프로그램을 쓰는지 물어본다.

        **언제/몇 명에게 물을지는 여기서 정하지 않는다.** 한꺼번에 우르르 보내면 서버가
        홍수로 보고 끊어버리므로, 간격을 두는 일은 어댑터(gui/version_prober.py)가 한다.
        """
        if not user_id or user_id == self.my_id:
            return
        self.protocol.request_client_version(self, user_id)

    def request_client_versions_in_channel(self, channel: str):
        """채널 전체에 한 줄로 물어본다(개인별로 묻는 길이 막힌 서버용)."""
        if channel:
            self.protocol.request_client_versions_in_channel(self, channel)

    def unknown_client_users(self, channel: str) -> list[str]:
        """그 채널에서 아직 무슨 프로그램인지 모르는 사람들(나 자신은 뺀다)."""
        return [user for user in sorted(self.members.get(channel, ()))
                if user != self.my_id and user not in self.client_versions]

    def apply_nickname(self, user_id: str, nickname):
        if nickname:
            self.nicknames[user_id] = nickname
        else:
            self.nicknames.pop(user_id, None)
        self._emit(events.NicknameUpdated(user_id, nickname))

    # ==================== 의도(intent) - 어댑터가 사용자 행동에 반응해서 호출 ====================

    def login(self, user_id: str, password: str):
        self.pending_auth_mode = "login"
        self.pending_user_id = user_id
        self.protocol.start_auth(self, user_id, password, "login")

    def register(self, user_id: str, password: str):
        self.pending_auth_mode = "register"
        self.pending_user_id = user_id
        self.protocol.start_auth(self, user_id, password, "register")

    def create_channel(self, channel: str, key: str = ""):
        self.protocol.create_channel(self, channel, key)

    def join_channel(self, channel: str, key: str = ""):
        self.protocol.join(self, channel, key)

    def leave_channel(self, channel: str):
        self.protocol.leave(self, channel)

    def send_message(self, channel: str, text: str):
        """입력창에 친 한 줄을 처리 - 슬래시 명령 / 치트 / 일반 채팅을 여기서 갈라줌.

        @호출·치트 쿨타임에 걸리면 전송 자체를 안 하고 안내 이벤트만 발행함(채팅창에 안 남음).
        """
        parsed = commands.parse_command(text)
        if parsed is not None:
            self.run_command(channel, *parsed)
            return
        # '//공지'처럼 슬래시로 시작하는 평문을 보내려던 경우 앞 슬래시 하나를 떼고 전송
        text = commands.escape_literal(text)

        cheat = find_cheat(text)
        if cheat is not None:
            remaining = self._check_cheat_cooldown(channel, cheat)
            if remaining:
                self._emit(events.CheatBlocked(remaining))
                return
            self.cheat_cooldowns[(channel, cheat.id)] = time.time()
            self.protocol.send_chat(self, channel, text)
            return

        self.send_wire_chat(channel, text, text)

    def send_wire_chat(self, channel: str, wire_text: str, display_text: str) -> bool:
        """@호출 쿨타임 정책을 적용한 뒤 실제로 전송. 막히면 False.

        wire_text는 실제로 나가는 문자열(/me면 CTCP 프레이밍이 씌워진 형태),
        display_text는 쿨타임 판정에 쓰는 사람이 읽는 본문 - 프레이밍 때문에 @토큰 판정이
        달라지면 안 되므로 둘을 분리했음.
        """
        blocked_target, remaining = self._check_mention_cooldown(channel, display_text)
        if blocked_target is not None:
            self._emit(events.MentionBlocked(blocked_target, remaining))
            return False
        self._record_mention_cooldowns(channel, display_text)
        self.protocol.send_chat(self, channel, wire_text)
        return True

    def run_command(self, channel: str, name: str, args: str):
        """슬래시 명령 실행을 프로토콜 전략에 위임.

        이 파일에 명령별 분기를 두지 않는 게 핵심(OCP) - 어떤 명령을 지원하는지는
        프로토콜마다 다르고, 새 명령 추가도 프로토콜 쪽 표에 한 줄이면 끝나야 함.
        """
        if self.protocol.run_command(self, channel, name, args):
            return
        known = {spec.name for spec in self.protocol.command_specs()}
        if name in known:  # 이론상 도달 불가 - 표와 핸들러가 어긋났을 때만
            self._emit(events.CommandError(f"/{name} 명령을 처리하지 못했습니다."))
        else:
            self._emit(events.CommandError(
                f"/{name} 은(는) 이 서버에서 지원하지 않는 명령입니다. /help 로 목록을 볼 수 있습니다."
            ))

    def command_specs(self):
        """자동완성 목록/도움말이 쓰는 지금 프로토콜의 명령 목록"""
        return self.protocol.command_specs()

    def _check_cheat_cooldown(self, channel: str, cheat) -> int:
        """남은 쿨타임(초). 0이면 지금 써도 됨"""
        if not cheat.cooldown_sec:
            return 0
        last = self.cheat_cooldowns.get((channel, cheat.id))
        if last is None:
            return 0
        elapsed = time.time() - last
        if elapsed >= cheat.cooldown_sec:
            return 0
        return int(cheat.cooldown_sec - elapsed) + 1

    def set_avatar(self, avatar_b64: str) -> bool:
        """너무 크면 아무 것도 안 하고 False 반환"""
        if len(avatar_b64) > AVATAR_MAX_B64_CHARS:
            return False
        self.apply_avatar(self.my_id, avatar_b64)
        self.protocol.publish_avatar(self, avatar_b64)
        return True

    def set_nickname(self, nickname: str):
        self.protocol.publish_nickname(self, nickname)

    def restore_my_profile(self, avatar_b64: str | None):
        """로그인 직후, 예전에 내가 설정해둔 아이콘을 되살림(네트워크로 보내지는 않음).

        보낼 필요가 없는 이유: 커스텀 서버는 계정에 이미 저장해두고 입장 때 알아서
        내려주고, IRC는 채널에 입장하는 순간 JOIN 처리에서 자동으로 뿌려짐. 여기서는
        "내 아이콘이 뭐였는지"를 세션이 기억하게만 해두면 됨 - 이게 없으면 재시작 후
        프로필 창이 비어 보이고, IRC에선 남들에게 내 아이콘을 다시 못 보냄."""
        if not avatar_b64 or not self.my_id:
            return
        self.apply_avatar(self.my_id, avatar_b64)

    def normalize_channel(self, channel: str) -> str:
        return self.protocol.normalize_channel(channel)

    # ==================== 수신 처리 ====================

    def handle_incoming(self, raw):
        """소켓에서 받은 원시 메시지 한 건(커스텀=dict, IRC=IrcMessage)을 프로토콜에 위임"""
        self.protocol.handle_incoming(self, raw)

    # ==================== @호출 정책 (프로토콜 무관 - 우리 앱만의 규칙) ====================

    def display_name_for(self, user_id: str) -> str:
        return self.nicknames.get(user_id, user_id)

    def _mentioned_targets(self, channel: str, text: str) -> list[str]:
        """text의 @토큰들을 그 채널의 실제 참여자(닉네임 또는 아이디)로 해석"""
        tokens = MENTION_TOKEN_RE.findall(text)
        if not tokens:
            return []
        members = self.members.get(channel, set())
        by_display = {self.display_name_for(uid): uid for uid in members}
        by_id = {uid: uid for uid in members}
        resolved = []
        for token in tokens:
            target = by_display.get(token) or by_id.get(token)
            if target and target not in resolved:
                resolved.append(target)
        return resolved

    def _check_mention_cooldown(self, channel: str, text: str) -> tuple[str | None, int]:
        now = time.time()
        for target in self._mentioned_targets(channel, text):
            last = self.mention_cooldowns.get((channel, target))
            if last is not None and now - last < MENTION_COOLDOWN_SEC:
                remaining = int(MENTION_COOLDOWN_SEC - (now - last)) + 1
                return self.display_name_for(target), remaining
        return None, 0

    def _record_mention_cooldowns(self, channel: str, text: str):
        now = time.time()
        for target in self._mentioned_targets(channel, text):
            self.mention_cooldowns[(channel, target)] = now

    def _is_mentioned(self, text: str) -> bool:
        if not self.my_id:
            return False
        my_names = {self.my_id, self.display_name_for(self.my_id)}
        return any(token in my_names for token in MENTION_TOKEN_RE.findall(text))
