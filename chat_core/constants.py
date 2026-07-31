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
    """치트 이스터에그 하나. 채팅에 phrase를 그대로 치면 채널 전원 화면에 효과가 뜸.

    쿨타임은 도배 방지용이라 사람 단위가 아니라 채널 단위이고, 치트마다 따로 센다
    (소환 해제처럼 되돌리는 동작까지 막으면 오히려 답답하므로 0을 줄 수 있게 함).
    새 치트는 아래 CHEAT_SPECS에 한 줄 추가하면 되고 세션 코드는 안 건드려도 됨.
    """
    id: str
    phrase: str
    cooldown_sec: int


CHEAT_RESOURCES = "resources"
CHEAT_BATTLECRUISER_SUMMON = "battlecruiser_summon"
CHEAT_BATTLECRUISER_DISMISS = "battlecruiser_dismiss"

CHEAT_SPECS = (
    CheatSpec(CHEAT_RESOURCES, "show me the money", 60),
    CheatSpec(CHEAT_BATTLECRUISER_SUMMON, "배틀크루저 소환", 60),
    # 해제는 소환한 걸 치우는 동작이라 쿨타임을 두면 화면에 박제됨
    CheatSpec(CHEAT_BATTLECRUISER_DISMISS, "배틀크루저 소환해제", 0),
)

_CHEATS_BY_PHRASE = {spec.phrase: spec for spec in CHEAT_SPECS}

# 예전 이름 - 자원 치트만 있던 시절의 호출부/테스트 호환용
CHEAT_PHRASE = CHEAT_SPECS[0].phrase
CHEAT_COOLDOWN_SEC = CHEAT_SPECS[0].cooldown_sec


def find_cheat(text: str) -> CheatSpec | None:
    """치트 문구면 그 명세를, 아니면 None. 완전일치라 '소환'/'소환해제'가 안 헷갈림"""
    return _CHEATS_BY_PHRASE.get(text.strip().lower())


def is_cheat_phrase(text: str) -> bool:
    return find_cheat(text) is not None
