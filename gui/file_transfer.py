"""파일을 사람끼리 직접 주고받는다(서버를 거치지 않는다).

보내는 쪽이 잠깐 문을 열고(포트), 받는 쪽이 그 문으로 직접 붙어 파일을 가져간다.
채팅 서버에는 "이 주소로 오라"는 한 줄만 지나간다 - 그래서 몇십 MB를 보내도 서버는
아무 부담이 없다.

알아둘 한계(솔직하게):
- 받는 쪽이 보내는 쪽 주소로 **직접 접속할 수 있어야** 한다. 둘 다 공유기 뒤에 있고
  포트가 닫혀 있으면 연결이 안 된다(같은 와이파이/랜이면 대개 된다).
- 처음 보낼 때 윈도우 방화벽이 물어볼 수 있다("액세스 허용"을 눌러야 한다).
이런 경우 조용히 실패하면 사람이 이유를 알 수 없으므로, 실패는 반드시 알려준다.
"""
import os

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QHostAddress, QTcpServer, QTcpSocket

# 한 번에 읽어 보내는 크기. 너무 크면 화면이 멈추고, 너무 작으면 느리다
CHUNK_BYTES = 64 * 1024
# 상대가 이 시간 안에 안 오면 문을 닫는다(열어둔 채 잊히지 않게)
OFFER_TIMEOUT_MS = 120_000
# 받는 쪽이 이 시간 안에 못 붙으면 포기한다
CONNECT_TIMEOUT_MS = 15_000
# 이보다 큰 파일은 보내지 않는다(실수로 수십 GB를 걸어두는 사고 방지)
MAX_FILE_BYTES = 512 * 1024 * 1024


class FileSender(QObject):
    """파일 하나를 보내기 위해 잠깐 문을 열고 기다린다.

    progress(보낸 바이트, 전체) / finished(성공 여부, 안내글)
    """

    progress = Signal(int, int)
    finished = Signal(bool, str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.filename = os.path.basename(path)
        self.size = os.path.getsize(path)
        self._file = None
        self._sent = 0
        self._socket = None
        self._server = QTcpServer(self)
        self._server.newConnection.connect(self._on_peer_arrived)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_nobody_came)

    def listen(self) -> int:
        """문을 열고 포트 번호를 돌려준다(0이면 실패)."""
        if not self._server.listen(QHostAddress.SpecialAddress.Any, 0):
            return 0
        self._timeout.start(OFFER_TIMEOUT_MS)
        return self._server.serverPort()

    def cancel(self, reason: str = "보내기를 취소했습니다."):
        self._cleanup()
        self.finished.emit(False, reason)

    # ---------------- 내부 ----------------

    def _on_peer_arrived(self):
        self._timeout.stop()
        self._socket = self._server.nextPendingConnection()
        self._server.close()          # 한 사람만 받으면 된다
        if self._socket is None:
            self.finished.emit(False, "연결을 받지 못했습니다.")
            return
        self._socket.bytesWritten.connect(self._on_written)
        self._socket.disconnected.connect(self._on_peer_left)
        try:
            self._file = open(self.path, "rb")
        except OSError as error:
            self._cleanup()
            self.finished.emit(False, f"파일을 열 수 없습니다: {error}")
            return
        self._push()

    def _push(self):
        """다음 조각을 실어 보낸다. 소켓이 비었을 때만 넣어 메모리가 안 쌓이게 한다."""
        if self._file is None or self._socket is None:
            return
        chunk = self._file.read(CHUNK_BYTES)
        if not chunk:
            return                     # 다 읽었다 - 상대가 끊으면 끝난 것
        self._socket.write(chunk)

    def _on_written(self, count: int):
        self._sent += count
        self.progress.emit(self._sent, self.size)
        if self._sent >= self.size:
            # 다 보냈다. 상대가 받아가도록 잠시 두었다가 정리한다
            QTimer.singleShot(300, self._done)
            return
        self._push()

    def _done(self):
        self._cleanup()
        self.finished.emit(True, f"{self.filename} 보내기 완료")

    def _on_peer_left(self):
        if self._sent < self.size:
            self._cleanup()
            self.finished.emit(False, "상대가 받다가 연결을 끊었습니다.")

    def _on_nobody_came(self):
        self._cleanup()
        self.finished.emit(False, "상대가 받지 않아 취소했습니다.")

    def _cleanup(self):
        self._timeout.stop()
        if self._file is not None:
            self._file.close()
            self._file = None
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._server.isListening():
            self._server.close()


class FileReceiver(QObject):
    """상대가 연 문으로 붙어 파일을 받아 저장한다.

    progress(받은 바이트, 전체) / finished(성공 여부, 안내글 또는 저장 경로)
    """

    progress = Signal(int, int)
    finished = Signal(bool, str)

    def __init__(self, ip: str, port: int, size: int, save_path: str, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.port = port
        self.size = size
        self.save_path = save_path
        self._received = 0
        self._file = None
        self._socket = QTcpSocket(self)
        self._socket.readyRead.connect(self._on_data)
        self._socket.disconnected.connect(self._on_closed)
        self._socket.errorOccurred.connect(self._on_error)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_timeout)

    def start(self):
        try:
            self._file = open(self.save_path, "wb")
        except OSError as error:
            self.finished.emit(False, f"저장할 수 없습니다: {error}")
            return
        self._timeout.start(CONNECT_TIMEOUT_MS)
        self._socket.connectToHost(self.ip, self.port)

    def cancel(self, reason: str = "받기를 취소했습니다."):
        self._cleanup(remove=True)
        self.finished.emit(False, reason)

    # ---------------- 내부 ----------------

    def _on_data(self):
        self._timeout.stop()
        data = bytes(self._socket.readAll())
        if not data or self._file is None:
            return
        self._file.write(data)
        self._received += len(data)
        self.progress.emit(self._received, self.size)
        # 규약: 지금까지 받은 바이트 수를 4바이트로 돌려준다(보내는 쪽이 속도를 조절한다)
        self._socket.write(self._received.to_bytes(4, "big"))
        if self._received >= self.size:
            self._cleanup()
            self.finished.emit(True, self.save_path)

    def _on_closed(self):
        if self._received < self.size:
            self._cleanup(remove=True)
            self.finished.emit(False, "받는 도중 연결이 끊겼습니다.")

    def _on_error(self, _error):
        if self._received >= self.size:
            return
        self._cleanup(remove=True)
        self.finished.emit(
            False, "상대에게 연결하지 못했습니다(공유기·방화벽이 막았을 수 있습니다).")

    def _on_timeout(self):
        if self._socket.state() != QTcpSocket.SocketState.ConnectedState:
            self._cleanup(remove=True)
            self.finished.emit(False, "상대에게 연결하지 못했습니다(시간 초과).")

    def _cleanup(self, remove: bool = False):
        self._timeout.stop()
        if self._file is not None:
            self._file.close()
            self._file = None
        self._socket.close()
        if remove:
            # 실패한 파일을 남겨두면 나중에 열었다가 깨진 파일에 당황하게 된다
            try:
                if os.path.exists(self.save_path) and self._received < self.size:
                    os.remove(self.save_path)
            except OSError:
                pass
