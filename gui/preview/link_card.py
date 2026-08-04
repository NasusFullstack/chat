"""뉴스/게시물 링크를 카드 모양으로 보여주는 위젯."""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from gui.preview.image_preview import CARD_THUMB_PX, crop_to_square

CARD_MAX_WIDTH = 360


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
