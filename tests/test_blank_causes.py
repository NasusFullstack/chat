"""제보: "채팅 내용이 다 사라지고 참여자도 다 사라져서 빈 공간으로 보여"

원인 두 가지를 각각 재현해서 고쳐졌는지 확인한다.
1) 참여자 목록: 353 없이 366(End of NAMES)만 오면 목록이 통째로 비워지는가
2) 채팅 내용: 안쪽 위젯 높이가 실제보다 커서, 맨 아래로 내리면 화면이 통째로 빈 공간인가
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
SRC = sys.argv[1] if len(sys.argv) > 1 else _REPO
sys.path.insert(0, SRC)

import json

from PySide6.QtWidgets import QApplication

import gui_client as g
from fixtures import sample_history
import irc_protocol

app = QApplication.instance() or QApplication([])
app.setStyleSheet(g.STYLE_SHEET)

print(f"소스: {SRC}\n")
checks = []

# ---------- 1) 참여자 목록 ----------
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
session = win.session


def feed(line):
    session.handle_incoming(irc_protocol.parse_line(line))
    for _ in range(3):
        app.processEvents()


feed(":irc.test 001 Mong :Welcome")
feed(":Mong!u@h JOIN :#pdlab")
feed(":irc.test 353 Mong = #pdlab :Mong Ming hjsong hjsong_mobile MangMang2")
feed(":irc.test 366 Mong #pdlab :End of /NAMES list")
before = len(win.chat_page._members.get("#pdlab", []))

# (a) 353 없이 366만 한 번 더 - 다른 데서 NAMES를 부르거나 응답이 겹칠 때 실제로 생김
feed(":irc.test 366 Mong #pdlab :End of /NAMES list")
after_bare = len(win.chat_page._members.get("#pdlab", []))

# (b) 채널 이름 대소문자가 다르게 돌아오는 경우
feed(":irc.test 353 Mong = #PDLab :Mong Ming hjsong hjsong_mobile MangMang2")
feed(":irc.test 366 Mong #pdlab :End of /NAMES list")
after_case = len(win.chat_page._members.get("#pdlab", []))

print(f"1) 참여자 수: 정상 수신 {before}명 -> 빈 366 뒤 {after_bare}명"
      f" -> 대소문자 다른 353/366 뒤 {after_case}명")
checks.append(("빈 366이 와도 참여자 목록이 안 비워진다", after_bare == before))
checks.append(("353과 366의 채널 대소문자가 달라도 목록이 유지된다", after_case == before))

# ---------- 2) 채팅 내용 ----------
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
for _ in range(6):
    app.processEvents()

view = page._log_views["#pdlab"]


def empty_at_bottom(width):
    """맨 아래로 내렸을 때 화면에 메시지가 하나도 안 보이면 '빈 공간'으로 보인다"""
    page.resize(width, 700)
    for _ in range(8):
        app.processEvents()
    sb = view.verticalScrollBar()
    sb.setValue(sb.maximum())
    for _ in range(6):
        app.processEvents()
    top = sb.value()
    bottom = top + view.viewport().height()
    visible = 0
    for m in view._messages:
        y = m.geometry().top()
        if top <= y <= bottom:
            visible += 1
    content = view.widget()
    layout = content.layout()
    last = 0
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if w is not None and w.isVisible():
            last = max(last, w.geometry().bottom())
    dead = content.height() - last
    print(f"   창 폭 {width}: 화면에 보이는 메시지 {visible}개 /"
          f" 아래 빈 공간 {dead}px (보이는 높이 {view.viewport().height()})")
    return visible, dead


print("2) 맨 아래로 내렸을 때")
v1, d1 = empty_at_bottom(880)
v2, d2 = empty_at_bottom(700)
v3, d3 = empty_at_bottom(560)
checks.append(("맨 아래에서 메시지가 보인다(880)", v1 > 0))
checks.append(("맨 아래에서 메시지가 보인다(700)", v2 > 0))
checks.append(("맨 아래에서 메시지가 보인다(560)", v3 > 0))
checks.append(("빈 공간이 화면 높이를 넘지 않는다",
               max(d1, d2, d3) < view.viewport().height()))

print("\n=== 검증 결과 ===")
ok_all = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    ok_all = ok_all and ok
print("\n전체 통과:", ok_all)
sys.exit(0 if ok_all else 1)
