"""'배틀크루저 소환' 치트 오버레이 - 채팅창 위에 떠서 방향키로 조종되는 함선.

그림은 원본 스프라이트를 쓰지 않고 QPainter로 직접 그림(자원 치트의 숫자와 같은 이유):
게임 리소스는 배포물에 넣을 수 없고, 직접 그리면 어느 PC에서든 똑같이 나옴.
팀 컬러는 요청대로 연보라 대신 회색 계열.

움직임은 실제 게임의 배틀크루저 느낌을 목표로 함:
- 가속/감속이 아주 느린 무거운 함선(키를 놓아도 관성으로 조금 더 미끄러짐)
- 방향키를 두 개 같이 누르면 대각선
- 멈춰 있으면 마지막으로 향하던 방향을 유지한 채 제자리에서 둥실둥실
- 소환 해제하면 순간 가속해서 0.5초 안에 화면 밖으로 빠져나가며 사라짐
"""
import math
import os

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget

from gui.helpers import _find_image_in_app_dirs

TICK_MS = 16  # 약 60fps

# 무거운 함선 느낌 - 최고속까지 약 0.5초 걸리고, 키를 놓으면 관성으로 미끄러지다 멈춤
ACCEL = 0.10          # 틱당 속도 증가량(px/tick^2)
MAX_SPEED = 3.0       # 틱당 최대 이동량(px) ≈ 초당 190px
DRAG = 0.96           # 키를 놓았을 때 틱당 남는 속도 비율

# 소환 해제: 0.5초 안에 화면 밖으로 나가야 하므로 가속을 훨씬 크게 줌
LEAVE_MS = 500
LEAVE_ACCEL = 2.6

BOB_PERIOD_MS = 2600  # 제자리에서 둥실거리는 주기
BOB_AMPLITUDE = 3.5   # 위아래 흔들림(px)
BOB_TILT_DEG = 2.0    # 함께 살짝 기우는 각도

SHIP_PX = 96          # 오버레이 위젯 한 변(회전해도 안 잘리게 넉넉히)
TURN_STEP_DEG = 22.5  # 실제 게임처럼 방향을 16방향으로 끊어서 표현

ARROW_KEYS = {
    Qt.Key.Key_Left: (-1, 0),
    Qt.Key.Key_Right: (1, 0),
    Qt.Key.Key_Up: (0, -1),
    Qt.Key.Key_Down: (0, 1),
}

# 회색 팀 컬러 (원본의 연보라 자리)
_TEAM = QColor("#b9bdc7")
_TEAM_DARK = QColor("#6e727c")
_HULL_LIGHT = QColor("#9aa0ab")
_HULL_MID = QColor("#6b7079")
_HULL_DARK = QColor("#3e424b")
_OUTLINE = QColor("#22252b")
_ENGINE = QColor("#cfe8ff")


SPRITE_FILENAME = "battlecruiser.png"
SPRITE_MAX_PX = 256
_sprite_cache: list = []  # [QPixmap] 또는 [None] - 파일 탐색을 한 번만 하려고 캐시


def _grayify_team_color(image: QImage) -> QImage:
    """스프라이트의 팀 컬러(분홍/마젠타) 픽셀만 회색으로 바꿈.

    스타 유닛 스프라이트는 팀 컬러를 분홍색으로 칠해두고 플레이어 색으로 치환하는 구조라,
    분홍 계열(R·B는 높고 G는 낮음)만 골라 같은 밝기의 회색으로 옮기면 회색 팀이 됨.
    """
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() == 0:
                continue
            r, g, b = color.red(), color.green(), color.blue()
            if r > 90 and b > 90 and g + 60 < min(r, b):
                level = max(r, b)
                image.setPixelColor(x, y, QColor(level, level, level, color.alpha()))
    return image


def _trim_transparent(image: QImage) -> QImage:
    """투명한 바깥 여백을 잘라냄.

    스프라이트 시트에서 배 한 대를 오려낼 때 여백이 넉넉히 남기 마련인데, 그대로 두면
    회전 중심이 배가 아니라 여백 한가운데가 돼서 제자리에서 도는 게 아니라 원을 그리며
    돌아버림. 실제 그림이 차지하는 영역만 남겨서 중심을 맞춤.
    """
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    left, top = image.width(), image.height()
    right = bottom = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 8:
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)
    if right < 0:  # 전부 투명하면 그대로 둠
        return image
    return image.copy(left, top, right - left + 1, bottom - top + 1)


