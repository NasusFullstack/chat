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
window.chat_page.add_channel("chanA")   # activates chanA
window.chat_page.add_channel("chanB")   # activates chanB, chanA becomes hidden/inactive
app.processEvents()

view_a = window.chat_page._log_views["chanA"]
print("chanA (never actually shown/current) geometry:", view_a.geometry())
print("chanA viewport width (hidden):", view_a.viewport().width())
print("chanA isVisible:", view_a.isVisible())

# 이 상태에서 (숨겨진 채로) 메시지 추가
long_text = "가나다라마바사아자차카타파하 " * 20
window.chat_page.append_message("chanA", "someone", long_text, False, 0.0)
app.processEvents()
w = view_a._messages[0]
print("append 시점 text_label maximumWidth:", w._text_label.maximumWidth())
sb = view_a.verticalScrollBar()
print("append 직후 scrollbar value/max (숨김 상태):", sb.value(), sb.maximum())

# 실제로 chanA로 전환
window.chat_page.set_active_channel("chanA")
app.processEvents()
print()
print("=== chanA로 전환 직후 ===")
print("scrollbar value/max:", sb.value(), sb.maximum())
print("text_label maximumWidth:", w._text_label.maximumWidth())
print("text_label actual width/height:", w._text_label.width(), w._text_label.height())

# 사용자가 맨 아래로 스크롤 시도 (이미 맨아래겠지만 명시)
sb.setValue(sb.maximum())
app.processEvents()
print()
print("맨아래로 맞춘 후:", sb.value(), sb.maximum())

# 다시 chanB로 갔다가 chanA로 복귀 (반복)
for i in range(3):
    window.chat_page.set_active_channel("chanB")
    app.processEvents()
    window.chat_page.set_active_channel("chanA")
    app.processEvents()
    print(f"[반복 {i+1}] chanB 갔다옴 후 scrollbar value/max:", sb.value(), sb.maximum())
