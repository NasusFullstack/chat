"""연결이 죽었는지 스스로 알아채는가(180초 핑 타임아웃 대응).

실제 상황(2026-08-13): 사용자가 "180초쯤 지나면 팅긴다"고 신고했다. 서버에 직접 붙어
7분간 가만히 있어보고 잰 결과가 근거다.

    14:06:46 서버 PING 도착
    14:08:16 서버 PING 도착 (직전 핑에서 90초)
    14:09:46 서버 PING 도착 (직전 핑에서 90초)

즉 서버(UnrealIRCd)는 **90초마다 PING**을 보내고, 180초(핑 두 번) 동안 답이 없으면
끊는다. 우리 클라이언트에는 180초짜리 타이머가 없다 - 그 180초는 서버 것이다.

우리가 답을 못 하는 경우는 둘이다.
1. 화면이 그만큼 오래 멈춘 경우(Qt는 화면과 네트워크가 같은 한 줄기다)
2. 연결이 조용히 죽어서 서버의 PING이 아예 도착하지 않는 경우

2번은 가만히 두면 영영 모른다. 그래서 조용하면 우리가 먼저 물어보고, 그래도 답이 없으면
서버가 끊기 전에 우리가 먼저 다시 붙는다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import irc_protocol  # noqa: E402
from chat_core.session import build_session  # noqa: E402
from gui import liveness  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


# ---------- 1) 언제 무엇을 할지 ----------
check("대화가 오가는 동안에는 아무 것도 안 한다",
      liveness.action_for(0) == liveness.OK and liveness.action_for(30) == liveness.OK)
check(f"서버가 핑을 보내는 주기({liveness.SERVER_PING_INTERVAL_SEC}초)까지는 조용해도 정상",
      liveness.action_for(liveness.SERVER_PING_INTERVAL_SEC + 5) == liveness.OK,
      liveness.action_for(liveness.SERVER_PING_INTERVAL_SEC + 5))
check("그보다 오래 조용하면 우리가 먼저 물어본다",
      liveness.action_for(liveness.PING_AFTER_SEC + 1) == liveness.PING)
check("그래도 답이 없으면 죽은 연결로 본다",
      liveness.action_for(liveness.DEAD_AFTER_SEC + 1) == liveness.DEAD)

# 이 순서가 뒤집히면 안 된다 - 서버가 먼저 끊으면 우리가 복구할 기회를 놓친다
check(f"서버가 끊기 전에 우리가 먼저 판단한다"
      f"({liveness.DEAD_AFTER_SEC}초 < {liveness.SERVER_TIMEOUT_SEC}초)",
      liveness.DEAD_AFTER_SEC < liveness.SERVER_TIMEOUT_SEC)
check("물어보기가 죽음 판정보다 먼저다",
      liveness.PING_AFTER_SEC < liveness.DEAD_AFTER_SEC)
check("정상일 때는 핑을 아예 안 보낸다(서버 부담 0)",
      liveness.PING_AFTER_SEC > liveness.SERVER_PING_INTERVAL_SEC,
      (liveness.PING_AFTER_SEC, liveness.SERVER_PING_INTERVAL_SEC))

# ---------- 2) 실제로 보내는 줄 ----------
sent = []
irc = build_session("irc", "home.pdlab.kr", 6667, transport=sent.append,
                    on_event=lambda e: None)
irc.my_id = "몽키"
irc.keepalive()
check(f"IRC는 PING 한 줄을 보낸다({sent})",
      len(sent) == 1 and sent[0].startswith("PING"), sent)
check("한 줄짜리라 서버에 부담이 없다", len(sent[0]) < 60, sent)

# 서버가 그 핑에 답하면(PONG) 그건 그냥 흘려보내야 한다 - 화면에 뜨면 안 된다
seen = []
irc2 = build_session("irc", "h", 1, transport=lambda p: None, on_event=seen.append)
irc2.my_id = "몽키"
irc2.handle_incoming(irc_protocol.parse_line(":home.pdlab.kr PONG home.pdlab.kr :h"))
check(f"서버의 PONG은 채팅창에 안 뜬다({[type(e).__name__ for e in seen]})", not seen, seen)

custom_sent = []
custom = build_session("custom", "h", 1, transport=custom_sent.append,
                       on_event=lambda e: None)
custom.my_id = "몽키"
custom.keepalive()
check("우리 서버에는 따로 물어볼 것이 없다(끊기면 바로 앎)", not custom_sent, custom_sent)

not_logged_in = []
fresh = build_session("irc", "h", 1, transport=not_logged_in.append, on_event=lambda e: None)
fresh.keepalive()
check("로그인 전에는 아무 것도 안 보낸다", not not_logged_in, not_logged_in)

# ---------- 3) 서버 PING에는 즉시 답하는가 ----------
# 이게 곧 연결 유지의 핵심이다. 화면 상태와 무관하게 소켓 단에서 바로 답해야 한다
from gui.network import ChatClient  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
client = ChatClient()
written = []
client.write = lambda data: written.append(bytes(data))
client._buffer = irc_protocol.encode_line("PING :home.pdlab.kr")
client._process_irc_buffer()
check(f"서버 PING에 바로 PONG으로 답한다({written})",
      written and written[0].startswith(b"PONG"), written)
check("마지막으로 받은 시각을 기록한다(연결 확인의 근거)",
      hasattr(client, "last_rx_at"))

print("=== 검증 결과 (연결 살아있음 확인) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
