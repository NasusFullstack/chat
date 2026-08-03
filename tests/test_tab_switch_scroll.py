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

window = g.MainWindow()
window.resize(900, 600)
window.show()
window.stack.setCurrentWidget(window.chat_page)
window.chat_page.add_channel("chanA")
window.chat_page.add_channel("chanB")  # activates chanB, chanA becomes inactive
app.processEvents()

# chanA에 메시지를 잔뜩 넣어서 스크롤이 생기게 함 (지금 비활성 상태에서)
for i in range(40):
    window.chat_page.append_message("chanA", "someone", f"메시지 번호 {i} 내용입니다 좀 길게 써볼게요 가나다라마바사", False, float(i))
app.processEvents()

view_a = window.chat_page._log_views["chanA"]
sb = view_a.verticalScrollBar()
print("chanA로 전환 전 (숨겨진 상태) scrollbar value/max:", sb.value(), sb.maximum())

# chanA로 전환 (탭 클릭)
window.chat_page.set_active_channel("chanA")
app.processEvents()
print("chanA로 막 전환한 직후 scrollbar value/max:", sb.value(), sb.maximum(), "(맨 아래여야 정상 - 새 메시지 도착시 자동 스크롤 관례)")

# 사용자가 위로 스크롤해서 중간쯤 본다고 가정
sb.setValue(sb.maximum() // 2)
app.processEvents()
mid_value = sb.value()
print("사용자가 중간으로 스크롤 후:", mid_value)

# chanB로 갔다가 다시 chanA로 돌아옴 (사용자가 보고한 시나리오)
window.chat_page.set_active_channel("chanB")
app.processEvents()
window.chat_page.set_active_channel("chanA")
app.processEvents()
print("chanB 갔다가 chanA로 복귀 후 scrollbar value:", sb.value(), "(중간 유지 vs 맨 아래로 강제 리셋?)")
