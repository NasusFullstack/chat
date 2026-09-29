"""전투가 처음부터 끝까지 이어지는가 - 치트 입력 -> 방 알림 -> 대기방 -> 전투 -> 이탈.

부품 하나하나는 각자 검사가 있다. 여기서는 **이어져 있는지**를 본다. 부품이 다 멀쩡해도
중간에 한 줄이 안 이어져 있으면 아무 일도 안 일어난다(CLAUDE.md 6번과 같은 이유로,
핸들러를 직접 부르지 않고 실제 경로로 확인한다).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import time  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import battle_protocol as bp  # noqa: E402
import irc_protocol  # noqa: E402
from chat_core import constants  # noqa: E402
from chat_core import events as domain_events  # noqa: E402
from chat_core.session import build_session  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def line(raw):
    return irc_protocol.parse_line(raw)


def new_session():
    sent, got = [], []
    session = build_session("irc", "h", 6667, transport=sent.append, on_event=got.append)
    session.login("Mong", "")
    session.handle_incoming(line(":h 001 Mong :Welcome"))
    session.handle_incoming(line(":Mong!u@h JOIN :#room"))
    sent.clear()
    got.clear()
    return session, sent, got


# ---------- 1) 방을 열면 채널에 방 번호가 나간다 ----------
session, sent, got = new_session()
room = bp.new_room()
session.announce_battle_room("#room", room)
check(f"채널로 한 줄이 나간다({sent})", len(sent) == 1, sent)
outgoing = sent[0]
check("PRIVMSG 로 나간다", outgoing.startswith("PRIVMSG #room :"), outgoing)
check("우리끼리만 보이는 숨김 프레임이다(다른 클라이언트엔 안 뜬다)",
      irc_protocol.is_ctcp_frame(outgoing.split(":", 1)[1]), outgoing)
check(f"방 번호가 그대로 실린다",
      bp.parse_room_notice(outgoing.split(":", 1)[1]) == room, outgoing)

# **주소가 어디에도 없어야 한다** - 중계로 바꾼 이유가 이것이다
for leak in (".", "127", "192.168", "@"):
    body = outgoing.split(":", 1)[1].strip("\x01")
    check(f"주소 같은 게 안 실린다({leak!r})", leak not in body.replace("CHUPBATTLE ROOM ", ""),
          body)

# ---------- 2) 남이 연 방 알림을 받으면 이벤트가 난다 ----------
session2, sent2, got2 = new_session()
session2.handle_incoming(line(
    f":Gil!u@h PRIVMSG #room :{bp.format_room_notice(room)}"))
opened = [e for e in got2 if isinstance(e, domain_events.BattleRoomOpened)]
check(f"방이 열렸다는 이벤트가 난다({opened})", len(opened) == 1, got2)
if opened:
    check(f"누가 열었는지 안다({opened[0].host})", opened[0].host == "Gil")
    check(f"방 번호가 온다", opened[0].room == room, opened[0].room)
    check(f"어느 채널인지 안다({opened[0].channel})", opened[0].channel == "#room")

# 채팅으로는 절대 새면 안 된다(예전에 잘린 CTCP가 채널에 쓰레기로 뜬 적이 있다)
leaked = [e for e in got2 if isinstance(e, domain_events.MessageReceived)]
check(f"채팅으로는 안 샌다({[e.text[:20] for e in leaked]})", not leaked, leaked)

# 내가 연 방 알림이 돌아와도 나에게는 안 뜬다
session3, _s3, got3 = new_session()
session3.handle_incoming(line(
    f":Mong!u@h PRIVMSG #room :{bp.format_room_notice(room)}"))
check("내가 연 방은 나에게 다시 안 알린다",
      not [e for e in got3 if isinstance(e, domain_events.BattleRoomOpened)], got3)

# 이상한 방 번호는 무시
session4, _s4, got4 = new_session()
session4.handle_incoming(line(":Gil!u@h PRIVMSG #room :\x01CHUPBATTLE ROOM ../etc\x01"))
check("이상한 방 번호는 무시한다",
      not [e for e in got4 if isinstance(e, domain_events.BattleRoomOpened)], got4)

# ---------- 3) 치트가 표에 이어져 있는가 ----------
import gui_client as g  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402

for phrase, cheat_id in (("배틀크루저 전투", constants.CHEAT_BATTLE_OPEN),
                         ("배틀크루저 전투 참가", constants.CHEAT_BATTLE_JOIN)):
    spec = constants.find_cheat(phrase)
    check(f"'{phrase}' 가 치트로 잡힌다", spec is not None and spec.id == cheat_id, spec)
    check(f"'{phrase}' 가 창의 전투 표에 이어져 있다", cheat_id in MainWindow._BATTLE_CHEATS,
          list(MainWindow._BATTLE_CHEATS))

# 라우터가 방 알림 이벤트를 창으로 넘기는가
from gui import event_router  # noqa: E402

check("라우터 표에 방 알림이 있다",
      domain_events.BattleRoomOpened in event_router.EVENT_HANDLERS,
      list(event_router.EVENT_HANDLERS)[:3])
check("창에 받을 곳이 있다", hasattr(MainWindow, "on_battle_room"))

# ---------- 4) 실제 창에서 한 판을 끌고 가는가 ----------
app.setStyleSheet(g.STYLE_SHEET)
window = g.MainWindow()
window.resize(1000, 700)
window.show()
chat = window.chat_page
chat.add_channel("#room")
window.show_page(chat)
for _ in range(8):
    app.processEvents()

notices = []
controller = window.battle
controller.system_notice.connect(lambda ch, text: notices.append((ch, text)))
announced = []
controller.announce_room.connect(lambda ch, r: announced.append((ch, r)))

# 열린 방이 없는데 참가하면 안내가 나와야 한다(조용히 아무 일도 안 일어나면 안 됨)
controller.join_room("#room", "Mong", time.time())
check(f"열린 방이 없으면 알려준다({notices})",
      notices and "열린 전투가 없습니다" in notices[-1][1], notices)
check("헛되이 연결하지 않는다", controller.is_running is False)

# 남이 방을 열었다는 알림 -> 안내가 뜨고 참가할 수 있게 된다
notices.clear()
controller.remember_room("#room", "Gil", room, time.time())
check(f"방이 열리면 안내가 뜬다({notices})",
      notices and "Gil" in notices[-1][1] and "참가" in notices[-1][1], notices)

# 오래된 방은 잊는다
controller.remember_room("#old", "Gil", room, time.time() - 10 * 60 * 60)
notices.clear()
controller.join_room("#old", "Mong", time.time())
check(f"오래된 방은 잊는다({notices})",
      notices and "열린 전투가 없습니다" in notices[-1][1], notices)

# 방 열기 - 대기방이 뜨고 채널에 알림이 나간다
notices.clear()
controller.open_room("#room", "Mong", time.time())
for _ in range(6):
    app.processEvents()
check(f"방을 열면 채널에 알린다({announced})",
      announced and announced[0][0] == "#room" and len(announced[0][1]) >= 16, announced)
check("대기방이 뜬다", controller._lobby is not None and controller._lobby.isVisible())
check("연결을 시작한다", controller.is_running is True)

# 이미 하고 있으면 또 안 연다
notices.clear()
controller.open_room("#room", "Mong", time.time())
check(f"이미 참여 중이면 알려준다({notices})",
      notices and "이미 전투" in notices[-1][1], notices)

# ---------- 5) 전투로 넘어가고 이탈까지 ----------
# 서버 없이도 흐름을 볼 수 있게, 중계에서 오는 신호를 직접 흘려 넣는다
lobby = controller._lobby
lobby.set_me(0, color=0, capacity=2)
lobby.practice.setChecked(True)          # 혼자서도 시작할 수 있게(연습 상대)
for _ in range(4):
    app.processEvents()
check("연습 상대를 켜면 혼자서도 시작할 수 있다", lobby.start_button.isEnabled() is True)

controller._on_started()
for _ in range(6):
    app.processEvents()
check("전투 화면이 뜬다", controller._arena is not None and controller._arena.is_active)
check("대기방은 닫힌다", controller._lobby is None)
check(f"시작 안내가 뜬다({notices[-1][1][:24] if notices else ''})",
      notices and "전투 시작" in notices[-1][1], notices)
check(f"연습 상대가 들어갔다({len(controller._arena._ai_slots)}명)",
      len(controller._arena._ai_slots) >= 1, controller._arena._ai_slots)

# 몇 틱 돌려본다 - 실제로 조작이 나가고 그림이 그려져야 한다
outgoing_inputs = []
controller._arena.input_ready.connect(lambda t, k: outgoing_inputs.append((t, k)))
for _ in range(30):
    controller._arena._advance()
app.processEvents()
# 화면이 스스로 60fps로 돌고 있으므로 내가 돌린 것보다 많을 수 있다(적으면 안 이어진 것)
check(f"조작이 중계로 나간다({len(outgoing_inputs)}번)", len(outgoing_inputs) >= 30,
      len(outgoing_inputs))

# 격추되면 채팅에 한 줄
notices.clear()
controller._arena.killed.emit(1, 0)
check(f"격추되면 채팅에 남는다({notices})",
      notices and "격추" in notices[-1][1], notices)

# ESC -> 물어보고 이탈
import gui_client  # noqa: E402

asked = {}
real_question = gui_client.themed_question
gui_client.themed_question = lambda parent, title, text: (
    asked.update(title=title, text=text), True)[1]
notices.clear()
controller._arena.escape_pressed.emit()
for _ in range(4):
    app.processEvents()
gui_client.themed_question = real_question
check(f"ESC를 누르면 물어본다({asked.get('text')})",
      "이탈" in asked.get("text", ""), asked)
check(f"이탈하면 알린다({notices})", notices and "이탈" in notices[-1][1], notices)
check("전투가 정리된다", controller.is_running is False and controller._arena is None)

print("=== 검증 결과 (전투 흐름) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