def _load_sprite() -> QPixmap | None:
    """battlecruiser.png가 있으면 그 이미지를, 없으면 아래 _draw_ship()으로 직접 그림.

    찾는 곳은 로고(icon.png)와 완전히 같은 경로 규칙 - 설치 폴더와 PyInstaller 번들
    양쪽을 봄. 그래서 저장소에 파일을 넣고 빌드 스크립트에 --add-data 한 줄만 추가하면
    설치할 때 자동으로 따라가고, 파일이 없으면 그냥 직접 그린 함선이 나옴(둘 다 정상 동작).
    """
    if _sprite_cache:
        return _sprite_cache[0]
    path = _find_image_in_app_dirs((SPRITE_FILENAME,))
    pixmap = None
    if path:
        image = QImage(path)
        if not image.isNull():
            # 팀 컬러 치환이 픽셀 단위 파이썬 루프라, 큰 원본(스프라이트 시트 전체 등)을
            # 그대로 돌리면 첫 소환 때 화면이 몇 초 멈춤. 어차피 100px 이하로 그리므로
            # 먼저 줄여놓고 치환함
            if max(image.width(), image.height()) > SPRITE_MAX_PX:
                image = image.scaled(
                    SPRITE_MAX_PX, SPRITE_MAX_PX,
                    Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
                )
            pixmap = QPixmap.fromImage(_grayify_team_color(_trim_transparent(image)))
    _sprite_cache.append(pixmap)
    return pixmap


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


