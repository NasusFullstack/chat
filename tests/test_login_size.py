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
window.show()
app.processEvents()
app.processEvents()

print("window size:", window.size())
print("titlebar height:", window._title_bar.height() if window._title_bar else None)
print("stack size:", window.stack.size())
print("login_page sizeHint:", window.login_page.sizeHint())
print("login_page minimumSizeHint:", window.login_page.minimumSizeHint())
print("login_page actual size:", window.login_page.size())
print("channel_page minimumSizeHint:", window.channel_page.minimumSizeHint())
print("chat_page minimumSizeHint:", window.chat_page.minimumSizeHint())
