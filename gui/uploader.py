"""파일·사진을 서버에 올리고 **주소 한 줄**을 받아오는 담당.

## 왜 주소만 받아오면 끝인가
받은 주소를 채팅에 넣으면 그 뒤는 **이미 있는 길**이 알아서 한다 - 사진이면 미리보기가
뜨고(gui/preview), 일반 파일이면 눌러서 받는 링크가 된다. 그래서 여기는 올리는 일만
하고 화면은 모른다.

## 한도는 서버가 정한다
크기 상한도, 하루 총량도 서버가 판단한다. 여기서 같은 숫자를 또 적어두면 둘이 어긋날 때
"앱은 되는데 서버가 거절하는" 상태가 된다. 다만 **올리기 전에 눈에 띄게 큰 것**은
미리 걸러서, 100MB를 다 보내고 나서 거절당하는 헛수고를 막는다(그 값도 서버에서 받아온다).
"""
import os
import urllib.parse

from PySide6.QtCore import (QByteArray, QFile, QIODevice, QObject, QTimer, QUrl,
                            Signal)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

import relay

# 주소는 relay.py 한 곳에서 정한다(예전엔 전투와 파일에 각각 적혀 있었다)
SERVER = relay.SERVER
UPLOAD_URL = relay.FILES_URL

# 서버가 알려주기 전에 쓰는 값. 서버 상태를 한 번 받아오면 그 값으로 바뀐다
FALLBACK_MAX_BYTES = 1024 * 1024 * 1024

# **진행이 멈춘 채로** 이만큼 지나면 끊는다. 전체 시간으로 재면 안 된다 - 1GB를 느린
# 회선으로 올리면 몇십 분이 걸리는데 그건 되고 있는 것이지 실패가 아니다
STALL_TIMEOUT_MS = 90_000
STATUS_TIMEOUT_MS = 8_000


