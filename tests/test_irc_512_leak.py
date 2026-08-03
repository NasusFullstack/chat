"""잘린 아바타 프레임이 '채팅 메시지'로 새는지 실제 수신 경로로 확인."""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import sys
sys.path.insert(0, _REPO)

import irc_protocol
from chat_core import events
from chat_core.constants import AVATAR_MAX_B64_CHARS
from chat_core.history_adapter import NullHistoryStore
from chat_core.session import build_session

fails = []


def check(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + ("" if cond else f"  <- {extra}"))
    if not cond:
        fails.append(label)


IRC_LINE_LIMIT = 512

sent, evs = [], []
s = build_session("irc", "h", 1, sent.append, evs.append, history_store=NullHistoryStore())
s.my_id = "me"
s.joined_channels.add("#chan")
s.active_channel = "#chan"

# 실제 서버가 512에서 자른 뒤 중계하는 상황을 그대로 재현
# 고친 뒤의 format_ctcp_avatar는 조각내서 보내므로, 여기서는 "옛날처럼 한 줄에
# 통째로 실었을 때" 무슨 일이 벌어졌는지를 재현하려고 직접 조립한다
def _legacy_line(target, b64):
    return irc_protocol.format_privmsg(
        target, f"\x01{irc_protocol.AVATAR_CTCP_TAG} {b64}\x01")


avatar_line = _legacy_line("#chan", "A" * AVATAR_MAX_B64_CHARS)
relayed = f":friend!u@h {avatar_line}"
truncated = relayed[:IRC_LINE_LIMIT - 2]

print("[1] 옛 형식이라도 안 잘렸으면 인식되어야 함(구버전 호환)")
evs.clear()
s.handle_incoming(irc_protocol.parse_line(relayed))
avatars = [e for e in evs if isinstance(e, events.AvatarUpdated)]
msgs = [e for e in evs if isinstance(e, events.MessageReceived)]
check("아바타로 처리됨", len(avatars) == 1, evs)
check("채팅으로는 안 뜸", len(msgs) == 0, msgs)

print("\n[2] 512에서 잘린 경우 - 무슨 일이 일어나는가")
evs.clear()
s.handle_incoming(irc_protocol.parse_line(truncated))
avatars = [e for e in evs if isinstance(e, events.AvatarUpdated)]
msgs = [e for e in evs if isinstance(e, events.MessageReceived)]
print(f"  AvatarUpdated {len(avatars)}건 / MessageReceived {len(msgs)}건")
check("아이콘은 안 옴(기대한 실패)", len(avatars) == 0, avatars)
if msgs:
    body = msgs[0].text
    print(f"  채팅에 뜬 내용 길이: {len(body)}자")
    print(f"  앞부분: {body[:50]!r}")
check("잘린 쓰레기가 채팅 메시지로 새지 않아야 함", len(msgs) == 0,
      f"{len(msgs)}건이 채팅으로 샜음 - 채널에 긴 쓰레기 문자열이 그대로 보임")

print()
if fails:
    print(f"확인된 문제 {len(fails)}건: {fails}")
    sys.exit(1)
print("문제 없음")
