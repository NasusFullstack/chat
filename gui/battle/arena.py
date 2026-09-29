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
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

import battle_ai
import battle_protocol as bp
import battle_sim as sim
from gui.battle.hp_bar import draw_hp_bar
from gui.battle.lobby import ship_color
from gui.ship.painter import _draw_ship
from gui.ship.sprite import _load_sprite

# 조작 - 방향키 + 스페이스(야마토포)
KEY_BITS = {
    Qt.Key.Key_Left: bp.KEY_LEFT,
    Qt.Key.Key_Right: bp.KEY_RIGHT,
    Qt.Key.Key_Up: bp.KEY_UP,
    Qt.Key.Key_Down: bp.KEY_DOWN,
    Qt.Key.Key_Space: bp.KEY_FIRE,
}

SHIP_DRAW_PX = 110         # 전투장(1200x800) 기준 배 한 척 크기(작으면 뭘 하는지 안 보인다)
# 야마토포 불덩이 기본 크기(모은 만큼 커진다)
SHELL_CORE_PX = 9
TRAIL_STEPS = 5           # 뒤로 남는 불꼬리 마디 수
HP_BAR_WIDTH = 60
HP_BAR_HEIGHT = 8
HP_BAR_GAP = 8             # 배 아래로 이만큼 떨어뜨린다(스타1처럼 아래에 붙는다)

CRASH_TICKS = 29           # 추락 연출 길이(약 1초)
BOOM_TICKS = 12            # 폭발이 보이는 시간
# 추락하며 도는 빠르기(틱마다 방향 프레임을 이만큼씩 넘긴다)
CRASH_SPIN_STEP = 2

# 키가 그대로여도 이만큼마다 한 번은 다시 보낸다(약 1초). 규약 상한(초당 30줄) 아래로
# 넉넉히 들어가면서, 한 줄을 놓쳐 어긋난 상태가 오래 남지 않게 하는 값
RESEND_TICKS = 29

