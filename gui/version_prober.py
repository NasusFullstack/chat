"""참여자들에게 "무슨 프로그램 쓰세요?"를 **천천히** 물어보는 담당자.

왜 천천히인가: IRC 서버는 짧은 시간에 여러 줄을 보내면 홍수(flood)로 보고 연결을
끊어버린다. 참여자가 30명인 채널에 들어가자마자 30줄을 보내면 그대로 튕긴다.
그래서 한 번에 한 명씩, 간격을 두고 묻는다.

한 번 물어본 사람은 다시 묻지 않는다(답을 안 준 사람도 마찬가지). 답을 안 주는 설정을
쓰는 사람에게 계속 묻는 건 실례이기도 하고, 어차피 답이 오지 않는다.

이 파일은 '언제 묻는가'만 안다. 무엇을 보내는지는 프로토콜이, 받은 답을 어떻게
보여주는지는 참여자 목록이 정한다.
"""
from PySide6.QtCore import QObject, QTimer

# 한 명 물어보고 다음 사람까지 기다리는 시간. 서버의 홍수 판정에 안 걸릴 만큼 넉넉히 둔다.
# 급할 이유가 전혀 없는 일(로고 하나 뜨는 것)이라 여유 있게 잡는다
PROBE_INTERVAL_MS = 3500
# 한 채널에서 물어볼 사람 수 상한. 수백 명짜리 채널에서 몇 분씩 요청을 보내지 않도록
MAX_PROBES_PER_ROUND = 25


class VersionProber(QObject):
    """물어볼 사람을 줄 세워 두고 하나씩 꺼내 묻는다."""

    def __init__(self, ask, parent=None):
        """ask(user_id) - 실제로 물어보는 일(세션의 request_client_version)."""
        super().__init__(parent)
        self._ask = ask
        self._queue: list[str] = []
        self._asked: set[str] = set()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._ask_next)

    def enqueue(self, user_ids):
        """아직 안 물어본 사람만 줄에 넣는다."""
        added = False
        for user_id in list(user_ids)[:MAX_PROBES_PER_ROUND]:
            if user_id and user_id not in self._asked and user_id not in self._queue:
                self._queue.append(user_id)
                added = True
        if added and not self._timer.isActive():
            # 첫 한 명도 바로 묻지 않는다 - 채널에 들어가는 순간은 서버가 참여자 목록,
            # 지난 대화 등으로 이미 바쁘다. 한 박자 쉬고 시작한다
            self._timer.start(PROBE_INTERVAL_MS)

    def _ask_next(self):
        if not self._queue:
            self._timer.stop()
            return
        user_id = self._queue.pop(0)
        self._asked.add(user_id)
        self._ask(user_id)

    def reset(self):
        """로그아웃/재접속 - 다른 서버면 사람도 프로그램도 다른 세상이다."""
        self._timer.stop()
        self._queue.clear()
        self._asked.clear()

    def pending(self) -> int:
        return len(self._queue)

    def is_working(self) -> bool:
        """지금 물어보는 중인가(=서버가 낸 오류가 우리 때문일 수 있는가)."""
        return bool(self._queue) or bool(self._asked)
