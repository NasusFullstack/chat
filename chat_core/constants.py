"""도메인 코어에서 해석/적용하는 상수.

store.py(서버 사이드)의 같은 이름 상수와 값을 반드시 맞춰야 함.
"""
import re

# store.py의 AVATAR_MAX_B64_CHARS와 값 일치
AVATAR_MAX_B64_CHARS = 2000

# 같은 채널에서 같은 사람을 다시 @호출하려면 이만큼(초) 기다려야 함
MENTION_COOLDOWN_SEC = 60

MENTION_TOKEN_RE = re.compile(r"@([^\s@]+)")

# 치트 이스터에그: 채팅에 이 문구를 치면 채널 전원 화면에 자원 오버레이가 뜸.
# 채널당 쿨타임(초) - 도배 방지용이라 채널 단위(사람 단위가 아님)
CHEAT_PHRASE = "show me the money"
CHEAT_COOLDOWN_SEC = 60


def is_cheat_phrase(text: str) -> bool:
    return text.strip().lower() == CHEAT_PHRASE
