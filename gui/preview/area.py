"""한 메시지에 딸린 링크들의 미리보기 자리.

이미지 직링크면 바로 그림을, 그 외 링크면 <head>의 og 태그를 읽어 카드를 만든다.
어느 단계에서 실패하든 조용히 포기하고 평소의 하이퍼링크만 남긴다 - 미리보기는 덤이라
실패했다고 오류 문구를 채팅에 남기면 오히려 지저분해진다.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

import link_meta
from gui.preview.fetcher import HTML_LIMIT_BYTES
from gui.preview.image_preview import ImagePreview, is_image_url
from gui.preview.link_card import CARD_MAX_WIDTH, LinkCard


class LinkPreviewArea(QWidget):
    """메시지 하나에 딸린 미리보기들을 담는 칸. 받아오는 일까지 전부 여기서 한다.

    - 이미지 직링크: 주소가 곧 그림이므로 바로 받아서 보여줌
    - 그 외 링크: HTML을 받아 og 태그를 읽고 카드를 만든 뒤, 거기 적힌 이미지 주소로
      그림을 한 번 더 받아 붙임

    끝까지 아무 것도 못 받으면 계속 높이 0이라 평소 메시지와 똑같이 보인다.
    fetcher를 안 주면 아무 요청도 하지 않는다(테스트/오프라인에서 안전).
    """

    def __init__(self, urls, fetcher: "ImageFetcher | None" = None, parent=None,
                 on_preview_shown=None):
        super().__init__(parent)
        self.setObjectName("linkPreviewArea")
        self.setStyleSheet("QWidget#linkPreviewArea { background: transparent; }")
        self._fetcher = fetcher
        # 미리보기가 실제로 하나라도 그려졌을 때 알려주는 콜백(메시지가 주소 문자열을
        # 지울지 판단하는 데 씀). 끝내 아무것도 못 받으면 호출되지 않으므로 주소가 남음
        self._on_preview_shown = on_preview_shown
        self._filled = set()
        # 채팅창에서 쓸 수 있는 폭. 나중에 도착하는 미리보기에도 그대로 적용해야
        # 좁은 창에서 이미지가 삐져나가지 않음
        self._max_width = 0
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        # 세로를 Fixed로 두면 안 된다 - 안에 들어가는 카드는 폭에 따라 높이가 달라지는데
        # Fixed면 폭을 반영 못 한 높이(한 줄 기준)로 굳어 카드가 눌린다
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        if fetcher is None:
            return
        for url in urls:
            if is_image_url(url):
                fetcher.fetch(url, lambda data, u=url: self._on_direct_image(u, data))
            else:
                fetcher.fetch(url, lambda data, u=url: self._on_html(u, data),
                              limit=HTML_LIMIT_BYTES)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt 규약
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        height = self._layout.heightForWidth(width)
        return height if height > 0 else self._layout.sizeHint().height()

    def set_max_width(self, width: int):
        """채팅창 폭이 바뀌었을 때 - 이미 그려진 미리보기와 앞으로 올 것 모두에 적용."""
        if width <= 0 or width == self._max_width:
            return
        self._max_width = width
        for child in self.findChildren(ImagePreview):
            child.set_max_width(width)
        for card in self.findChildren(LinkCard):
            card.setMaximumWidth(min(CARD_MAX_WIDTH, width))
            card.adjust_height()

    def _on_direct_image(self, url: str, data):
        if url in self._filled or not data:
            return
        preview = ImagePreview(url, self)
        preview.set_max_width(self._max_width)
        if not preview.set_image_data(data):
            preview.deleteLater()
            return
        self._filled.add(url)
        self._layout.addWidget(preview, 0, Qt.AlignmentFlag.AlignTop)
        self._notify_shown()

    def _notify_shown(self):
        # 미리보기는 네트워크로 나중에 도착하므로, 그때 이 칸의 크기가 바뀐다는 걸
        # 위쪽 레이아웃에 명시적으로 알려야 한다. 안 알리면 메시지 높이가 도착 전 값으로
        # 굳어 그림이 잘리거나 아래에 빈 공간이 남는다(이 코드베이스에서 이미 한 번 난
        # 사고 유형 - CLAUDE.md의 "줄바꿈 폭" 항목과 같은 뿌리).
        self.updateGeometry()
        parent = self.parentWidget()
        while parent is not None:
            parent.updateGeometry()
            layout = parent.layout()
            if layout is not None:
                layout.invalidate()
            # 메시지 목록(ChannelLogView)까지 올라가서 높이를 다시 맞추게 한다.
            # 예전엔 여기서 안쪽 위젯에 adjustSize()를 불렀는데, 그건 폭까지 sizeHint로
            # 바꿔버려서 스크롤 영역이 정하는 폭과 싸운다
            sync = getattr(parent, "sync_content_height", None)
            if callable(sync):
                sync()
                break
            parent = parent.parentWidget()
        if self._on_preview_shown is not None:
            self._on_preview_shown()

    def _on_html(self, url: str, data):
        """받아온 HTML에서 메타태그를 뽑아 카드를 만듦. 제목이 없으면 아무 것도 안 함."""
        if url in self._filled or not data:
            return
        info = link_meta.parse_meta(
            link_meta.decode_html(link_meta.head_only(data)), base_url=url)
        if not info.get("title"):
            return  # 보여줄 게 없으면 하이퍼링크만 남김
        self._filled.add(url)
        card = LinkCard(url, info["title"], info.get("description", ""), self)
        if self._max_width > 0:
            card.setMaximumWidth(min(CARD_MAX_WIDTH, self._max_width))
        card.adjust_height()
        self._layout.addWidget(card, 0, Qt.AlignmentFlag.AlignTop)
        self._notify_shown()
        # 화면에 붙은 뒤 실제 글꼴로 한 번 더 재게 함(카드당 딱 한 번).
        # showEvent에서 하면 다시 보일 때마다 예약이 쌓여 스택이 넘쳤다
        QTimer.singleShot(0, card.remeasure)
        image_url = info.get("image_url", "")
        if image_url:
            self._fetcher.fetch(image_url, lambda d: self._on_card_image(card, d))

    @staticmethod
    def _on_card_image(card: LinkCard, data):
        if not data:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data) and not pixmap.isNull():
            card.set_thumbnail(pixmap)
