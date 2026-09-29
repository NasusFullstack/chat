"""연습 상대(AI)가 누를 키를 정한다 - 순수 모듈(Qt도 소켓도 안 쓴다).

## 왜 '나만 보이는' 연습 상대인가
규약은 **남의 자리로는 조작을 보낼 수 없게** 막혀 있다(`battle_protocol` 5번 규칙).
그게 "남의 배를 대신 움직일 수 없다"는 보안의 핵심이라, AI를 남들 화면에도 띄우려면
그 막음을 풀어야 한다. 혼자 있을 때 시험해 보는 것이 목적이므로 **자기 화면에서만**
도는 연습 상대로 둔다. 방에 사람이 들어오면 사람만 서로 보인다.

## 어떻게 움직이나
가장 가까운 상대를 쫓되 너무 붙지는 않는다(붙으면 서로 스쳐 지나가기만 한다).
조준이 대충 맞고 재장전이 끝났으면 쏜다. 자리 번호마다 조금씩 다르게 돌아서
여럿을 넣어도 똑같이 움직이지 않는다.

계산은 전부 정수다 - 전투 계산과 같은 단위(1/256칸)를 쓰므로 여기서 실수를 섞으면
그 값이 전투로 흘러든다.
"""
from math import isqrt as _isqrt

import battle_protocol as bp
import battle_sim as sim

# 이 거리보다 가까우면 물러난다(계속 붙어 있으면 서로 스쳐 지나가기만 한다)
TOO_CLOSE = 180 * sim.SCALE
# 이 거리보다 멀면 다가간다
TOO_FAR = 420 * sim.SCALE
# 조준이 이 정도 맞으면 쏜다(1.0이 정확히 정면). 너무 빡빡하면 영영 안 쏜다
AIM_TOLERANCE = 0.74
# 옆으로 도는 주기 - 직선으로만 오면 너무 쉽게 맞는다
STRAFE_PERIOD = 46
# 예측 조준을 이 틱 이상으로는 안 한다 - 멀수록 상대가 방향을 바꿔 오히려 빗나간다
LEAD_LIMIT_TICKS = 22


def _nearest_enemy(battle, slot):
    """가장 가까운, 살아 있는 상대. 없으면 None."""
    me = battle.ships.get(slot)
    if me is None or not me.alive:
        return None
    best, best_distance = None, None
    for other_slot in sorted(battle.ships):     # 자리 번호 순서로 봐야 항상 같은 답
        if other_slot == slot:
            continue
        other = battle.ships[other_slot]
        if not other.alive:
            continue
        dx = other.x - me.x
        dy = other.y - me.y
        distance = dx * dx + dy * dy
        if best_distance is None or distance < best_distance:
            best, best_distance = other, distance
    return best


def decide(battle, slot: int, tick: int) -> int:
    """이 틱에 AI가 누를 키(비트 묶음)."""
    me = battle.ships.get(slot)
    if me is None or not me.alive:
        return 0
    target = _nearest_enemy(battle, slot)
    if target is None:
        return 0

    # **상대가 갈 자리를 쏜다.** 지금 자리를 겨누면 포탄이 도착할 때쯤 상대는 이미
    # 비켜 있다(실측: 예측 없이는 30초에 두 대밖에 못 맞혔다).
    # 포탄이 닿는 데 걸리는 틱 ≈ 거리 / 포탄 속도
    raw_dx = target.x - me.x
    raw_dy = target.y - me.y
    rough = _isqrt(raw_dx * raw_dx + raw_dy * raw_dy)
    travel = rough // max(1, sim.SHELL_SPEED)
    travel = min(travel, LEAD_LIMIT_TICKS)      # 너무 멀면 예측이 오히려 빗나간다
    dx = target.x + target.vx * travel - me.x
    dy = target.y + target.vy * travel - me.y
    distance_squared = dx * dx + dy * dy

    keys = 0
    # **배가 향하는 쪽은 움직이는 쪽이다.** 그래서 옆으로만 돌면 코가 상대를 안 봐서
    # 영영 못 쏜다(처음 만들었을 때 30초에 5대만 맞히고 격추가 한 번도 안 났다).
    # 그래서 리듬을 준다 - 장전이 끝나면 상대 쪽으로 붙어 조준하고, 쏘고 나면
    # 재장전하는 동안 옆으로 돌아 피한다
    ready_to_fire = me.reload_left == 0
    if distance_squared < TOO_CLOSE * TOO_CLOSE:
        move_x, move_y = -dx, -dy
    elif distance_squared > TOO_FAR * TOO_FAR or ready_to_fire:
        move_x, move_y = dx, dy
    else:
        # 상대를 향한 방향의 직각으로 돈다. 자리 번호마다 도는 시점을 어긋나게 해서
        # 여럿이 똑같이 움직이지 않게 한다
        turn = ((tick + slot * STRAFE_PERIOD // 3) // STRAFE_PERIOD) % 2
        move_x, move_y = (-dy, dx) if turn else (dy, -dx)

    # 방향을 키로 옮긴다. 한쪽이 확실히 클 때만 그 축을 눌러 지그재그를 줄인다
    threshold = max(abs(move_x), abs(move_y)) // 3
    if move_x > threshold:
        keys |= bp.KEY_RIGHT
    elif move_x < -threshold:
        keys |= bp.KEY_LEFT
    if move_y > threshold:
        keys |= bp.KEY_DOWN
    elif move_y < -threshold:
        keys |= bp.KEY_UP

    # 조준: 지금 향한 쪽과 상대 쪽이 얼추 같으면 쏜다
    if ready_to_fire and distance_squared <= (TOO_FAR * 2) ** 2:
        ux, uy = sim.DIRECTION_TABLE[me.facing]
        # 내적(정수). 길이로 나누는 대신 양변을 제곱해 비교하면 실수가 안 끼어든다
        dot = dx * ux + dy * uy
        if dot > 0:
            need = int(AIM_TOLERANCE * AIM_TOLERANCE * 10000)
            got = (dot * dot * 10000) // max(1, distance_squared * sim.SCALE * sim.SCALE)
            if got >= need:
                keys |= bp.KEY_FIRE
    return keys
