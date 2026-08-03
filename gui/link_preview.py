"""채팅에 붙은 링크의 미리보기.

역할 분담(서버 unfurl.py와 짝):
- **서버**: 페이지 HTML을 읽어 og 태그에서 제목/설명/이미지주소만 뽑아 준다(글자만, 1KB 미만).
- **여기(클라이언트)**: 서버가 알려준 이미지 주소로 직접 접속해 그림을 받아 그린다.
  서버는 그림을 중계하지 않는다 - 서버 대역폭을 이미지에 쓰지 않기 위함.

이미지 직링크(.png/.gif 등)는 서버에 물어볼 것도 없이 그 주소가 곧 그림이므로 바로 받는다.

미리보기 이미지가 있으면 보여주고, 없으면 글자만(또는 아무 것도) 보여준다.
어느 단계에서 실패하든 조용히 포기하고 평소의 하이퍼링크만 남긴다 - 미리보기는 덤이라
실패했다고 오류 문구를 채팅에 남기면 오히려 지저분해진다.
"""
import re

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QMovie, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

# 이미지 미리보기 최대 크기. 원본이 크면 이 안에 들어오게 비율대로 줄여서 보여줌
IMAGE_PREVIEW_WIDTH = 320
IMAGE_PREVIEW_MAX_HEIGHT = 320

# 뉴스/게시물 카드의 썸네일은 작은 정사각형 고정. 원본이 아무리 커도 여기 맞춰 잘라냄
# (안 그러면 큰 헤더 이미지가 채팅창을 통째로 차지함)
CARD_THUMB_PX = 80
CARD_MAX_WIDTH = 360

DOWNLOAD_LIMIT_BYTES = 8 * 1024 * 1024  # 이보다 크면 받다가 중단(거대 파일로 앱 멈춤 방지)
REQUEST_TIMEOUT_MS = 10000              # 죽은 링크가 계속 붙잡고 있지 않게

USER_AGENT = b"Mozilla/5.0 (compatible; FriendChat/1.0)"

_IMAGE_EXT_RE = re.compile(r"\.(png|jpe?g|gif|webp|bmp)(?:[?#].*)?$", re.IGNORECASE)


def is_image_url(url: str) -> bool:
    """확장자로 이미지 직링크인지 판단.

    확장자가 없는 이미지 서비스는 웹페이지로 취급되는데, 그런 곳은 대개 og:image를
    갖고 있어서 서버가 카드로 만들어 주므로 문제되지 않음."""
    return bool(_IMAGE_EXT_RE.search(url))


class ImageFetcher:
    """이미지를 받아오는 얇은 래퍼. 위젯과 분리해서 테스트하기 쉽게 둠."""

    def __init__(self, parent=None):
        self._manager = QNetworkAccessManager(parent)

    def fetch(self, url: str, on_done):
        """url을 받아 on_done(bytes | None) 호출. 실패/초과/타임아웃이면 None."""
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
            if received > DOWNLOAD_LIMIT_BYTES:
                reply.abort()  # 다 받기 전에 끊음

        def on_finished():
            if reply.error() != reply.NetworkError.NoError:
                finish(None)
                return
            data = bytes(reply.readAll())
            finish(data if len(data) <= DOWNLOAD_LIMIT_BYTES else None)

        timer = QTimer(self._manager)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: (reply.abort(), finish(None)))
        timer.start(REQUEST_TIMEOUT_MS)
        reply.downloadProgress.connect(on_progress)
        reply.finished.connect(on_finished)
        return reply


def _looks_like_gif(data: bytes) -> bool:
    return data[:6] in (b"GIF87a", b"GIF89a")


def _preview_size(width: int, height: int) -> QSize:
    """상한 안에 들어가도록 비율을 유지해 줄인 크기.

    1.0을 못 넘게 막는 이유: 작은 이미지를 억지로 키우면 뭉개지므로 원본 크기 유지."""
    if width <= 0 or height <= 0:
        return QSize(IMAGE_PREVIEW_WIDTH, IMAGE_PREVIEW_WIDTH)
    scale = min(IMAGE_PREVIEW_WIDTH / width, IMAGE_PREVIEW_MAX_HEIGHT / height, 1.0)
    # int()로 버리면 320이 319가 되고, 거기에 KeepAspectRatio가 한 번 더 맞추면서 318까지
    # 줄어들었음. 반올림 + 아래의 IgnoreAspectRatio 조합으로 목표 크기에 정확히 맞춤
    return QSize(max(1, round(width * scale)), max(1, round(height * scale)))


def _scaled_for_preview(pixmap: QPixmap) -> QPixmap:
    size = _preview_size(pixmap.width(), pixmap.height())
    if size == pixmap.size():
        return pixmap
    return pixmap.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)


