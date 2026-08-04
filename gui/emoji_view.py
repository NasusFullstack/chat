"""메시지 안에 붙는 이모티콘 그림.

링크 미리보기(320px 카드)와 다른 점:
- 링크 미리보기(320px)보다 작은 192px로 그린다(보관함 격자는 이보다 더 작음)
- 여러 개면 가로로 이어 붙고, 폭이 모자라면 다음 줄로 내려간다
- 주소 문자열은 대화에 보이지 않는다(보낸 쪽이 표시로 감싸서 보냄)

그림을 받아오는 일은 링크 미리보기와 같은 ImageFetcher가 한다(크기 제한·타임아웃·사설망
차단이 이미 들어 있음). 그림이 늦게 도착하므로, 도착한 뒤 **반드시 위쪽 목록에 높이를
다시 재라고 알려야 한다** - 안 그러면 예전 높이가 남아 채팅 맨 아래에 빈 공간이 생긴다
(CLAUDE.md의 "채팅 목록 안쪽 위젯 높이" 항목과 같은 뿌리의 사고).
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLayout, QSizePolicy, QWidget

from gui.link_preview import ImagePreview

EMOJI_PX = 192         # 채팅에 보이는 이모티콘 한 변의 최대 크기
EMOJI_GAP = 4


class _FlowLayout(QLayout):
    """왼쪽부터 채우다 폭이 모자라면 다음 줄로 내리는 배치.

    Qt에 이런 레이아웃이 기본으로 없어서 직접 만든다(가로 QHBoxLayout만 쓰면 이모티콘을
    여러 개 보냈을 때 창 밖으로 삐져나가 가로 스크롤이 생긴다).
    """

    def __init__(self, parent=None, spacing=EMOJI_GAP):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802 - Qt 규약
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width):  # noqa: N802
        return self._arrange(width, apply=False)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._arrange(rect.width(), apply=True, origin=rect.topLeft())

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _arrange(self, width, apply, origin=None):
        x = y = 0
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            if x and x + hint.width() > width:
                x = 0
                y += line_height + self._spacing
                line_height = 0
            if apply and origin is not None:
                item.setGeometry(
                    item.geometry().__class__(origin.x() + x, origin.y() + y,
                                              hint.width(), hint.height()))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())
        return y + line_height


class EmojiRow(QWidget):
    """한 메시지에 들어있는 이모티콘들"""

    def __init__(self, urls, fetcher=None, parent=None):
        super().__init__(parent)
        self.setObjectName("emojiRow")
        self.setStyleSheet("QWidget#emojiRow { background: transparent; }")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._layout = _FlowLayout(self)
        self._previews = []
        for url in urls:
            preview = ImagePreview(url, self)
            preview.set_max_width(EMOJI_PX)
            preview.setFixedSize(EMOJI_PX, EMOJI_PX)  # 도착 전에도 자리를 잡아둠
            self._layout.addWidget(preview)
            self._previews.append(preview)
            if fetcher is not None:
                fetcher.fetch(url, lambda data, p=preview: self._on_image(p, data))

    def _on_image(self, preview, data):
        if not data or not preview.set_image_data(data):
            return
        preview.set_max_width(EMOJI_PX)
        self.updateGeometry()
        # 도착한 뒤 위쪽에 높이를 다시 재라고 알림(안 하면 아래에 빈 공간이 남음)
        parent = self.parentWidget()
        while parent is not None:
            sync = getattr(parent, "sync_content_height", None)
            if callable(sync):
                sync()
                return
            parent.updateGeometry()
            parent = parent.parentWidget()

    def urls(self):
        return [p.url for p in self._previews]
