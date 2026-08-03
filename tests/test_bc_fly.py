"""배틀크루저를 '실제로 방향키로 날리면서' 채팅/참여자가 살아있는지 본다.

앞선 테스트는 소환만 하고 가만히 뒀다(제자리 부유). 사용자는 방향키로 화면 끝까지
몰고 다니므로 그 경로를 실제 키 이벤트로 재현한다. 날아다니는 도중에 메시지도 들어오고
창 크기도 바뀌는 상황까지 섞는다.
사용법: test_bc_fly.py <소스경로>
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

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

import gui_client as g
from fixtures import sample_history

app = QApplication.instance() or QApplication([])
app.setStyleSheet(g.STYLE_SHEET)
print(f"소스: {SRC}\n")

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
page.update_userlist("#pdlab", ["Mong", "Ming", "hjsong", "hjsong_mobile", "MangMang2"])
for _ in range(8):
    app.processEvents()

view = page._log_views["#pdlab"]
bc = page._battlecruiser


def press(key, down=True):
    """실제 키 이벤트를 입력창에 보냄(오버레이가 이벤트 필터로 가로채는 그 경로)"""
    ev = QKeyEvent(QEvent.Type.KeyPress if down else QEvent.Type.KeyRelease,
                   key, Qt.KeyboardModifier.NoModifier)
    app.sendEvent(page.msg_input, ev)


def snap(tag):
    for _ in range(5):
        app.processEvents()
    sb = view.verticalScrollBar()
    sb.setValue(sb.maximum())
    for _ in range(3):
        app.processEvents()
    top, bottom = sb.value(), sb.value() + view.viewport().height()
    seen = sum(1 for m in view._messages if top <= m.geometry().top() <= bottom)
    members = len(page._members.get("#pdlab", []))
    print(f"    [{tag:22s}] 보이는 메시지 {seen:2d} / 참여자 {members} /"
          f" 배 위치 ({bc.x()},{bc.y()}) 보임={bc.isVisible()} /"
          f" 내용높이 {view.widget().height()}")
    return seen, members


results = []
results.append(("소환 전", *snap("소환 전")))
page.summon_battlecruiser()
results.append(("소환 직후", *snap("소환 직후")))

# 방향키로 실제 비행 - 위/오른쪽/아래/왼쪽으로 끝까지 몰아본다
for key, name in ((Qt.Key.Key_Up, "위"), (Qt.Key.Key_Right, "오른쪽"),
                  (Qt.Key.Key_Down, "아래"), (Qt.Key.Key_Left, "왼쪽")):
    press(key, True)
    for i in range(60):
        bc._tick()
        app.processEvents()
        if i == 30:  # 날아다니는 도중에 새 메시지가 들어오는 상황
            page.append_message("#pdlab", "hjsong", f"{name}으로 나는 중 메시지", False, 1.0)
    press(key, False)
    results.append((f"{name}으로 비행", *snap(f"{name}으로 비행")))

# 대각선으로 화면 밖까지
press(Qt.Key.Key_Up, True)
press(Qt.Key.Key_Right, True)
for _ in range(120):
    bc._tick()
    app.processEvents()
press(Qt.Key.Key_Up, False)
press(Qt.Key.Key_Right, False)
results.append(("대각선 화면 밖", *snap("대각선 화면 밖")))

# 날아다니는 중에 창 크기 변경
page.resize(700, 620)
results.append(("비행 중 창 축소", *snap("비행 중 창 축소")))
page.resize(880, 700)
results.append(("비행 중 창 복원", *snap("비행 중 창 복원")))

page.dismiss_battlecruiser()
for _ in range(60):
    bc._tick()
    app.processEvents()
results.append(("해제 후", *snap("해제 후")))

print("\n=== 결과 ===")
bad = [r for r in results if r[1] == 0 or r[2] == 0]
for name, seen, members in results:
    mark = "FAIL" if (seen == 0 or members == 0) else "OK"
    print(f"[{mark}] {name}: 메시지 {seen} / 참여자 {members}")
print("\n채팅이나 참여자가 빈 순간:", "없음" if not bad else [b[0] for b in bad])
sys.exit(1 if bad else 0)
