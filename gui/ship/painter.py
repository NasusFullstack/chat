"""스프라이트 파일이 없을 때 쓰는, 직접 그린 배틀크루저.

자원 치트의 숫자와 같은 이유로 그림 파일에 기대지 않는 길을 함께 둔다 - 파일이 없어도
기능이 죽지 않아야 하기 때문.
"""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPolygonF

from gui.ship.sprite import (_ENGINE, _HULL_DARK, _HULL_LIGHT, _HULL_MID, _OUTLINE,
                             _TEAM, _TEAM_DARK)


def _draw_ship(painter: QPainter, size: float):
    """원점을 중심으로, 위쪽(-y)이 진행 방향인 배틀크루저를 그림"""
    s = size / 100.0  # 100 기준으로 좌표를 잡고 마지막에 축소

    def p(x, y):
        return QPointF(x * s, y * s)

    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(_OUTLINE, 1.2))

    # 뒤쪽 엔진 노즐 4개
    painter.setBrush(_HULL_DARK)
    for ex in (-26, -10, 10, 26):
        painter.drawRoundedRect(QRectF(p(ex - 7, 26), p(ex + 7, 46)), 3 * s, 3 * s)
    painter.setBrush(_ENGINE)
    painter.setPen(Qt.PenStyle.NoPen)
    for ex in (-26, -10, 10, 26):
        painter.drawRoundedRect(QRectF(p(ex - 4, 40), p(ex + 4, 50)), 2 * s, 2 * s)
    painter.setPen(QPen(_OUTLINE, 1.2))

    # 좌우 날개(엔진 포드)
    hull_grad = QLinearGradient(p(-40, -40), p(40, 40))
    hull_grad.setColorAt(0.0, _HULL_LIGHT)
    hull_grad.setColorAt(0.6, _HULL_MID)
    hull_grad.setColorAt(1.0, _HULL_DARK)
    painter.setBrush(QBrush(hull_grad))
    painter.drawPolygon(QPolygonF([p(-16, -6), p(-40, 10), p(-38, 30), p(-14, 26)]))
    painter.drawPolygon(QPolygonF([p(16, -6), p(40, 10), p(38, 30), p(14, 26)]))

    # 중앙 선체 - 앞이 뾰족한 길쭉한 형태
    painter.drawPolygon(QPolygonF([
        p(0, -48), p(11, -30), p(16, -2), p(18, 24), p(10, 34),
        p(-10, 34), p(-18, 24), p(-16, -2), p(-11, -30),
    ]))

    # 함교(앞쪽 돌출부)
    painter.setBrush(_HULL_LIGHT)
    painter.drawPolygon(QPolygonF([p(0, -44), p(7, -28), p(0, -20), p(-7, -28)]))

    # 팀 컬러 패널 - 원본에서 분홍/보라로 칠해지는 부분(요청대로 회색 계열)
    painter.setPen(QPen(_TEAM_DARK, 1))
    painter.setBrush(_TEAM)
    painter.drawRect(QRectF(p(-6, -14), p(6, 4)))
    painter.drawRect(QRectF(p(-34, 13), p(-22, 23)))
    painter.drawRect(QRectF(p(22, 13), p(34, 23)))

    # 선체 위 디테일 라인
    painter.setPen(QPen(_HULL_DARK, 1))
    painter.drawLine(p(-12, 8), p(12, 8))
    painter.drawLine(p(-13, 18), p(13, 18))
