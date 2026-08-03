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

chat_page = g.ChatPage(
    on_send=lambda ch, text: None, on_add_channel=lambda: None,
    on_leave_channel=lambda ch: None, on_set_avatar=lambda: None,
)
chat_page.my_id = "me"
chat_page.resize(420, 300)
chat_page.show()
chat_page.add_channel("#test")
chat_page.append_message("#test", "alice", "안녕하세요 짧은 메시지", False, 1700000000.0)
chat_page.append_message("#test", "me", "네 저도 반갑습니다", True, 1700000060.0)
chat_page.append_message("#test", "bob", "이건 꽤 긴 메시지라서 줄바꿈이 될 수도 있는 텍스트를 넣어봅니다 얼마나 자연스럽게 보이는지 확인", False, 1700000120.0)
app.processEvents()
app.processEvents()

pixmap = chat_page.grab()
pixmap.save(_os.path.join(_HERE, "msgwidget_preview.png"))
print("saved preview")
