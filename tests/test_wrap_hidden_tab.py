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
avatar = g._hashed_avatar_pixmap("t")

chat_page = g.ChatPage(
    on_send=lambda a, b: None, on_add_channel=lambda: None,
    on_leave_channel=lambda c: None, on_set_avatar=lambda: None,
)
chat_page.resize(300, 400)
chat_page.show()
app.processEvents()

chat_page.add_channel("#a")  # 활성 채널
chat_page.add_channel("#b", activate=False)  # #a가 계속 활성 상태 - #b는 안 보이는 채널
app.processEvents()

long_text = "매우 긴 텍스트를 넣어서 줄바꿈이 필요한 메시지를 시험합니다 " * 5
chat_page.append_message("#b", "other", long_text, False, 0)
# #b 탭은 지금 화면에 안 보이는 상태로 메시지가 쌓임 - resizeEvent/showEvent가
# 한 번도 안 왔을 수 있는 상황을 재현
app.processEvents()

view_b = chat_page._log_views["#b"]
w = view_b._layout.itemAt(0).widget()
print("탭 비활성 상태에서의 maximumWidth:", w._text_label.maximumWidth())

# 이제 실제로 #b 탭으로 전환(사용자가 그 채널을 봄)
# 폭은 ChatPage.add_channel() 시점에 이미 self.tabs.width() 기준으로 미리 반영돼있으므로
# (탭 전환 순간에 재계산하는 게 아니라 - 그게 스크롤 출렁임의 원인이었음), 전환 전후로
# 값이 똑같이 유지되면서도 실제 뷰포트 폭 근처(scrollbar 등 chrome만큼의 오차 허용)여야 함
chat_page.set_active_channel("#b")
app.processEvents()
app.processEvents()

viewport_based = max(40, view_b.viewport().width() - g.AVATAR_MSG_PX - 24)
checks.append(("탭 전환 전에 이미 뷰포트 폭 근처로 미리 반영돼있었음(±40px 오차 허용)",
               abs(w._text_label.maximumWidth() - viewport_based) <= 40))
checks.append(("탭 전환 후 실제 렌더링 폭이 뷰포트를 넘지 않음",
               w.width() <= view_b.viewport().width() + 2))

print("\n=== 검증 결과 (비활성 탭에 쌓인 메시지의 줄바꿈 - 탭 전환 시 보정) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
