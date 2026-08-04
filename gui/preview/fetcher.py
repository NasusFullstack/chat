"""주소 하나를 비동기로 받아오는 일만 담당.

받아오는 쪽과 그리는 쪽을 갈라놓으면, 그림 없이도(네트워크 없이도) 나머지를 시험할 수 있다.
이름은 ImageFetcher지만 HTML도 같은 방법으로 받는다(둘 다 그냥 GET이라).

알아둘 성질: 링크가 오면 그 채널 사람들의 앱이 각자 그 주소에 접속한다. 그래서 링크 주인에게
접속자들이 보인다. 대신 사설망 주소는 아예 요청하지 않는다(link_meta.is_safe_public_url) -
누가 http://192.168.0.1/ 을 올려 남의 공유기를 두드리게 만드는 걸 막기 위함.
"""
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

import link_meta

DOWNLOAD_LIMIT_BYTES = 8 * 1024 * 1024  # 이보다 크면 받다가 중단(거대 파일로 앱 멈춤 방지)
HTML_LIMIT_BYTES = 256 * 1024           # og 태그는 <head>에 있어 앞부분만 있으면 충분
REQUEST_TIMEOUT_MS = 10000              # 죽은 링크가 계속 붙잡고 있지 않게

USER_AGENT = b"Mozilla/5.0 (compatible; FriendChat/1.0)"


class ImageFetcher:
    """주소 하나를 비동기로 받아오는 얇은 래퍼. 위젯과 분리해서 테스트하기 쉽게 둠.

    이름은 ImageFetcher지만 HTML도 같은 방법으로 받는다(둘 다 그냥 GET이라)."""

    def __init__(self, parent=None):
        self._manager = QNetworkAccessManager(parent)

    def fetch(self, url: str, on_done, limit: int = DOWNLOAD_LIMIT_BYTES):
        """url을 받아 on_done(bytes | None) 호출. 실패/초과/타임아웃이면 None.

        접속하면 안 되는 주소(사설망 등)는 아예 요청하지 않고 바로 None."""
        if not link_meta.is_safe_public_url(url):
            on_done(None)
            return None
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", USER_AGENT)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        reply = self._manager.get(request)
        state = {"done": False}

        def finish(data):
            if state["done"]:
                return
            state["done"] = True
            timer.stop()
            reply.deleteLater()
            on_done(data)

        def on_progress(received, _total):
            if received > limit:
                reply.abort()  # 다 받기 전에 끊음

        def on_finished():
            if reply.error() != reply.NetworkError.NoError:
                finish(None)
                return
            data = bytes(reply.readAll())
            finish(data[:limit] if data else None)

        timer = QTimer(self._manager)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: (reply.abort(), finish(None)))
        timer.start(REQUEST_TIMEOUT_MS)
        reply.downloadProgress.connect(on_progress)
        reply.finished.connect(on_finished)
        return reply
