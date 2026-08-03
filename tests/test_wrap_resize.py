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

view = g.ChannelLogView("test")
view.resize(600, 400)
view.show()
app.processEvents()

long_text = "가나다라마바사아자차카타파하 " * 30
pix = g._hashed_avatar_pixmap("someone")
view.append_message("someone", long_text, False, 0.0, pix)
app.processEvents()

w = view._messages[0]
print("initial viewport width:", view.viewport().width())
print("initial text_label width:", w._text_label.width(), "height:", w._text_label.height())
print("initial text_label maximumWidth:", w._text_label.maximumWidth())
print("initial widget width:", w.width(), "height:", w.height())

# Now shrink the window (simulate resizing app narrower)
view.resize(250, 400)
app.processEvents()
print()
print("after resize -> viewport width:", view.viewport().width())
print("after resize -> text_label width:", w._text_label.width(), "height:", w._text_label.height())
print("after resize -> text_label maximumWidth:", w._text_label.maximumWidth())
print("after resize -> widget width:", w.width(), "height:", w.height())
