"""'배틀크루저 소환' 치트 오버레이 - 채팅창 위에 떠서 방향키로 조종되는 함선.

그림 담당은 둘로 나뉜다 - 스프라이트 파일이 있으면 gui/ship/sprite.py가 읽어서 쓰고,
없으면 gui/ship/painter.py가 직접 그린다. 게임 리소스는 배포물에 넣을 수 없으므로
파일이 없어도 기능이 죽지 않아야 한다. 팀 컬러는 연보라 대신 회색 계열.

여기 남은 것은 **움직임과 조작**뿐이다.

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
from gui.ship.painter import _draw_ship
from gui.ship.sprite import _load_sprite

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
TURN_STEP_DEG = 11.25  # 실제 게임과 같은 32방향으로 끊어서 표현 (360/32)

ARROW_KEYS = {
    Qt.Key.Key_Left: (-1, 0),
    Qt.Key.Key_Right: (1, 0),
    Qt.Key.Key_Up: (0, -1),
    Qt.Key.Key_Down: (0, 1),
}


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
        sprite = _load_sprite()

        moving = math.hypot(self._vx, self._vy) > 0.15
        bobbing = (not moving) and self._leaving_ms < 0
        wave = math.sin(2 * math.pi * self._phase / BOB_PERIOD_MS) if bobbing else 0.0
        if bobbing:
            # 멈춰 있을 때만 제자리에서 둥실둥실 (방향은 마지막 것 그대로 유지)
            painter.translate(0, wave * BOB_AMPLITUDE)

        if sprite is not None and sprite.directional:
            # 방향별 그림이 있으면 회전시키지 않고 해당 방향 프레임을 고름.
            # 둥실거릴 때의 미세한 기울기까지 프레임으로 표현할 수는 없으므로 그건 생략 -
            # 어차피 위아래 흔들림만으로도 떠 있는 느낌은 충분히 남
            self._draw_pixmap(painter, sprite.pick(self._facing))
            painter.end()
            return

        painter.rotate(self._facing + wave * BOB_TILT_DEG)
        if sprite is not None:
            self._draw_pixmap(painter, sprite.frames[0])
        else:
            _draw_ship(painter, SHIP_PX * 0.86)
        painter.end()

    @staticmethod
    def _draw_pixmap(painter: QPainter, pixmap: QPixmap):
        scaled = pixmap.scaled(
            int(SHIP_PX * 0.9), int(SHIP_PX * 0.9),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(-scaled.width() // 2, -scaled.height() // 2, scaled)
