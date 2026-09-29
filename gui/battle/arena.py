"""전투 화면 - 채팅 영역 위를 덮는 전투장.

## 고정 좌표계를 화면에 맞춰 그린다
`battle_sim`의 전투장은 **모두에게 똑같은 1200x800**이다. 채팅창 크기를 그대로 쓰면
창이 다른 사람끼리 배 위치가 갈리기 때문이다. 여기서는 그 고정 좌표를 지금 창 크기에
맞춰 **비율을 지켜** 옮겨 그린다(남는 쪽에는 여백을 둔다 - 늘려 찌그러뜨리면 맞음
판정과 눈에 보이는 것이 어긋난다).

## 체력은 '주인 말'이 맞다
모두가 같은 계산을 하지만 조작이 도착하는 시점이 사람마다 몇 ms씩 다르므로 배 위치가
아주 조금 어긋날 수 있다. 그래서 **맞았는지는 자기 배에 대해서만 판단하고**, 그 결과를
서버를 통해 알린다. 남의 배 체력은 그 사람이 보낸 것만 따른다. 이러면 화면이 조금
달라도 "누가 몇 대 맞았나"는 모두 같다.

## 추락·폭발은 눈요기다
전투에서 빠진 사람은 계산에서 **즉시** 뺀다(`Battle.remove`). 나가는 순간이 사람마다
다른데 그 동안 배가 남아 있으면 누구 화면에선 맞고 누구 화면에선 안 맞는다.
떨어지며 터지는 연출은 계산과 무관하게 여기서만 그린다.
"""
import math

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

import battle_ai
import battle_protocol as bp
import battle_sim as sim
from gui.battle.hp_bar import draw_hp_bar
from gui.battle.lobby import ship_color
from gui.ship.painter import _draw_ship

# 조작 - 방향키 + 스페이스(야마토포)
KEY_BITS = {
    Qt.Key.Key_Left: bp.KEY_LEFT,
    Qt.Key.Key_Right: bp.KEY_RIGHT,
    Qt.Key.Key_Up: bp.KEY_UP,
    Qt.Key.Key_Down: bp.KEY_DOWN,
    Qt.Key.Key_Space: bp.KEY_FIRE,
}

SHIP_DRAW_PX = 54          # 전투장(1200x800) 기준 배 한 척 크기
SHELL_DRAW_PX = 7
HP_BAR_WIDTH = 46
HP_BAR_HEIGHT = 7
HP_BAR_GAP = 8             # 배 아래로 이만큼 떨어뜨린다(스타1처럼 아래에 붙는다)

CRASH_TICKS = 60           # 추락 연출 길이(약 1초)
BOOM_TICKS = 24            # 폭발이 보이는 시간


class _Crash:
    """추락해서 터지는 배 하나 - **계산이 아니라 연출이다.**"""

    __slots__ = ("x", "y", "vx", "vy", "facing", "color", "left", "boom")

    def __init__(self, x, y, vx, vy, facing, color):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.facing = facing
        self.color = color
        self.left = CRASH_TICKS
        self.boom = 0


