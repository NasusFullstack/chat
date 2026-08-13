"""도메인 코어가 바깥세상과 만나는 경계(포트) 정의.

DIP(의존성 역전): 코어(ChatSession)는 여기 있는 "추상"에만 의존하고, 실제 구현체
(파일에 저장하는 기록 저장소, Qt 소켓, asyncio 소켓 등)는 바깥에서 주입받음. 그래서
코어는 Qt/asyncio/파일시스템을 전혀 몰라도 되고, 테스트에서는 가짜 구현을 꽂아
넣기만 하면 됨.

typing.Protocol을 쓰는 이유: 구현체가 이 클래스를 상속할 필요 없이 "메서드 모양만
맞으면" 되는 구조적 타이핑이라, 기존 모듈(history_store.py 등)을 건드리지 않고도
얇은 래퍼만으로 포트를 만족시킬 수 있음.
"""
from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class HistoryStorePort(Protocol):
    """대화 기록 저장소. 기본 구현은 JSON 파일이지만 코어는 그걸 몰라도 됨."""

    def load_history(self, protocol: str, host: str, port: int, channel: str) -> list[dict]:
        ...

    def append_message(
        self, protocol: str, host: str, port: int, channel: str,
        sender: str, text: str, ts: float,
    ) -> None:
        ...


@runtime_checkable
class ProtocolPort(Protocol):
    """와이어 프로토콜별 전략(strategy).

    OCP(개방-폐쇄): 새 프로토콜을 추가할 때 ChatSession을 열어서 if/else를 늘리는 게
    아니라, 이 포트를 만족하는 클래스를 새로 만들고 factory에 한 줄 등록하기만 하면 됨.
    ChatSession에는 프로토콜 이름을 비교하는 분기가 하나도 없어야 함.

    각 메서드는 첫 인자로 session(SessionContext)을 받아서 상태 조회/이벤트 발행/전송을
    함 - 프로토콜 구현체가 세션 상태를 직접 소유하지 않고 빌려 쓰는 형태.
    """

    name: str

    def start_auth(self, session: Any, user_id: str, password: str, mode: str) -> None:
        """mode는 "login" 또는 "register" (프로토콜이 구분을 안 하면 무시해도 됨)"""
        ...

    def create_channel(self, session: Any, channel: str, key: str) -> None:
        ...

    def join(self, session: Any, channel: str, key: str) -> None:
        ...

    def leave(self, session: Any, channel: str) -> None:
        ...

    def send_chat(self, session: Any, channel: str, text: str) -> None:
        ...

    def publish_avatar(self, session: Any, avatar_b64: str) -> None:
        ...

    def request_client_version(self, session: Any, user_id: str) -> None:
        """상대가 무슨 프로그램을 쓰는지 물어봄(프로토콜마다 방법이 다름)."""
        ...

    def request_client_versions_in_channel(self, session: Any, channel: str) -> None:
        """채널 전체에 한 번에 물어봄(개인별로 묻는 길이 막힌 서버에서 쓰는 우회로)."""
        ...

    def keepalive(self, session: Any) -> None:
        """조용할 때 "살아 있냐"를 한 줄 보낸다(프로토콜마다 방식이 다르다)."""

    def disconnect_gracefully(self, session: Any, reason: str) -> None:
        """끊기 전에 서버에 '나갑니다'라고 알림(프로토콜마다 방법이 다름)."""
        ...

    def publish_nickname(self, session: Any, nickname: str) -> None:
        ...

    def handle_incoming(self, session: Any, raw: Any) -> None:
        """소켓에서 받은 원시 메시지 한 건을 해석해 세션 상태를 갱신하고 이벤트를 발행"""
        ...

    def normalize_channel(self, channel: str) -> str:
        ...

    def command_specs(self) -> Any:
        """이 프로토콜이 지원하는 슬래시 명령 명세 목록(chat_core.commands.CommandSpec).

        자동완성 목록과 /help가 같은 출처를 쓰게 하려고 포트에 둠 - 프로토콜마다
        실제로 할 수 있는 명령이 다르므로(예: /whois는 IRC만) 목록도 프로토콜이 정함.
        """
        ...

    def run_command(self, session: Any, channel: str, name: str, args: str) -> bool:
        """슬래시 명령 실행. 이 프로토콜이 모르는 명령이면 False를 반환(세션이 안내함)."""
        ...


# 전송 포트: 프로토콜 구현체가 만든 페이로드를 실제로 소켓에 내보내는 콜러블.
# 커스텀 프로토콜은 dict를, IRC는 문자열 라인을 넘김 - 어느 쪽이든 어댑터(GUI/CLI)가
# 자기 소켓에 맞게 처리함. 코어는 "보낸다"는 사실만 알고 어떻게 보내는지는 모름.
TransportPort = Callable[[Any], None]

# 이벤트 싱크: 코어가 발행하는 chat_core.events 인스턴스를 받아가는 콜러블.
EventSink = Callable[[Any], None]
