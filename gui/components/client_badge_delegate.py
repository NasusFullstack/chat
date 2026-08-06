"""참여자 줄 오른쪽 끝에 접속 프로그램 로고를 그리는 그리는이.

배지를 항목 아이콘으로 넣지 않고 직접 그리는 이유: 항목 아이콘 자리는 이미 그 사람의
프로필 아이콘이 쓰고 있고, Qt 목록은 한 항목에 아이콘을 하나만 준다. 오른쪽 끝은
비어 있으니 거기에 우리가 얹는다.

크기는 닉네임 글자를 넘지 않아야 한다(CLIENT_BADGE_PX=12). 목록 폭이 좁아 이름이
길면, 이름을 배지 자리까지 침범하지 않게 잘라서 그린다.
"""
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QStyledItemDelegate

from gui.client_badges import CLIENT_BADGE_PX

# 배지와 목록 오른쪽 끝 사이 여백(스크롤바가 있어도 겹치지 않을 만큼)
BADGE_RIGHT_MARGIN = 6
# 이름과 배지 사이 최소 간격
BADGE_LEFT_GAP = 6


class ClientBadgeDelegate(QStyledItemDelegate):
    """user_id -> 배지 그림을 받아와 오른쪽 끝에 그린다."""

    def __init__(self, badge_source, parent=None):
        """badge_source(user_id) -> QPixmap | None. 무엇을 그릴지는 바깥이 정한다."""
        super().__init__(parent)
        self._badge_source = badge_source

    def paint(self, painter, option, index):
        badge = self._badge_source(index.data(Qt.ItemDataRole.UserRole))
        if badge is None or badge.isNull():
            super().paint(painter, option, index)
            return

        # 이름이 배지 자리를 침범하지 않도록 그릴 폭을 미리 줄인다
        reserved = badge.width() + BADGE_RIGHT_MARGIN + BADGE_LEFT_GAP
        narrowed = option
        narrowed.rect = QRect(option.rect.left(), option.rect.top(),
                              max(0, option.rect.width() - reserved), option.rect.height())
        super().paint(painter, narrowed, index)

        x = option.rect.right() - badge.width() - BADGE_RIGHT_MARGIN + 1
        y = option.rect.top() + (option.rect.height() - badge.height()) // 2
        painter.drawPixmap(x, y, badge)


def badge_height() -> int:
    return CLIENT_BADGE_PX
