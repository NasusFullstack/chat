"""배틀크루저 전투 규약 - 받은 값을 제대로 걸러내는가.

이 규약으로 오는 값은 **전부 남이 정한 값**이다(중계 서버가 보낸 것도 마찬가지).
그래서 검사가 곧 보안이다. 여기서 막아야 할 것들:

- 주소가 어디에도 실리지 않는가(중계 방식으로 바꾼 이유가 이것이다)
- 남의 배를 대신 움직이거나 대신 죽었다고 신고할 수 있는가
- 이상한 값(범위 밖, 자료형 다름, 너무 긴 줄)이 통과하는가
- 너무 빨리 보내는 연결을 끊을 수 있는가
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
_sys.path.insert(0, _REPO)

import json  # noqa: E402

import battle_protocol as bp  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def line(message):
    return json.dumps(message, separators=(",", ":")).encode("utf-8")


# ---------- 1) 채팅에는 방 번호만 오간다(주소가 안 실린다) ----------
room = bp.new_room()
notice = bp.format_room_notice(room)
check(f"방 번호를 알리는 한 줄({notice!r})", bp.parse_room_notice(notice) == room, notice)
check("우리 것인지 알아본다", bp.is_battle_notice(notice))
check("방 번호가 난수라 겹치지 않는다", bp.new_room() != bp.new_room())
check("방 번호는 짧지 않다(찍어서 못 맞히게)", len(room) >= 16, len(room))

# **주소가 실리면 안 된다** - 중계로 바꾼 이유가 이것이라, 실수로 다시 들어오면 잡아야 한다
source = open(_os.path.join(_REPO, "battle_protocol.py"), encoding="utf-8").read()
for banned in ("ip_to_number", "number_to_ip", "ipaddress"):
    check(f"주소를 다루는 코드가 없다({banned})", banned not in source, banned)

for bad in ("", "hello", "\x01CHUPBATTLE ROOM\x01", "\x01CHUPBATTLE ROOM 없는값\x01",
            "\x01CHUPBATTLE OPEN 2130706433 5000 abcdef12 4\x01",
            "\x01DCC SEND a 2130706433 5000 1\x01"):
    check(f"이상한 알림은 무시한다({bad[:36]!r})", bp.parse_room_notice(bad) == "", bad)

# ---------- 2) 남의 배를 못 건드린다 ----------
moved = bp.decode(line({"t": "in", "tick": 10, "keys": bp.KEY_LEFT, "slot": 3}))
check(f"조작에는 자리 번호가 안 담긴다({moved})", moved is not None and "slot" not in moved, moved)

reported = bp.decode(line({"t": "dead", "by": 1, "slot": 2, "hp": 0}))
check(f"'죽었다'도 자리 번호를 안 받는다({reported})",
      reported is not None and "slot" not in reported, reported)
check(f"대신 남은 체력을 싣는다({reported})", reported.get("hp") == 0, reported)
check("체력이 빠진 보고는 버린다",
      bp.decode(line({"t": "hit", "by": 1})) is None)
check("말도 안 되는 체력은 버린다",
      bp.decode(line({"t": "hit", "by": 1, "hp": -1})) is None)

relayed = bp.decode(line({"t": "peerdead", "slot": 2, "by": 1, "hp": 0}))
check(f"중계 서버가 붙여 보낸 것에는 자리 번호가 있다({relayed})",
      relayed == {"t": bp.PEER_DEAD, "slot": 2, "by": 1, "hp": 0}, relayed)

# ---------- 3) 이상한 값은 통과 못 한다 ----------
BAD = [
    ("모르는 종류", {"t": "quit_everyone"}),
    ("종류가 없음", {"tick": 1, "keys": 1}),
    ("JSON이 아님", None),
    ("자리 번호가 범위 밖", {"t": "peer", "slot": bp.MAX_PLAYERS, "tick": 1, "keys": 1}),
    ("자리 번호가 음수", {"t": "peer", "slot": -1, "tick": 1, "keys": 1}),
    ("틱이 너무 큼", {"t": "in", "tick": bp.MAX_TICK + 1, "keys": 1}),
    ("키 값이 범위 밖", {"t": "in", "tick": 1, "keys": 999}),
    ("키가 참/거짓", {"t": "in", "tick": 1, "keys": True}),
    ("틱이 글자", {"t": "in", "tick": "1", "keys": 1}),
    ("틱이 소수", {"t": "in", "tick": 1.5, "keys": 1}),
    ("방 번호가 이상함", {"t": "join", "room": "../../etc/passwd", "nick": "a"}),
    ("방 번호가 없음", {"t": "join", "nick": "a"}),
    ("참여자 목록이 아님", {"t": "welcome", "slot": 0, "tick": 0, "players": "전부"}),
    ("참여자가 너무 많음", {"t": "welcome", "slot": 0, "tick": 0,
                      "players": [{"slot": 0}] * (bp.MAX_PLAYERS + 1)}),
]
for label, payload in BAD:
    raw = b"{not json" if payload is None else line(payload)
    check(f"{label}: 버린다", bp.decode(raw) is None, bp.decode(raw))

check("목록(list)은 받지 않는다", bp.decode(b'["in",1,2]') is None)
check("빈 줄은 버린다", bp.decode(b"") is None)
check("깨진 글자는 버린다", bp.decode(b'{"t":"bye"\xff}') is None)

too_long = line({"t": "in", "tick": 1, "keys": 1, "pad": "x" * bp.MAX_LINE_BYTES})
check(f"너무 긴 줄은 버린다({len(too_long)}바이트)", bp.decode(too_long) is None, len(too_long))
check("보낼 때도 상한을 넘기지 않는다",
      bp.encode({"t": "in", "pad": "x" * bp.MAX_LINE_BYTES}) == b"")

good = bp.encode({"t": "in", "tick": 5, "keys": bp.KEY_FIRE})
check(f"평범한 조작은 한 줄로 나간다({len(good)}바이트)",
      good.endswith(b"\n") and len(good) < 64, good)

# ---------- 3-1) 대기방 설정(정원/색) ----------
joined_room = bp.decode(line({"t": "join", "room": room, "nick": "Mong", "color": 3, "cap": 2}))
check(f"정원과 색을 담아 들어간다({joined_room})",
      joined_room == {"t": bp.JOIN, "room": room, "nick": "Mong", "color": 3, "cap": 2,
                      "bots": 0},
      joined_room)

plain_join = bp.decode(line({"t": "join", "room": room, "nick": "Mong"}))
check(f"안 적으면 기본값이 채워진다({plain_join})",
      plain_join["color"] == 0 and plain_join["cap"] == bp.MAX_HUMANS, plain_join)

for bad_setting, why in (
    ({"color": bp.COLOR_COUNT}, "없는 색"),
    ({"color": -1}, "음수 색"),
    ({"cap": 1}, "혼자서는 전투가 안 됨"),
    ({"cap": bp.MAX_HUMANS + 1}, "정원 초과"),
    ({"bots": bp.MAX_BOTS + 1}, "연습 상대 초과"),
):
    got = bp.decode(line({"t": "join", "room": room, "nick": "a", **bad_setting}))
    # 값이 이상하면 기본값으로 떨어질 뿐, 그 값이 그대로 통과하면 안 된다
    check(f"{why}: 그대로 통과하지 않는다({bad_setting} -> color={got['color']}, cap={got['cap']})",
          0 <= got["color"] < bp.COLOR_COUNT and bp.MIN_PLAYERS <= got["cap"] <= bp.MAX_HUMANS
          and 0 <= got["bots"] <= bp.MAX_BOTS,
          got)

welcome = bp.decode(line({"t": "welcome", "slot": 1, "tick": 0, "cap": 3, "color": 2,
                          "players": [{"slot": 0, "nick": "Mong", "color": 5}],
                          "started": False}))
check(f"환영에 정원·색·시작여부가 온다({welcome})",
      welcome["cap"] == 3 and welcome["color"] == 2
      and welcome["players"][0]["color"] == 5 and welcome["started"] is False, welcome)

check("정원이 빠진 환영은 버린다",
      bp.decode(line({"t": "welcome", "slot": 0, "tick": 0, "color": 0, "players": []})) is None)

check("시작 신호는 자리 번호를 안 싣는다(방장인지는 서버가 판단)",
      bp.decode(line({"t": "start", "slot": 2})) == {"t": bp.START})
check("시작됐다 신호", bp.decode(line({"t": "started"})) == {"t": bp.STARTED})

# ---------- 4) 이름은 표시용으로만 ----------
check("제어문자를 걷어낸다", bp.safe_nick("\x03" + "04빨강" + "\x0f") == "04빨강",
      bp.safe_nick("\x0304빨강\x0f"))
check(f"길이를 자른다({len(bp.safe_nick('가' * 100))}자)",
      len(bp.safe_nick("가" * 100)) == bp.MAX_NICK_LEN)
check("빈 이름도 뭔가는 된다", bp.safe_nick("   ") == "손님")
check("줄바꿈을 끼워 넣을 수 없다", "\n" not in bp.safe_nick("a\nb"))

# ---------- 5) 정원과 속도 제한 ----------
check(f"사람은 {bp.MAX_HUMANS}명까지, 연습 상대 {bp.MAX_BOTS}대까지 = {bp.MAX_PLAYERS}대",
      bp.MAX_HUMANS == 6 and bp.MAX_BOTS == 6 and bp.MAX_PLAYERS == 12)
check("자리 번호로 사람과 연습 상대가 갈린다",
      not bp.is_bot_slot(0) and not bp.is_bot_slot(bp.MAX_HUMANS - 1)
      and bp.is_bot_slot(bp.MAX_HUMANS) and bp.is_bot_slot(bp.MAX_PLAYERS - 1)
      and not bp.is_bot_slot(bp.MAX_PLAYERS))
check(f"색이 20가지 + 무지개({bp.COLOR_COUNT})", bp.COLOR_COUNT == 21)

# 연습 상대를 대신 조종하는 길은 **AI 자리에만** 열린다
check("방장은 연습 상대 자리를 움직일 수 있다",
      bp.decode(line({"t": "botin", "slot": bp.MAX_HUMANS, "tick": 1, "keys": 1}))
      == {"t": bp.BOT_INPUT, "slot": bp.MAX_HUMANS, "tick": 1, "keys": 1})
for human_slot in (0, 1, bp.MAX_HUMANS - 1):
    check(f"사람 자리({human_slot})는 대신 못 움직인다",
          bp.decode(line({"t": "botin", "slot": human_slot, "tick": 1, "keys": 1})) is None)
check("없는 자리도 안 된다",
      bp.decode(line({"t": "botin", "slot": bp.MAX_PLAYERS, "tick": 1, "keys": 1})) is None)
check("정원 밖 자리는 안 받는다",
      bp.decode(line({"t": "joined", "slot": bp.MAX_PLAYERS, "nick": "a"})) is None)

window = bp.RateWindow(limit_per_sec=10)
check("정상 속도는 통과", all(window.allow(1.0 + i * 0.11, 20) for i in range(8)))
burst = bp.RateWindow(limit_per_sec=10)
allowed = sum(1 for _ in range(30) if burst.allow(5.0, 20))
check(f"한꺼번에 쏟으면 막는다(30줄 중 {allowed}줄만 통과)", allowed == 10, allowed)
later = bp.RateWindow(limit_per_sec=10)
for _ in range(10):
    later.allow(5.0, 20)
check("1초 지나면 다시 받는다", later.allow(6.5, 20) is True)

heavy = bp.RateWindow(limit_per_sec=1000)
check("전체 바이트 상한도 있다",
      heavy.allow(1.0, bp.MAX_SESSION_BYTES + 1) is False)

print("=== 검증 결과 (전투 규약) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
