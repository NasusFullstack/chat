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

from gui.components import relayout
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
        """**한 줄에 다 늘어놓았을 때의 크기**(= 이 칸의 '자연스러운' 크기).

        Qt의 FlowLayout 예제는 여기서 `minimumSize()`를 돌려주는데, 그러면 폭이
        '가장 넓은 항목 하나'(192px)로 보고된다. Qt는 `totalSizeHint()`에서 그 폭을
        다시 넣어 높이를 물어보므로(`heightForWidth(192)`), 이모티콘이 전부 세로로
        쌓인 높이가 '자연 크기'로 굳는다.

        실측(2026-09-29, 이모티콘 6개): 실제 높이 516px인데 sizeHint가 832px.
        이 칸은 세로 정책이 Minimum이라 sizeHint가 곧 최소 높이가 되고, 그 값이
        메시지 한 줄(751 -> 1067)과 대화 목록(3039 -> 4223)까지 그대로 전파됐다.
        남는 1184px이 **채팅 맨 아래 빈 공간**이었다.

        실제 폭에서의 높이는 `heightForWidth()`가 정확히 답하므로, 여기서는 규약대로
        '자연스러운 크기'만 답하면 된다.
        """
        width = 0
        height = 0
        for item in self._items:
            hint = item.sizeHint()
            width += hint.width() + self._spacing
            height = max(height, hint.height())
        if self._items:
            width -= self._spacing
        margins = self.contentsMargins()
        return QSize(max(0, width) + margins.left() + margins.right(),
                     height + margins.top() + margins.bottom())

    def minimumSize(self):  # noqa: N802
        """가장 좁혔을 때 - 이모티콘 한 개는 들어가야 한다(그보다 좁으면 잘린다)."""
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return QSize(size.width() + margins.left() + margins.right(),
                     size.height() + margins.top() + margins.bottom())

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
    """한 메시지에 들어있는 이모티콘들.

    높이는 **글자와 같은 방식으로 정한다**(gui/components/message_text.py 참고):
    쓸 수 있는 폭을 알려주면 그 폭에서 몇 줄이 되는지 세어 높이를 못 박는다.
    레이아웃이 추측할 여지를 없애야 '눌려서 잘림'도 '아래 빈 공간'도 안 생긴다.
    """

    def __init__(self, urls, fetcher=None, parent=None):
        super().__init__(parent)
        self.setObjectName("emojiRow")
        self.setStyleSheet("QWidget#emojiRow { background: transparent; }")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._layout = _FlowLayout(self)
        # 이 칸이 쓸 수 있는 폭. 메시지 줄이 알려준다(안 알려주면 자기 폭을 씀)
        self._wrap_width = 0
        self._previews = []
        for url in urls:
            preview = ImagePreview(url, self)
            preview.set_max_width(EMOJI_PX)
            preview.setFixedSize(EMOJI_PX, EMOJI_PX)  # 도착 전에도 자리를 잡아둠
            self._layout.addWidget(preview)
            self._previews.append(preview)
            if fetcher is not None:
                fetcher.fetch(url, lambda data, p=preview: self._on_image(p, data))

    def set_wrap_width(self, width: int):
        """이 칸이 쓸 수 있는 폭 - 이 폭에서 몇 줄이 되는지 정해 높이를 고정한다."""
        if width <= 0 or width == self._wrap_width:
            return
        self._wrap_width = width
        self.setMaximumWidth(width)
        self._apply_height()

    def _apply_height(self):
        width = self._wrap_width or self.width()
        if width <= 0:
            return
        needed = self._layout.heightForWidth(width)
        if needed > 0:
            self.setFixedHeight(needed)

    def _on_image(self, preview, data):
        if not data or not preview.set_image_data(data):
            return
        preview.set_max_width(EMOJI_PX)
        # 자리를 잡아둔 크기(192x192)와 실제 그림 크기가 다르므로 줄 수가 달라진다.
        # 높이를 여기서 다시 못 박고, 크기가 바뀌었다는 것만 위쪽에 알린다.
        # 알리는 방법을 손으로 짜지 말 것 - 예전에 이 자리에서 조상 레이아웃 무효화를
        # 빠뜨려서 이모티콘 여러 개일 때 아래에 1184px이 남았다(relayout.py 참고)
        self._apply_height()
        relayout.size_changed(self)

    def urls(self):
        return [p.url for p in self._previews]
