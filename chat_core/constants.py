"""도메인 코어에서 해석/적용하는 상수.

store.py(서버 사이드)의 같은 이름 상수와 값을 반드시 맞춰야 함.
"""
import re
from dataclasses import dataclass

# store.py의 AVATAR_MAX_B64_CHARS와 값 일치
AVATAR_MAX_B64_CHARS = 2000

# 같은 채널에서 같은 사람을 다시 @호출하려면 이만큼(초) 기다려야 함
MENTION_COOLDOWN_SEC = 60

MENTION_TOKEN_RE = re.compile(r"@([^\s@]+)")


@dataclass(frozen=True)
class CheatSpec:
    """치트 이스터에그 하나. 채팅에 phrase를 그대로 치면 효과가 뜸.

    쿨타임은 도배 방지용이라 사람 단위가 아니라 채널 단위이고, 치트마다 따로 센다
    (소환 해제처럼 되돌리는 동작까지 막으면 오히려 답답하므로 0을 줄 수 있게 함).

    for_everyone: 효과를 그 채널 사람 모두가 보는지, 친 사람만 보는지.
      - 자원 오버레이처럼 '보여주는' 연출은 모두가 봐야 재미있음
      - 배틀크루저처럼 '조종하는' 것은 친 사람만 봐야 함. 모두에게 뜨면 각자 화면에
        배가 생겨서 서로 다른 걸 조종하게 되고, 남이 친 것 때문에 내 방향키가 먹히는
        상황이 됨
    새 치트는 아래 CHEAT_SPECS에 한 줄 추가하면 되고 세션 코드는 안 건드려도 됨.
    """
    id: str
    phrase: str
    cooldown_sec: int
    for_everyone: bool = True


CHEAT_RESOURCES = "resources"
CHEAT_BATTLECRUISER_SUMMON = "battlecruiser_summon"
CHEAT_BATTLECRUISER_DISMISS = "battlecruiser_dismiss"

CHEAT_SPECS = (
    # 자원 오버레이는 보여주는 연출이라 채널 전원 화면에 뜸
    CheatSpec(CHEAT_RESOURCES, "show me the money", 60, for_everyone=True),
    # 배틀크루저는 방향키로 조종하는 것이라 친 사람 화면에만 띄움
    CheatSpec(CHEAT_BATTLECRUISER_SUMMON, "배틀크루저 소환", 60, for_everyone=False),
    # 해제는 소환한 걸 치우는 동작이라 쿨타임을 두면 화면에 박제됨
    CheatSpec(CHEAT_BATTLECRUISER_DISMISS, "배틀크루저 소환해제", 0, for_everyone=False),
)

_CHEATS_BY_PHRASE = {spec.phrase: spec for spec in CHEAT_SPECS}

CHEAT_COOLDOWN_SEC = CHEAT_SPECS[0].cooldown_sec


def find_cheat(text: str) -> CheatSpec | None:
    """치트 문구면 그 명세를, 아니면 None. 완전일치라 '소환'/'소환해제'가 안 헷갈림"""
    return _CHEATS_BY_PHRASE.get(text.strip().lower())


