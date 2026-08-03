"""ChatSession(session.py)이 상태 변화를 어댑터(GUI/CLI)에 알리는 불변 이벤트들.

Qt/asyncio 어느 쪽에도 의존하지 않는 순수 데이터. 어댑터는 on_event 콜백에서
isinstance로 분기해서 자기 방식대로 렌더링(Qt 위젯 갱신 / print)하면 됨.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LoggedIn:
    """커스텀 프로토콜 로그인 성공 / IRC 접속 확정(RPL_WELCOME) 둘 다 여기로 옴"""
    user_id: str


@dataclass(frozen=True)
class RegisterSucceeded:
    """커스텀 프로토콜 전용 - 회원가입 성공(아직 로그인은 안 됨)"""
    pass


@dataclass(frozen=True)
class AuthFailed:
    text: str


@dataclass(frozen=True)
class ChannelCreated:
    """커스텀 프로토콜 전용 - 채널 생성만 완료된 상태(아직 입장은 안 됨, 뒤이어
    join_channel()을 또 호출해야 함 - 서버가 생성과 입장을 별개 단계로 처리하기 때문)"""
    channel: str
    text: str


@dataclass(frozen=True)
class ChannelJoined:
    channel: str
    text: str
    history: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class ChannelJoinFailed:
    channel: str
    text: str


@dataclass(frozen=True)
class ChannelLeft:
    channel: str


@dataclass(frozen=True)
class ChannelLeaveFailed:
    channel: str
    text: str


@dataclass(frozen=True)
class MessageReceived:
    channel: str
    sender: str
    text: str
    mine: bool
    ts: float
    is_mention: bool = False
    # commands.KIND_* - /me는 "action", /notice는 "notice", 평범한 채팅은 "chat".
    # 종류 판정은 코어가 하고 어댑터는 그리기만 함
    kind: str = "chat"


@dataclass(frozen=True)
class SystemNotice:
    channel: str
    text: str


@dataclass(frozen=True)
class UserlistUpdated:
    channel: str
    users: list[str]


@dataclass(frozen=True)
class AvatarUpdated:
    user_id: str
    avatar_b64: str | None


@dataclass(frozen=True)
class NicknameUpdated:
    user_id: str
    nickname: str | None


@dataclass(frozen=True)
class NicknameChangeFailed:
    text: str


@dataclass(frozen=True)
class NicknameRetrying:
    """IRC 등록 중 닉네임이 이미 사용 중이라 다른 닉네임으로 자동 재시도하는 중"""
    new_nickname: str


@dataclass(frozen=True)
class CheatActivated:
    """치트 문구가 채널에 떴음 - 그 채널을 보는 모두에게 해당 효과를 띄우면 됨.

    cheat_id는 constants.CHEAT_* 값(자원 오버레이 / 배틀크루저 소환 / 해제)"""
    channel: str
    cheat_id: str = "resources"


@dataclass(frozen=True)
class CheatBlocked:
    """치트가 채널 쿨타임에 걸려 전송되지 않음 - 친 사람한테만 남은 시간을 알림"""
    remaining_sec: int


@dataclass(frozen=True)
class CommandError:
    """슬래시 명령이 잘못됐거나 이 프로토콜에서 지원되지 않음 - 친 사람한테만 보여줌"""
    text: str


@dataclass(frozen=True)
class UnfurlResult:
    """서버가 대신 가져와 준 링크 미리보기 정보.

    thumb_b64는 서버가 이미지 기능을 켰을 때만 채워짐(기본은 꺼져 있어 제목/설명만 옴).
    아무것도 못 가져왔으면 title이 비어 있으니 어댑터는 미리보기를 만들지 않으면 됨."""
    url: str
    title: str = ""
    description: str = ""
    thumb_b64: str = ""


@dataclass(frozen=True)
class CommandHelp:
    """/help 결과 - 어댑터가 목록을 자기 방식대로 출력(GUI는 채팅창, CLI는 print)"""
    channel: str
    lines: list[str]


@dataclass(frozen=True)
class MentionBlocked:
    """@호출 쿨타임에 걸려서 메시지 자체가 전송 안 됐음 - 보낸 사람한테만 보여줄 안내"""
    target_display: str
    remaining_sec: int


@dataclass(frozen=True)
class ConnectionClosed:
    text: str


@dataclass(frozen=True)
class GenericError:
    text: str
