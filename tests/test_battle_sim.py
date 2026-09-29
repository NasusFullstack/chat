"""전투 계산이 **누가 돌려도 똑같은가** - 그리고 규칙대로 도는가.

이게 어긋나면 화면마다 다른 게 보인다. 조작만 주고받고 배와 포탄은 각자 계산하는
구조라서, 계산이 갈리는 순간 "내 화면에선 맞혔는데 쟤는 안 맞았다"가 된다.

그래서 가장 먼저 확인하는 것이 결정론이다:
- 같은 입력을 두 번 돌리면 모든 값이 완전히 같은가
- 조작이 **도착하는 순서**가 뒤섞여도 같은가(사람마다 순서가 다르게 도착한다)
- 부동소수가 끼어들 자리가 있는가
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
_sys.path.insert(0, _REPO)

import io  # noqa: E402
import re  # noqa: E402

import battle_protocol as bp  # noqa: E402
import battle_sim as sim  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def run(script, slots=(0, 1)):
    """script: [ {자리: 키}, ... ] 틱마다 누른 키. 끝난 판과 일어난 일들을 돌려준다."""
    battle = sim.Battle(slots)
    events = []
    for keys in script:
        events.extend(battle.advance(keys))
    return battle, events


# ---------- 1) 결정론 ----------
SCRIPT = []
for i in range(400):
    a = 0
    b = 0
    if i % 7 < 3:
        a |= bp.KEY_RIGHT
    if i % 5 < 2:
        a |= bp.KEY_DOWN
    if i % 11 == 0:
        a |= bp.KEY_FIRE
    if i % 6 < 4:
        b |= bp.KEY_LEFT
    if i % 9 < 3:
        b |= bp.KEY_UP
    if i % 13 == 0:
        b |= bp.KEY_FIRE
    SCRIPT.append({0: a, 1: b})

first, first_events = run(SCRIPT)
second, second_events = run(SCRIPT)
check("같은 입력을 두 번 돌리면 상태가 완전히 같다",
      first.snapshot() == second.snapshot(),
      (first.snapshot()["ships"][0], second.snapshot()["ships"][0]))
check(f"일어난 일도 같다({len(first_events)}건)", first_events == second_events,
      (first_events[:3], second_events[:3]))

# 조작이 도착하는 순서가 달라도 같아야 한다(딕셔너리 순서를 뒤집어 넣는다)
reversed_order = [dict(reversed(list(keys.items()))) for keys in SCRIPT]
third, third_events = run(reversed_order)
check("조작이 도착한 순서가 달라도 결과가 같다", first.snapshot() == third.snapshot(),
      (first.snapshot()["ships"], third.snapshot()["ships"]))
check("일어난 일의 순서도 같다", first_events == third_events)

# 값이 전부 정수여야 한다 - 하나라도 실수면 플랫폼에 따라 갈릴 수 있다
numbers = []
for row in first.snapshot()["ships"]:
    numbers.extend(row)
for row in first.snapshot()["shells"]:
    numbers.extend(row)
check(f"좌표·속도가 전부 정수다({len(numbers)}개 확인)",
      all(isinstance(v, int) for v in numbers),
      [v for v in numbers if not isinstance(v, int)][:5])

# 계산 도중에 흔들릴 수 있는 함수를 쓰지 않았는가(표를 만들 때 한 번만 허용)
source = io.open(_os.path.join(_REPO, "battle_sim.py"), encoding="utf-8").read()
body = source.split("DIRECTION_TABLE = _build_direction_table()", 1)[1]
for risky in ("math.sin", "math.cos", "math.atan2", "math.hypot", "math.sqrt", "math.degrees"):
    check(f"표를 만든 뒤에는 {risky} 를 안 쓴다", risky not in body, risky)
check("정확한 정수 제곱근(math.isqrt)을 쓴다", "math.isqrt" in body)

# ---------- 2) 화면과 같은 느낌인가(상수 대조) ----------
overlay = io.open(_os.path.join(_REPO, "gui/battlecruiser.py"), encoding="utf-8").read()


def number_in(text, name):
    match = re.search(rf"^{name}\s*=\s*([0-9.]+)", text, re.M)
    return float(match.group(1)) if match else None


for name, ours, theirs in (
    ("가속", sim.ACCEL / sim.SCALE, number_in(overlay, "ACCEL")),
    ("최고속", sim.MAX_SPEED / sim.SCALE, number_in(overlay, "MAX_SPEED")),
    ("관성", sim.DRAG_NUM / sim.DRAG_DEN, number_in(overlay, "DRAG")),
    ("틱", sim.TICK_MS, number_in(overlay, "TICK_MS")),
    ("방향 단위", sim.TURN_STEP_DEG, number_in(overlay, "TURN_STEP_DEG")),
):
    check(f"{name}이 화면 쪽과 같다(계산 {ours} / 화면 {theirs})",
          theirs is not None and abs(ours - theirs) < 0.02, (ours, theirs))

# ---------- 3) 움직임 ----------
battle = sim.Battle((0,))
ship = battle.ships[0]
start_x = ship.x
for _ in range(60):
    battle.advance({0: bp.KEY_RIGHT})
check(f"오른쪽을 누르면 오른쪽으로 간다({(ship.x - start_x) / sim.SCALE:.1f}px)",
      ship.x > start_x, (start_x, ship.x))
check(f"최고속을 안 넘는다({(ship.vx / sim.SCALE):.2f} <= 3.0)",
      ship.vx <= sim.MAX_SPEED + 1, ship.vx)

moving_x = ship.x
for _ in range(200):
    battle.advance({0: 0})
check("키를 놓으면 미끄러지다 선다", ship.vx == 0 and ship.x > moving_x, (ship.vx, ship.x))

# 대각선이 더 빠르면 안 된다
straight = sim.Battle((0,), 4000, 4000)
diagonal = sim.Battle((0,), 4000, 4000)
for _ in range(120):
    straight.advance({0: bp.KEY_RIGHT})
    diagonal.advance({0: bp.KEY_RIGHT | bp.KEY_DOWN})
straight_speed = math_speed = None
s = straight.ships[0]
d = diagonal.ships[0]
straight_speed = (s.vx ** 2 + s.vy ** 2) ** 0.5
diagonal_speed = (d.vx ** 2 + d.vy ** 2) ** 0.5
check(f"대각선이 더 빠르지 않다(직선 {straight_speed / sim.SCALE:.2f} / 대각 "
      f"{diagonal_speed / sim.SCALE:.2f})",
      diagonal_speed <= straight_speed + sim.SCALE * 0.05,
      (straight_speed, diagonal_speed))

# 전투장 밖으로 안 나간다
boxed = sim.Battle((0,), 300, 200)
for _ in range(600):
    boxed.advance({0: bp.KEY_RIGHT | bp.KEY_DOWN})
edge = boxed.ships[0]
check(f"전투장 밖으로 안 나간다({edge.px:.0f},{edge.py:.0f} / 300x200)",
      0 <= edge.x <= boxed.width and 0 <= edge.y <= boxed.height, (edge.x, edge.y))

# ---------- 4) 야마토포 ----------
# 포탄이 금방 전투장 밖으로 나가버리면 세는 게 헷갈리므로 넉넉한 판에서 잰다
firing = sim.Battle((0,), 4000, 4000)
firing.advance({0: bp.KEY_FIRE})
check(f"쏘면 포탄이 생긴다({len(firing.shells)}발)", len(firing.shells) == 1, firing.shells)
check(f"쏘면 재장전이 걸린다({firing.ships[0].reload_left}틱)",
      firing.ships[0].reload_left > 0, firing.ships[0].reload_left)
for _ in range(10):
    firing.advance({0: bp.KEY_FIRE})
check(f"누르고 있어도 연사가 안 된다({len(firing.shells)}발)", len(firing.shells) == 1,
      len(firing.shells))
for _ in range(sim.RELOAD_TICKS + 2):
    firing.advance({0: 0})
check(f"재장전이 끝난다({firing.ships[0].reload_left}틱)",
      firing.ships[0].reload_left == 0, firing.ships[0].reload_left)
firing.advance({0: bp.KEY_FIRE})
check(f"재장전되면 또 쏜다({len(firing.shells)}발)", len(firing.shells) >= 2, len(firing.shells))

# 포탄은 언젠가 사라진다(영원히 쌓이면 안 된다)
lonely = sim.Battle((0,), 4000, 4000)
lonely.advance({0: bp.KEY_FIRE})
for _ in range(sim.SHELL_LIFE_TICKS + 5):
    lonely.advance({0: 0})
check(f"포탄은 수명이 끝나면 사라진다({len(lonely.shells)}발 남음)", not lonely.shells,
      len(lonely.shells))

# ---------- 5) 맞음 판정 ----------
duel = sim.Battle((0, 1))
duel.ships[0].x, duel.ships[0].y = 100 * sim.SCALE, 300 * sim.SCALE
duel.ships[1].x, duel.ships[1].y = 400 * sim.SCALE, 300 * sim.SCALE
duel.ships[0].facing = 8          # 오른쪽(32방향 중 1/4)
duel.ships[0].vx = duel.ships[0].vy = 0
events = []
events += duel.advance({0: bp.KEY_FIRE})
for _ in range(80):
    events += duel.advance({0: 0, 1: 0})
hits = [e for e in events if e["t"] == "hit"]
check(f"쏜 포탄이 상대에게 맞는다({hits})", hits and hits[0]["slot"] == 1 and hits[0]["by"] == 0,
      events)
check(f"맞으면 체력이 깎인다({duel.ships[1].hp}/{sim.MAX_HP})",
      duel.ships[1].hp == sim.MAX_HP - sim.SHELL_DAMAGE, duel.ships[1].hp)

# 자기 포탄엔 안 맞는다
selfshot = sim.Battle((0,))
selfshot.ships[0].vx = selfshot.ships[0].vy = 0
got = selfshot.advance({0: bp.KEY_FIRE})
for _ in range(120):
    got += selfshot.advance({0: 0})
check(f"자기 포탄에는 안 맞는다({got})", not got, got)
check("자기 체력도 그대로", selfshot.ships[0].hp == sim.MAX_HP)

# ---------- 6) 격추 ----------
kill = sim.Battle((0, 1))
kill.ships[1].hp = sim.SHELL_DAMAGE       # 한 방이면 죽는다
kill.ships[0].x, kill.ships[0].y = 100 * sim.SCALE, 300 * sim.SCALE
kill.ships[1].x, kill.ships[1].y = 400 * sim.SCALE, 300 * sim.SCALE
kill.ships[0].facing = 8
kill.ships[0].vx = kill.ships[0].vy = 0
kill_events = kill.advance({0: bp.KEY_FIRE})
for _ in range(80):
    kill_events += kill.advance({0: 0, 1: 0})
dead = [e for e in kill_events if e["t"] == "dead"]
check(f"체력이 0이 되면 격추({dead})", dead and dead[0] == {"t": "dead", "slot": 1, "by": 0},
      kill_events)
check("체력이 음수로 안 간다", kill.ships[1].hp == 0, kill.ships[1].hp)
check("격추 수가 올라간다", kill.ships[0].kills == 1 and kill.ships[1].deaths == 1,
      (kill.ships[0].kills, kill.ships[1].deaths))
check("격추된 배는 살아있지 않다", kill.ships[1].alive is False)

# 격추된 배는 더 안 맞는다
before = len([e for e in kill_events if e["t"] == "hit"])
extra = []
for _ in range(sim.RELOAD_TICKS + 2):
    extra += kill.advance({0: 0, 1: 0})
extra += kill.advance({0: bp.KEY_FIRE})
for _ in range(80):
    extra += kill.advance({0: 0, 1: 0})
check(f"격추된 배는 포탄이 통과한다({extra})", not any(e["slot"] == 1 for e in extra), extra)

# 다시 살아난다
for _ in range(sim.RESPAWN_TICKS + 5):
    kill.advance({0: 0, 1: 0})
check(f"시간이 지나면 다시 살아난다(체력 {kill.ships[1].hp})",
      kill.ships[1].alive and kill.ships[1].hp == sim.MAX_HP, kill.ships[1].hp)

# ---------- 7) 전투 중 이탈 ----------
# 창 크기가 달라도 전투장은 모두에게 같아야 한다 - 안 그러면 배 위치가 갈린다
check(f"전투장 크기가 고정돼 있다({sim.FIELD_WIDTH}x{sim.FIELD_HEIGHT})",
      sim.FIELD_WIDTH > 0 and sim.FIELD_HEIGHT > 0)
default_field = sim.Battle((0, 1))
check("기본값으로 만들면 언제나 같은 크기다",
      (default_field.width, default_field.height)
      == (sim.FIELD_WIDTH * sim.SCALE, sim.FIELD_HEIGHT * sim.SCALE),
      (default_field.width, default_field.height))

leaving = sim.Battle((0, 1, 2))
check("셋으로 시작", len(leaving.ships) == 3)
check("나가면 즉시 빠진다", leaving.remove(1) is True and 1 not in leaving.ships,
      list(leaving.ships))
check("없는 사람을 또 빼도 안 터진다", leaving.remove(1) is False)
leaving.advance({0: bp.KEY_FIRE, 2: bp.KEY_LEFT})
check("나간 뒤에도 판이 계속 돈다", len(leaving.ships) == 2, list(leaving.ships))

# 나간 사람에게는 포탄이 더 이상 안 맞아야 한다(맞으면 화면마다 다르게 보인다)
gone = sim.Battle((0, 1))
gone.ships[0].x, gone.ships[0].y = 100 * sim.SCALE, 300 * sim.SCALE
gone.ships[1].x, gone.ships[1].y = 400 * sim.SCALE, 300 * sim.SCALE
gone.ships[0].facing = 8
gone.ships[0].vx = gone.ships[0].vy = 0
gone_events = gone.advance({0: bp.KEY_FIRE})
gone.remove(1)
for _ in range(80):
    gone_events += gone.advance({0: 0})
check(f"나간 사람에게는 포탄이 안 맞는다({gone_events})", not gone_events, gone_events)

# 떠난 사람이 쏴둔 포탄은 그대로 날아간다
left_shell = sim.Battle((0, 1))
left_shell.ships[1].x, left_shell.ships[1].y = 400 * sim.SCALE, 300 * sim.SCALE
left_shell.ships[0].x, left_shell.ships[0].y = 100 * sim.SCALE, 300 * sim.SCALE
left_shell.ships[1].facing = 24        # 왼쪽
left_shell.ships[1].vx = left_shell.ships[1].vy = 0
left_shell.advance({1: bp.KEY_FIRE})
check("떠나기 전에 쏜 포탄이 있다", len(left_shell.shells) == 1)
left_shell.remove(1)
after_leave = []
for _ in range(80):
    after_leave += left_shell.advance({0: 0})
check(f"떠난 사람이 쏜 포탄도 그대로 맞는다({after_leave})",
      any(e["slot"] == 0 and e["by"] == 1 for e in after_leave), after_leave)

# ---------- 8) 화면이 쓸 값 ----------
check(f"체력바 칸 수가 있다({sim.HP_SEGMENTS}칸)", sim.HP_SEGMENTS > 1)
check(f"정원만큼 배를 만들 수 있다({bp.MAX_PLAYERS}척)",
      len(sim.Battle(range(bp.MAX_PLAYERS)).ships) == bp.MAX_PLAYERS)
corners = {(s.x, s.y) for s in sim.Battle(range(bp.MAX_PLAYERS)).ships.values()}
check(f"시작 자리가 서로 겹치지 않는다({len(corners)}곳)", len(corners) == bp.MAX_PLAYERS,
      corners)

print("=== 검증 결과 (전투 계산) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
