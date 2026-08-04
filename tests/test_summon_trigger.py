"""소환이 '죽은 공간'을 만드는 방아쇠인지 - 소환 직전/직후를 같은 조건에서 비교.

오버레이를 띄우면 그 부모(가운데 스택)에 배치 요청이 생기고, 스크롤 영역이 안쪽 위젯
높이를 다시 계산한다. 계산식이 틀려 있으면 바로 그 순간 죽은 공간이 생긴다.
사용법: test_summon_trigger.py <소스경로>
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import json
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
SRC = sys.argv[1] if len(sys.argv) > 1 else _REPO
sys.path.insert(0, SRC)

from PySide6.QtWidgets import QApplication

import gui_client as g
from fixtures import sample_history
import irc_protocol

app = QApplication.instance() or QApplication([])
app.setStyleSheet(g.STYLE_SHEET)

win = g.MainWindow()
win.resize(880, 700)
win.show()
app.processEvents()
lp = win.login_page
lp.protocol_combo.setCurrentIndex(lp.protocol_combo.findData("irc"))
lp.host_input.setText("127.0.0.1")
lp.port_input.setText("16700")
lp.ssl_checkbox.setChecked(False)
lp.user_input.setText("Mong")
win._handle_login_submit("login")
app.processEvents()


def feed(line):
    win.session.handle_incoming(irc_protocol.parse_line(line))
    for _ in range(2):
        app.processEvents()


feed(":irc.test 001 Mong :Welcome")
feed(":Mong!u@h JOIN :#pdlab")
feed(":irc.test 353 Mong = #pdlab :Mong Ming hjsong MangMang2")
feed(":irc.test 366 Mong #pdlab :End of /NAMES list")
page = win.chat_page
win.stack.setCurrentWidget(page)
page.set_active_channel("#pdlab")
for _ in range(6):
    app.processEvents()
msgs = sample_history(200)
page.load_history("#pdlab", msgs[-60:])
for _ in range(10):
    app.processEvents()

view = page._log_views["#pdlab"]
content = view.widget()
layout = content.layout()


def report(tag):
    for _ in range(6):
        app.processEvents()
    sb = view.verticalScrollBar()
    sb.setValue(sb.maximum())
    for _ in range(4):
        app.processEvents()
    bottom = 0
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if w is not None and not w.isHidden():
            bottom = max(bottom, w.geometry().bottom() + 1)
    top, view_bottom = sb.value(), sb.value() + view.viewport().height()
    seen = sum(1 for m in view._messages
               if m.geometry().bottom() > top and m.geometry().top() < view_bottom)
    dead = content.height() - bottom - layout.contentsMargins().bottom()
    print(f"   {tag:26s} 보이는 메시지 {seen:2d} / 죽은 공간 {dead:5d}px"
          f" / 입력창 사용가능={page.message_input.line.isEnabled()}"
          f" / 참여자 {page.member_panel.list.count()}")
    return seen, dead


print(f"소스: {SRC}")
report("소환 전")
page.summon_battlecruiser()
report("소환 직후")
for _ in range(20):
    page._battlecruiser._tick()
    app.processEvents()
report("비행 중")
# 소환된 상태에서 새 메시지가 오면 보이는가(사용자가 '채팅이 안 쳐진다'고 한 상황)
for i in range(3):
    feed(f":hjsong!u@h PRIVMSG #pdlab :소환된 상태에서 온 메시지 {i}")
seen_after, dead_after = report("소환 상태에서 새 메시지")
win._handle_send("#pdlab", "내가 친 메시지")
seen_mine, dead_mine = report("소환 상태에서 내가 침")
page.dismiss_battlecruiser()
for _ in range(30):
    page._battlecruiser._tick()
    app.processEvents()
report("해제 후")

ok = seen_after > 0 and seen_mine > 0
print(f"\n소환된 상태에서도 새 메시지가 보이는가: {'예' if ok else '아니오'}")
sys.exit(0 if ok else 1)
