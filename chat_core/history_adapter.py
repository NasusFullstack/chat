"""HistoryStorePort의 기본 구현 - 기존 history_store.py(JSON 파일)를 감싸는 얇은 어댑터.

코어는 HistoryStorePort라는 추상에만 의존하고, "JSON 파일에 저장한다"는 세부사항은
여기에만 있음(DIP). 나중에 SQLite나 서버 저장으로 바꾸고 싶으면 이 파일과 같은 모양의
클래스를 하나 더 만들어서 주입하면 되고, 코어는 안 건드려도 됨.
"""
import history_store


class JsonFileHistoryStore:
    """실행 파일 옆 history.json에 (프로토콜, 호스트, 포트, 채널)별로 기록을 남김"""

    def load_history(self, protocol: str, host: str, port: int, channel: str) -> list[dict]:
        return history_store.load_history(protocol, host, port, channel)

    def append_message(
        self, protocol: str, host: str, port: int, channel: str,
        sender: str, text: str, ts: float,
    ) -> None:
        history_store.append_message(protocol, host, port, channel, sender, text, ts)


class NullHistoryStore:
    """기록을 전혀 남기지 않는 구현 - 테스트나 '기록 끄기' 옵션에 쓸 수 있음"""

    def load_history(self, protocol: str, host: str, port: int, channel: str) -> list[dict]:
        return []

    def append_message(
        self, protocol: str, host: str, port: int, channel: str,
        sender: str, text: str, ts: float,
    ) -> None:
        pass
