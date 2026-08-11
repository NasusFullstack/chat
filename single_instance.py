"""이 컴퓨터에서 춥채팅이 **하나만** 뜨게 한다.

두 번 실행하면 트레이 아이콘이 두 개 생기고, 같은 계정으로 두 번 접속되며, 알림도 두 번
뜬다. 두 번째로 켠 사람은 보통 "창이 안 보여서" 다시 누른 것이므로, 새로 띄우는 대신
**이미 떠 있는 창을 꺼내주는 것**이 원하는 동작이다.

방법: 이름 있는 로컬 소켓(QLocalServer)을 자리처럼 쓴다.
- 자리에 연결이 되면 = 이미 누가 실행 중 -> 그쪽에 "창 좀 띄워줘"를 보내고 우리는 끝낸다
- 연결이 안 되면 = 우리가 처음 -> 그 자리를 차지하고, 나중에 누가 연결해오면 창을 띄운다

**업데이트 직후에는 조심해야 한다.** 새 버전이 실행될 때 예전 프로세스가 아직 완전히
안 죽었을 수 있는데, 그때 "이미 실행 중"으로 판단해 그냥 끝내버리면 업데이트 후 앱이
영영 안 뜬다. 그래서 업데이트 직후에는 잠깐 기다렸다가 다시 시도한다.
"""
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from version import IS_BETA

# 자리 이름. 사용자마다 다른 이름을 쓸 필요는 없다 - 로컬 소켓은 원래 사용자 세션 안에서만
# 보이고, 한 컴퓨터에서 한 사람이 하나만 켜면 된다는 것이 이 기능의 목적이다
# 테스트 버전은 자리 이름이 달라야 한다 - 안 그러면 정식 버전을 켜둔 채로 테스트 버전을
# 켰을 때 "이미 실행 중"으로 보고 그냥 꺼진다(둘을 나란히 놓고 비교할 수가 없다)
INSTANCE_KEY = "ChupChat-single-instance" + ("-beta" if IS_BETA else "")

CONNECT_TIMEOUT_MS = 400
# 업데이트 직후 예전 프로세스가 사라지길 기다리는 최대 시간
POST_UPDATE_WAIT_SEC = 8.0
POST_UPDATE_RETRY_SEC = 0.4

WAKE_MESSAGE = b"show"


class SingleInstance(QObject):
    """자리를 잡거나, 이미 있는 쪽을 깨우거나.

    activated: 다른 실행이 "창 띄워줘"라고 알려왔을 때
    """

    activated = Signal()

    def __init__(self, key: str = INSTANCE_KEY, parent=None):
        super().__init__(parent)
        self._key = key
        self._server = None
        # 깨우는 신호를 보낸 소켓. **참조를 들고 있어야 한다** - 함수가 끝나면서 객체가
        # 정리되면 저쪽이 읽기도 전에 연결이 닫혀 신호가 유실된다(실측으로 확인)
        self._waker = None

    # ---------------- 자리 잡기 ----------------

    def try_acquire(self, wait_for_previous: bool = False) -> bool:
        """우리가 유일한 실행이면 True.

        이미 다른 실행이 있으면 그쪽 창을 띄워주고 False를 돌려준다(호출자는 조용히 종료).
        wait_for_previous=True면 업데이트 직후로 보고, 예전 프로세스가 사라질 때까지
        잠시 기다렸다가 다시 시도한다.
        """
        deadline = time.time() + (POST_UPDATE_WAIT_SEC if wait_for_previous else 0.0)
        while True:
            if not self._someone_is_running():
                return self._listen()
            if time.time() >= deadline:
                return False
            time.sleep(POST_UPDATE_RETRY_SEC)

    def _someone_is_running(self) -> bool:
        """자리에 연결해본다. 연결되면 그쪽에 창을 띄우라고 알린다."""
        socket = QLocalSocket(self)
        self._waker = socket
        socket.connectToServer(self._key)
        if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
            self._waker = None
            return False
        socket.write(WAKE_MESSAGE)
        socket.flush()
        socket.waitForBytesWritten(CONNECT_TIMEOUT_MS)
        # **바로 끊으면 안 된다.** 저쪽이 받기 전에 연결이 사라져 신호가 유실된다
        # (실측: 두 번째로 켰는데 첫 번째 창이 안 떴다). 저쪽은 읽고 나서 끊으므로,
        # 끊길 때까지 잠깐 기다리면 "확실히 전달됨"이 된다. 저쪽이 죽어 있으면
        # 시간만 조금 쓰고 넘어간다
        socket.waitForDisconnected(CONNECT_TIMEOUT_MS)
        return True

    def _listen(self) -> bool:
        """자리를 차지한다. 예전에 비정상 종료해서 남은 자리는 치우고 다시 시도한다."""
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        if self._server.listen(self._key):
            return True
        # 앱이 강제 종료되면 자리가 남아 있을 수 있다(리눅스의 소켓 파일 등).
        # 위에서 '연결 안 됨'을 확인했으므로 이 자리는 주인이 없는 것이 확실하다
        QLocalServer.removeServer(self._key)
        return self._server.listen(self._key)

    def _on_new_connection(self):
        """연결이 오면 그 자리에서 읽는다.

        readyRead 신호에 기대지 않는 이유: 보낸 쪽이 쓰자마자 끊어버리기 때문에, 신호가
        오기 전에 연결이 정리되면 메시지를 놓칠 수 있다. 짧게 기다렸다 직접 읽는 편이
        확실하고, 어차피 한 줄짜리 신호라 기다리는 시간도 사실상 없다.
        """
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        if socket.bytesAvailable() == 0:
            socket.waitForReadyRead(CONNECT_TIMEOUT_MS)
        message = bytes(socket.readAll()).strip()
        socket.disconnectFromServer()
        socket.deleteLater()
        if message == WAKE_MESSAGE:
            self.activated.emit()

    def release(self):
        if self._server is not None:
            self._server.close()
            self._server = None
