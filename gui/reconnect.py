"""서버가 끊겼을 때 다시 붙는 정책.

'언제 다시 붙을지'만 정하는 부품이다 - 소켓도 세션도 위젯도 모른다. 실제로 접속하는 일과
안내를 띄우는 일은 생성자로 받은 함수에 맡긴다. 그래서 Qt 창 없이도 이 정책만 따로
시험할 수 있고, MainWindow는 "무엇을 할지"만 남는다.

정책 자체는 단순하다:
- 예기치 않게 끊기면 보던 채널을 기억해두고 재시도를 건다
- 시도할수록 간격을 늘린다(죽은 서버를 같은 속도로 계속 두드리지 않게)
- 정해진 횟수를 넘기면 포기하고 사용자에게 알린다
- 다시 로그인에 성공하면 기억해둔 채널로 돌아간다
"""
from PySide6.QtCore import QObject, QTimer

from gui.theme import RECONNECT_BASE_MS, RECONNECT_MAX_ATTEMPTS, RECONNECT_MAX_MS


class ReconnectPolicy(QObject):
    def __init__(self, connect_now, notify, parent=None):
        """connect_now(): 실제 접속 시도. notify(글자): 사용자에게 보여줄 안내."""
        super().__init__(parent)
        self._connect_now = connect_now
        self._notify = notify
        self.active = False           # 지금 자동 재접속 중인가
        self.attempt = 0
        self._channels: list[str] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fire)

    def start(self, channels) -> bool:
        """끊김이 확인됐을 때 호출. 이미 진행 중이면 False."""
        if self.active:
            return False
        self.active = True
        self.attempt = 0
        self._channels = sorted(channels)   # 다시 붙은 뒤 돌아갈 곳
        self._notify("서버와의 연결이 끊어졌습니다. 다시 연결하는 중...")
        self.schedule()
        return True

    def schedule(self):
        """다음 시도를 예약. 한도를 넘으면 포기한다."""
        self.attempt += 1
        if self.attempt > RECONNECT_MAX_ATTEMPTS:
            self.active = False
            self._notify("다시 연결하지 못했습니다. 로그인 화면에서 다시 접속해 주세요.")
            return
        delay = min(RECONNECT_BASE_MS * self.attempt, RECONNECT_MAX_MS)
        self._notify(f"다시 연결 시도 {self.attempt}/{RECONNECT_MAX_ATTEMPTS}"
                     f" ({delay // 1000}초 후)")
        self._timer.start(delay)

    def _fire(self):
        if self.active:
            self._connect_now()

    def succeeded(self) -> list[str]:
        """다시 로그인까지 됐을 때 - 돌아갈 채널 목록을 돌려주고 정책을 끝낸다."""
        self.active = False
        self.attempt = 0
        self._notify("다시 연결되었습니다.")
        channels, self._channels = self._channels, []
        return channels

    def cancel(self):
        """로그아웃/종료 등 일부러 끊는 경우 - 재시도를 완전히 접는다."""
        self._timer.stop()
        self.active = False
        self.attempt = 0
        self._channels = []

    @property
    def pending_channels(self) -> list[str]:
        return list(self._channels)
