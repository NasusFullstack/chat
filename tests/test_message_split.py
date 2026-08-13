"""긴 메시지가 서버에서 잘리지 않는가.

IRC 한 줄은 CR-LF 포함 **512바이트**가 절대 상한이고(RFC 1459), 서버는 넘는 부분을
그냥 잘라버린다. 받는 쪽에는 서버가 `:닉!사용자@호스트 `를 앞에 붙여 보내므로 그 몫까지
계산해야 한다. 한글은 한 글자가 3바이트라 **150자쯤에서 걸린다**(실측: 한글 150자 =
받는 쪽 기준 509바이트).

예전에는 나누지 않고 한 줄로 보냈다. 보낸 사람 화면에는 전체가 보이는데 남들에게는
뒷부분이 없어서, 알아채기도 어려웠다(사용자 대화 기록에서 가장 긴 메시지가 94자였다).

지금은 나눠 보내고, 보낸 사람 화면에도 나눈 그대로 보여준다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import irc_protocol  # noqa: E402
from chat_core import events as domain_events  # noqa: E402
from chat_core.session import build_session  # noqa: E402

# 서버가 앞에 붙이는 부분(넉넉히 잡은 실제 예시)
SERVER_PREFIX = len(":Mong!Mong@C2934F06.CE183712.3118A5B3.IP ".encode())
HARD_LIMIT = 512

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def wire_size(piece: str) -> int:
    """그 조각이 받는 쪽에 도착할 때의 줄 크기(CR-LF 포함)."""
    return len(irc_protocol.format_privmsg("#pdlab", piece).encode("utf-8")) + 2 + SERVER_PREFIX


CASES = {
    "짧은 글": "안녕하세요",
    "한글 300자(띄어쓰기 없음)": "가" * 300,
    "한글 300자(띄어쓰기 있음)": "가나다라 마바사아 자차카타 " * 22,
    "영문 2000자": "hello world " * 166,
    "실제로 잘렸던 길이(한글 200자)": "내가 벽뿌수기 카타르시스느낀건 " * 13,
}

for name, text in CASES.items():
    pieces = irc_protocol.split_message(text)
    biggest = max(wire_size(piece) for piece in pieces)
    check(f"{name}: 모든 줄이 512바이트 안({biggest}바이트, {len(pieces)}줄)",
          biggest <= HARD_LIMIT, biggest)
    restored = " ".join(pieces) if " " in text else "".join(pieces)
    check(f"{name}: 글자가 안 빠지고 안 깨짐",
          restored.replace(" ", "") == text.replace(" ", ""),
          (len(restored), len(text)))

# 한 글자도 중간에서 쪼개지면 안 된다(한글이 깨진다)
for piece in irc_protocol.split_message("가" * 500):
    check("한 글자를 바이트로 쪼개지 않는다", "�" not in piece and piece.encode("utf-8"))

# 가능하면 띄어쓰기에서 자른다
spaced = irc_protocol.split_message("단어 " * 200)
check(f"띄어쓰기가 있으면 단어를 안 쪼갠다({spaced[0][-6:]!r})",
      all(not piece.endswith("단") for piece in spaced), spaced[0][-10:])

# 실제로 보내는 경로에서 나눠 나가는가
sent, events = [], []
session = build_session("irc", "h", 6667, transport=sent.append, on_event=events.append)
session.my_id = "Mong"
session.send_message("#pdlab", "가" * 300)
privmsgs = [line for line in sent if line.startswith("PRIVMSG")]
check(f"긴 글은 여러 줄로 나가고({len(privmsgs)}줄) 각 줄이 한계 안",
      len(privmsgs) > 1 and all(len(line.encode()) + 2 + SERVER_PREFIX <= HARD_LIMIT
                                for line in privmsgs), privmsgs[:1])

echoed = [e for e in events if isinstance(e, domain_events.MessageReceived)]
check(f"내 화면에도 나눈 그대로 보인다({len(echoed)}개 - 남들이 보는 것과 같아야 한다)",
      len(echoed) == len(privmsgs), (len(echoed), len(privmsgs)))

# 너무 길면 보내지 않고 알린다(서버가 홍수로 보고 끊는 것보다 낫다)
sent.clear()
events.clear()
session.send_message("#pdlab", "가" * 5000)
refused = [e for e in events if isinstance(e, domain_events.CommandError)]
check(f"지나치게 길면 보내지 않고 알려준다({[e.text[:30] for e in refused]})",
      bool(refused) and not sent, (len(sent), len(refused)))

# 우리 서버(커스텀)는 이 제한이 없다 - 한 번에 보낸다
custom_sent = []
custom = build_session("custom", "h", 1, transport=custom_sent.append,
                       on_event=lambda e: None)
custom.my_id = "Mong"
custom.send_message("#pdlab", "가" * 1000)
check("우리 서버에는 한 번에 보낸다(그쪽은 512 제한이 없다)", len(custom_sent) == 1,
      len(custom_sent))

print("=== 검증 결과 (긴 메시지 나눠 보내기) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
