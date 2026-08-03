"""치트 효과를 누가 보는지 - 자원은 모두, 배틀크루저는 친 사람만"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import sys
sys.path.insert(0, _REPO)

from chat_core import events
from chat_core.constants import (
    CHEAT_BATTLECRUISER_DISMISS, CHEAT_BATTLECRUISER_SUMMON, CHEAT_RESOURCES, CHEAT_SPECS,
)
from chat_core.history_adapter import NullHistoryStore
from chat_core.session import build_session

fails = []


def check(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + ("" if cond else f"  <- {extra}"))
    if not cond:
        fails.append(label)


def new_session(mode="custom"):
    sent, evs = [], []
    s = build_session(mode, "h", 1, sent.append, evs.append, history_store=NullHistoryStore())
    s.my_id = "me"
    s.members["#a"] = {"me", "Mong"}
    s.active_channel = "#a"
    s.joined_channels.add("#a")
    return s, sent, evs


def activated(evs):
    return [e.cheat_id for e in evs if isinstance(e, events.CheatActivated)]


def messages(evs):
    return [e for e in evs if isinstance(e, events.MessageReceived)]


print("[1] 명세 확인")
by_id = {c.id: c for c in CHEAT_SPECS}
check("자원 치트는 모두에게", by_id[CHEAT_RESOURCES].for_everyone is True)
check("배틀크루저 소환은 친 사람만", by_id[CHEAT_BATTLECRUISER_SUMMON].for_everyone is False)
check("배틀크루저 해제도 친 사람만", by_id[CHEAT_BATTLECRUISER_DISMISS].for_everyone is False)

print("\n[2] 남이 친 경우 (커스텀 서버로 전달받음)")
s, sent, evs = new_session("custom")
for phrase, cheat_id, should_see in (
    ("show me the money", CHEAT_RESOURCES, True),
    ("배틀크루저 소환", CHEAT_BATTLECRUISER_SUMMON, False),
    ("배틀크루저 소환해제", CHEAT_BATTLECRUISER_DISMISS, False),
):
    evs.clear()
    s.handle_incoming({"type": "chat", "from": "Mong", "channel": "#a",
                       "text": phrase, "ts": 1.0})
    got = activated(evs)
    check(f"'{phrase}' -> {'뜸' if should_see else '안 뜸'}",
          (cheat_id in got) is should_see, got)
    check(f"  '{phrase}' 채팅 메시지 자체는 보임", len(messages(evs)) == 1, evs)

print("\n[3] 내가 친 경우 (커스텀 서버가 되돌려줌)")
s, sent, evs = new_session("custom")
for phrase, cheat_id in (
    ("show me the money", CHEAT_RESOURCES),
    ("배틀크루저 소환", CHEAT_BATTLECRUISER_SUMMON),
    ("배틀크루저 소환해제", CHEAT_BATTLECRUISER_DISMISS),
):
    evs.clear()
    s.handle_incoming({"type": "chat", "from": "me", "channel": "#a",
                       "text": phrase, "ts": 1.0})
    check(f"'{phrase}' -> 내 화면엔 뜸", cheat_id in activated(evs), activated(evs))

print("\n[4] IRC 모드 - 내가 친 것은 로컬 에코로 처리됨")
s2, sent2, evs2 = new_session("irc")
evs2.clear()
s2.send_message("#a", "배틀크루저 소환")
check("내가 치면 뜸", CHEAT_BATTLECRUISER_SUMMON in activated(evs2), activated(evs2))

import irc_protocol
evs2.clear()
s2.handle_incoming(irc_protocol.parse_line(
    ":Mong!u@h " + irc_protocol.format_privmsg("#a", "배틀크루저 소환")))
check("남이 치면 안 뜸", CHEAT_BATTLECRUISER_SUMMON not in activated(evs2), activated(evs2))
check("  채팅 메시지 자체는 보임", len(messages(evs2)) == 1, evs2)

evs2.clear()
s2.handle_incoming(irc_protocol.parse_line(
    ":Mong!u@h " + irc_protocol.format_privmsg("#a", "show me the money")))
check("자원 치트는 남이 쳐도 뜸", CHEAT_RESOURCES in activated(evs2), activated(evs2))

print("\n[5] 코어에 치트별 분기가 없는지 (명세 표로만 처리)")
src = open(_os.path.join(_REPO, "chat_core", "session.py"), encoding="utf-8").read()
check("세션에 battlecruiser 문자열 없음", "battlecruiser" not in src.lower())
# 주석은 빼고 실제 코드에서만 셈
code_lines = [ln for ln in src.splitlines() if "for_everyone" in ln and "#" not in ln.split("for_everyone")[0]]
check("세션이 for_everyone을 코드에서 쓰는 곳은 한 곳뿐(치트별 분기 없음)",
      len(code_lines) == 1, code_lines)

print()
if fails:
    print(f"실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("전부 통과")
