"""올린 파일을 서버에서 내리기.

카드에서 '내리기'를 누르면 여기로 온다. 표(token)를 실어 보내야 서버가 지워준다 -
계정이 없는 서버라 그 표가 곧 "내가 올린 것"이라는 증거다(file_tokens.py).

일꾼을 모듈이 붙들어두는 이유는 gui/emoji_register.py와 같다 - 지역 변수로만 두면
답이 오기 전에 파이썬이 치워버린다.
"""
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

import file_tokens
import relay

TIMEOUT_MS = 15_000

_WORKING: set = set()


class _TakeBack(QObject):
    done = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self._manager = QNetworkAccessManager(self)

    def start(self, file_id: str):
        token = file_tokens.token_for(file_id)
        if not token:
            self.done.emit(False, "내가 올린 파일만 내릴 수 있습니다.")
            return
        request = QNetworkRequest(QUrl(f"{relay.SERVER}/files/{file_id}"))
        request.setRawHeader(b"X-File-Token", token.encode("ascii"))
        reply = self._manager.deleteResource(request)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(reply.abort)
        timer.start(TIMEOUT_MS)

        def finished():
            timer.stop()
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            failed = reply.error() != reply.NetworkError.NoError
            reply.deleteLater()
            if failed or status != 200:
                # 404면 이미 없는 것이다 - 사람 눈에는 내려간 것과 같으므로 성공으로 친다
                if status == 404:
                    file_tokens.forget(file_id)
                    self.done.emit(True, "")
                    return
                self.done.emit(False, "내리지 못했습니다. 잠시 뒤 다시 시도해 주세요.")
                return
            file_tokens.forget(file_id)
            self.done.emit(True, "")

        reply.finished.connect(finished)


def take_back(file_id: str, on_done):
    worker = _TakeBack()
    _WORKING.add(worker)

    def finished(ok, note):
        _WORKING.discard(worker)
        worker.deleteLater()
        on_done(ok, note)

    worker.done.connect(finished)
    worker.start(file_id)
    return worker
