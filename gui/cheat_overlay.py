"""'show me the money' 치트 오버레이 - 미네랄/가스 아이콘 + 숫자가 0에서 쭉 올라감.

숫자는 시스템 폰트가 아니라 5x7 픽셀 비트맵을 직접 그림:
- 스타크래프트 원본 폰트 파일은 공개 배포에 넣을 수 없고,
- 시스템 폰트에 의존하면 PC마다 모양이 달라지는데,
직접 그리면 어느 PC에서든 항상 똑같은 픽셀 모양이 나옴(느낌도 원본에 가장 가까움).
아이콘도 같은 이유로 이미지 파일이 아니라 QPainter로 직접 그림.
"""
import os

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF, QBrush, QLinearGradient
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget

from gui.helpers import _find_image_in_app_dirs

# 이 이름의 이미지가 있으면 직접 그린 아이콘 대신 그 이미지를 씀. 없으면 아래의
# _draw_mineral/_draw_gas로 직접 그림(둘 다 정상 동작).
# 찾는 경로는 로고(icon.png)와 같은 규칙 - 설치 폴더와 PyInstaller 번들 양쪽을 보므로,
# 저장소에 파일을 넣고 빌드 스크립트에 --add-data 한 줄만 더하면 설치 때 자동으로 따라감.
MINERAL_FILENAME = "mineral.png"
GAS_FILENAME = "gas.png"
_icon_cache: dict[str, QPixmap | None] = {}


def _custom_icon(filename: str) -> QPixmap | None:
    if filename in _icon_cache:
        return _icon_cache[filename]
    path = _find_image_in_app_dirs((filename,))
    pixmap = None
    if path:
        loaded = QPixmap(path)
        if not loaded.isNull():
            pixmap = loaded
    _icon_cache[filename] = pixmap
    return pixmap


