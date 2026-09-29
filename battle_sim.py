"""전투 한 판의 계산 - 순수 모듈(Qt도 소켓도 파일도 안 쓴다).

## 왜 이 파일이 따로 있나
조작(누른 키)만 주고받고 **배와 포탄은 각자 계산한다.** 서버는 넘겨주기만 하므로
60fps로 움직여도 오가는 줄이 몇 개 안 된다. 대신 계산이 조금이라도 갈리면 화면마다
다른 게 보이므로, 이 계산은 **누가 언제 돌려도 똑같아야** 한다.

## 그래서 정수로만 센다
부동소수는 같은 식이라도 플랫폼/라이브러리에 따라 마지막 자리가 달라질 수 있다.
특히 `math.sin/cos/atan2/hypot`은 libm 구현이라 위험하다. 여기서는:

- 좌표와 속도를 **1/256 픽셀 단위 정수**로 센다(`SCALE`)
- 방향은 32방향으로 끊고(`TURN_STEP`), 각 방향의 단위벡터를 **미리 계산한 정수표**로 둔다
  (배틀크루저 화면이 이미 32방향으로 끊어 그리므로 보이는 것도 똑같다)
- 속도 상한은 `math.isqrt`(정확한 정수 제곱근)로 건다

그래서 같은 입력이면 어떤 PC에서도 **완전히 같은 좌표**가 나온다.

## 화면(gui/battlecruiser.py)과 같은 느낌이어야 한다
움직임 상수는 그쪽 값을 정수로 옮긴 것이다. 두 곳이 어긋나면 혼자 날 때와 전투할 때
배가 다르게 움직이므로, `tests/test_battle_sim.py`가 그쪽 소스를 읽어 값을 대조한다.
"""
import math

import battle_protocol as bp

# ---- 정밀도 ----------------------------------------------------------------
SCALE = 256               # 1칸 = 256. 좌표·속도는 전부 이 단위의 정수

# ---- 전투장 크기는 **모두에게 똑같이 고정**한다 -----------------------------
# 채팅창 크기를 그대로 쓰면 창이 다른 사람끼리 전투장이 달라져 배 위치가 갈린다.
# 그렇다고 창을 고정하면 답답하고, 애초에 두 사람 창 크기가 다르면 소용도 없다.
# 그래서 좌표계를 고정해두고 **그리는 쪽에서 자기 화면에 맞춰 비율대로 늘려 그린다**
# (가로세로 비가 다르면 남는 쪽에 여백을 둔다 - 늘려 찌그러뜨리면 맞음 판정과 눈이 어긋난다).
FIELD_WIDTH = 1200
FIELD_HEIGHT = 800

# **약 30fps.** 60fps로 돌릴 이유가 없다 - 눈에 띄는 차이가 없는데 그리는 비용만 두 배다.
# 아래 움직임 상수는 전부 '틱당' 값이라, 틱 길이를 바꾸면 같이 환산해야 한다
# (안 하면 배가 절반 속도로 기어간다). 초당 기준으로는 화면 쪽과 똑같다 - 검사가 대조한다
TICK_MS = 33

# ---- 움직임(gui/battlecruiser.py 와 같은 느낌) -------------------------------
ACCEL = 111               # 초당 기준으로 화면 쪽(0.10 px/16ms^2)과 같은 가속
MAX_SPEED = 1600          # 초당 약 187px - 화면 쪽(3.0 px/16ms)과 같은 빠르기
DRAG_NUM, DRAG_DEN = 9185, 10000   # 0.96^(33/16) - 화면 쪽과 같은 미끄러짐
STOP_BELOW = 10           # 이보다 느리면 선다(화면 쪽과 같은 취지)

# 대각선이 더 빨라지지 않게 나눌 값. sqrt(2) = 1.41421356... 을 1/256 단위로
DIAG = 362                # round(1.41421356 * 256)

# ---- 방향 -------------------------------------------------------------------
TURN_STEP_DEG = 11.25     # 32방향 (화면과 같음)
DIRECTIONS = 32

