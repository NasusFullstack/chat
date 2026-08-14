"""채널 목록을 여닫는 손잡이 - 사이드바와 대화창 경계 세로 가운데에 붙는다.

버튼을 목록 위에 두지 않고 경계에 세로로 붙인 이유: 여닫는 대상은 '경계 왼쪽 전체'라
손잡이가 그 경계에 있어야 무엇이 열리고 닫히는지 한눈에 보인다. 목록 위에 있으면 접었을 때
버튼만 덩그러니 남아 무슨 버튼인지 알 수 없다.

그림은 QSS가 아니라 여기서 직접 그린다. 화살표를 글자(‹ ›)로 두면 글꼴에 따라 크기와
가운데 정렬이 제각각이라 어느 컴퓨터에서는 삐뚤어 보이기 때문이다. 선으로 그리면 어디서든
같은 모양이 나온다. 색은 테마 색표에서 가져오므로 테마를 바꾸면 같이 바뀐다.
"""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from gui.styles.palette import colors
from gui.theme import (SIDEBAR_HANDLE_ARROW_PX, SIDEBAR_HANDLE_HEIGHT,
                       SIDEBAR_HANDLE_RADIUS, SIDEBAR_HANDLE_WIDTH)


class SidebarHandle(QWidget):
    """세로로 길쭉한 알약 모양 손잡이. 누르면 toggled."""

    toggled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(SIDEBAR_HANDLE_WIDTH, SIDEBAR_HANDLE_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._collapsed = False
        self._hover = False
        self._update_tip()

    def set_collapsed(self, collapsed: bool):
        """화살표는 **누르면 화면이 움직이는 방향**을 가리킨다.

        채널 목록을 접고 펼 때 창의 왼쪽 변이 움직인다(대화 영역은 제자리에 있다).
        - 펼친 상태에서 누르면: 목록이 사라지며 창 왼쪽 변이 **오른쪽**으로 온다 -> ▶
        - 접힌 상태에서 누르면: 목록이 나오며 창 왼쪽 변이 **왼쪽**으로 간다 -> ◀

        움직임과 반대로 그리면 "화살표가 반대인 것 같다"는 말을 듣는다(실제로 들었다).
        """
        self._collapsed = collapsed
        self._update_tip()
        self.update()

    def _update_tip(self):
        self.setToolTip("채널 목록 펼치기" if self._collapsed else "채널 목록 접기")

    # ---------------- 마우스 ----------------

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.toggled.emit()
        super().mouseReleaseEvent(event)

    # ---------------- 그리기 ----------------

    def paintEvent(self, _event):
        theme = colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 평소엔 배경에 가라앉아 있다가 마우스를 올리면 또렷해진다 - 늘 눈에 띄면
        # 대화 내용보다 손잡이가 먼저 보여서 산만하다
        body = QColor(theme["BG_ITEM_HOVER" if self._hover else "BG_ITEM"])
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                            SIDEBAR_HANDLE_RADIUS, SIDEBAR_HANDLE_RADIUS)
        painter.fillPath(path, body)

        arrow = QColor(theme["ACCENT" if self._hover else "TEXT_DIMMER"])
        pen = QPen(arrow, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        # 접혀 있으면 '펴는 쪽'(오른쪽), 펴져 있으면 '접는 쪽'(왼쪽)을 가리킨다
        cx, cy = self.width() / 2, self.height() / 2
        reach = SIDEBAR_HANDLE_ARROW_PX / 2
        # 펼침 -> 누르면 오른쪽으로 움직인다(▶) / 접힘 -> 누르면 왼쪽으로 움직인다(◀)
        tip = cx + reach if not self._collapsed else cx - reach
        back = cx - reach if not self._collapsed else cx + reach
        chevron = QPainterPath()
        chevron.moveTo(back, cy - SIDEBAR_HANDLE_ARROW_PX)
        chevron.lineTo(tip, cy)
        chevron.lineTo(back, cy + SIDEBAR_HANDLE_ARROW_PX)
        painter.drawPath(chevron)
