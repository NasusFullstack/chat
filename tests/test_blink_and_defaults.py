import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QEventLoop
import gui_client as g

app = QApplication(sys.argv)
app.setStyleSheet(g.STYLE_SHEET)

checks = []

# ---- 로그인 기본값 ----
window = g.MainWindow()
window.show()
app.processEvents()
lp = window.login_page
checks.append(("기본 프로토콜이 실제 IRC 서버", lp.protocol_combo.currentData() == "irc"))
checks.append(("기본 주소가 home.pdlab.kr", lp.host_input.text() == "home.pdlab.kr"))
checks.append(("기본 SSL이 꺼짐", lp.ssl_checkbox.isChecked() is False))
checks.append(("SSL 꺼짐에 맞춰 포트도 평문 포트로", lp.port_input.text() == g.DEFAULT_PLAIN_PORT))
checks.append(("IRC 기본 선택에 맞춰 닉네임 플레이스홀더로 바뀜(크래시 없이)", lp.user_input.placeholderText() == "닉네임"))
checks.append(("로그인 버튼 텍스트도 '접속'으로 바뀜", lp.login_btn.text() == "접속"))
checks.append(("회원가입 버튼은 숨겨짐(IRC엔 없음)", lp.register_btn.isVisible() is False))

# ---- 안읽음 깜빡임: 4번 깜빡이고 밝은 색 유지 ----
chat_page = g.ChatPage(
    on_send=lambda a, b: None, on_add_channel=lambda: None,
    on_leave_channel=lambda c: None, on_set_avatar=lambda: None,
)
chat_page.show()
chat_page.add_channel("#a")
chat_page.add_channel("#b", activate=False)
idx_b = chat_page.tabs.indexOf(chat_page._log_views["#b"])

samples = []


def sample():
    samples.append(chat_page.tabs.tabBar().tabTextColor(idx_b).name() == g.UNREAD_BLINK_COLOR)


chat_page.append_message("#b", "other", "ping", False, 0)

loop = QEventLoop()
timer = QTimer()
timer.timeout.connect(sample)
timer.start(20)
# 4번 깜빡이는데 필요한 시간(350ms * (2*4-1) = 2450ms)보다 넉넉하게 대기
QTimer.singleShot(3200, loop.quit)
loop.exec()
timer.stop()

on_count = sum(1 for s in samples if s)
transitions_on_to_off = sum(1 for i in range(1, len(samples)) if samples[i - 1] and not samples[i])
checks.append(("정확히 4번 깜빡인 뒤(off로 안 바뀌고) 멈춤 - on->off 전환이 3번만 있음", transitions_on_to_off == g.UNREAD_BLINK_COUNT - 1))
checks.append(("타이머가 멈추고 밝은 색 상태로 유지됨(탭 사전에 없음)", "#b" not in chat_page._unread_timers))
checks.append(("깜빡임이 끝난 뒤에도 탭 글자색은 계속 밝은 색", samples[-1] is True))

# 탭을 실제로 보면 그제서야 기본 색으로 돌아옴
chat_page.set_active_channel("#b")
app.processEvents()
checks.append(("탭을 보면 그제서야 기본 색으로 돌아옴", chat_page.tabs.tabBar().tabTextColor(idx_b).name() != g.UNREAD_BLINK_COLOR))

print("\n=== 검증 결과 (로그인 기본값 + 안읽음 4번 깜빡임 후 유지) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
