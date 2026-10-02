"""서버 채팅(jsserv `/chat/ws`)과의 통로 - `ChatClient` 와 **같은 모양**으로 보인다.

## 왜 같은 모양이어야 하나
창(`MainWindow`)의 접속 절차는 이미 복잡하고, 거기를 건드리는 것은 따로 잡아야 할
수술이다(CLAUDE.md). 그래서 전송 수단만 바꾸고 **창이 보는 창구는 그대로** 둔다 -
창은 `self.client` 가 TLS 소켓인지 WebSocket 인지 몰라도 된다.

맞춰야 하는 것(창이 실제로 쓰는 것만):

    신호: connected / encrypted / disconnected
          message_received(dict) / connection_failed(str)
    함수: set_mode / connect_to_server / send_cmd / send_irc
          flush_pending / recent_lines / abort / state
    값:   last_rx_at / _pinned_cert

`irc_line_received` 와 `certificate_untrusted` 는 여기서 쓸 일이 없지만 **같이 둔다** -
창이 어느 쪽에든 연결하기 때문이다(없으면 연결할 때 터진다).

## 인증서는 보통대로 검사한다
IRC 서버에 쓰는 지문 고정(`trusted_certs.py`)을 여기 갖다 쓰면 안 된다. 중계 서버는
정식 인증서라 그럴 이유가 없고, 백신이 HTTPS 를 가로채는 PC 에서는 지문이 사람마다
달라져 전부 막힌다(전투 중계 `gui/battle/net.py` 에 같은 설명이 있다).
"""
import json
import time
from collections import deque

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWebSockets import QWebSocket

import relay

# 사고 직전에 서버가 뭘 보냈는지 알아보려고 남겨두는 줄 수(ChatClient 와 같은 값)
RECENT_LINE_COUNT = 40

# 이 안에 못 붙으면 포기한다. 방화벽이 조용히 버리면 성공도 실패도 안 오고 매달린다
CONNECT_TIMEOUT_MS = 12_000


class ServerChatLink(QObject):
    """서버 채팅 한 연결. 소켓 사정은 여기서 끝내고 위로는 신호만 올린다."""

    # ---- 창이 연결하는 신호들(ChatClient 와 같은 이름·같은 뜻) ----
    connected = Signal()
    encrypted = Signal()
    disconnected = Signal()
    message_received = Signal(dict)
    irc_line_received = Signal(object)      # 여기선 안 쓴다(창이 연결만 한다)
    connection_failed = Signal(str)
    certificate_untrusted = Signal(str, int, str, str)   # 여기선 안 쓴다

    def __init__(self, parent=None):
        super().__init__(parent)
        self._socket = QWebSocket()
        self._socket.connected.connect(self._on_open)
        self._socket.textMessageReceived.connect(self._on_text)
        self._socket.disconnected.connect(self._on_close)
        self._socket.errorOccurred.connect(self._on_error)

        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_timeout)

        self._recent = deque(maxlen=RECENT_LINE_COUNT)
        self.last_rx_at = time.time()
        # 정식 인증서를 쓰므로 지문을 고정하지 않는다(위 설명). 창이 오류 문구를
        # 고를 때 이 값을 본다
        self._pinned_cert = False
        self._closing = False

    # ---------------------------------------------------------- 창이 부르는 것
    def set_mode(self, mode: str) -> None:
        """프로토콜 이름. 여기는 하나뿐이라 받아만 둔다(창구를 맞추려고)."""

    def connect_to_server(self, host: str, port: int, cert_path: str,
                          use_ssl: bool) -> None:
        """붙는다. **주소는 우리가 안다** - 사람이 적은 주소는 쓰지 않는다.

        IRC 는 아무 서버에나 붙을 수 있어서 주소를 받지만, 서버 채팅은 우리 서버
        하나뿐이다. 그래서 받은 값은 무시하고 `relay` 가 아는 주소로 간다 - 사람이
        주소를 잘못 적어 "왜 안 되지"가 되는 일이 없다.
        """
        self._closing = False
        self._timeout.start(CONNECT_TIMEOUT_MS)
        self._socket.open(QUrl(f"{relay.WS_SERVER}/chat/ws"))

    def send_cmd(self, payload: dict) -> None:
        if self._socket.state() != QAbstractSocket.SocketState.ConnectedState:
            return
        self._socket.sendTextMessage(json.dumps(payload, ensure_ascii=False))

    def send_irc(self, line: str) -> None:
        """여기서는 IRC 줄을 보낼 일이 없다 - 창구를 맞추려고 둔다."""

    def flush_pending(self, timeout_ms: int = 700) -> None:
        """WebSocket 은 보낸 것이 바로 나간다 - 기다릴 것이 없다.

        (TLS 소켓은 write 가 예약만 해서, 종료 직전 QUIT 이 안 나가는 일이 있었다.)
        """
        self._socket.flush()

    def recent_lines(self) -> list:
        """서버에서 받은 마지막 줄들(오래된 것부터). 사고 원인을 찾을 때 쓴다."""
        return list(self._recent)

    def abort(self) -> None:
        """일부러 끊는다. 그 뒤에 오는 '끊겼다'는 사고가 아니다."""
        self._closing = True
        self._timeout.stop()
        self._socket.abort()

    def state(self):
        """창이 `QAbstractSocket.SocketState.ConnectedState` 와 비교한다."""
        return self._socket.state()

    # ---------------------------------------------------------- 소켓에서 오는 것
    def _on_open(self):
        self._timeout.stop()
        self.last_rx_at = time.time()
        # 창은 '붙었다' 다음에 '암호화됐다'를 기다린다(TLS 소켓이 그렇게 동작한다).
        # wss 는 붙은 시점에 이미 암호화되어 있으므로 둘 다 바로 올린다
        self.connected.emit()
        self.encrypted.emit()

    def _on_text(self, text: str):
        self.last_rx_at = time.time()
        self._recent.append(text)
        try:
            message = json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return                       # 읽을 수 없는 줄은 조용히 버린다
        if isinstance(message, dict):
            self.message_received.emit(message)

    def _on_close(self):
        if self._closing:
            return                       # 일부러 끊은 것은 사고가 아니다
        self._timeout.stop()
        self.disconnected.emit()

    def _on_error(self, _error):
        if self._closing:
            return
        self._timeout.stop()
        self.connection_failed.emit(
            f"서버 채팅에 연결하지 못했습니다: {self._socket.errorString()}")

    def _on_timeout(self):
        if self._socket.state() == QAbstractSocket.SocketState.ConnectedState:
            return
        self._socket.abort()
        self.connection_failed.emit(
            "서버 채팅에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요.")