def _build_direction_table():
    """32방향 단위벡터를 1/256 단위 정수로 미리 계산한다.

    **여기서만 sin/cos를 쓴다.** 모듈을 읽어 들일 때 한 번 계산해 표로 굳히므로,
    그 뒤의 계산에는 부동소수가 끼어들지 않는다. 표 자체는 상수이므로 어느 PC에서나
    같은 값이 나온다(파이썬의 sin/cos가 이 정도 값에서 흔들릴 여지는 없고, 설령
    마지막 자리가 달라도 round 후 정수라 같다).
    """
    table = []
    for step in range(DIRECTIONS):
        radians = math.radians(step * TURN_STEP_DEG)
        # 화면과 같은 기준: 위쪽(-y)이 0도, 시계방향으로 증가
        table.append((round(math.sin(radians) * SCALE), round(-math.cos(radians) * SCALE)))
    return tuple(table)

DIRECTION_TABLE = _build_direction_table()

# ---- 야마토포 ---------------------------------------------------------------
# **기를 모아 쏜다.** 스페이스를 누르고 있으면 차고, 떼면 나간다.
# 바로 떼면 약하고 느리게, 꽉 채우면 세고 빠르게 - 실제 야마토포처럼 한 방을 노리는 무기.
# (연발로 두면 그냥 총이 되고, 피하는 재미도 없다)
CHARGE_FULL_TICKS = 30        # 약 1초면 꽉 찬다
CHARGE_MIN = 6                # 이보다 짧게 누르면 발사 자체가 안 된다(오발 방지)

SHELL_SPEED_MIN = 2200        # 바로 떼면 느리다
SHELL_SPEED_MAX = 6600        # 꽉 채우면 세 배 빠르다
SHELL_SPEED = SHELL_SPEED_MAX  # 옛 이름(검사/AI가 거리를 어림할 때 쓴다)
SHELL_LIFE_TICKS = 43         # 약 1.5초. 화면을 가로지르고 사라진다
RELOAD_TICKS = 12             # 쏜 뒤 다시 모으기 시작할 때까지(모으는 시간이 따로 있으므로 짧게)
SHELL_RADIUS = 6 * SCALE      # 맞음 판정 반지름(포탄)
SHIP_RADIUS = 26 * SCALE      # 맞음 판정 반지름(배). 그림(96px)보다 작게 - 스쳐도 맞는 건 억울하다

# ---- 체력 -------------------------------------------------------------------
MAX_HP = 500              # 스타1 배틀크루저와 같은 숫자(보는 재미)
HP_SEGMENTS = 10          # 체력바를 몇 칸으로 나눠 그릴지(화면이 이 값을 쓴다)
SHELL_DAMAGE_MIN = 70     # 바로 떼면 약하다
SHELL_DAMAGE_MAX = 260    # 꽉 채우면 스타1 야마토포와 같은 값 - **두 방이면 격추**
SHELL_DAMAGE = SHELL_DAMAGE_MAX   # 옛 이름(검사가 최대치를 볼 때 쓴다)
# 열 방을 맞아야 죽게 뒀더니 한 판이 1분을 넘어가 지루했다(실측: AI끼리 30초에 10대,
# 격추 0번). 실제 값으로 맞추니 주고받는 맛이 산다

# 배가 다시 살아나는 데 걸리는 시간. 0이면 한 번 죽고 끝이라 금방 심심해진다
RESPAWN_TICKS = 86            # 약 3초


class Ship:
    """배 한 척. 좌표·속도는 전부 1/256 픽셀 단위 정수."""

    __slots__ = ("slot", "x", "y", "vx", "vy", "facing", "hp", "reload_left",
                 "respawn_left", "kills", "deaths", "charge")

    def __init__(self, slot: int, x: int, y: int, facing: int = 0):
        self.slot = slot
        self.x = x
        self.y = y
        self.vx = 0
        self.vy = 0
        self.facing = facing          # DIRECTION_TABLE 의 번호
        self.hp = MAX_HP
        self.reload_left = 0
        self.charge = 0            # 기를 모은 정도(스페이스를 누르고 있는 틱 수)
        self.respawn_left = 0
        self.kills = 0
        self.deaths = 0

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def px(self) -> float:
        """화면에 그릴 x(픽셀). 그리는 쪽에서만 쓴다 - 계산에는 절대 쓰지 말 것."""
        return self.x / SCALE

    @property
    def py(self) -> float:
        return self.y / SCALE


