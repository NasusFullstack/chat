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
# 안읽음 표시는 탭 글자색이 아니라 **채널 줄 전체를 옅은 노랑으로 덧칠**하는 방식이다
# (QSS가 색을 정한 자리는 코드로 못 바꾼다 - CLAUDE.md 4번). 그래서 진하기를 본다
sidebar = chat_page.channel_sidebar
samples = []


def sample():
    samples.append(sidebar.unread_alpha("#b"))


chat_page.append_message("#b", "other", "ping", False, 0)

loop = QEventLoop()
timer = QTimer()
timer.timeout.connect(sample)
timer.start(20)
# 4번 깜빡이는 데 필요한 시간(350ms * (2*4-1) = 2450ms)보다 넉넉하게 대기
QTimer.singleShot(3200, loop.quit)
loop.exec()
timer.stop()

from gui.theme import (UNREAD_TINT_ALPHA_IDLE, UNREAD_TINT_ALPHA_OFF,
                       UNREAD_TINT_ALPHA_ON)

bright = UNREAD_TINT_ALPHA_ON
dim = UNREAD_TINT_ALPHA_OFF
on_to_off = sum(1 for i in range(1, len(samples))
                if samples[i - 1] == bright and samples[i] == dim)
checks.append((f"정해진 횟수만큼 깜빡임(밝음->흐림 {on_to_off}번)",
               on_to_off == g.UNREAD_BLINK_COUNT - 1))
checks.append(("깜빡임이 끝나면 타이머가 정리됨", not sidebar.is_blinking("#b")))
checks.append((f"멈춘 뒤에도 노란색이 남아 있음(진하기 {samples[-1]})",
               samples[-1] == UNREAD_TINT_ALPHA_IDLE))

# 그 채널을 실제로 봐야 노란색이 사라진다
chat_page.set_active_channel("#b")
app.processEvents()
checks.append(("채널을 보면 노란색이 사라짐", sidebar.unread_alpha("#b") == 0))

print("\n=== 검증 결과 (로그인 기본값 + 안읽음 4번 깜빡임 후 유지) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