class BattlecruiserOverlay(QWidget):
    """부모 위젯(채팅 영역) 위를 떠다니는 배틀크루저.

    방향키는 자기가 직접 못 받음(포커스는 보통 메시지 입력창에 있음). 대신
    attach_input()으로 입력창에 이벤트 필터를 걸고, **입력창이 비어 있을 때만**
    방향키를 가로챈다 - 뭔가 타이핑하는 중이면 방향키는 원래대로 커서 이동이라
    채팅에 지장을 주지 않음.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setFixedSize(SHIP_PX, SHIP_PX)
        self.hide()

        self._x = 0.0
        self._y = 0.0
        self._vx = 0.0
        self._vy = 0.0
        self._facing = 0.0  # 진행 방향(도). 0 = 위쪽, 시계방향
        self._pressed: set = set()
        self._leaving_ms = -1  # >=0 이면 퇴장 연출 중
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._input = None

    # ---------- 외부에서 부르는 것 ----------

    def attach_input(self, line_edit):
        """방향키를 가로챌 입력창을 지정(중복 호출해도 안전)"""
        if self._input is line_edit:
            return
        if self._input is not None:
            self._input.removeEventFilter(self)
        self._input = line_edit
        if line_edit is not None:
            line_edit.installEventFilter(self)

    def summon(self):
        """이미 떠 있으면 화면 가운데로 되돌리며 다시 시작"""
        parent = self.parentWidget()
        if parent is None:
            return
        self._x = (parent.width() - self.width()) / 2
        self._y = (parent.height() - self.height()) / 2
        self._vx = self._vy = 0.0
        self._facing = 0.0
        self._pressed.clear()
        self._leaving_ms = -1
        self._phase = 0
        self.move(int(self._x), int(self._y))
        self.show()
        self.raise_()
        self._timer.start(TICK_MS)

    def dismiss(self):
        """순간 가속해서 화면 밖으로 빠져나간 뒤 사라짐"""
        if not self.isVisible() or self._leaving_ms >= 0:
            return
        self._leaving_ms = 0
        self._pressed.clear()
        if not self._timer.isActive():
            self._timer.start(TICK_MS)

    @property
    def is_active(self) -> bool:
        return self.isVisible() and self._leaving_ms < 0

    def stop(self):
        """화면 전환/로그아웃 등에서 연출 없이 즉시 치움"""
        self._timer.stop()
        self._pressed.clear()
        self._leaving_ms = -1
        self.hide()

    # ---------- 입력 ----------

    def eventFilter(self, obj, event):
        if obj is not self._input or not self.is_active:
            return False
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        direction = ARROW_KEYS.get(event.key())
        if direction is None:
            return False
        # 메시지를 쓰는 중이라면 방향키는 커서 이동이어야 함(채팅이 우선)
        if self._input.text():
            return False
        if event.type() == QEvent.Type.KeyPress:
            self._pressed.add(event.key())
        else:
            self._pressed.discard(event.key())
        return True

    # ---------- 물리 ----------

    def _tick(self):
        self._phase += TICK_MS
        if self._leaving_ms >= 0:
            self._tick_leaving()
        else:
            self._tick_flying()
        self.update()

    def _tick_flying(self):
        dx = dy = 0.0
        for key in self._pressed:
            kx, ky = ARROW_KEYS[key]
            dx += kx
            dy += ky
        if dx or dy:
            length = math.hypot(dx, dy)  # 대각선이 더 빨라지지 않게 정규화
            self._vx += ACCEL * dx / length
            self._vy += ACCEL * dy / length
            speed = math.hypot(self._vx, self._vy)
            if speed > MAX_SPEED:
                self._vx *= MAX_SPEED / speed
                self._vy *= MAX_SPEED / speed
            self._facing = self._quantized_angle(self._vx, self._vy)
        else:
            # 키를 놓아도 곧바로 서지 않고 관성으로 미끄러짐
            self._vx *= DRAG
            self._vy *= DRAG
            if abs(self._vx) < 0.02:
                self._vx = 0.0
            if abs(self._vy) < 0.02:
                self._vy = 0.0

        self._x += self._vx
        self._y += self._vy
        self._clamp_to_parent()
        self.move(int(self._x), int(self._y))

    def _tick_leaving(self):
        self._leaving_ms += TICK_MS
        # 마지막으로 향하던 방향 그대로 순간 가속
        rad = math.radians(self._facing)
        self._vx += LEAVE_ACCEL * math.sin(rad)
        self._vy += LEAVE_ACCEL * -math.cos(rad)
        self._x += self._vx
        self._y += self._vy
        self.move(int(self._x), int(self._y))
        if self._leaving_ms >= LEAVE_MS or self._is_off_parent():
            self.stop()

    @staticmethod
    def _quantized_angle(vx: float, vy: float) -> float:
        # atan2(x, -y): 위쪽(-y)이 0도, 시계방향으로 증가
        angle = math.degrees(math.atan2(vx, -vy))
        return round(angle / TURN_STEP_DEG) * TURN_STEP_DEG

    def _clamp_to_parent(self):
        parent = self.parentWidget()
        if parent is None:
            return
        # 절반쯤은 밖으로 나가도 되게 여유를 둬서 가장자리가 답답하지 않게 함
        margin = self.width() / 2
        max_x = parent.width() - self.width() + margin
        max_y = parent.height() - self.height() + margin
        if self._x < -margin:
            self._x, self._vx = -margin, 0.0
        elif self._x > max_x:
            self._x, self._vx = max_x, 0.0
        if self._y < -margin:
            self._y, self._vy = -margin, 0.0
        elif self._y > max_y:
            self._y, self._vy = max_y, 0.0

    def _is_off_parent(self) -> bool:
        parent = self.parentWidget()
        if parent is None:
            return True
        return (self._x + self.width() < 0 or self._y + self.height() < 0
                or self._x > parent.width() or self._y > parent.height())

    # ---------- 그리기 ----------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.translate(self.width() / 2, self.height() / 2)

        moving = math.hypot(self._vx, self._vy) > 0.15
        if not moving and self._leaving_ms < 0:
            # 멈춰 있을 때만 제자리에서 둥실둥실 (방향은 마지막 것 그대로 유지)
            wave = math.sin(2 * math.pi * self._phase / BOB_PERIOD_MS)
            painter.translate(0, wave * BOB_AMPLITUDE)
            painter.rotate(self._facing + wave * BOB_TILT_DEG)
        else:
            painter.rotate(self._facing)

        sprite = _load_sprite()
        if sprite is not None:
            scaled = sprite.scaled(
                int(SHIP_PX * 0.9), int(SHIP_PX * 0.9),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(-scaled.width() // 2, -scaled.height() // 2, scaled)
        else:
            _draw_ship(painter, SHIP_PX * 0.86)
        painter.end()