class Uploader(QObject):
    """파일 하나를 올린다. 화면은 신호로만 안다."""

    progress = Signal(int, int)        # 보낸 바이트, 전체
    finished = Signal(str, str)        # 주소(실패면 ""), 안내글
    limits_known = Signal(dict)        # 서버가 알려준 한도

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._limits = {"file_bytes": FALLBACK_MAX_BYTES}
        self._reply = None
        self._file = None

    # ------------------------------------------------------------------
    @property
    def max_bytes(self) -> int:
        return int(self._limits.get("file_bytes", FALLBACK_MAX_BYTES))

    def refresh_limits(self):
        """서버가 정한 한도를 받아온다(실패해도 기본값으로 동작한다)."""
        request = QNetworkRequest(QUrl(UPLOAD_URL))
        reply = self._manager.get(request)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(reply.abort)
        timer.start(STATUS_TIMEOUT_MS)

        def done():
            timer.stop()
            if reply.error() == reply.NetworkError.NoError:
                import json

                try:
                    limits = json.loads(bytes(reply.readAll()).decode("utf-8")).get("limits")
                except (ValueError, UnicodeDecodeError):
                    limits = None
                if isinstance(limits, dict):
                    self._limits = limits
                    self.limits_known.emit(dict(limits))
            reply.deleteLater()

        reply.finished.connect(done)

    # ------------------------------------------------------------------
    def upload(self, path: str, kind: str = "file"):
        """파일 하나를 올린다. 끝나면 finished(주소, 안내글)."""
        if self._reply is not None:
            self.finished.emit("", "이미 올리는 중입니다. 끝난 뒤에 다시 시도해 주세요.")
            return
        try:
            size = os.path.getsize(path)
        except OSError as error:
            self.finished.emit("", f"파일을 읽을 수 없습니다: {error}")
            return
        if size == 0:
            self.finished.emit("", "빈 파일은 올릴 수 없습니다.")
            return
        if size > self.max_bytes:
            self.finished.emit(
                "", f"파일이 너무 큽니다({_readable(size)}). "
                    f"{_readable(self.max_bytes)}까지 올릴 수 있습니다.")
            return

        # **Qt가 읽는 파일 객체여야 한다.** 파이썬 `open()`이 준 것을 넘기면 post()가
        # 타입 오류로 거절한다. 그리고 한 번에 다 읽어 바이트로 넘기면 100MB짜리가
        # 통째로 메모리에 올라오므로, 읽어가며 보내도록 QFile을 그대로 물려준다
        self._file = QFile(path, self)
        if not self._file.open(QIODevice.OpenModeFlag.ReadOnly):
            reason = self._file.errorString()
            self._file = None
            self.finished.emit("", f"파일을 열 수 없습니다: {reason}")
            return

        self._reply = self._manager.post(self._request_for(os.path.basename(path), kind),
                                         self._file)
        self._watch()

    def _request_for(self, name: str, kind: str) -> QNetworkRequest:
        request = QNetworkRequest(QUrl(UPLOAD_URL))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader,
                          "application/octet-stream")
        # **이름은 부호화해서 싣는다.** HTTP 헤더는 ASCII만 실을 수 있어서 한글 이름을
        # 그대로 넣으면 아예 안 올라간다
        request.setRawHeader(b"X-File-Name", urllib.parse.quote(name).encode("ascii"))
        request.setRawHeader(b"X-File-Kind", kind.encode("ascii"))
        # 이모티콘은 **같이 쓰는 것**이다. 지금 붙어 있는 채팅 서버를 알려주면 그 서버를
        # 쓰는 사람들 목록에 같이 올라간다(안 알려주면 나만 쓴다)
        group = relay.current_group()
        if kind == "emoji" and group:
            request.setRawHeader(b"X-Emoji-Group", group.encode("ascii"))
        return request

    def _watch(self):
        """진행을 지켜보다가 **멈춘 채로** 오래되면 끊는다.

        전체 시간으로 제한을 걸면 안 된다. 1GB를 느린 회선으로 올리면 몇십 분이
        걸리는데, 그건 멀쩡히 되고 있는 것이지 실패가 아니다. 반대로 회선이 죽었으면
        아무리 큰 파일이라도 진행이 멈춘다 - 그걸 본다.
        """
        self._reply.uploadProgress.connect(self._on_progress)
        self._reply.finished.connect(self._on_finished)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._reply.abort)
        self._timeout.start(STALL_TIMEOUT_MS)

    def upload_bytes(self, data: bytes, name: str, kind: str = "file"):
        """이미 손에 들고 있는 그림을 올린다(이모티콘 등록에 쓴다).

        이모티콘은 채팅에 떠 있는 그림을 저장하는 것이라 **파일이 아니라 바이트**로
        들고 있다. 임시 파일로 떨어뜨렸다가 다시 읽으면 지우는 일까지 챙겨야 해서
        그냥 바로 보낸다.
        """
        if self._reply is not None:
            self.finished.emit("", "이미 올리는 중입니다. 끝난 뒤에 다시 시도해 주세요.")
            return
        if not data:
            self.finished.emit("", "빈 그림은 올릴 수 없습니다.")
            return
        self._reply = self._manager.post(self._request_for(name, kind), QByteArray(data))
        self._watch()

    def cancel(self):
        if self._reply is not None:
            self._reply.abort()

    # ------------------------------------------------------------------
    def _on_progress(self, sent, total):
        # 한 조각이라도 나갔으면 아직 살아 있는 것이다 - 시계를 다시 돌린다
        if getattr(self, "_timeout", None) is not None:
            self._timeout.start(STALL_TIMEOUT_MS)
        if total > 0:
            self.progress.emit(int(sent), int(total))

    def _on_finished(self):
        import json

        reply, self._reply = self._reply, None
        if getattr(self, "_timeout", None) is not None:
            self._timeout.stop()
        if self._file is not None:
            self._file.close()
            self._file.deleteLater()
            self._file = None
        if reply is None:
            return
        body = bytes(reply.readAll())
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        failed = reply.error() != reply.NetworkError.NoError
        reply.deleteLater()

        try:
            answer = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            answer = {}

        if failed or status != 200:
            # 서버가 왜 거절했는지 그대로 보여준다 - "실패했습니다"만 뜨면 사람이
            # 무엇을 고쳐야 할지 알 수 없다
            reason = answer.get("error") or "올리지 못했습니다. 잠시 뒤 다시 시도해 주세요."
            self.finished.emit("", reason)
            return
        url = answer.get("url", "")
        if not url:
            self.finished.emit("", "서버가 주소를 돌려주지 않았습니다.")
            return
        self.finished.emit(SERVER + url, f"{answer.get('name', '파일')} 올렸습니다.")


def _readable(size: int) -> str:
    """사람이 읽는 크기. 바이트 숫자를 그대로 보여주면 감이 안 온다."""
    for unit, step in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if size >= step:
            return f"{size / step:.1f}{unit}"
    return f"{size}B"
