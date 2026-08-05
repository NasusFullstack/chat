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
        theme = colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(theme['ACCENT' if self._hover else 'TEXT_DIMMER'])
        pen = QPen(color, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        cx = cy = self.width() / 2
        radius = self.width() / 2 - GEAR_TOOTH_PX - 1
        painter.drawEllipse(QPointF(cx, cy), radius, radius)          # 바깥 테두리
        painter.drawEllipse(QPointF(cx, cy), radius / 2.6, radius / 2.6)  # 가운데 구멍

        # 톱니는 바깥 테두리에서 바깥쪽으로 뻗는 짧은 선으로 표현한다(면으로 그리면
        # 이 크기에서는 뭉개져서 그냥 동그라미로 보인다)
        path = QPainterPath()
        for i in range(GEAR_TEETH):
            angle = 2 * math.pi * i / GEAR_TEETH
            dx, dy = math.cos(angle), math.sin(angle)
            path.moveTo(cx + dx * radius, cy + dy * radius)
            path.lineTo(cx + dx * (radius + GEAR_TOOTH_PX), cy + dy * (radius + GEAR_TOOTH_PX))
        painter.drawPath(path)
