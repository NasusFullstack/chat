"""그림 하나를 중계 서버에 이모티콘으로 등록하기.

## 왜 서버에 올리는가
채팅에 뜬 그림의 주소는 **오래 안 간다.** 우리 서버에 올린 것은 하루 뒤 지워지고, 남의
사이트에 있는 그림은 언제 사라질지 우리가 알 수 없다. 그 주소를 보관함에 적어두면 어느 날
이모티콘이 통째로 깨진다 - 그래서 한동안 이 기능을 잠가뒀었다.

지금은 저장할 때 **그림을 서버에 등록한다.** 서버가 이모티콘 크기로 줄여서(320px) 기한 없이
보관하고, 보관함에는 그 주소를 적는다. 같은 그림을 여럿이 저장해도 서버에 한 벌만 남는다.

## 누가 부르나
그림 미리보기에서 우클릭 - 내 이모티콘으로 저장. 등록이 끝나야 보관함에 넣을 수 있으므로
(주소를 받아야 하므로) 결과를 기다렸다가 알린다.
"""
from PySide6.QtCore import QObject, Signal

from gui.uploader import Uploader

# 등록하는 동안 살아 있어야 하는 일꾼들. 끝나면 스스로 빠진다
_WORKING: set = set()


class EmojiRegister(QObject):
    """그림 하나를 이모티콘으로 등록한다. 끝나면 done(주소, 안내글)."""

    done = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._uploader = Uploader(self)
        self._uploader.finished.connect(self._finished)

    def start(self, data: bytes, name: str):
        if not data:
            self.done.emit("", "그림을 아직 다 받지 못했습니다. 잠시 뒤 다시 시도해 주세요.")
            return
        self._uploader.upload_bytes(data, f"{name or '이모티콘'}.png", kind="emoji")

    def _finished(self, url: str, note: str):
        self.done.emit(url, note)


def register(data: bytes, name: str, on_done):
    """그림을 등록하고 끝나면 on_done(주소, 안내글)을 부른다.

    일꾼을 **모듈이 붙들어둔다.** 지역 변수로만 두면 이 함수가 끝나는 순간 파이썬이
    치워버려서 답이 오기 전에 사라진다(신호가 영영 안 온다).
    """
    worker = EmojiRegister()
    _WORKING.add(worker)

    def finished(url, note):
        _WORKING.discard(worker)
        worker.deleteLater()
        on_done(url, note)

    worker.done.connect(finished)
    worker.start(data, name)
    return worker
