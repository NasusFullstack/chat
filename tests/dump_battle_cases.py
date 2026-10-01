"""전투 계산의 답안지를 뜬다 - 매 틱의 상태를 그대로.

## 왜 이것만은 특별히 꼼꼼한가
전투는 **조작(누른 키)만 주고받고 배와 포탄은 각자 계산한다.** 계산이 조금이라도
갈리면 내 화면에선 맞았는데 상대 화면에선 안 맞은 게 된다. 오류도 안 나고, 그냥
"쟤는 안 죽었다는데?"로만 나타난다.

그래서 파이썬이 **매 틱의 좌표·속도·방향·체력·포탄**을 전부 적어두고, Dart 가 같은
입력을 먹여 **한 칸도 안 틀리는지** 본다(mobile/test/battle_sim_test.dart).

## Dart 로 옮길 때 가장 위험한 것
파이썬의 `//` 는 **아래로 내림**이고 Dart 의 `~/` 는 **0 쪽으로 자른다.** 음수에서
답이 갈린다: `-7 // 2 == -4` 인데 `-7 ~/ 2 == -3`.

전투 계산에는 음수가 널렸다(왼쪽·위쪽으로 가면 속도가 음수, 방향표의 성분도 음수).
그래서 왼쪽 위로 날아가는 배만 조금씩 어긋나다가 한참 뒤에 포탄이 빗나간다 - 이
답안지는 **일부러 왼쪽·위쪽으로도 날린다.**

쓰는 법:
    python tests/dump_battle_cases.py      # mobile/test/battle_cases.json 을 뜬다
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

import battle_protocol as bp  # noqa: E402
import battle_sim  # noqa: E402

OUT = os.path.join(REPO, "mobile", "test", "battle_cases.json")

L, R, U, D, F = (bp.KEY_LEFT, bp.KEY_RIGHT, bp.KEY_UP, bp.KEY_DOWN, bp.KEY_FIRE)


def keys_for(script, tick):
    """대본에서 이 틱에 누르고 있는 키를 꺼낸다. {자리: 키}."""
    return {slot: press(tick) for slot, press in script.items()}


def hold(*spans):
    """(시작틱, 끝틱, 키) 묶음들 - 그 사이에는 그 키를 누르고 있다."""
    def press(tick):
        keys = 0
        for start, end, value in spans:
            if start <= tick < end:
                keys |= value
        return keys
    return press


# 각 판: 이름, 자리들, 자리별 대본, 몇 틱을 돌릴지
CASES = [
    # 1) 오른쪽·아래로 - 가장 평범한 경우(양수만 나온다)
    ("오른쪽 아래로 날아간다", [0, 1], {
        0: hold((0, 40, R | D)),
        1: hold((0, 40, 0)),
    }, 60),

    # 2) **왼쪽·위로** - `//` 와 `~/` 가 갈리는 자리. 여기가 틀리면 한쪽만 어긋난다
    ("왼쪽 위로 날아간다", [0, 1], {
        0: hold((0, 40, L | U)),
        1: hold((0, 40, 0)),
    }, 60),

    # 3) 대각선 - 더 빨라지지 않게 나누는 계산(음수 나눗셈이 또 나온다)
    ("네 방향을 돌아가며 누른다", [0, 1], {
        0: hold((0, 15, R), (15, 30, D), (30, 45, L), (45, 60, U)),
        1: hold((0, 60, L | U)),
    }, 80),

    # 4) 벽에 부딪혀 선다
    ("벽까지 밀어붙인다", [0, 1], {
        0: hold((0, 120, L | U)),
        1: hold((0, 120, R | D)),
    }, 130),

    # 5) 기를 모아 쏜다 - 꽉 채운 것과 살짝 누른 것과 스친 것
    ("야마토포를 세 가지로 쏜다", [0, 1], {
        0: hold((5, 40, F),            # 꽉 채움
                (60, 70, F),           # 절반쯤
                (90, 92, F)),          # 스친 정도 - 안 나가야 한다
        1: hold((0, 120, 0)),
    }, 130),

    # 6) **맞히고 격추까지** 간다.
    #    자리 0은 위쪽 복판, 자리 8은 아래쪽 복판 - 시작 자리가 서로 마주 본다
    #    (자리 번호로 원을 그리며 놓이므로 0과 8이 정반대다).
    #    아래로 날면 배가 아래를 보고, 그때 쏘면 포탄이 상대에게 곧장 간다.
    #    꽉 채운 한 방이 260, 체력이 500이므로 **두 방이면 격추**된다
    ("아래로 쏴서 격추한다", [0, 8], {
        0: hold((0, 200, D),                 # 계속 아래를 보게 한다
                (5, 36, F),                  # 꽉 채워 한 방
                (50, 81, F)),                # 또 한 방 - 여기서 격추
        8: hold((0, 200, 0)),
    }, 220),

    # 6-2) **위로 쏜다** - 포탄 속도가 음수가 되는 경우.
    #      파이썬의 // 와 Dart 의 ~/ 가 갈리는 자리라 일부러 따로 둔다
    ("위로 쏴서 맞힌다", [0, 8], {
        0: hold((0, 200, 0)),
        8: hold((0, 200, U),
                (5, 36, F),
                (50, 81, F)),
    }, 220),

    # 7) 여럿이 붙는다 - 자리 번호 순서대로 처리되는지(순서가 바뀌면 답이 갈린다)
    ("네 명이 한꺼번에 움직인다", [0, 1, 2, 3], {
        0: hold((0, 60, R | F)),
        1: hold((0, 60, L | U)),
        2: hold((0, 60, D)),
        3: hold((10, 60, U | R | F)),
    }, 90),
]


def run_case(name, slots, script, ticks):
    battle = battle_sim.Battle(slots)
    frames = []
    events = []
    for tick in range(ticks):
        happened = battle.advance(keys_for(script, tick))
        for item in happened:
            events.append({"tick": tick + 1, **item})
        # 매 틱을 다 적으면 파일이 커진다. 처음과 끝은 촘촘히, 가운데는 띄엄띄엄 -
        # 어긋나면 어차피 그 뒤로 계속 어긋나므로 이걸로 충분히 잡힌다
        if tick < 5 or tick % 5 == 0 or tick >= ticks - 3:
            frames.append(battle.snapshot())
    return {
        "name": name,
        "slots": slots,
        "ticks": ticks,
        # 대본을 Dart 가 그대로 재현할 수 있게 **틱마다 누른 키**를 적는다.
        # 함수를 옮기면 옮기다 틀릴 수 있으므로 결과만 넘긴다
        "keys": [keys_for(script, tick) for tick in range(ticks)],
        "frames": frames,
        "events": events,
    }


def main():
    data = {
        # Dart 쪽이 같은 상수를 쓰는지도 같이 본다 - 하나만 달라도 전부 어긋난다
        "constants": {
            "SCALE": battle_sim.SCALE,
            "FIELD_WIDTH": battle_sim.FIELD_WIDTH,
            "FIELD_HEIGHT": battle_sim.FIELD_HEIGHT,
            "TICK_MS": battle_sim.TICK_MS,
            "ACCEL": battle_sim.ACCEL,
            "MAX_SPEED": battle_sim.MAX_SPEED,
            "DRAG_NUM": battle_sim.DRAG_NUM,
            "DRAG_DEN": battle_sim.DRAG_DEN,
            "STOP_BELOW": battle_sim.STOP_BELOW,
            "DIAG": battle_sim.DIAG,
            "DIRECTIONS": battle_sim.DIRECTIONS,
            "CHARGE_FULL_TICKS": battle_sim.CHARGE_FULL_TICKS,
            "CHARGE_MIN": battle_sim.CHARGE_MIN,
            "SHELL_SPEED_MIN": battle_sim.SHELL_SPEED_MIN,
            "SHELL_SPEED_MAX": battle_sim.SHELL_SPEED_MAX,
            "SHELL_LIFE_TICKS": battle_sim.SHELL_LIFE_TICKS,
            "RELOAD_TICKS": battle_sim.RELOAD_TICKS,
            "SHELL_RADIUS": battle_sim.SHELL_RADIUS,
            "SHIP_RADIUS": battle_sim.SHIP_RADIUS,
            "MAX_HP": battle_sim.MAX_HP,
            "HP_SEGMENTS": battle_sim.HP_SEGMENTS,
            "SHELL_DAMAGE_MIN": battle_sim.SHELL_DAMAGE_MIN,
            "SHELL_DAMAGE_MAX": battle_sim.SHELL_DAMAGE_MAX,
            "RESPAWN_TICKS": battle_sim.RESPAWN_TICKS,
            "MAX_PLAYERS": bp.MAX_PLAYERS,
            "KEY_LEFT": bp.KEY_LEFT,
            "KEY_RIGHT": bp.KEY_RIGHT,
            "KEY_UP": bp.KEY_UP,
            "KEY_DOWN": bp.KEY_DOWN,
            "KEY_FIRE": bp.KEY_FIRE,
        },
        # 32방향 표도 그대로 넘긴다. Dart 에서 sin/cos 로 다시 만들면 마지막 자리가
        # 다를 수 있고, 그러면 배가 아주 조금씩 다른 쪽으로 날아간다
        "directions": [list(pair) for pair in battle_sim.DIRECTION_TABLE],
        "cases": [run_case(*case) for case in CASES],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False)
    size = os.path.getsize(OUT)
    print(f"{OUT} 에 적었습니다 ({size:,} 바이트, 판 {len(CASES)}개)")
    for case in data["cases"]:
        print(f"  - {case['name']}: {case['ticks']}틱, "
              f"적어둔 상태 {len(case['frames'])}개, 일어난 일 {len(case['events'])}개")


if __name__ == "__main__":
    main()
