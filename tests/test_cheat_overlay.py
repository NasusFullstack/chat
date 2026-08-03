"""show me the money 치트: 코어 판정(쿨타임/전파) + GUI 오버레이 동작 검증."""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication
import gui_client as g
from chat_core import events
from chat_core.constants import CHEAT_COOLDOWN_SEC
from chat_core.session import build_session
from chat_core.history_adapter import NullHistoryStore
from gui.cheat_overlay import CheatOverlay, TARGET_AMOUNT

app = QApplication(sys.argv)
app.setStyleSheet(g.STYLE_SHEET)
checks = []

# ===== 코어: 치트 전송/쿨타임/전파 =====
sent, evs = [], []
s = build_session("custom", "h", 1, transport=lambda p: sent.append(p),
                  on_event=lambda e: evs.append(e), history_store=NullHistoryStore())
s.my_id = "me"

n = len(sent)
s.send_message("#c", "show me the money")
checks.append(("치트 첫 사용은 정상 전송", len(sent) == n + 1))

n = len(sent)
s.send_message("#c", "show me the money")
checks.append(("같은 채널 쿨타임 중에는 전송 자체가 막힘", len(sent) == n))
checks.append(("CheatBlocked 이벤트로 남은 시간 안내",
               isinstance(evs[-1], events.CheatBlocked) and 0 < evs[-1].remaining_sec <= CHEAT_COOLDOWN_SEC + 1))

n = len(sent)
s.send_message("#other", "show me the money")
checks.append(("다른 채널은 쿨타임과 무관하게 사용 가능(채널당 쿨타임)", len(sent) == n + 1))

# 대소문자/공백 허용
s.cheat_cooldowns.clear()
n = len(sent)
s.send_message("#c", "  SHOW ME THE MONEY  ")
checks.append(("대소문자/앞뒤공백 달라도 치트로 인식", len(sent) == n + 1))

# 수신 시 채널 전원에게 전파 (내가 친 것도 포함)
evs.clear()
s.handle_incoming({"type": "chat", "channel": "#c", "from": "someone", "text": "show me the money", "ts": 1.0})
checks.append(("남이 친 치트도 CheatActivated로 전파",
               any(isinstance(e, events.CheatActivated) and e.channel == "#c" for e in evs)))
evs.clear()
s.handle_incoming({"type": "chat", "channel": "#c", "from": "me", "text": "show me the money", "ts": 2.0})
checks.append(("내가 친 치트도 내 화면에 뜸", any(isinstance(e, events.CheatActivated) for e in evs)))

evs.clear()
s.handle_incoming({"type": "chat", "channel": "#c", "from": "x", "text": "그냥 잡담", "ts": 3.0})
checks.append(("일반 메시지는 치트로 오인 안 함",
               not any(isinstance(e, events.CheatActivated) for e in evs)))

# ===== GUI: 오버레이 =====
chat_page = g.ChatPage(on_send=lambda a, b: None, on_add_channel=lambda: None,
                       on_leave_channel=lambda c: None, on_set_avatar=lambda: None)
chat_page.resize(800, 500)
chat_page.show()
chat_page.add_channel("#c")
app.processEvents()

ov = chat_page._cheat_overlay
checks.append(("평소엔 오버레이가 안 보임", not ov.isVisible()))

chat_page.show_resource_cheat()
app.processEvents()
checks.append(("치트 발동 시 오버레이가 보임", ov.isVisible()))
checks.append(("0부터 시작", ov._value == 0))

# 롤링이 실제로 올라가는지
start = time.time()
while time.time() - start < 1.0:
    app.processEvents()
    time.sleep(0.02)
mid = ov._value
checks.append(("숫자가 0에서 위로 올라감", 0 < mid <= TARGET_AMOUNT))

# 끝까지 기다리면 10000 찍고 사라지는지
start = time.time()
reached = mid >= TARGET_AMOUNT
while time.time() - start < 3.0:
    app.processEvents()
    if ov._value >= TARGET_AMOUNT:
        reached = True
    if not ov.isVisible():
        break
    time.sleep(0.02)
checks.append((f"최대 {TARGET_AMOUNT}까지 올라감", reached))
checks.append(("다 보여준 뒤 자동으로 사라짐", not ov.isVisible()))

# 테두리/배경 없이 겹쳐 뜨는지 (투명 속성)
from PySide6.QtCore import Qt
checks.append(("배경 투명(테두리 없음)", ov.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)))
checks.append(("마우스 클릭을 가로채지 않음", ov.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)))

print("\n=== 검증 결과 (show me the money 치트) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