def crop_to_square(pixmap: QPixmap, side: int) -> QPixmap:
    """가운데를 정사각형으로 잘라 썸네일 크기에 맞춤.

    그냥 축소만 하면 가로로 긴 뉴스 헤더 이미지가 납작해져 알아보기 어렵고, 카드 높이도
    이미지마다 들쭉날쭉해짐. 가운데를 잘라내면 카드 높이가 항상 일정함.
    """
    if pixmap.isNull():
        return pixmap
    edge = min(pixmap.width(), pixmap.height())
    x = (pixmap.width() - edge) // 2
    y = (pixmap.height() - edge) // 2
    return pixmap.copy(x, y, edge, edge).scaled(
        side, side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


class ImagePreview(QLabel):
    """이미지 직링크 미리보기. 움직이는 GIF면 움직이게 재생함."""

    def __init__(self, url: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("linkImagePreview")
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._url = url
        self._movie = None
        self._buffer = None

    def set_image_data(self, data: bytes) -> bool:
        """받은 바이트로 이미지를 세팅. 못 읽으면 False(호출자가 미리보기를 지움)."""
        if not data:
            return False
        if _looks_like_gif(data):
            return self._set_animated(data)
        pixmap = QPixmap()
        if not pixmap.loadFromData(data) or pixmap.isNull():
            return False
        self.setPixmap(_scaled_for_preview(pixmap))
        return True

    def _set_animated(self, data: bytes) -> bool:
        # QMovie는 파일이나 QIODevice에서 읽으므로 메모리 버퍼를 물려줌.
        # 버퍼를 self에 붙들어두지 않으면 GC돼서 재생 중 끊김
        self._buffer = QBuffer(self)
        self._buffer.setData(QByteArray(data))
        if not self._buffer.open(QIODevice.OpenModeFlag.ReadOnly):
            return False
        movie = QMovie(self)
        movie.setDevice(self._buffer)
        if not movie.isValid():
            return False
        movie.jumpToFrame(0)
        size = movie.currentPixmap().size()
        if size.width() > 0:
            movie.setScaledSize(_preview_size(size.width(), size.height()))
        self._movie = movie
        self.setMovie(movie)
        movie.start()
        return True

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._url:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mouseReleaseEvent(event)


class LinkCard(QFrame):
    """뉴스/게시물 카드 - (썸네일이 있으면) 왼쪽에 작게, 오른쪽에 제목/설명/도메인."""

    def __init__(self, url: str, title: str, description: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("linkCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMaximumWidth(CARD_MAX_WIDTH)
        self._url = url

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(10)

        self.thumb = QLabel()
        self.thumb.setObjectName("linkCardThumb")
        self.thumb.setFixedSize(CARD_THUMB_PX, CARD_THUMB_PX)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 그림이 실제로 도착해야 자리를 차지함(없는 링크면 글자만 나옴)
        self.thumb.setVisible(False)
        row.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title_label = QLabel(title or url)
        self.title_label.setObjectName("linkCardTitle")
        self.title_label.setWordWrap(True)
        text_col.addWidget(self.title_label)

        self.desc_label = QLabel(description)
        self.desc_label.setObjectName("linkCardDesc")
        self.desc_label.setWordWrap(True)
        self.desc_label.setVisible(bool(description))
        text_col.addWidget(self.desc_label)

        self.host_label = QLabel(QUrl(url).host())
        self.host_label.setObjectName("linkCardHost")
        text_col.addWidget(self.host_label)
        text_col.addStretch(1)
        row.addLayout(text_col, 1)

    def set_thumbnail(self, pixmap: QPixmap):
        if pixmap.isNull():
            return
        self.thumb.setPixmap(crop_to_square(pixmap, CARD_THUMB_PX))
        self.thumb.setVisible(True)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mouseReleaseEvent(event)


class LinkPreviewArea(QWidget):
    """메시지 하나에 딸린 미리보기들을 담는 칸.

    - 이미지 직링크: 주소가 곧 그림이므로 바로 받아서 보여줌
    - 그 외 링크: 서버가 메타데이터를 보내줄 때까지 비워두고, 오면 카드를 만든 뒤
      거기 적힌 이미지 주소로 그림을 받아 채움

    끝까지 아무 것도 안 오면 계속 높이 0이라 평소 메시지와 똑같이 보인다.
    """

    def __init__(self, urls, fetcher: "ImageFetcher | None" = None, parent=None):
        super().__init__(parent)
        self.setObjectName("linkPreviewArea")
        self.setStyleSheet("QWidget#linkPreviewArea { background: transparent; }")
        self._fetcher = fetcher
        self._pending = set(urls)
        self._filled = set()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        for url in urls:
            if is_image_url(url) and fetcher is not None:
                self._start_direct_image(url)

    def _start_direct_image(self, url: str):
        self._pending.discard(url)  # 서버 응답을 기다릴 필요 없는 종류
        self._fetcher.fetch(url, lambda data: self._on_direct_image(url, data))

    def _on_direct_image(self, url: str, data):
        if url in self._filled:
            return
        preview = ImagePreview(url, self)
        if not preview.set_image_data(data):
            preview.deleteLater()
            return
        self._filled.add(url)
        self._layout.addWidget(preview)

    def wants(self, url: str) -> bool:
        """이 메시지가 서버 응답을 기다리고 있는 링크인지"""
        return url in self._pending and url not in self._filled

    def apply_result(self, url: str, title: str, description: str, image_url: str = ""):
        """서버가 보내준 메타데이터로 카드를 만듦. 제목이 없으면 아무 것도 안 함."""
        if not self.wants(url) or not title:
            return
        self._filled.add(url)
        card = LinkCard(url, title, description, self)
        self._layout.addWidget(card)
        # 그림은 서버가 아니라 우리가 그 주소에서 직접 받아옴
        if image_url and self._fetcher is not None:
            self._fetcher.fetch(image_url, lambda data: self._on_card_image(card, data))

    @staticmethod
    def _on_card_image(card: LinkCard, data):
        if not data:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data) and not pixmap.isNull():
            card.set_thumbnail(pixmap)
