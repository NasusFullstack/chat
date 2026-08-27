"""입장/퇴장 안내에 시각이 같이 뜨는가.

요청(2026-08-27): "채팅방 입장 퇴장 시간도 표기해줘. 채팅이랑 똑같이는 말고
'입장했습니다' 하고 시간 표기 뜨게."

그래서 두 가지를 지킨다:
1. **사람이 오간 일에만** 시각이 붙는다 - 도움말 출력이나 "── 이전 대화 기록 ──"
   같은 안내에 시각이 붙으면 지저분하고 뜻도 없다. 무엇에 붙일지는 "무슨 일이
   일어났는가"를 아는 코어가 정한다(어댑터가 아무 안내에나 지금 시각을 찍으면 안 됨).
2. 대화와 **같은 모양은 아니다** - 말풍선/아이콘/시간 배지를 달지 않고, 안내 한 줄
   끝에 흐리게 붙인다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import re  # noqa: E402
import time  # noqa: E402

import irc_protocol  # noqa: E402
from chat_core import events as domain_events  # noqa: E402
from chat_core.session import build_session  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def new_session():
    sent, got = [], []
    session = build_session("irc", "h", 6667, transport=sent.append, on_event=got.append)
    session.login("Mong", "")
    session.handle_incoming(irc_protocol.parse_line(":h 001 Mong :Welcome"))
    session.handle_incoming(irc_protocol.parse_line(":Mong!u@h JOIN :#room"))
    got.clear()
    return session, got


def notices(events):
    return [e for e in events if isinstance(e, domain_events.SystemNotice)]


# ---------- 1) 코어가 '언제'를 같이 알려주는가 ----------
started = time.time()
session, got = new_session()
session.handle_incoming(irc_protocol.parse_line(":Ming!u@h JOIN :#room"))
session.handle_incoming(irc_protocol.parse_line(":Ming!u@h PART #room"))
session.handle_incoming(irc_protocol.parse_line(":Gil!u@h JOIN :#room"))
session.handle_incoming(irc_protocol.parse_line(":Gil!u@h QUIT :bye"))
session.handle_incoming(irc_protocol.parse_line(":Op!u@h JOIN :#room"))
session.handle_incoming(irc_protocol.parse_line(":Boss!u@h KICK #room Op :규칙 위반"))
ended = time.time()

wanted = ("입장했습니다", "나갔습니다", "접속을 종료했습니다", "내보내졌습니다")
for word in wanted:
    found = [e for e in notices(got) if word in e.text]
    check(f"'{word}' 안내가 있다", bool(found), [e.text for e in notices(got)])
    if found:
        stamps = [e.ts for e in found]
        check(f"'{word}'에 시각이 붙는다({stamps})", all(t > 0 for t in stamps), stamps)
        check(f"'{word}' 시각이 방금이다",
              all(started - 1 <= t <= ended + 1 for t in stamps), stamps)

# ---------- 2) 시각이 뜻 없는 안내에는 안 붙는가 ----------
session2, got2 = new_session()
session2.handle_incoming(irc_protocol.parse_line(":h 332 Mong #room :방 주제"))
session2.send_message("#room", "/help")
plain = [e for e in notices(got2) if e.ts == 0.0]
check(f"시각 없는 안내도 그대로 있다({len(plain)}건)", bool(plain),
      [(e.text[:20], e.ts) for e in notices(got2)])

# ---------- 3) 화면에 실제로 시각이 보이는가 ----------
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
import gui_client as g  # noqa: E402
from gui.components.message_item import _build_system_label  # noqa: E402
from gui.components.message_log import ChannelLogView  # noqa: E402

app.setStyleSheet(g.STYLE_SHEET)

when = time.mktime((2026, 8, 27, 14, 32, 0, 0, 0, -1))
label = _build_system_label("Ming님이 입장했습니다.", when)
shown = label.text()
check(f"안내 글자가 그대로 있다({label.text()[:40]})", "입장했습니다" in shown, shown)
check("시각이 같이 보인다(14:32)", "14:32" in shown, shown)

plain_label = _build_system_label("── 이전 대화 기록 ──")
check(f"시각이 없으면 아무 것도 안 붙는다({plain_label.text()[:40]})",
      not re.search(r"\d\d:\d\d", plain_label.text()), plain_label.text())

# ---------- 4) 대화와 같은 모양은 아니어야 한다 ----------
from gui.components.message_item import MessageWidget  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402

view = ChannelLogView("#room")
view.resize(700, 400)
view.show()
view.set_container_width(700)
view.append_system("Ming님이 입장했습니다.", when)
view.append_message("Ming", "안녕", False, when, QPixmap(28, 28))
for _ in range(6):
    app.processEvents()

items = [view._layout.itemAt(i).widget() for i in range(view._layout.count())]
items = [w for w in items if w is not None]
system_widget = items[0]
check(f"안내는 말풍선 위젯이 아니다({type(system_widget).__name__})",
      not isinstance(system_widget, MessageWidget), type(system_widget).__name__)
check("안내에는 시간 배지가 없다",
      not system_widget.findChildren(object.__class__)
      or not [c for c in system_widget.children()
              if getattr(c, "objectName", lambda: "")() == "timestampBadge"])
chat_widget = [w for w in items if isinstance(w, MessageWidget)]
check("대화 쪽에는 시간 배지가 그대로 있다",
      bool(chat_widget) and bool([c for c in chat_widget[0].findChildren(type(system_widget))
                                  if c.objectName() == "timestampBadge"]))
check(f"안내가 대화보다 낮다(안내 {system_widget.height()}px"
      f" / 대화 {chat_widget[0].height() if chat_widget else 0}px)",
      bool(chat_widget) and system_widget.height() < chat_widget[0].height(),
      (system_widget.height(), chat_widget[0].height() if chat_widget else 0))

print("=== 검증 결과 (입장/퇴장 시각 표기) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
