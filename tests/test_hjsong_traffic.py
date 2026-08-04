"""'그 사람이 칠 때마다 채팅/참여자가 빈다'는 제보의 원인 후보를 실제 수신 경로로 훑는다.

각 단계마다 (1) 예외가 났는지 (2) 채팅이 보이는지 (3) 참여자가 남아있는지를 본다.
PySide6는 슬롯 안 예외로 앱을 죽이지 않으므로, 예외가 나면 '그 뒤 코드가 안 돌아서'
화면이 빈 채로 남는다 - 그게 이 증상의 모양이다.
사용법: test_hjsong_traffic.py <소스경로>
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import json
import os
import sys
import traceback

os.environ["QT_QPA_PLATFORM"] = "offscreen"
SRC = sys.argv[1] if len(sys.argv) > 1 else _REPO
sys.path.insert(0, SRC)

from PySide6.QtWidgets import QApplication

import gui_client as g
from fixtures import sample_history
import irc_protocol

app = QApplication.instance() or QApplication([])
app.setStyleSheet(g.STYLE_SHEET)

EXC = []
_orig = sys.excepthook


def hook(t, e, tb):
    EXC.append("".join(traceback.format_exception(t, e, tb)))


sys.excepthook = hook

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
page = win.chat_page


def feed(line):
    try:
        win.session.handle_incoming(irc_protocol.parse_line(line))
    except Exception:  # noqa: BLE001 - 실제 앱에서는 여기서 안 죽고 화면만 덜 그려짐
        EXC.append(traceback.format_exc())
    for _ in range(3):
        app.processEvents()


feed(":irc.test 001 Mong :Welcome")
feed(":Mong!u@h JOIN :#pdlab")
feed(":irc.test 353 Mong = #pdlab :Mong Ming hjsong hjsong_mobile MangMang2")
feed(":irc.test 366 Mong #pdlab :End of /NAMES list")
# 실제로 채팅 화면을 띄워야 위젯 좌표가 진짜 값이 된다(안 그러면 측정이 전부 헛것)
win.stack.setCurrentWidget(win.chat_page)
page.set_active_channel("#pdlab")
for _ in range(6):
    app.processEvents()
msgs = sample_history(200)
page.load_history("#pdlab", msgs[-40:])
for _ in range(8):
    app.processEvents()

view = page._log_views["#pdlab"]
results = []


def check(tag):
    for _ in range(5):
        app.processEvents()
    sb = view.verticalScrollBar()
    sb.setValue(sb.maximum())
    for _ in range(3):
        app.processEvents()
    top, bottom = sb.value(), sb.value() + view.viewport().height()
    # 화면에 걸쳐 있으면 보이는 것으로 셈(윗변만 보면 큰 메시지를 놓침)
    seen = sum(1 for m in view._messages
               if m.geometry().bottom() > top and m.geometry().top() < bottom)
    members = page.member_panel.list.count()
    n_exc = len(EXC)
    last = view._messages[-1].geometry().bottom() if view._messages else 0
    label = getattr(view._messages[-1], "_text_label", None) if view._messages else None
    print(f"   {tag:30s} 메시지 {seen:2d} / 참여자 {members} / 예외 {n_exc}"
          f" | 내용높이 {view.widget().height()} 끝 {last}"
          f" | 기준폭 {view._container_width} 뷰포트 {view.viewport().width()}"
          f" 라벨최대 {label.maximumWidth() if label else '-'}"
          f" 레이아웃sizeHint {view.widget().layout().sizeHint().height()}")
    results.append((tag, seen, members, n_exc))


check("정상 상태")

# (a) 아이콘이 깨진 값으로 올 때
feed(":hjsong!u@h PRIVMSG #pdlab :\x01FCAVATAR abc 1/1 !!!이건base64가아님!!!\x01")
check("(a) 깨진 아이콘 프레임")

# (b) 조각이 빠진 아이콘(1/3만 옴)
feed(":hjsong!u@h PRIVMSG #pdlab :\x01FCAVATAR xy 1/3 QUJD\x01")
check("(b) 조각 빠진 아이콘")

# (c) mIRC 색/굵게 같은 제어문자가 섞인 메시지(모바일/다른 클라이언트가 자주 보냄)
feed(":hjsong!u@h PRIVMSG #pdlab :\x0304빨간글씨\x03 \x02굵게\x02 보통")
check("(c) 색/굵기 제어문자")

# (d) HTML처럼 생긴 문자열
feed(":hjsong!u@h PRIVMSG #pdlab :<div style='x'>테스트</div> <b>굵게")
check("(d) HTML처럼 생긴 메시지")

# (e) 모바일이 재접속을 반복(입장/퇴장) - 그때마다 아이콘 교환이 일어남
for i in range(3):
    feed(":hjsong_mobile!u@h QUIT :Ping timeout")
    feed(":hjsong_mobile!u@h JOIN :#pdlab")
    feed(f":hjsong!u@h PRIVMSG #pdlab :모바일 재접속 사이 메시지 {i}")
check("(e) 모바일 재접속 반복")

# (f) 그 사람이 닉네임을 바꿀 때
feed(":hjsong!u@h NICK :희준")
feed(":희준!u@h PRIVMSG #pdlab :닉 바꾸고 한마디")
check("(f) 닉네임 변경 후 메시지")

# (g) 아주 긴 한 줄(512 근처)
feed(":MangMang2!u@h PRIVMSG #pdlab :" + "가" * 150)
check("(g) 아주 긴 메시지")

# (h) 그 사람이 나를 호출(@Mong) - 알림 경로(창 흔들기/작업표시줄) 포함
feed(":MangMang2!u@h PRIVMSG #pdlab :@Mong 이거 봐봐")
check("(h) @호출 알림")

print("\n=== 결과 ===")
bad = [r for r in results if r[1] == 0 or r[2] == 0 or r[3] > 0]
for tag, seen, members, n in results:
    print(f"[{'FAIL' if (seen == 0 or members == 0 or n > 0) else 'OK'}] {tag}"
          f" (메시지 {seen}, 참여자 {members}, 누적예외 {n})")
if EXC:
    print("\n=== 발생한 예외 ===")
    for e in EXC:
        print(e)
sys.exit(1 if bad else 0)
