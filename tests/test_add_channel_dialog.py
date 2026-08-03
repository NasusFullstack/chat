import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)
from PySide6.QtWidgets import QApplication
import gui_client as g

app = QApplication(sys.argv)
app.setStyleSheet(g.STYLE_SHEET)

checks = []

window = g.MainWindow()

calls = []
orig_send_irc = window.client.send_irc
window.client.send_irc = lambda line: calls.append(line)

# 프로토콜은 이제 세션이 단일 출처라, IRC 모드를 흉내내려면 IRC 세션을 실제로 만들어야 함
# (예전처럼 window._protocol_mode만 바꾸는 건 이제 불가능 - 읽기 전용 파생 속성)
from chat_core.session import build_session
from chat_core.history_adapter import NullHistoryStore
window.session = build_session(
    "irc", "127.0.0.1", 6667,
    transport=window.client.send_irc,
    on_event=window._on_domain_event,
    history_store=NullHistoryStore(),
)

call_count = {"n": 0}
orig_get_text = g.themed_get_text


def fake_get_text(parent, title, label, echo_mode=None):
    call_count["n"] += 1
    if call_count["n"] == 1:
        return "#newchan", True
    return "", True  # 비밀번호는 빈 값


g.themed_get_text = fake_get_text
window._handle_add_channel()
g.themed_get_text = orig_get_text

checks.append(("themed_get_text가 두 번(채널명/비번) 호출됨", call_count["n"] == 2))
checks.append(("IRC JOIN 명령이 전송됨", any("JOIN #newchan" in c for c in calls)))

window.client.send_irc = orig_send_irc

print("\n=== 검증 결과 (채널 추가 - 테마 입력창 연동) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
