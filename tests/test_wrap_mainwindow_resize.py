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
app.processEvents()

# 채팅 페이지를 강제로 세팅 (실제 로그인/입장 플로우 없이 렌더링만 검증)
window.stack.setCurrentWidget(window.chat_page)
window.chat_page.add_channel("testchan")
app.processEvents()

long_text = "가나다라마바사아자차카타파하 " * 30
pix = g._hashed_avatar_pixmap("someone")
window.chat_page.append_message("testchan", "someone", long_text, False, 0.0)
app.processEvents()

view = window.chat_page._log_views["testchan"]
w = view._messages[0]
print("=== 초기 (900x600 창) ===")
print("viewport width:", view.viewport().width())
print("text_label width:", w._text_label.width(), "height:", w._text_label.height())
print("view geometry:", view.geometry())

window.resize(500, 600)
app.processEvents()
app.processEvents()

print()
print("=== 리사이즈 후 (500x600 창) ===")
print("viewport width:", view.viewport().width())
print("text_label width:", w._text_label.width(), "height:", w._text_label.height())
print("view geometry:", view.geometry())
