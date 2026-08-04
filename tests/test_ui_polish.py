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

# ---- 안읽음: 탭 아이콘이 빠르게(반복적으로) 깜빡임 (글자색은 QTabBar::tab { color: ... }
# 스타일시트가 항상 이겨서 setTabTextColor()로는 절대 안 바뀌길래 아이콘 방식으로 바꿈) ----
chat_page.add_channel("#a")
chat_page.add_channel("#b", activate=False)  # #a가 활성 상태 유지
idx_b = chat_page.tabs.indexOf(chat_page._log_views["#b"])

color_states = []


def sample():
    color_states.append(not chat_page.tabs.tabBar().tabIcon(idx_b).isNull())


chat_page.append_message("#b", "other", "ping", False, 0)  # #a가 활성이므로 #b는 비활성 채널

# 0~1400ms 동안 40ms 간격으로 샘플링해서 계속 반복되는 on/off 패턴을 관찰
loop = QEventLoop()
samples_timer = QTimer()
samples_timer.timeout.connect(sample)
samples_timer.start(40)
QTimer.singleShot(1400, loop.quit)
loop.exec()
samples_timer.stop()

# on->off 전환 횟수를 세서 "두 번만 깜빡이고 멈추는 게 아니라 계속 반복"되는지 확인
transitions_on_to_off = sum(
    1 for i in range(1, len(color_states)) if color_states[i - 1] and not color_states[i]
)
checks.append(("탭을 안 보는 동안 계속 반복해서 깜빡임(멈추지 않음)", transitions_on_to_off >= 2))

# 탭으로 전환하면 즉시 깜빡임이 멈추고 원래 색으로 돌아옴
chat_page.set_active_channel("#b")
app.processEvents()
checks.append(("탭으로 전환하면 깜빡임이 멈추고 아이콘이 사라짐",
               chat_page.tabs.tabBar().tabIcon(idx_b).isNull()))
checks.append(("전환 후 깜빡임 타이머도 완전히 정리됨", "#b" not in chat_page._unread_timers))

print("color_states 샘플:", color_states)

print("\n=== 검증 결과 ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
