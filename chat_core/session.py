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

from chat_core import events
from chat_core.constants import (
    AVATAR_MAX_B64_CHARS, CHEAT_COOLDOWN_SEC, MENTION_COOLDOWN_SEC, MENTION_TOKEN_RE,
    is_cheat_phrase,
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
        # (채널, 호출 대상 user_id) -> 마지막으로 그 사람을 @호출해서 실제로 전송한 시각
        self.mention_cooldowns: dict[tuple[str, str], float] = {}
        # 채널 -> 마지막으로 치트를 실제로 전송한 시각 (채널당 쿨타임, 사람 무관)
        self.cheat_cooldowns: dict[str, float] = {}

        # 프로토콜 구현체가 자기 진행 상태를 여기에 보관함(세션은 의미를 해석하지 않고
        # 저장 공간만 제공 - 프로토콜별 필드를 세션 코드가 알 필요가 없게)
        self.pending_auth_mode = ""
        self.pending_user_id = ""
        self.pending_irc_nick = ""
        self.irc_password = ""
        self.irc_identified = False
        self.irc_names_buffer: dict[str, list[str]] = {}
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
        is_mention = (not mine) and self._is_mentioned(text)
        self._emit(events.MessageReceived(channel, sender, text, mine, ts, is_mention))
        if record_history:
            self._history.append_message(
                self.protocol.name, self.host, self.port, channel, sender, text, ts
            )
        # 치트 문구는 그 채널을 보고 있는 모두에게 효과가 떠야 하므로, 보낸 사람 여부와
        # 무관하게(내가 친 것도 포함) 메시지가 도착하면 이벤트를 발행함
        if is_cheat_phrase(text):
            self._emit(events.CheatActivated(channel))

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
        """@호출/치트 쿨타임에 걸리면 전송 자체를 안 하고 안내 이벤트만 발행(채팅창에 안 남음)"""
        if is_cheat_phrase(text):
            remaining = self._check_cheat_cooldown(channel)
            if remaining:
                self._emit(events.CheatBlocked(remaining))
                return
            self.cheat_cooldowns[channel] = time.time()
            self.protocol.send_chat(self, channel, text)
            return

        blocked_target, remaining = self._check_mention_cooldown(channel, text)
        if blocked_target is not None:
            self._emit(events.MentionBlocked(blocked_target, remaining))
            return
        self._record_mention_cooldowns(channel, text)
        self.protocol.send_chat(self, channel, text)

    def _check_cheat_cooldown(self, channel: str) -> int:
        """남은 쿨타임(초). 0이면 지금 써도 됨"""
        last = self.cheat_cooldowns.get(channel)
        if last is None:
            return 0
        elapsed = time.time() - last
        if elapsed >= CHEAT_COOLDOWN_SEC:
            return 0
        return int(CHEAT_COOLDOWN_SEC - elapsed) + 1

    def set_avatar(self, avatar_b64: str) -> bool:
        """너무 크면 아무 것도 안 하고 False 반환"""
        if len(avatar_b64) > AVATAR_MAX_B64_CHARS:
            return False
        self.apply_avatar(self.my_id, avatar_b64)
        self.protocol.publish_avatar(self, avatar_b64)
        return True

    def set_nickname(self, nickname: str):
        self.protocol.publish_nickname(self, nickname)

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
