"""채팅에 붙은 링크의 미리보기 카드 (화면 그리기만 담당).

**링크를 실제로 가져오는 건 서버가 한다** - 이 파일은 서버가 보내준 결과를 그리기만
한다. 클라이언트가 각자 그 주소에 접속하면 (1) 채널 인원수만큼 요청이 나가고,
(2) 링크 주인에게 참여자 전원의 IP가 노출되고, (3) 각자 원본 이미지(수 MB)를 통째로
받게 된다. 서버가 한 번만 받아 캐시해두고 결과만 나눠주면 셋 다 해결된다
(자세한 내용과 SSRF 방어는 저장소 루트의 unfurl.py 참고).

그래서 여기에는 네트워크 코드가 없다. 미리보기가 안 오면(서버가 못 가져왔거나, 실제
IRC 서버라 대신 가져와 줄 주체가 없거나) 그냥 평소처럼 하이퍼링크만 남는다.

썸네일은 서버가 이미지 기능을 켰을 때만 온다(기본은 꺼져 있어 제목/설명만 옴).
"""
import base64
import binascii

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

# 카드 썸네일은 작은 정사각형으로 고정. 원본이 아무리 커도 서버가 여기 맞춰 줄여서 보냄
# (안 그러면 큰 뉴스 헤더 이미지가 채팅창을 통째로 차지함)
CARD_THUMB_PX = 80
CARD_MAX_WIDTH = 360


def crop_to_square(pixmap: QPixmap, side: int) -> QPixmap:
    """가운데를 정사각형으로 잘라 썸네일 크기에 맞춤.

    서버가 이미 정사각으로 줄여서 보내지만, 옛 서버가 다른 비율로 보낼 수도 있으므로
    받는 쪽에서도 한 번 더 맞춰서 카드 높이가 항상 일정하게 유지되도록 함.
    """
    if pixmap.isNull():
        return pixmap
    edge = min(pixmap.width(), pixmap.height())
    x = (pixmap.width() - edge) // 2
    y = (pixmap.height() - edge) // 2
    return pixmap.copy(x, y, edge, edge).scaled(
        side, side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def decode_thumb(thumb_b64: str) -> QPixmap:
    """서버가 보내준 base64 썸네일을 QPixmap으로. 이상하면 빈 QPixmap."""
    if not thumb_b64:
        return QPixmap()
    try:
        raw = base64.b64decode(thumb_b64, validate=True)
    except (binascii.Error, ValueError):
        return QPixmap()
    pixmap = QPixmap()
    if not pixmap.loadFromData(raw) or pixmap.isNull():
        return QPixmap()
    return pixmap


class LinkCard(QFrame):
    """뉴스/게시물 카드 - (썸네일이 있으면) 왼쪽에 작게, 오른쪽에 제목/설명/도메인."""

    def __init__(self, url: str, title: str, description: str = "", thumb_b64: str = "",
                 parent=None):
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
        # 썸네일이 없으면(서버가 이미지 기능을 꺼둔 평소 상태) 자리를 차지하지 않음
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

        if thumb_b64:
            self.set_thumbnail(decode_thumb(thumb_b64))

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

    처음엔 비어 있고(높이 0), 서버가 결과를 보내주면 그때 카드가 채워진다.
    끝까지 아무것도 안 오면 계속 높이 0이라 평소 메시지와 똑같이 보인다.
    """

    def __init__(self, urls, parent=None):
        super().__init__(parent)
        self.setObjectName("linkPreviewArea")
        self.setStyleSheet("QWidget#linkPreviewArea { background: transparent; }")
        self._urls = set(urls)
        self._filled = set()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def wants(self, url: str) -> bool:
        """이 메시지가 기다리고 있는 링크인지(같은 링크를 두 번 그리지 않게도 함)"""
        return url in self._urls and url not in self._filled

    def apply_result(self, url: str, title: str, description: str, thumb_b64: str):
        """서버가 보내준 결과로 카드를 만듦. 제목이 없으면 아무 것도 안 함."""
        if not self.wants(url) or not title:
            return
        self._filled.add(url)
        self._layout.addWidget(LinkCard(url, title, description, thumb_b64, self))
