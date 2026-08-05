"""안읽음 채널을 옅은 노란색으로 물들이는 그리는이(델리게이트).

채널 목록(channel_sidebar.py)에서 떼어낸 이유: 저쪽이 바뀌는 이유는 "채널을 어떻게
다루는가"(추가/선택/나가기/접기)이고, 이 파일이 바뀌는 이유는 "안읽음을 어떻게 보여주는가"다.
색을 바꾸거나 테두리 모양을 손볼 때 채널 목록 코드를 읽을 필요가 없어야 한다.

왜 항목 배경색(`item.setBackground()`)을 안 쓰는가: 스타일시트에
`QListWidget#channelList::item {{ background-color: ... }}`가 있으면 **항상 그쪽이 이겨서**
코드로 준 배경색은 무시된다(예전 탭에서 글자색으로 같은 일을 겪어 아이콘으로 우회했었다).
그리는이는 스타일이 다 그린 **뒤에** 덧칠하므로 이 싸움에서 자유롭고, 선택/마우스오버
상태도 그대로 비쳐 보인다(반투명이라 덮지 않고 물들이기만 함).
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QStyledItemDelegate

from gui.theme import CHANNEL_ROW_GAP, UNREAD_BLINK_COLOR, UNREAD_TINT_RADIUS


class UnreadTintDelegate(QStyledItemDelegate):
    """안읽음 채널 항목 위에 옅은 노란색을 덧칠한다. 진하기는 바깥이 정한다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alphas: dict[str, int] = {}

    def set_alpha(self, channel: str, alpha: int):
        """0이면 표시를 지운다. 그 밖에는 0~255 투명도."""
        if alpha <= 0:
            self._alphas.pop(channel, None)
        else:
            self._alphas[channel] = alpha
        view = self.parent()
        if view is not None:
            view.viewport().update()

    def alpha_of(self, channel: str) -> int:
        return self._alphas.get(channel, 0)

    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        alpha = self._alphas.get(index.data(Qt.ItemDataRole.UserRole), 0)
        if alpha <= 0:
            return
        color = QColor(UNREAD_BLINK_COLOR)
        color.setAlpha(alpha)
        # 항목의 둥근 모서리를 그대로 따라가야 네모난 색판이 삐져나오지 않는다.
        # 아래를 CHANNEL_ROW_GAP만큼 비우는 이유: 넘어오는 사각형은 줄 전체(44px)인데
        # 알약은 QSS의 margin-bottom만큼 그 안쪽에 그려진다. 그대로 칠하면 항목 사이
        # 틈까지 노랗게 번진다(실측으로 확인)
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(option.rect).adjusted(0.5, 0.5, -0.5, -CHANNEL_ROW_GAP - 0.5),
            UNREAD_TINT_RADIUS, UNREAD_TINT_RADIUS)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillPath(path, color)
        painter.restore()
