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
# 배지가 둘일 때(로고 + 종류 표시) 그 사이 간격
BADGE_GAP = 3


class ClientBadgeDelegate(QStyledItemDelegate):
    """user_id -> 배지 그림을 받아와 오른쪽 끝에 그린다."""

    def __init__(self, badge_source, parent=None):
        """badge_source(user_id) -> [QPixmap, ...]. 무엇을 그릴지는 바깥이 정한다.

        여러 개인 이유: 휴대폰이나 봇은 로고 옆에 회색 표시를 하나 더 붙인다
        (로고 위에 겹쳐 그리면 12px에서는 보이지 않는다).
        """
        super().__init__(parent)
        self._badge_source = badge_source

    def paint(self, painter, option, index):
        badges = [b for b in self._badge_source(index.data(Qt.ItemDataRole.UserRole)) or []
                  if b is not None and not b.isNull()]
        if not badges:
            super().paint(painter, option, index)
            return

        total = sum(b.width() for b in badges) + BADGE_GAP * (len(badges) - 1)
        # 이름이 배지 자리를 침범하지 않도록 그릴 폭을 미리 줄인다
        narrowed = option
        narrowed.rect = QRect(option.rect.left(), option.rect.top(),
                              max(0, option.rect.width() - total - BADGE_RIGHT_MARGIN
                                  - BADGE_LEFT_GAP),
                              option.rect.height())
        super().paint(painter, narrowed, index)

        # 오른쪽 끝에서부터 거꾸로 놓는다(마지막 것이 가장 오른쪽)
        x = option.rect.right() - BADGE_RIGHT_MARGIN + 1
        for badge in reversed(badges):
            x -= badge.width()
            y = option.rect.top() + (option.rect.height() - badge.height()) // 2
            painter.drawPixmap(x, y, badge)
            x -= BADGE_GAP


def badge_height() -> int:
    return CLIENT_BADGE_PX
