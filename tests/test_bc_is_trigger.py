"""배틀크루저가 정말 원인인지 - 두 가지를 v1.8.1에서 직접 확인.

(A) 남이 소환했을 때 내 클라이언트에서 뭔가 일어나는가?
(B) 소환/해제 자체가 채팅 화면을 비게 만드는가? (대화 200건을 얹은 상태에서)
사용법: test_bc_is_trigger.py <소스경로>
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
print(f"소스: {SRC}\n")

# ---------- (A) 남이 소환할 때 ----------
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
    for _ in range(3):
        app.processEvents()


feed(":irc.test 001 Mong :Welcome")
feed(":Mong!u@h JOIN :#pdlab")
feed(":irc.test 353 Mong = #pdlab :Mong Ming hjsong hjsong_mobile MangMang2")
feed(":irc.test 366 Mong #pdlab :End of /NAMES list")

bc = win.chat_page._battlecruiser
print("(A) 남이 소환했을 때 내 화면")
for who in ("hjsong_mobile", "MangMang2", "Ming"):
    feed(f":{who}!u@h PRIVMSG #pdlab :배틀크루저 소환")
    print(f"    {who} 소환 -> 내 배틀크루저 보임={bc.isVisible()}"
          f" / 참여자 {len(win.chat_page.member_panel._members.get('#pdlab', []))}명")
a_ok = not bc.isVisible()

# ---------- (B) 내가 소환할 때 채팅이 비는가 ----------
msgs = sample_history(200)
page = g.ChatPage(on_send=lambda c, t: None, on_add_channel=lambda: None,
                  on_leave_channel=lambda c: None, on_set_avatar=lambda: None)
page.resize(880, 700)
page.show()
page.my_id = "Mong"
page.add_channel("#pdlab")
page.set_active_channel("#pdlab")
for _ in range(6):
    app.processEvents()
page.load_history("#pdlab", msgs)
for _ in range(8):
    app.processEvents()
view = page._log_views["#pdlab"]


def visible_count(tag):
    for _ in range(6):
        app.processEvents()
    sb = view.verticalScrollBar()
    sb.setValue(sb.maximum())
    for _ in range(4):
        app.processEvents()
    top, bottom = sb.value(), sb.value() + view.viewport().height()
    n = sum(1 for m in view._messages if top <= m.geometry().top() <= bottom)
    content = view.widget()
    print(f"    [{tag}] 보이는 메시지 {n:2d}개 / 내용높이 {content.height()}"
          f" / 스크롤최대 {sb.maximum()}")
    return n


print("\n(B) 내가 소환/해제할 때 채팅 화면")
b0 = visible_count("소환 전")
page.summon_battlecruiser()
b1 = visible_count("소환 직후")
for _ in range(30):
    page._battlecruiser._tick()
    app.processEvents()
b2 = visible_count("비행 중")
page.dismiss_battlecruiser()
for _ in range(40):
    page._battlecruiser._tick()
    app.processEvents()
b3 = visible_count("해제 후")

print("\n=== 결과 ===")
print(f"[{'OK' if a_ok else 'FAIL'}] 남이 소환해도 내 화면에는 아무 일도 안 일어난다")
b_ok = min(b1, b2, b3) > 0
print(f"[{'OK' if b_ok else 'FAIL'}] 소환/비행/해제 중에도 채팅이 계속 보인다"
      f" ({b0} -> {b1} -> {b2} -> {b3})")
sys.exit(0 if (a_ok and b_ok) else 1)
