"""뉴스/게시물 링크를 카드 모양으로 보여주는 위젯."""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

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
        # 제목/설명이 word wrap이라 **폭이 좁아지면 줄이 늘어 높이가 커진다**. 그 사실을
        # 부모에게 알리지 않으면 한 줄 높이만 받아서 글자가 위아래로 잘린다(실측: 설명이
        # 54px 필요한데 27px만 받아 절반이 잘림). 세로 가운데 정렬이 기본이라 잘린 티가
        # 위아래로 똑같이 나서 "가운데 정렬된 채 잘렸다"처럼 보였다
        policy = self.sizePolicy()
        policy.setHeightForWidth(True)
        policy.setVerticalPolicy(QSizePolicy.Policy.Minimum)
        self.setSizePolicy(policy)

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
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        text_col.addWidget(self.title_label)

        self.desc_label = QLabel(description)
        self.desc_label.setObjectName("linkCardDesc")
        self.desc_label.setWordWrap(True)
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.desc_label.setVisible(bool(description))
        text_col.addWidget(self.desc_label)

        self.host_label = QLabel(QUrl(url).host())
        self.host_label.setObjectName("linkCardHost")
        text_col.addWidget(self.host_label)
        text_col.addStretch(1)
        row.addLayout(text_col, 1)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt 규약
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        layout = self.layout()
        height = layout.heightForWidth(width) if layout is not None else -1
        return height if height > 0 else super().heightForWidth(width)

    def adjust_height(self):
        """지금 폭에 맞는 높이로 자기 키를 고정한다.

        word wrap 라벨의 sizeHint는 "글자가 한 줄에 다 들어가는 넓은 폭"을 가정해서 나오기
        때문에, 좁은 카드 안에서는 실제 필요한 높이보다 작다(실측: 필요 117인데 87). 그
        차이만큼 글자가 위아래로 잘렸다.

        레이아웃의 heightForWidth에 맡기면 반대로 부풀려 나와서(실측 329), 여기서는 글자
        칸의 실제 폭을 구해 라벨 세 개의 높이를 직접 더한다. 계산이 눈에 보이는 게 낫다.
        """
        margins = self.layout().contentsMargins()
        # 항상 '허용된 최대 폭' 기준으로 잰다. 아직 배치되기 전의 self.width()는 기본값
        # (작은 값)이라, 그걸 쓰면 글자가 여러 줄로 계산돼 카드가 세 배로 부풀었다(실측 322).
        # 최대 폭은 set_max_width()가 채팅창 실제 폭에 맞춰 이미 좁혀둔 값이다
        card_width = self.maximumWidth()
        text_width = card_width - margins.left() - margins.right()
        # isVisible()은 아직 화면에 안 붙은 위젯에도 False라서 쓰면 안 된다
        # (카드를 만들자마자 계산하면 전부 0이 나와 높이가 20px로 찌그러졌다)
        if not self.thumb.isHidden():
            text_width -= CARD_THUMB_PX + self.layout().spacing()
        if text_width <= 0:
            return

        gaps = 2  # 제목-설명-도메인 사이 간격 두 번(QVBoxLayout spacing=2)
        # 라벨마다 "이 폭이면 몇 픽셀 필요한가"를 물어서 더한다. fontMetrics로 직접 재는
        # 방법도 써봤지만, 스타일시트가 지정한 글자 크기가 아직 안 붙은 시점에는 실제보다
        # 작게 나와 설명이 또 잘렸다(실측 필요 54인데 40으로 계산). heightForWidth는 그
        # 라벨의 진짜 글꼴을 쓰므로 정확하다 - 예전에 이 값이 이상했던 건 폭을 잘못 넘겨서였다
        text_height = 0
        for label in (self.title_label, self.desc_label, self.host_label):
            if label.isHidden():
                continue
            # 이미 배치된 뒤라면 라벨의 진짜 폭을 쓴다. 카드 폭에서 여백만 뺀 값은 QSS
            # 테두리(좌우 1px씩)를 모르기 때문에 2px 넓게 잡히고, 그만큼 마지막 줄이 잘렸다
            width = label.width() if label.width() > 0 else text_width
            needed = label.heightForWidth(width)
            text_height += needed if needed > 0 else label.sizeHint().height()
        text_height += gaps * 2

        content = max(text_height, 0 if self.thumb.isHidden() else CARD_THUMB_PX)
        # 세로 레이아웃이 라벨들에 높이를 나눠줄 때 계산이 1~2px 어긋나 마지막 줄의
        # 아래가 살짝 잘렸다. 그만큼만 여유를 둔다(눈에 안 띄고, 잘림은 확실히 막힌다)
        self.setFixedHeight(content + margins.top() + margins.bottom() + 2)

    def _ask_parent_to_remeasure(self):
        """내 키가 바뀌었으니 대화 목록에도 높이를 다시 재라고 알림.

        안 알리면 목록이 예전 높이를 그대로 써서 채팅 맨 아래에 빈 공간이 남는다.
        """
        parent = self.parentWidget()
        while parent is not None:
            sync = getattr(parent, "sync_content_height", None)
            if callable(sync):
                sync()
                return
            parent.updateGeometry()
            parent = parent.parentWidget()

    def remeasure(self):
        """높이를 다시 재고, 달라졌으면 위쪽에도 알린다.

        스타일시트가 정한 글자 크기는 위젯이 화면에 붙은 뒤에야 적용되므로, 만들자마자
        잰 높이는 실제보다 작다(실측: 설명이 54 필요한데 35). 붙은 뒤 한 번 더 부른다.
        """
        before = self.height()
        self.adjust_height()
        if self.height() != before:
            self._ask_parent_to_remeasure()

    def set_thumbnail(self, pixmap: QPixmap):
        if pixmap.isNull():
            return
        self.thumb.setPixmap(crop_to_square(pixmap, CARD_THUMB_PX))
        self.thumb.setVisible(True)
        self.adjust_height()   # 썸네일이 붙으면 필요한 높이가 달라짐

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mouseReleaseEvent(event)
