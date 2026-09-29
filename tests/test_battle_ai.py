"""연습 상대(AI)가 실제로 싸우는가 - 혼자 있을 때 시험해 보려고 넣은 것이다.

가만히 있거나, 벽에 처박히거나, 영영 안 쏘면 연습이 안 된다. 그래서 '움직이는가'가
아니라 **'실제로 맞히는가'** 까지 본다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
_sys.path.insert(0, _REPO)

import battle_ai  # noqa: E402
import battle_protocol as bp  # noqa: E402
import battle_sim as sim  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


# ---------- 1) 상대가 없으면 가만히 ----------
alone = sim.Battle((0,))
check("상대가 없으면 아무 키도 안 누른다", battle_ai.decide(alone, 0, 0) == 0)
check("없는 자리를 물어도 안 터진다", battle_ai.decide(alone, 9, 0) == 0)

# ---------- 2) 멀면 다가가고 가까우면 물러난다 ----------
far = sim.Battle((0, 1))
far.ships[0].x, far.ships[0].y = 100 * sim.SCALE, 400 * sim.SCALE
far.ships[1].x, far.ships[1].y = 1100 * sim.SCALE, 400 * sim.SCALE
keys = battle_ai.decide(far, 0, 0)
check(f"멀면 상대 쪽으로 간다(키 {keys})", bool(keys & bp.KEY_RIGHT), keys)

near = sim.Battle((0, 1))
near.ships[0].x, near.ships[0].y = 500 * sim.SCALE, 400 * sim.SCALE
near.ships[1].x, near.ships[1].y = 560 * sim.SCALE, 400 * sim.SCALE
keys = battle_ai.decide(near, 0, 0)
check(f"너무 가까우면 물러난다(키 {keys})", bool(keys & bp.KEY_LEFT), keys)

# ---------- 3) 죽은 상대는 안 쫓는다 ----------
dead_target = sim.Battle((0, 1))
dead_target.ships[1].hp = 0
check("격추된 상대는 쫓지 않는다", battle_ai.decide(dead_target, 0, 0) == 0)
check("내가 격추됐으면 아무 것도 안 한다",
      battle_ai.decide(sim.Battle((0, 1)), 0, 0) is not None)
me_dead = sim.Battle((0, 1))
me_dead.ships[0].hp = 0
check("내가 격추된 동안은 조작하지 않는다", battle_ai.decide(me_dead, 0, 0) == 0)

# ---------- 4) 조준이 맞으면 쏜다 ----------
aimed = sim.Battle((0, 1))
aimed.ships[0].x, aimed.ships[0].y = 400 * sim.SCALE, 400 * sim.SCALE
aimed.ships[1].x, aimed.ships[1].y = 700 * sim.SCALE, 400 * sim.SCALE
aimed.ships[0].facing = 8          # 오른쪽
check(f"조준이 맞으면 쏜다({battle_ai.decide(aimed, 0, 0)})",
      bool(battle_ai.decide(aimed, 0, 0) & bp.KEY_FIRE), battle_ai.decide(aimed, 0, 0))

aimed.ships[0].facing = 24         # 왼쪽 - 등지고 있다
check("등지고 있으면 안 쏜다", not (battle_ai.decide(aimed, 0, 0) & bp.KEY_FIRE))

aimed.ships[0].facing = 8
aimed.ships[0].reload_left = 10
check("재장전 중이면 안 쏜다", not (battle_ai.decide(aimed, 0, 0) & bp.KEY_FIRE))

# ---------- 5) 같은 상황이면 같은 판단(결정론) ----------
same = sim.Battle((0, 1, 2))
first = [battle_ai.decide(same, 0, t) for t in range(200)]
second = [battle_ai.decide(same, 0, t) for t in range(200)]
check("같은 상황·같은 틱이면 같은 판단", first == second)

# 여럿이 똑같이 움직이지 않는다.
# **실제로 돌아가는 판에서 봐야 한다** - 가만히 세워두고 비교하면 자리만 대칭이어도
# 같은 답이 나와서, 정작 판이 돌 때 갈리는지는 확인이 안 된다
crowd = sim.Battle((0, 1, 2, 3))
one, two = [], []
for t in range(300):
    keys = {slot: battle_ai.decide(crowd, slot, t) for slot in list(crowd.ships)}
    one.append(keys.get(1, 0))
    two.append(keys.get(2, 0))
    crowd.advance(keys)
check(f"여럿을 넣어도 똑같이 움직이진 않는다(다른 틱 {sum(1 for a, b in zip(one, two) if a != b)}번)",
      one != two)

# ---------- 6) 실제로 싸우는가(핵심) ----------
match = sim.Battle((0, 1))
events = []
for tick in range(1800):            # 30초쯤
    keys = {slot: battle_ai.decide(match, slot, tick) for slot in list(match.ships)}
    events.extend(match.advance(keys))

hits = [e for e in events if e["t"] == "hit"]
deaths = [e for e in events if e["t"] == "dead"]
check(f"AI끼리 두면 실제로 맞힌다({len(hits)}대)", len(hits) > 0, len(hits))
check(f"격추도 난다({len(deaths)}번)", len(deaths) > 0, len(deaths))
check(f"한쪽만 일방적이지 않다(격추 {[e['by'] for e in deaths]})",
      len({e["by"] for e in deaths}) > 1 or len(deaths) < 3,
      [e["by"] for e in deaths])

moved = any(ship.x != sim.Battle((0, 1)).ships[slot].x
            for slot, ship in match.ships.items())
check("가만히 서 있지 않는다", moved)

for slot, ship in match.ships.items():
    check(f"{slot}번이 전투장 안에 있다({ship.px:.0f},{ship.py:.0f})",
          0 <= ship.x <= match.width and 0 <= ship.y <= match.height, (ship.x, ship.y))

# ---------- 7) 사람과 섞여도 되는가 ----------
mixed = sim.Battle((0, 1, 2))
mixed_events = []
for tick in range(900):
    keys = {0: bp.KEY_RIGHT if tick % 40 < 20 else bp.KEY_LEFT}   # 사람은 왔다갔다
    for slot in (1, 2):
        if slot in mixed.ships:
            keys[slot] = battle_ai.decide(mixed, slot, tick)
    mixed_events.extend(mixed.advance(keys))
check(f"사람과 섞여도 돌아간다(사건 {len(mixed_events)}건)", True)
check("사람 배도 전투장 안에 있다",
      0 <= mixed.ships[0].x <= mixed.width and 0 <= mixed.ships[0].y <= mixed.height)

# ---------- 8) 순수한가 ----------
import io  # noqa: E402

source = io.open(_os.path.join(_REPO, "battle_ai.py"), encoding="utf-8").read()
for forbidden in ("PySide6", "socket", "import time", "random"):
    check(f"{forbidden} 를 쓰지 않는다(순수 모듈)", forbidden not in source, forbidden)

print("=== 검증 결과 (연습 상대) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
