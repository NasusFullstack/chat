import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
from PySide6.QtCore import Qt, QTimer, QEventLoop
import gui_client as g

app = QApplication(sys.argv)
app.setStyleSheet(g.STYLE_SHEET)

events = {"leave": []}
chat_page = g.ChatPage(
    on_send=lambda ch, text: None,
    on_add_channel=lambda: None,
    on_leave_channel=lambda ch: events["leave"].append(ch),
    on_set_avatar=lambda: None,
)
chat_page.show()
app.processEvents()

checks = []

# ---- 채널 추가 버튼(왼쪽 사이드바) ----
checks.append(("'+' 채널 추가 버튼이 있음", chat_page.channel_sidebar.add_btn.text() == "+"))
checks.append(("'+' 버튼에 툴팁 있음", bool(chat_page.channel_sidebar.add_btn.toolTip())))

# ---- 채널 나가기: 항목마다 x를 박지 않고 우클릭 메뉴로 (이미지 디자인에 맞춤) ----
chat_page.add_channel("#x")
row = chat_page.channel_sidebar.row_of("#x")
checks.append(("사이드바에 채널 줄이 생김", row >= 0))
checks.append(("우클릭으로 나갈 수 있다고 안내함",
               "우클릭" in chat_page.channel_sidebar.list.item(row).toolTip()))
checks.append(("채널 목록에 가로 스크롤이 없음",
               chat_page.channel_sidebar.list.horizontalScrollBar().maximum() == 0))

# ---- 안읽음: 채널 줄을 옅은 노랑으로 깜빡임 ----
# 글자색은 QSS(QTabBar::tab { color: ... })가 항상 이겨서 setTabTextColor()로 못 바꾼다.
# 노란 점 아이콘도 쓰다가 없앴다(요청). 지금은 채널 줄 전체를 덧칠하는 방식이다
chat_page.add_channel("#a")
chat_page.add_channel("#b", activate=False)  # #a가 활성 상태 유지

from gui.theme import UNREAD_TINT_ALPHA_OFF, UNREAD_TINT_ALPHA_ON  # noqa: E402

alphas = []


def sample():
    alphas.append(chat_page.channel_sidebar.unread_alpha("#b"))


chat_page.append_message("#b", "other", "ping", False, 0)  # #a가 활성이므로 #b는 비활성 채널

# 0~1400ms 동안 40ms 간격으로 재서 켜짐/꺼짐이 실제로 반복되는지 관찰
loop = QEventLoop()
samples_timer = QTimer()
samples_timer.timeout.connect(sample)
samples_timer.start(40)
QTimer.singleShot(1400, loop.quit)
loop.exec()
samples_timer.stop()

transitions_on_to_off = sum(
    1 for i in range(1, len(alphas))
    if alphas[i - 1] == UNREAD_TINT_ALPHA_ON and alphas[i] == UNREAD_TINT_ALPHA_OFF
)
checks.append((f"안 보는 동안 실제로 깜빡임(밝음->흐림 {transitions_on_to_off}번)",
               transitions_on_to_off >= 2))

# 채널을 실제로 보면 즉시 멈추고 노란색도 사라짐
chat_page.set_active_channel("#b")
app.processEvents()
checks.append(("채널로 전환하면 노란색이 사라짐",
               chat_page.channel_sidebar.unread_alpha("#b") == 0))
checks.append(("전환 후 깜빡임 타이머도 완전히 정리됨",
               not chat_page.channel_sidebar.is_blinking("#b")))

print("덧칠 진하기 샘플:", alphas)

print("\n=== 검증 결과 ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
