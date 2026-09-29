"""대기방 창 - 방 연 사람과 들어온 사람이 실제로 다르게 보이는가.

사람이 실제로 누르는 경로로 확인한다(핸들러 직접 호출은 CLAUDE.md 6번 위반 -
그렇게 하면 '눌러도 아무 반응 없는' 버그를 못 잡는다).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import battle_protocol as bp  # noqa: E402
import gui_client as g  # noqa: E402
from gui.battle.lobby import (SHIP_COLORS, TITLE_MAX_WIDTH, BattleLobby,  # noqa: E402
                              color_name)

app.setStyleSheet(g.STYLE_SHEET)

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def pump(times=6):
    for _ in range(times):
        app.processEvents()


# ---------- 1) 색 표가 규약과 맞는가 ----------
check(f"색 개수가 규약과 같다({len(SHIP_COLORS)} == {bp.COLOR_COUNT})",
      len(SHIP_COLORS) == bp.COLOR_COUNT)
check("색 이름이 전부 다르다", len({n for n, _h in SHIP_COLORS}) == len(SHIP_COLORS))
check("색 값도 전부 다르다", len({h for _n, h in SHIP_COLORS}) == len(SHIP_COLORS))

# ---------- 2) 방 연 사람 ----------
host = BattleLobby(is_host=True, my_nick="Mong")
host.show()
pump()
host.set_me(0, color=3, capacity=4)
pump()

check("방 연 사람은 정원을 바꿀 수 있다", host.capacity.isEnabled() is True)
check("방 연 사람에게는 시작 버튼이 보인다", host.start_button.isVisible() is True)
check(f"혼자일 때는 시작이 안 눌린다({host.player_count()}명)",
      host.start_button.isEnabled() is False, host.player_count())
check(f"내 색이 반영된다({host.color.currentData()})", host.color.currentData() == 3)

pressed = []
host.start_pressed.connect(lambda: pressed.append(True))
QTest.mouseClick(host.start_button, Qt.MouseButton.LeftButton)
pump()
check("안 눌리는 상태에서는 눌러도 아무 일 없다", not pressed, pressed)

host.add_player(1, "Gil", 5)
pump()
check(f"둘이 되면 시작이 눌린다({host.player_count()}명)",
      host.start_button.isEnabled() is True, host.player_count())
QTest.mouseClick(host.start_button, Qt.MouseButton.LeftButton)
pump()
check("진짜 클릭으로 시작 신호가 나간다", pressed == [True], pressed)

# 남이 쓰는 색은 못 고른다
check(f"남이 쓰는 색이 잠긴다(잠긴 색 {host.taken_colors()})",
      host.taken_colors() == {5}, host.taken_colors())
model = host.color.model()
locked = [host.color.itemData(i) for i in range(host.color.count())
          if not model.item(i).isEnabled()]
check(f"목록에서도 실제로 잠겼다({[color_name(c) for c in locked]})", locked == [5], locked)

# 정원을 바꾸면 신호가 나간다
caps = []
host.capacity_chosen.connect(caps.append)
host.capacity.setCurrentIndex(0)      # 2명
pump()
check(f"정원을 바꾸면 신호가 나간다({caps})", caps == [bp.MIN_PLAYERS], caps)

# 색을 바꾸면 신호가 나간다
colors = []
host.color_chosen.connect(colors.append)
host.color.setCurrentIndex(1)
pump()
check(f"색을 바꾸면 신호가 나간다({colors})", colors == [1], colors)

# 사람이 나가면 목록에서 빠지고 시작도 다시 잠긴다
host.remove_player(1)
pump()
check(f"나가면 목록에서 빠진다({host.player_count()}명)", host.player_count() == 1)
check("혼자가 되면 시작이 다시 잠긴다", host.start_button.isEnabled() is False)
check("잠겼던 색이 다시 열린다", host.taken_colors() == set(), host.taken_colors())

# ---------- 3) 들어온 사람 ----------
guest = BattleLobby(is_host=False, my_nick="Gil")
guest.show()
pump()
guest.set_me(1, color=2, capacity=2)
guest.set_players([{"slot": 0, "nick": "Mong", "color": 3}])
pump()

check("들어온 사람은 정원을 못 바꾼다", guest.capacity.isEnabled() is False)
check("들어온 사람에게도 정원이 보인다(몇 명짜리 방인지 알아야 함)",
      guest.capacity.isVisible() is True)
check(f"정원이 방장이 정한 값으로 보인다({guest.capacity.currentData()}명)",
      guest.capacity.currentData() == 2, guest.capacity.currentData())
check("들어온 사람에게는 시작 버튼이 없다", guest.start_button.isVisible() is False)
check(f"들어온 사람도 색은 고를 수 있다", guest.color.isEnabled() is True)
check(f"방장이 쓰는 색은 잠긴다({guest.taken_colors()})", guest.taken_colors() == {3})
check(f"목록에 둘 다 보인다({guest.player_count()}명)", guest.player_count() == 2)

labels = [guest.players.item(i).text() for i in range(guest.players.count())]
check(f"내가 누군지 보인다({labels})", any("← 나" in text for text in labels), labels)
check(f"방장이 누군지 보인다({labels})", any("[방장]" in text for text in labels), labels)

# ---------- 4) 그만두면 알린다 ----------
closed = []
guest.closed.connect(lambda: closed.append(True))
QTest.mouseClick(guest.leave_button, Qt.MouseButton.LeftButton)
pump()
check("그만두기를 누르면 알린다", closed == [True], closed)

# ---------- 5) 글자가 잘리지 않는가 ----------
fresh = BattleLobby(is_host=True, my_nick="Mong")
fresh.show()
pump()
needed = fresh.notice.heightForWidth(max(1, fresh.notice.width()))
check(f"안내 문구가 안 잘린다(필요 {needed}px / 칸 {fresh.notice.height()}px)",
      fresh.notice.height() >= needed, (needed, fresh.notice.height()))

# ---------- 6) 시작 그림 ----------
titled = BattleLobby(is_host=True, my_nick="Mong")
titled.show()
pump()
if titled.title_image is not None:
    shown = titled.title_image.pixmap()
    check(f"시작 그림이 걸린다({shown.width()}x{shown.height()})",
          not shown.isNull() and shown.width() > 0, shown.size())
    check(f"창을 넘지 않게 줄여서 건다({shown.width()} <= {TITLE_MAX_WIDTH})",
          shown.width() <= TITLE_MAX_WIDTH, shown.width())
    check(f"비율이 안 찌그러졌다({shown.width() / max(1, shown.height()):.2f})",
          abs(shown.width() / max(1, shown.height()) - 1.5) < 0.1,
          (shown.width(), shown.height()))
else:
    check("그림 파일이 없어도 창은 떴다(그림 하나로 전투를 막으면 안 됨)", True)

# 파일이 없는 상황에서도 안 터지는지 - 찾는 함수를 잠깐 바꿔 확인한다
import gui.battle.lobby as lobby_module  # noqa: E402

real_finder = lobby_module._find_image_in_app_dirs
lobby_module._find_image_in_app_dirs = lambda names: ""
try:
    bare = BattleLobby(is_host=False, my_nick="Gil")
    bare.show()
    pump()
    check("그림이 없어도 창이 뜬다", bare.title_image is None and bare.isVisible())
finally:
    lobby_module._find_image_in_app_dirs = real_finder

# ---------- 7) 순환참조 규칙(CLAUDE.md 1번) ----------
import io  # noqa: E402

source = io.open(_os.path.join(_REPO, "gui/battle/lobby.py"), encoding="utf-8").read()
head = source.split("class ", 1)[0]
check("파일 맨 위에서 gui_client 를 import 하지 않는다(PyInstaller에서 죽는다)",
      "import gui_client" not in head, head[:0])
check("소켓을 모른다(대기방은 신호만 올린다)",
      "QWebSocket" not in source and "battle.net" not in source)

print("=== 검증 결과 (대기방) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