# 물들인 배 그림을 보관해 두는 한도. 무지개는 색이 계속 바뀌어 끝없이 쌓이므로 상한을 둔다
# 색을 얼마나 밝혀서 곱할지(100이 원래 색). 원본이 중간 밝기라 그냥 곱하면 시커메진다
TINT_LIGHTEN = 185
# 어두운 부분을 얼마나 살릴지(클수록 옅게 얹는다)
TINT_LIFT = 280
TINT_CACHE_LIMIT = 256
_TINT_CACHE = {}


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
    bot_input = Signal(int, int, int)  # 연습 상대 자리, 틱, 키 - 방장이 중계로 보내야 함
    bot_hit = Signal(int, int, int)    # 연습 상대 자리, 쏜 자리, 남은 체력
    bot_dead = Signal(int, int)        # 연습 상대 자리, 쏜 자리
    i_was_hit = Signal(int, int)       # 내가 맞았다(쏜 사람 자리, 내 남은 체력)
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
        # 마지막으로 중계에 보낸 키. -1은 "아직 아무것도 안 보냄"(0도 유효한 값이라 구분이 필요)
        self._last_sent_keys = -1
        self._last_sent_tick = 0
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
        # **내가 판정하는 배는 내 배와 연습 상대뿐이다.** 남의 배까지 여기서 깎으면
        # 그 사람이 보낸 신고와 겹쳐 두 배로 닳는다(자세한 이유는 battle_sim.judged)
        self._battle = sim.Battle(sorted(players),
                                  judged={my_slot} | self._ai_slots)
        self._pressed.clear()
        self._peer_keys.clear()
        self._crashes.clear()
        self._tick = 0
        self._last_sent_keys = -1
        self._last_sent_tick = 0
        self._last_bot_keys = {}
        self._last_bot_tick = {}
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

    def apply_peer_hit(self, slot: int, _by: int, hp: int):
        """남이 맞았다고 알려온 것 - **남은 체력을 그대로 따른다.**

        예전에는 최대 데미지를 깎았는데, 기를 모은 정도에 따라 70~260으로 달라지므로
        약하게 맞은 배가 내 화면에서만 죽어 보이지도 맞지도 않는 유령이 됐다.
        받은 값으로 맞추면 한 줄을 놓쳐도 다음 보고에서 저절로 복구된다.
        """
        if self._battle is None or slot == self._my_slot:
            return
        ship = self._battle.ships.get(slot)
        if ship is not None:
            ship.hp = max(0, min(sim.MAX_HP, int(hp)))

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
        if event.type() == QEvent.Type.KeyRelease:
            # **키를 뗀 건 무조건 반영한다.** 예전에는 입력창에 글자가 있으면 여기서
            # 바로 돌아갔는데, 방향키를 누른 채 글자를 치면 그 키가 눌린 채로 박혀
            # 배가 그쪽으로 계속 갔다. 떼는 건 막을 이유가 없다
            self._pressed.discard(bit)
            return not self._input.text()
        # 메시지를 쓰는 중이면 조작을 가로채지 않는다 - 전투 중에도 채팅이 우선
        if self._input.text():
            return False
        self._pressed.add(bit)
        return True

    # ---------- 한 틱 ----------
    def _advance(self):
        if self._battle is None:
            return
        self._tick += 1
        keys = 0
        for bit in self._pressed:
            keys |= bit

        # **바뀔 때만 보낸다.** 처음에는 매 틱(60fps) 보냈는데, 규약 상한이 초당 30줄이라
        # 시작하자마자 "너무 빠르게 보내고 있습니다"로 끊겼다(실제 신고 2026-09-29).
        # 어차피 같은 키를 60번 보낼 이유가 없다 - 받는 쪽은 '지금 눌린 키'만 알면 된다.
        # 키를 누르고 떼는 건 사람 손이라 초당 몇 번을 넘지 않는다.
        # 아주 가끔(아래 주기) 같은 값이라도 한 번 보내, 늦게 들어온 사람이나
        # 중간에 한 줄을 놓친 경우가 영영 어긋난 채로 남지 않게 한다
        if keys != self._last_sent_keys or self._tick - self._last_sent_tick >= RESEND_TICKS:
            self._last_sent_keys = keys
            self._last_sent_tick = self._tick
            self.input_ready.emit(self._tick, keys)

        all_keys = dict(self._peer_keys)
        if self._my_slot >= 0:
            all_keys[self._my_slot] = keys
        # **연습 상대는 방장이 굴려서 모두에게 넘긴다.** 각자 계산하면 조작이 도착하는
        # 시점이 달라 AI 위치가 사람마다 갈린다. 손님은 넘어온 조작을 받기만 한다
        for ai_slot in sorted(self._ai_slots):
            keys_for_bot = battle_ai.decide(self._battle, ai_slot, self._tick)
            all_keys[ai_slot] = keys_for_bot
            changed = keys_for_bot != self._last_bot_keys.get(ai_slot, -1)
            stale = self._tick - self._last_bot_tick.get(ai_slot, 0) >= RESEND_TICKS
            if changed or stale:
                self._last_bot_keys[ai_slot] = keys_for_bot
                self._last_bot_tick[ai_slot] = self._tick
                self.bot_input.emit(ai_slot, self._tick, keys_for_bot)

        for event in self._battle.advance(all_keys):
            # 계산이 내주는 건 **내가 판정하는 배**(내 배 + 연습 상대)에 대한 것뿐이다.
            # 그 결과를 중계로 알려야 남들 화면에서도 체력이 같아진다
            if event["slot"] == self._my_slot:
                mine = self._battle.ships.get(self._my_slot)
                if event["t"] == "hit":
                    self.i_was_hit.emit(event["by"], mine.hp if mine else 0)
                else:
                    self.i_died.emit(event["by"])
                    self.killed.emit(event["slot"], event["by"])
            elif event["slot"] in self._ai_slots:
                # 연습 상대가 맞은 것도 모두에게 알려야 체력이 같아진다
                hurt = self._battle.ships.get(event["slot"])
                if event["t"] == "hit":
                    self.bot_hit.emit(event["slot"], event["by"], hurt.hp if hurt else 0)
                else:
                    self.bot_dead.emit(event["slot"], event["by"])
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
        """야마토포 - 총알이 아니라 **붉은 불덩이**다.

        실제 야마토포는 기를 모아 쏘는 큰 불덩어리라, 작은 점으로 그리면 전혀 다른
        무기처럼 보인다. 모은 만큼 커지고 뒤로 불꼬리가 길게 남는다.
        """
        center = self._to_screen(box, shell.x, shell.y)
        power = max(0, min(100, getattr(shell, "power", 100)))
        radius = (SHELL_CORE_PX * (0.55 + 0.45 * power / 100)) * scale
        painter.setPen(Qt.PenStyle.NoPen)

        # 불꼬리 - 날아온 쪽으로 점점 작아지며 옅어진다
        speed = max(1, abs(shell.vx) + abs(shell.vy))
        step_x = -shell.vx / speed
        step_y = -shell.vy / speed
        for index in range(1, TRAIL_STEPS + 1):
            fade = 1.0 - index / (TRAIL_STEPS + 1)
            tail = QPointF(center.x() + step_x * index * radius * 1.5,
                           center.y() + step_y * index * radius * 1.5)
            flame = QRadialGradient(tail, radius * fade * 1.6)
            flame.setColorAt(0.0, QColor(255, 170, 40, int(150 * fade)))
            flame.setColorAt(1.0, QColor(160, 30, 0, 0))
            painter.setBrush(flame)
            painter.drawEllipse(tail, radius * fade * 1.6, radius * fade * 1.6)

        # 불덩이 본체 - 가운데는 하얗게 타고 밖으로 갈수록 붉다
        core = QRadialGradient(center, radius * 2.4)
        core.setColorAt(0.0, QColor(255, 255, 235))
        core.setColorAt(0.25, QColor(255, 226, 120))
        core.setColorAt(0.55, QColor(255, 120, 20))
        core.setColorAt(0.8, QColor(200, 40, 10, 190))
        core.setColorAt(1.0, QColor(120, 10, 0, 0))
        painter.setBrush(core)
        painter.drawEllipse(center, radius * 2.4, radius * 2.4)

        # 누가 쏜 것인지 알 수 있게 바깥에 그 사람 색을 옅게 두른다
        owner = ship_color(self._colors.get(shell.owner, 0), self._tick)
        halo = QRadialGradient(center, radius * 3.2)
        halo.setColorAt(0.0, QColor(owner.red(), owner.green(), owner.blue(), 0))
        halo.setColorAt(0.75, QColor(owner.red(), owner.green(), owner.blue(), 70))
        halo.setColorAt(1.0, QColor(owner.red(), owner.green(), owner.blue(), 0))
        painter.setBrush(halo)
        painter.drawEllipse(center, radius * 3.2, radius * 3.2)

    @staticmethod
    def _team_colored(pixmap, mask, color: QColor):
        """**팀 컬러 자리만** 그 사람 색으로 칠한 배 그림.

        스타 유닛 그림은 팀 컬러 자리를 분홍으로 칠해두고 플레이어 색으로 바꾸는 구조다
        (gui/ship/sprite.py가 그 자리를 따로 담아둔다). 처음에는 배 전체를 물들였는데,
        선체까지 색종이가 돼서 배로 안 보였다 - 실제 게임처럼 그 자리만 칠한다.

        같은 색·같은 프레임은 다시 안 만든다 - 30fps로 네 척이면 초당 120번이라
        매번 만들면 그게 곧 렉이다.
        """
        if mask is None or mask.isNull():
            return pixmap
        key = (id(pixmap), color.rgb())
        cached = _TINT_CACHE.get(key)
        if cached is not None:
            return cached

        # 팀 컬러 자리를 그 색으로 칠한다(담아둔 밝기가 알파라 음영이 살아 있다)
        patch = QPixmap(mask.size())
        patch.fill(Qt.GlobalColor.transparent)
        painter = QPainter(patch)
        painter.drawPixmap(0, 0, mask)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(patch.rect(), color)
        painter.end()

        result = QPixmap(pixmap.size())
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.drawPixmap(0, 0, pixmap)
        painter.drawPixmap(0, 0, patch)
        painter.end()

        if len(_TINT_CACHE) > TINT_CACHE_LIMIT:
            _TINT_CACHE.clear()      # 무지개는 색이 계속 바뀌므로 한도를 두고 통째로 비운다
        _TINT_CACHE[key] = result
        return result

    @staticmethod
    def _paint_ship(painter, center, facing_index: int, size: float, color=None):
        """배 한 대를 그린다 - 그림 파일이 있으면 그걸, 없으면 직접 그린 배를.

        방향별 프레임이 있는 그림은 **회전시키지 않는다.** 아이소메트릭 그림을 돌리면
        각도가 어긋나 보여서, 실제 게임처럼 방향에 맞는 프레임을 고른다
        (혼자 날 때와 같은 규칙 - gui/ship/sprite.py).
        계산의 32방향과 그림의 32프레임이 같은 기준(0=북, 시계방향)이라 번호가 그대로 맞는다.
        """
        sprite = _load_sprite()
        painter.save()
        painter.translate(center)
        if sprite is not None:
            if sprite.directional:
                facing_deg = facing_index * sim.TURN_STEP_DEG
                pixmap = sprite.pick(facing_deg)
                mask = sprite.team_mask(facing_deg)
            else:
                painter.rotate(facing_index * sim.TURN_STEP_DEG)
                pixmap = sprite.frames[0]
                mask = sprite.team_frames[0] if sprite.team_frames else None
            if color is not None:
                pixmap = BattleArena._team_colored(pixmap, mask, color)
            scaled = pixmap.scaled(
                int(size), int(size), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(int(-scaled.width() / 2), int(-scaled.height() / 2), scaled)
        else:
            painter.rotate(facing_index * sim.TURN_STEP_DEG)
            _draw_ship(painter, size)
        painter.restore()

    def _draw_ship_at(self, painter, box, ship, scale):
        center = self._to_screen(box, ship.x, ship.y)
        if not ship.alive:
            return                        # 격추된 배는 안 보인다(다시 살아나면 보인다)
        size = SHIP_DRAW_PX * scale
        # **배 자체를 그 사람 색으로 물들인다.** 예전에는 색 고리를 둘렀는데, 배는
        # 그대로 흰색이라 "내 색"이라는 느낌이 안 나고 고리만 둥둥 떠 보였다
        self._paint_ship(painter, center, ship.facing, size,
                         ship_color(self._colors.get(ship.slot, 0), self._tick))

        bar = QRectF(center.x() - HP_BAR_WIDTH * scale / 2,
                     center.y() + size * 0.40 + HP_BAR_GAP * scale,
                     HP_BAR_WIDTH * scale, HP_BAR_HEIGHT * scale)
        draw_hp_bar(painter, bar, ship.hp / sim.MAX_HP, sim.HP_SEGMENTS)

        # 기를 모으는 중이면 배 위에 얼마나 찼는지 보여준다 - 안 보이면 언제 떼야 할지 모른다
        if ship.charge > 0:
            ratio = min(1.0, ship.charge / sim.CHARGE_FULL_TICKS)
            gauge = QRectF(center.x() - HP_BAR_WIDTH * scale / 2,
                           center.y() - size * 0.40 - (HP_BAR_GAP + HP_BAR_HEIGHT) * scale,
                           HP_BAR_WIDTH * scale * ratio, HP_BAR_HEIGHT * scale * 0.7)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 196, 60) if ratio < 1.0 else QColor(255, 250, 200))
            painter.drawRect(gauge)

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
        # 떨어지는 중 - 빙글 돌면서 연기를 낸다.
        # **그림을 돌리는 게 아니라 방향 프레임을 넘겨서** 돈다(아이소메트릭 그림은
        # 돌리면 각도가 어긋난다). 프레임이 없는 그림이면 그때만 실제로 회전한다
        spun = (crash.facing + (CRASH_TICKS - crash.left) * CRASH_SPIN_STEP) % sim.DIRECTIONS
        self._paint_ship(painter, center, spun, SHIP_DRAW_PX * scale,
                         ship_color(crash.color, self._tick))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(90, 90, 100, 120))
        painter.drawEllipse(center, 10 * scale, 10 * scale)


def format_kill_line(shooter: str, victim: str) -> str:
    """격추됐을 때 채팅에 남길 한 줄. 문구를 한 곳에서 정해 둔다."""
    return f"{shooter}님이 {victim}님의 배틀크루저를 격추했습니다."