class BattleArena(QWidget):
    """전투가 벌어지는 칸. 소켓을 모르고 신호로만 대화한다."""

    input_ready = Signal(int, int)     # 틱, 누른 키 - 중계로 보내야 함
    i_was_hit = Signal(int)            # 내가 맞았다(쏜 사람 자리)
    i_died = Signal(int)               # 내가 격추됐다(쏜 사람 자리)
    escape_pressed = Signal()          # ESC - 이탈할지 물어봐야 함
    killed = Signal(int, int)          # 격추된 자리, 쏜 자리 - 채팅에 한 줄 남기려고

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.hide()

        self._battle = None
        self._my_slot = -1
        self._colors = {}          # 자리 -> 색 번호
        self._names = {}           # 자리 -> 이름
        self._pressed = set()
        self._peer_keys = {}       # 자리 -> 마지막으로 받은 키
        self._crashes = []
        self._ai_slots = set()
        self._tick = 0
        self._input = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

    # ---------- 바깥에서 부르는 것 ----------
    def attach_input(self, line_edit):
        """조작을 가로챌 입력창. 혼자 날 때(BattlecruiserOverlay)와 같은 방식이다 -
        포커스는 보통 입력창에 있으므로 거기에 필터를 건다."""
        if self._input is line_edit:
            return
        if self._input is not None:
            self._input.removeEventFilter(self)
        self._input = line_edit
        if line_edit is not None:
            line_edit.installEventFilter(self)

    def start(self, my_slot: int, players: dict, ai_slots=()):
        """전투 시작. players = {자리: (이름, 색)}

        `ai_slots`는 연습 상대(AI)가 맡을 자리. **내 화면에서만 도는 상대다** -
        규약이 남의 자리로는 조작을 못 보내게 막아뒀기 때문이다(그게 보안의 핵심).
        혼자서 시험해 볼 때 쓴다.
        """
        self._my_slot = my_slot
        self._names = {slot: name for slot, (name, _c) in players.items()}
        self._colors = {slot: color for slot, (_n, color) in players.items()}
        self._ai_slots = {slot for slot in ai_slots if slot in players}
        self._battle = sim.Battle(sorted(players))
        self._pressed.clear()
        self._peer_keys.clear()
        self._crashes.clear()
        self._tick = 0
        self.show()
        self.raise_()
        self._timer.start(sim.TICK_MS)

    def stop(self):
        self._timer.stop()
        self._battle = None
        self._pressed.clear()
        self._crashes.clear()
        self.hide()

    @property
    def is_active(self) -> bool:
        return self._battle is not None and self.isVisible()

    def scores(self):
        """자리 -> (이름, 격추, 당한 수). 전투가 끝나고 보여줄 때 쓴다."""
        if self._battle is None:
            return {}
        return {slot: (self._names.get(slot, "?"), ship.kills, ship.deaths)
                for slot, ship in self._battle.ships.items()}

    # ---------- 중계에서 오는 것 ----------
    def apply_peer_input(self, slot: int, _tick: int, keys: int):
        """남의 조작. 도착하는 대로 반영한다 - 지연이 6ms 남짓이라 눈에 안 띈다."""
        if slot != self._my_slot:
            self._peer_keys[slot] = int(keys) & bp.KEY_MASK

    def apply_peer_hit(self, slot: int, _by: int):
        """남이 '나 맞았다'고 알려온 것. **그 사람 말이 맞다**(위 설명 참고)."""
        if self._battle is None or slot == self._my_slot:
            return
        ship = self._battle.ships.get(slot)
        if ship is not None and ship.alive:
            ship.hp = max(0, ship.hp - sim.SHELL_DAMAGE)

    def apply_peer_dead(self, slot: int, by: int):
        if self._battle is None or slot == self._my_slot:
            return
        ship = self._battle.ships.get(slot)
        if ship is not None:
            ship.hp = 0
            ship.deaths += 1
            ship.respawn_left = sim.RESPAWN_TICKS
            shooter = self._battle.ships.get(by)
            if shooter is not None:
                shooter.kills += 1
        self.killed.emit(slot, by)

    def remove_player(self, slot: int):
        """누가 전투에서 빠졌다 - 계산에서는 즉시 빼고, 추락 연출만 남긴다."""
        if self._battle is None:
            return
        ship = self._battle.ships.get(slot)
        if ship is not None:
            self._crashes.append(_Crash(ship.x, ship.y, ship.vx, ship.vy, ship.facing,
                                        self._colors.get(slot, 0)))
        self._battle.remove(slot)
        self._peer_keys.pop(slot, None)

    def name_of(self, slot: int) -> str:
        return self._names.get(slot, f"{slot}번")

    # ---------- 조작 ----------
    def eventFilter(self, obj, event):
        if obj is not self._input or not self.is_active:
            return False
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        if event.key() == Qt.Key.Key_Escape:
            if event.type() == QEvent.Type.KeyPress:
                self.escape_pressed.emit()
            return True
        bit = KEY_BITS.get(event.key())
        if bit is None:
            return False
        # 메시지를 쓰는 중이면 조작을 가로채지 않는다 - 전투 중에도 채팅이 우선
        if self._input.text():
            return False
        if event.type() == QEvent.Type.KeyPress:
            self._pressed.add(bit)
        else:
            self._pressed.discard(bit)
        return True

    # ---------- 한 틱 ----------
    def _advance(self):
        if self._battle is None:
            return
        self._tick += 1
        keys = 0
        for bit in self._pressed:
            keys |= bit

        # 내 조작은 중계로 보내고(남들이 같은 걸 계산하도록), 내 화면에도 바로 반영한다
        self.input_ready.emit(self._tick, keys)

        all_keys = dict(self._peer_keys)
        if self._my_slot >= 0:
            all_keys[self._my_slot] = keys
        # 연습 상대는 내 화면에서만 돈다(중계로 내보내지 않는다)
        for ai_slot in self._ai_slots:
            all_keys[ai_slot] = battle_ai.decide(self._battle, ai_slot, self._tick)
        for event in self._battle.advance(all_keys):
            # **내 배에 대한 것만 내가 판단한다.** 남의 배는 그 사람 말을 따른다
            if event["slot"] != self._my_slot:
                continue
            if event["t"] == "hit":
                self.i_was_hit.emit(event["by"])
            else:
                self.i_died.emit(event["by"])
                self.killed.emit(event["slot"], event["by"])

        self._step_crashes()
        self.update()

    def _step_crashes(self):
        alive = []
        for crash in self._crashes:
            if crash.boom:
                crash.boom -= 1
                if crash.boom:
                    alive.append(crash)
                continue
            crash.left -= 1
            crash.vy += 40                      # 떨어진다(1/256칸 단위)
            crash.x += crash.vx
            crash.y += crash.vy
            if crash.left <= 0 or crash.y > sim.FIELD_HEIGHT * sim.SCALE:
                crash.boom = BOOM_TICKS
            alive.append(crash)
        self._crashes = alive

    # ---------- 그리기 ----------
    def _field_box(self) -> QRectF:
        """고정 좌표계(1200x800)를 지금 창에 비율을 지켜 앉힌 자리."""
        scale = min(self.width() / sim.FIELD_WIDTH, self.height() / sim.FIELD_HEIGHT)
        width = sim.FIELD_WIDTH * scale
        height = sim.FIELD_HEIGHT * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2,
                      width, height)

    def _to_screen(self, box: QRectF, x: int, y: int) -> QPointF:
        return QPointF(box.x() + x / sim.SCALE / sim.FIELD_WIDTH * box.width(),
                       box.y() + y / sim.SCALE / sim.FIELD_HEIGHT * box.height())

    def paintEvent(self, _event):
        if self._battle is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = self._field_box()
        scale = box.width() / sim.FIELD_WIDTH

        # 전투장 테두리 - 어디까지 갈 수 있는지 보이게(없으면 벽이 어디인지 모른다)
        painter.setPen(QPen(QColor(120, 140, 200, 90), 1.5))
        painter.setBrush(QColor(10, 14, 28, 60))
        painter.drawRect(box)

        for shell in self._battle.shells:
            self._draw_shell(painter, box, shell, scale)
        for slot in sorted(self._battle.ships):
            self._draw_ship_at(painter, box, self._battle.ships[slot], scale)
        for crash in self._crashes:
            self._draw_crash(painter, box, crash, scale)
        painter.end()

    def _draw_shell(self, painter, box, shell, scale):
        center = self._to_screen(box, shell.x, shell.y)
        radius = SHELL_DRAW_PX * scale / 2
        glow = QRadialGradient(center, radius * 2.2)
        color = ship_color(self._colors.get(shell.owner, 0), self._tick)
        glow.setColorAt(0.0, QColor(255, 255, 220))
        glow.setColorAt(0.45, color)
        glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, radius * 2.2, radius * 2.2)

    def _draw_ship_at(self, painter, box, ship, scale):
        center = self._to_screen(box, ship.x, ship.y)
        if not ship.alive:
            return                        # 격추된 배는 안 보인다(다시 살아나면 보인다)
        size = SHIP_DRAW_PX * scale

        painter.save()
        painter.translate(center)
        painter.rotate(ship.facing * sim.TURN_STEP_DEG)
        _draw_ship(painter, size)
        painter.restore()

        # 누구 배인지 - 색 고리를 두른다(배 그림 자체는 모두 같은 회색이라 구분이 안 된다)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(ship_color(self._colors.get(ship.slot, 0), self._tick), 2.0))
        painter.drawEllipse(center, size * 0.62, size * 0.62)

        bar = QRectF(center.x() - HP_BAR_WIDTH * scale / 2,
                     center.y() + size * 0.62 + HP_BAR_GAP * scale,
                     HP_BAR_WIDTH * scale, HP_BAR_HEIGHT * scale)
        draw_hp_bar(painter, bar, ship.hp / sim.MAX_HP, sim.HP_SEGMENTS)

    def _draw_crash(self, painter, box, crash, scale):
        center = self._to_screen(box, crash.x, crash.y)
        if crash.boom:
            # 터지는 중 - 커지면서 옅어진다
            progress = 1.0 - crash.boom / BOOM_TICKS
            radius = (18 + 46 * progress) * scale
            glow = QRadialGradient(center, radius)
            glow.setColorAt(0.0, QColor(255, 244, 200, int(230 * (1 - progress))))
            glow.setColorAt(0.4, QColor(255, 150, 40, int(200 * (1 - progress))))
            glow.setColorAt(1.0, QColor(120, 30, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(center, radius, radius)
            return
        # 떨어지는 중 - 빙글 돌면서 연기를 낸다
        spin = (CRASH_TICKS - crash.left) * 7
        painter.save()
        painter.translate(center)
        painter.rotate(crash.facing * sim.TURN_STEP_DEG + spin)
        _draw_ship(painter, SHIP_DRAW_PX * scale)
        painter.restore()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(90, 90, 100, 120))
        painter.drawEllipse(center, 10 * scale, 10 * scale)


def format_kill_line(shooter: str, victim: str) -> str:
    """격추됐을 때 채팅에 남길 한 줄. 문구를 한 곳에서 정해 둔다."""
    return f"{shooter}님이 {victim}님의 배틀크루저를 격추했습니다."