def _draw_custom(painter: QPainter, filename: str, x: int, y: int, size: int) -> bool:
    pixmap = _custom_icon(filename)
    if pixmap is None:
        return False
    scaled = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    painter.drawPixmap(x, y + (size - scaled.height()) // 2, scaled)
    return True

# 5x7 픽셀 숫자 (스타 자원 표시처럼 굵고 각진 느낌)
_DIGITS = {
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
}

TARGET_AMOUNT = 10000
_ROLL_MS = 1400      # 0 -> 10000 올라가는 시간
_HOLD_MS = 1100      # 다 오른 뒤 잠깐 보여주는 시간
_TICK_MS = 30

_PIXEL = 5           # 숫자 1픽셀을 화면 몇 px로 그릴지
_DIGIT_W, _DIGIT_H = 5, 7
_DIGIT_GAP = 1       # 숫자 사이 간격(픽셀 단위)
_TEXT_COLOR = QColor("#f4f4f4")
_TEXT_SHADOW = QColor(0, 0, 0, 200)


def _draw_number(painter: QPainter, x: int, y: int, value: int):
    """5x7 비트맵으로 숫자를 그리고, 그린 전체 폭을 반환"""
    text = str(value)
    cx = x
    for ch in text:
        rows = _DIGITS.get(ch)
        if rows is None:
            cx += (_DIGIT_W + _DIGIT_GAP) * _PIXEL
            continue
        for ry, row in enumerate(rows):
            for rx, bit in enumerate(row):
                if bit != "1":
                    continue
                px = cx + rx * _PIXEL
                py = y + ry * _PIXEL
                # 검은 그림자를 1px 밀어서 먼저 찍어 어두운 배경에서도 또렷하게
                painter.fillRect(px + 1, py + 1, _PIXEL, _PIXEL, _TEXT_SHADOW)
        for ry, row in enumerate(rows):
            for rx, bit in enumerate(row):
                if bit == "1":
                    painter.fillRect(cx + rx * _PIXEL, y + ry * _PIXEL, _PIXEL, _PIXEL, _TEXT_COLOR)
        cx += (_DIGIT_W + _DIGIT_GAP) * _PIXEL
    return cx - x


def _draw_mineral(painter: QPainter, x: int, y: int, size: int):
    """미네랄 - 파란 결정 조각 두 개"""
    if _draw_custom(painter, MINERAL_FILENAME, x, y, size):
        return
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    grad = QLinearGradient(x, y, x + size, y + size)
    grad.setColorAt(0.0, QColor("#9fd8ff"))
    grad.setColorAt(0.5, QColor("#3aa0e8"))
    grad.setColorAt(1.0, QColor("#1663aa"))
    painter.setBrush(QBrush(grad))
    painter.setPen(QPen(QColor("#0d3f6b"), 1))
    h = size
    w = size * 0.55
    # 왼쪽 결정
    left = QPolygonF([
        QPointF(x + w * 0.5, y),
        QPointF(x + w, y + h * 0.42),
        QPointF(x + w * 0.62, y + h),
        QPointF(x + w * 0.06, y + h * 0.55),
    ])
    painter.drawPolygon(left)
    # 오른쪽 작은 결정
    ox = x + w * 0.62
    right = QPolygonF([
        QPointF(ox + w * 0.42, y + h * 0.18),
        QPointF(ox + w * 0.85, y + h * 0.58),
        QPointF(ox + w * 0.5, y + h),
        QPointF(ox + w * 0.12, y + h * 0.66),
    ])
    painter.drawPolygon(right)
    painter.restore()


def _draw_gas(painter: QPainter, x: int, y: int, size: int):
    """베스핀 가스 - 초록 통"""
    if _draw_custom(painter, GAS_FILENAME, x, y, size):
        return
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    grad = QLinearGradient(x, y, x + size, y + size)
    grad.setColorAt(0.0, QColor("#b9f6a6"))
    grad.setColorAt(0.5, QColor("#3fbf46"))
    grad.setColorAt(1.0, QColor("#14631f"))
    painter.setBrush(QBrush(grad))
    painter.setPen(QPen(QColor("#0b3d13"), 1))
    w = size * 0.62
    painter.drawRoundedRect(QRectF(x + size * 0.1, y + size * 0.16, w, size * 0.78),
                            size * 0.22, size * 0.22)
    # 위쪽 뚜껑
    painter.setBrush(QColor("#8fe27a"))
    painter.drawRoundedRect(QRectF(x + size * 0.26, y, w * 0.5, size * 0.22),
                            size * 0.08, size * 0.08)
    painter.restore()


class CheatOverlay(QWidget):
    """채팅창 가운데에 잠깐 떴다 사라지는 자원 표시. 테두리/배경 없이 아이콘+숫자만."""

    ICON_PX = 34
    GAP_ICON_TEXT = 10
    GAP_GROUPS = 46

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # 배경을 칠하지 않아 채팅 내용 위에 겹쳐 보이게 함(테두리 없음 요구사항)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.hide()

        self._value = 0
        self._elapsed = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        """이미 떠 있으면 처음부터 다시 시작"""
        self._value = 0
        self._elapsed = 0
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(_TICK_MS)
        self.update()

    def _tick(self):
        self._elapsed += _TICK_MS
        if self._elapsed <= _ROLL_MS:
            ratio = self._elapsed / _ROLL_MS
            self._value = int(TARGET_AMOUNT * ratio)
        elif self._elapsed <= _ROLL_MS + _HOLD_MS:
            self._value = TARGET_AMOUNT
        else:
            self._timer.stop()
            self.hide()
            return
        self.update()

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        w, h = 460, 60
        self.setGeometry((parent.width() - w) // 2, (parent.height() - h) // 2, w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        num_h = _DIGIT_H * _PIXEL
        icon = self.ICON_PX
        y_icon = (self.height() - icon) // 2
        y_num = (self.height() - num_h) // 2

        # 전체 폭을 먼저 재서 가운데 정렬
        text = str(self._value)
        num_w = len(text) * (_DIGIT_W + _DIGIT_GAP) * _PIXEL
        total = icon + self.GAP_ICON_TEXT + num_w + self.GAP_GROUPS + icon + self.GAP_ICON_TEXT + num_w
        x = (self.width() - total) // 2

        _draw_mineral(painter, x, y_icon, icon)
        x += icon + self.GAP_ICON_TEXT
        x += _draw_number(painter, x, y_num, self._value)
        x += self.GAP_GROUPS
        _draw_gas(painter, x, y_icon, icon)
        x += icon + self.GAP_ICON_TEXT
        _draw_number(painter, x, y_num, self._value)
        painter.end()
