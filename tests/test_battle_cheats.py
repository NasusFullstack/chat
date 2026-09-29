"""전투 치트가 기존 치트와 확실히 구분되는가.

'배틀크루저 소환'은 혼자 날아다니는 것이고 '배틀크루저 전투'는 사람끼리 붙는 것이다.
문구가 서로 겹치면 엉뚱한 게 뜨므로, **완전일치로 갈리는지**를 확인한다
(기존 '소환'/'소환해제'가 그래서 안 헷갈린다).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
_sys.path.insert(0, _REPO)

from chat_core import constants as c  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


# ---------- 1) 새 치트가 생겼는가 ----------
for cheat_id, phrase in ((c.CHEAT_BATTLE_OPEN, "배틀크루저 전투"),
                         (c.CHEAT_BATTLE_JOIN, "배틀크루저 전투 참가")):
    found = c.find_cheat(phrase)
    check(f"'{phrase}' 가 있다({found.id if found else None})",
          found is not None and found.id == cheat_id, found)
    check(f"'{phrase}' 는 친 사람에게만 보인다",
          found is not None and found.for_everyone is False, found)

# ---------- 2) 기존 치트가 그대로인가 ----------
for cheat_id, phrase, cooldown, everyone in (
    (c.CHEAT_RESOURCES, "show me the money", 60, True),
    (c.CHEAT_BATTLECRUISER_SUMMON, "배틀크루저 소환", 60, False),
    (c.CHEAT_BATTLECRUISER_DISMISS, "배틀크루저 소환해제", 0, False),
):
    spec = c.find_cheat(phrase)
    check(f"기존 '{phrase}' 가 그대로다",
          spec is not None and spec.id == cheat_id
          and spec.cooldown_sec == cooldown and spec.for_everyone is everyone, spec)

# ---------- 3) 문구가 서로 안 먹히는가(가장 중요) ----------
PAIRS = (
    ("배틀크루저 소환", c.CHEAT_BATTLECRUISER_SUMMON),
    ("배틀크루저 소환해제", c.CHEAT_BATTLECRUISER_DISMISS),
    ("배틀크루저 전투", c.CHEAT_BATTLE_OPEN),
    ("배틀크루저 전투 참가", c.CHEAT_BATTLE_JOIN),
)
for phrase, expected in PAIRS:
    got = c.find_cheat(phrase)
    check(f"'{phrase}' -> {expected}", got is not None and got.id == expected,
          got.id if got else None)

# '전투'가 '전투 참가'를 잡아먹거나 그 반대가 되면 안 된다
check("'배틀크루저 전투'가 '전투 참가'로 잘못 잡히지 않는다",
      c.find_cheat("배틀크루저 전투").id == c.CHEAT_BATTLE_OPEN)
check("'배틀크루저 전투 참가'가 '전투'로 잘못 잡히지 않는다",
      c.find_cheat("배틀크루저 전투 참가").id == c.CHEAT_BATTLE_JOIN)
check("'배틀크루저 소환'이 '소환해제'로 잘못 잡히지 않는다",
      c.find_cheat("배틀크루저 소환").id == c.CHEAT_BATTLECRUISER_SUMMON)

# 비슷하지만 다른 말은 안 걸려야 한다
for not_a_cheat in ("배틀크루저", "배틀크루저 전투 참가요", "전투", "배틀크루저 전투참가",
                    "배틀크루저 전투 ", "  배틀크루저 전투", "배틀 크루저 전투",
                    "배틀크루저 전투 참가 하자", "야 배틀크루저 전투"):
    got = c.find_cheat(not_a_cheat)
    # 앞뒤 공백은 find_cheat 이 다듬으므로 그건 걸려도 된다
    expected_hit = not_a_cheat.strip() in {p for p, _ in PAIRS}
    check(f"'{not_a_cheat}' -> {'치트' if expected_hit else '치트 아님'}",
          (got is not None) is expected_hit, got.id if got else None)

# ---------- 4) 표 자체가 성한가 ----------
ids = [spec.id for spec in c.CHEAT_SPECS]
check(f"id 가 겹치지 않는다({len(ids)}개)", len(ids) == len(set(ids)), ids)
phrases = [spec.phrase for spec in c.CHEAT_SPECS]
check("문구도 겹치지 않는다", len(phrases) == len(set(phrases)), phrases)
check("모르는 문구는 None", c.find_cheat("아무말") is None)
check("빈 문구도 안 터진다", c.find_cheat("") is None and c.find_cheat("   ") is None)

print("=== 검증 결과 (전투 치트) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