class Shell:
    """야마토포 포탄 하나."""

    __slots__ = ("owner", "x", "y", "vx", "vy", "life", "power")

    def __init__(self, owner: int, x: int, y: int, vx: int, vy: int):
        self.owner = owner
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = SHELL_LIFE_TICKS
        self.power = 100           # 얼마나 모아서 쏜 것인가(0~100)

    @property
    def px(self) -> float:
        return self.x / SCALE

    @property
    def py(self) -> float:
        return self.y / SCALE


def _facing_from(dx: int, dy: int, current: int) -> int:
    """움직이는 방향에 가장 가까운 32방향 번호. 안 움직이면 보던 쪽 그대로.

    표에서 **가장 가까운 것을 고르는** 방식이라 atan2가 필요 없다(정수 비교만 한다).
    """
    if dx == 0 and dy == 0:
        return current
    best, best_score = current, None
    for index, (ux, uy) in enumerate(DIRECTION_TABLE):
        # 내적이 클수록 같은 쪽. 정수라 비교가 정확하다
        score = dx * ux + dy * uy
        if best_score is None or score > best_score:
            best, best_score = index, score
    return best


class Battle:
    """한 판. `advance()`를 틱마다 부르면 그때 일어난 일을 돌려준다.

    **여기에는 화면이 없다.** 폭과 높이는 픽셀로 받아 두고(전투장 크기), 그 안에서만
    배가 움직인다. 모두가 같은 크기를 써야 결과가 같으므로 판을 열 때 정해 고정한다.
    """

    def __init__(self, slots, width: int = FIELD_WIDTH, height: int = FIELD_HEIGHT,
                 seed_facing: int = 0, judged=None):
        # 크기를 인자로 받긴 하지만 **평소에는 기본값을 그대로 쓴다.** 다르게 주면
        # 그 판에 있는 모두가 같은 값을 써야 한다(안 그러면 배 위치가 갈린다)
        self.width = int(width) * SCALE
        self.height = int(height) * SCALE
        self.tick = 0
        self.ships: dict[int, Ship] = {}
        self.shells: list[Shell] = []
        for slot in sorted(slots):
            x, y = self._start_position(slot)
            self.ships[slot] = Ship(slot, x, y, seed_facing)

        # **내가 맞았는지 판정할 배들.** 이걸 안 나누면 같은 피격이 두 번 깎인다 -
        # 내 화면에서 한 번(로컬 계산), 그 사람이 "나 맞았다"고 알려와서 또 한 번.
        # 실제로 "남은 한 방에 죽고 나는 안 죽는" 증상이 났다(2026-09-29 신고).
        # 그래서 자기 배(와 자기 화면에서만 도는 연습 상대)만 판정하고, 남의 배 체력은
        # 그 사람이 보낸 것만 따른다. 아무 것도 안 주면 전부 판정한다(혼자 시험할 때)
        self.judged = set(self.ships) if judged is None else set(judged)

    def _start_position(self, slot: int):
        """자리 번호로 정해지는 시작 자리 - 모두에게 같아야 하므로 계산으로 정한다.

        12대가 붙을 수 있으므로 귀퉁이 네 곳으로는 모자란다. 전투장 한가운데를 중심으로
        **원을 그리며** 늘어놓는다. 미리 계산한 정수표를 쓰므로 어느 PC에서나 같은 자리다
        (sin/cos를 여기서 부르면 계산에 부동소수가 끼어든다 - 위 설명 참고).
        """
        step = DIRECTIONS // bp.MAX_PLAYERS          # 12대면 32방향을 2~3칸씩 건너뛴다
        ux, uy = DIRECTION_TABLE[(slot * step) % DIRECTIONS]
        radius_x = self.width * 7 // 20              # 벽에 딱 붙지는 않게
        radius_y = self.height * 7 // 20
        return (self.width // 2 + ux * radius_x // SCALE,
                self.height // 2 + uy * radius_y // SCALE)

    # ------------------------------------------------------------------
    def advance(self, keys_by_slot: dict) -> list[dict]:
        """한 틱 진행한다. `keys_by_slot`은 {자리번호: 누른 키 비트}.

        돌려주는 것: 이번 틱에 일어난 일들
          {"t": "hit",  "slot": 맞은 자리, "by": 쏜 자리}
          {"t": "dead", "slot": 격추된 자리, "by": 쏜 자리}

        **자리 번호 순서대로 처리한다.** 딕셔너리가 들어오는 순서가 달라도 결과가
        같아야 하기 때문이다(조작이 도착하는 순서는 사람마다 다르다).
        """
        self.tick += 1
        events = []

        for slot in sorted(self.ships):
            keys = int(keys_by_slot.get(slot, 0)) & bp.KEY_MASK
            self._move(self.ships[slot], keys)

        for slot in sorted(self.ships):
            keys = int(keys_by_slot.get(slot, 0)) & bp.KEY_MASK
            self._maybe_fire(self.ships[slot], keys)

        events.extend(self._move_shells())
        return events

    # ------------------------------------------------------------------
    def _move(self, ship: Ship, keys: int):
        if not ship.alive:
            if ship.respawn_left > 0:
                ship.respawn_left -= 1
                if ship.respawn_left == 0:
                    self._revive(ship)
            return

        if ship.reload_left > 0:
            ship.reload_left -= 1

        dx = (bp.KEY_RIGHT & keys and 1 or 0) - (bp.KEY_LEFT & keys and 1 or 0)
        dy = (bp.KEY_DOWN & keys and 1 or 0) - (bp.KEY_UP & keys and 1 or 0)

        if dx or dy:
            if dx and dy:
                # 대각선이 더 빨라지지 않게 나눈다(화면 쪽의 정규화와 같은 취지)
                ship.vx += ACCEL * dx * SCALE // DIAG
                ship.vy += ACCEL * dy * SCALE // DIAG
            else:
                ship.vx += ACCEL * dx
                ship.vy += ACCEL * dy
            speed = math.isqrt(ship.vx * ship.vx + ship.vy * ship.vy)
            if speed > MAX_SPEED:
                ship.vx = ship.vx * MAX_SPEED // speed
                ship.vy = ship.vy * MAX_SPEED // speed
            ship.facing = _facing_from(ship.vx, ship.vy, ship.facing)
        else:
            ship.vx = ship.vx * DRAG_NUM // DRAG_DEN
            ship.vy = ship.vy * DRAG_NUM // DRAG_DEN
            if -STOP_BELOW < ship.vx < STOP_BELOW:
                ship.vx = 0
            if -STOP_BELOW < ship.vy < STOP_BELOW:
                ship.vy = 0

        ship.x += ship.vx
        ship.y += ship.vy
        # 전투장 밖으로는 못 나간다. 벽에 닿으면 그쪽 속도를 죽인다(튕기면 조종이 어렵다)
        if ship.x < 0:
            ship.x, ship.vx = 0, 0
        elif ship.x > self.width:
            ship.x, ship.vx = self.width, 0
        if ship.y < 0:
            ship.y, ship.vy = 0, 0
        elif ship.y > self.height:
            ship.y, ship.vy = self.height, 0

    def _maybe_fire(self, ship: Ship, keys: int):
        """기를 모으고, 손을 떼면 쏜다.

        누르고 있는 동안 `charge`가 차고, 뗀 순간 그만큼의 힘으로 나간다.
        꽉 채우면 세고 빠르게, 바로 떼면 약하고 느리게. 아주 짧게 눌린 건 오발로 보고
        안 쏜다(움직이려다 스페이스가 스친 경우).
        """
        if not ship.alive:
            ship.charge = 0
            return
        holding = bool(keys & bp.KEY_FIRE)
        if holding:
            if ship.reload_left == 0 and ship.charge < CHARGE_FULL_TICKS:
                ship.charge += 1
            return
        if ship.charge == 0:
            return
        charge, ship.charge = ship.charge, 0
        if charge < CHARGE_MIN:
            return                      # 스친 정도 - 안 쏜다

        # 0~100으로 환산해서 힘을 정한다(정수라 모두에게 같은 값이 나온다)
        power = min(100, charge * 100 // CHARGE_FULL_TICKS)
        speed = SHELL_SPEED_MIN + (SHELL_SPEED_MAX - SHELL_SPEED_MIN) * power // 100
        ux, uy = DIRECTION_TABLE[ship.facing]
        shell = Shell(
            ship.slot,
            ship.x + ux * SHIP_RADIUS // SCALE // SCALE * SCALE,
            ship.y + uy * SHIP_RADIUS // SCALE // SCALE * SCALE,
            ux * speed // SCALE,
            uy * speed // SCALE,
        )
        shell.power = power
        self.shells.append(shell)
        ship.reload_left = RELOAD_TICKS

    def _move_shells(self) -> list[dict]:
        events = []
        alive_shells = []
        hit_radius = SHIP_RADIUS + SHELL_RADIUS
        for shell in self.shells:
            shell.x += shell.vx
            shell.y += shell.vy
            shell.life -= 1
            if shell.life <= 0 or not (0 <= shell.x <= self.width and 0 <= shell.y <= self.height):
                continue                      # 수명이 다했거나 전투장 밖 - 사라진다

            struck = None
            for slot in sorted(self.ships):   # 자리 번호 순서로 봐야 결과가 같다
                ship = self.ships[slot]
                if slot == shell.owner or not ship.alive:
                    continue                  # 자기 포탄엔 안 맞고, 격추된 배는 통과한다
                dx = ship.x - shell.x
                dy = ship.y - shell.y
                if dx * dx + dy * dy <= hit_radius * hit_radius:
                    struck = ship
                    break
            if struck is None:
                alive_shells.append(shell)
                continue

            # 포탄은 어느 배에 닿든 여기서 사라진다(그래야 관통하는 것처럼 안 보인다).
            # 다만 **체력을 깎는 건 내가 판정하는 배뿐이다** - 남의 배는 그 사람이
            # "나 맞았다"고 알려줄 때만 깎인다. 둘 다 하면 두 배로 닳는다
            if struck.slot not in self.judged:
                continue

            damage = SHELL_DAMAGE_MIN + (SHELL_DAMAGE_MAX - SHELL_DAMAGE_MIN) * shell.power // 100
            struck.hp -= damage
            if struck.hp > 0:
                events.append({"t": "hit", "slot": struck.slot, "by": shell.owner})
            else:
                struck.hp = 0                 # 음수로 내려가지 않게
                struck.deaths += 1
                struck.respawn_left = RESPAWN_TICKS
                shooter = self.ships.get(shell.owner)
                if shooter is not None:
                    shooter.kills += 1
                events.append({"t": "dead", "slot": struck.slot, "by": shell.owner})
        self.shells = alive_shells
        return events

    def remove(self, slot: int) -> bool:
        """전투에서 빠진다(직접 그만뒀거나 연결이 끊겼거나).

        **바로 없앤다.** 추락해서 폭발하는 연출은 화면이 따로 그린다 - 나간 순간이
        사람마다 몇 ms씩 다른데, 그 동안 배가 남아 있으면 누구 화면에선 포탄이 맞고
        누구 화면에선 안 맞는다. 계산에서 즉시 빼면 그럴 일이 없다.

        떠난 사람이 쏴둔 포탄은 **그대로 날아간다** - 이미 발사된 것이라 없애면
        오히려 화면마다 다르게 보인다.
        """
        if slot not in self.ships:
            return False
        del self.ships[slot]
        return True

    def _revive(self, ship: Ship):
        ship.hp = MAX_HP
        ship.vx = ship.vy = 0
        ship.x, ship.y = self._start_position(ship.slot)

    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """지금 상태를 견줘보기 좋은 모양으로. 두 판이 같은지 확인할 때 쓴다."""
        return {
            "tick": self.tick,
            "ships": [(s.slot, s.x, s.y, s.vx, s.vy, s.facing, s.hp, s.reload_left,
                       s.respawn_left, s.kills, s.deaths)
                      for s in (self.ships[k] for k in sorted(self.ships))],
            "shells": [(s.owner, s.x, s.y, s.vx, s.vy, s.life) for s in self.shells],
        }
