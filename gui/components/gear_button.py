"""환경설정 톱니바퀴 - 채널 목록 맨 아래 왼쪽에 붙는 작은 버튼.

손잡이(sidebar_handle.py)와 같은 이유로 글자나 그림 파일이 아니라 선으로 직접 그린다:
글꼴에 이모지가 없으면 네모로 보이고, 그림 파일은 테마 색을 따라가지 못한다.

이 부품은 '눌렸다'만 알린다. 환경설정 창을 어떻게 여는지는 바깥이 정한다.
"""
import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from gui.styles.palette import colors
from gui.theme import GEAR_BTN_PX, GEAR_TEETH, GEAR_TOOTH_PX

class GearButton(QWidget):
    """회색 톱니바퀴. 마우스를 올리면 또렷해진다."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(GEAR_BTN_PX, GEAR_BTN_PX)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('환경설정')
        self._hover = False

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
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event):
        """톱니바퀴를 **면으로 채워서** 그린다.

        예전에는 얇은 선(1.5px)으로 원과 톱니를 그렸는데, 이 크기에서는 흐릿한 동그라미로
        보여서 "무슨 버튼인지" 알아보기 어려웠다. 지금은 톱니 달린 바퀴를 통째로 칠하고
        가운데를 뚫는다 - 작아도 형태가 또렷하다.
        """
        theme = colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(theme["ACCENT" if self._hover else "TEXT_DIMMER"])

        cx = cy = self.width() / 2
        outer = self.width() / 2 - 1          # 톱니 끝
        inner = outer - GEAR_TOOTH_PX         # 바퀴 몸통
        half = math.pi / GEAR_TEETH / 2       # 톱니 하나가 차지하는 각의 절반

        wheel = QPainterPath()
        for i in range(GEAR_TEETH):
            angle = 2 * math.pi * i / GEAR_TEETH
            # 톱니 하나: 몸통에서 올라갔다가 다시 몸통으로 내려온다
            for radius, offset in ((inner, -half * 1.6), (outer, -half),
                                   (outer, half), (inner, half * 1.6)):
                point = QPointF(cx + math.cos(angle + offset) * radius,
                                cy + math.sin(angle + offset) * radius)
                if i == 0 and radius == inner and offset < 0:
                    wheel.moveTo(point)
                else:
                    wheel.lineTo(point)
        wheel.closeSubpath()

        hole = QPainterPath()
        hole.addEllipse(QPointF(cx, cy), inner * 0.42, inner * 0.42)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(wheel.subtracted(hole))
