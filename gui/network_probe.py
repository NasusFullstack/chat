"""접속이 안 될 때 "네트워크가 막은 것인지"를 가려내는 작은 검사.

왜 필요한가: 학교/회사 와이파이는 보통 웹(80/443)만 열어두고 나머지 포트를 막는다.
그런 곳에서는 홈페이지는 멀쩡히 열리는데 채팅만 안 되므로, 사용자 눈에는 "서버가 죽었나?
내가 뭘 잘못 눌렀나?"로 보인다(실제 신고: 핫스팟으로는 되는데 학교 와이파이로는 안 됨).

그래서 접속에 실패하면 **같은 서버의 웹 포트**에 연결해본다.
- 웹은 되는데 채팅 포트만 안 된다 -> 서버는 살아 있고 네트워크가 막은 것이다
- 웹도 안 된다 -> 서버가 꺼졌거나 주소가 틀렸거나 인터넷 자체가 안 되는 것이다

이 파일은 판단만 하고 화면은 모른다. 무엇을 보여줄지는 부르는 쪽이 정한다.
"""
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QTcpSocket

# 웹이 열려 있는지 볼 때 쓰는 포트. 443 하나만 본다 - 막는 네트워크도 이건 거의 항상
# 열어두고, 여러 포트를 차례로 두드리면 그만큼 기다리는 시간만 길어진다
WEB_PORTS = (443,)
# 짧게 잡는다. 이건 "왜 안 되는지" 안내를 다듬는 부가 기능이라, 오래 붙잡고 있을 이유가 없다
PROBE_TIMEOUT_MS = 2500


class WebReachableProbe(QObject):
    """그 서버의 웹 포트에 붙을 수 있는지만 본다(아무 것도 보내지 않는다).

    finished(True)  = 웹은 되더라 -> 채팅 포트만 막힌 것
    finished(False) = 웹도 안 되더라 -> 서버/주소/인터넷 문제
    """

    finished = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._socket = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._host = ""
        self._remaining = []
        self._done = False

    def start(self, host: str):
        if not host:
            self._emit(False)
            return
        self._host = host
        self._remaining = list(WEB_PORTS)
        self._done = False
        self._try_next()

    def _try_next(self):
        if self._done:
            return
        if not self._remaining:
            self._emit(False)
            return
        port = self._remaining.pop(0)
        self._cleanup_socket()
        self._socket = QTcpSocket(self)
        self._socket.connected.connect(lambda: self._emit(True))
        self._socket.errorOccurred.connect(lambda _err: self._try_next())
        self._socket.connectToHost(self._host, port)
        self._timer.start(PROBE_TIMEOUT_MS)

    def _on_timeout(self):
        # 막힌 포트는 거절 대신 '그냥 아무 대답 없음'인 경우가 많다 - 그래서 시간 제한이 필요
        self._try_next()

    def _emit(self, reachable: bool):
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self._cleanup_socket()
        self.finished.emit(reachable)

    def _cleanup_socket(self):
        if self._socket is None:
            return
        socket, self._socket = self._socket, None
        socket.abort()
        socket.deleteLater()

    def cancel(self):
        self._done = True
        self._timer.stop()
        self._cleanup_socket()


def blocked_port_message(host: str, port: int) -> str:
    """웹은 되는데 채팅 포트만 막혔을 때 보여줄 안내.

    사용자가 스스로 할 수 있는 것(핫스팟)과, 서버를 가진 사람이 해야 하는 것(443 개방)을
    나눠서 적는다 - 안 그러면 "그래서 나보고 어쩌라고"가 된다.
    """
    return (f"이 네트워크가 채팅 포트({port})를 막고 있습니다.\n"
            f"같은 서버의 웹 포트는 열려 있어서 서버 자체는 정상입니다.\n"
            f"학교·회사 와이파이에서 흔한 설정입니다 - 휴대폰 핫스팟으로는 접속됩니다.\n"
            f"계속 이 네트워크에서 쓰려면 서버 관리자에게 443 포트 개방을 요청하세요.")
